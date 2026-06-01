"""
턴 기반 음성 파이프라인.
STT → LLM → TTS 직렬 실행. 한 턴이 끝나야 다음 턴 시작.
대시보드와 독립적으로 동작 — broadcast는 일방적 통지.
"""
import asyncio
import time
from ai_core.audio_manager import PRIORITY_CONVERSATION, PRIORITY_FALLBACK
from server.mic import MicCapture
from server.stt import STTClient
from server.websocket_handler import broadcast


class VoicePipeline:
    """턴 기반 음성 파이프라인. STT→LLM→TTS 직렬 실행.

    한 턴: listen → transcribe → think → speak → (다시 listen)
    어느 시점이든 STT/LLM/TTS 중 하나만 활성.
    """

    def __init__(
        self,
        mic: MicCapture,
        stt: STTClient,
        tts_lock: asyncio.Lock,
        cancel_narration=None,
        audio_manager=None,
    ):
        """
        Args:
            mic: MicCapture 인스턴스
            stt: STTClient 인스턴스
            tts_lock: TTS 재생 전역 Lock (narration/danger TTS와 경합 방지)
        """
        self._mic = mic
        self._stt = stt
        self._tts_lock = tts_lock
        self._cancel_narration = cancel_narration or (lambda: None)
        self._audio_manager = audio_manager
        self._running = False
        self._chat_history: list[dict] = []  # {"role": "user"|"assistant", "content": str}
        self._max_history = 8  # 최근 4턴만 유지해 LLM 응답 지연 최소화
        self._consecutive_fails = 0
        self._cooldown_steps = [2, 5, 10, 30]  # 초 단위 쿨다운 단계

    async def run(self):
        """메인 턴 루프. 한 번에 한 턴만 실행."""
        self._running = True
        print("[VoicePipeline] 파이프라인 시작")

        while self._running:
            try:
                await self._run_one_turn()
                # 빈 턴(발화 없음/인식 불가 등)이 I/O 대기 없이 즉시 끝나도
                # 이벤트 루프에 제어를 양보 — CPU 스핀 및 다른 태스크 굶김 방지.
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VoicePipeline] 턴 오류: {e}")
                await asyncio.sleep(1)  # 에러 시 잠시 대기 후 재시도

        print("[VoicePipeline] 파이프라인 종료")

    async def _run_one_turn(self):
        """한 턴 실행: listen → transcribe → think → speak"""

        if self._audio_manager:
            await self._audio_manager.wait_until_idle()

        # 1. 듣기 — broadcast "voice_listening"
        await broadcast({"type": "voice_listening", "timestamp": int(time.time() * 1000)})
        audio_data = await self._mic.listen()
        if audio_data is None:
            return  # 발화 없음 → 다시 듣기
        self._cancel_narration()

        # 2. STT — broadcast "voice_processing"
        await broadcast({"type": "voice_processing", "timestamp": int(time.time() * 1000)})
        stt_started = time.perf_counter()
        text = await self._stt.transcribe(audio_data)
        print(f"[VoicePipeline] STT 완료: {time.perf_counter() - stt_started:.2f}초")
        if not text or not text.strip():
            return  # 인식 불가 → 다시 듣기

        text = text.strip()
        print(f"[VoicePipeline] STT 결과: {text}")

        # 2-1. 호출어 게이팅 (결정 A2/A3)
        #  - 호출어 "시아야" 없음 → 무시 (대시보드 broadcast도 안 함 = 잡음/에코 차단)
        #  - 있음 → 호출어 뒤 질문만 추출. 질문이 비면("시아야"만) 무시.
        from server.wake_word import parse_wake_word
        query = parse_wake_word(text)
        if not query:  # None(비호출) 또는 ""(호출만, 질문 없음)
            print(f"[VoicePipeline] 호출어 없음 → 무시: {text!r}")
            return
        text = query

        # 2-2. 즉시 "잠깐만" 필러 — LLM 대기 동안 무응답 침묵 방지 (비대기)
        if self._audio_manager:
            self._audio_manager.play("buffer_01.wav", priority=PRIORITY_FALLBACK)

        # 사용자 질문을 대시보드에 표시 (호출어 제거된 질문)
        await broadcast({
            "type": "user_stt",
            "message": text,
            "timestamp": int(time.time() * 1000),
        })

        # 3. LLM 호출
        from ai_core.llm_client import call_async, SYSTEM_PROMPT

        # 히스토리를 system prompt에 포함
        context = self._build_context(SYSTEM_PROMPT)
        try:
            llm_started = time.perf_counter()
            response = await call_async(context, text)
            print(f"[VoicePipeline] LLM 완료: {time.perf_counter() - llm_started:.2f}초")
        except Exception as e:
            print(f"[VoicePipeline] LLM 에러: {e}")
            await self._play_fallback(f"LLM 에러: {type(e).__name__}")
            await self._cooldown_on_fail()
            return

        if not response:
            print("[VoicePipeline] LLM 응답 없음")
            await self._play_fallback("LLM 응답 없음")
            await self._cooldown_on_fail()
            return

        # LLM 성공 — 연속 실패 카운터 리셋
        self._consecutive_fails = 0

        # 히스토리 저장
        self._chat_history.append({"role": "user", "content": text})
        self._chat_history.append({"role": "assistant", "content": response})
        # 최대 길이 초과 시 오래된 것부터 제거
        if len(self._chat_history) > self._max_history:
            self._chat_history = self._chat_history[-self._max_history:]

        # 응답을 대시보드에 표시
        await broadcast({
            "type": "stt_response",
            "message": response,
            "timestamp": int(time.time() * 1000),
        })

        # 4. TTS 재생 (Lock으로 narration/danger와 경합 방지)
        async with self._tts_lock:
            await self._speak(response)

    async def _speak(self, text: str):
        """TTS 생성 + 오디오 재생. tts_start/tts_done broadcast."""
        try:
            from ai_core.tts import get_tts_cache
            from ai_core.audio_manager import get_audio_manager

            tts = get_tts_cache()
            tts_started = time.perf_counter()
            filepath = await tts.get_or_create(text)
            print(f"[VoicePipeline] TTS 준비 완료: {time.perf_counter() - tts_started:.2f}초")

            await broadcast({"type": "tts_start", "timestamp": int(time.time() * 1000)})

            if filepath:
                am = self._audio_manager or get_audio_manager()
                request = am.play_path(
                    str(filepath),
                    priority=PRIORITY_CONVERSATION,
                )
                await am.wait(request)

            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] TTS 오류: {e}")
            await broadcast({"type": "error", "message": f"TTS 오류: {type(e).__name__}", "timestamp": int(time.time() * 1000)})
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    async def _cooldown_on_fail(self):
        """연속 LLM 실패 시 점진적 쿨다운 대기."""
        self._consecutive_fails += 1
        idx = min(self._consecutive_fails - 1, len(self._cooldown_steps) - 1)
        delay = self._cooldown_steps[idx]
        print(f"[VoicePipeline] 연속 실패 {self._consecutive_fails}회 → {delay}초 쿨다운")
        await asyncio.sleep(delay)

    async def _play_fallback(self, error_msg: str):
        """에러 발생 시 fallback 오디오 재생."""
        try:
            from ai_core.audio_manager import get_audio_manager

            # 에러 메시지 broadcast
            await broadcast({
                "type": "error",
                "message": error_msg,
                "timestamp": int(time.time() * 1000),
            })

            # Fallback 오디오 재생
            async with self._tts_lock:
                await broadcast({"type": "tts_start", "timestamp": int(time.time() * 1000)})
                am = self._audio_manager or get_audio_manager()
                request = am.play("buffer_01.wav", priority=PRIORITY_FALLBACK)
                await am.wait(request)
                await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] Fallback 재생 오류: {e}")
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    def _build_context(self, base_prompt: str) -> str:
        """system prompt + 대화 히스토리 결합."""
        if not self._chat_history:
            return base_prompt

        history_lines = []
        for msg in self._chat_history:
            role = "아이" if msg["role"] == "user" else "시아"
            history_lines.append(f"{role}: {msg['content']}")

        history_text = "\n".join(history_lines)
        return f"{base_prompt}\n\n[이전 대화]\n{history_text}"

    def stop(self):
        """파이프라인 중지."""
        self._running = False

    def reset(self):
        """세션 리셋 — 히스토리 초기화 + 파이프라인 중지."""
        self._chat_history.clear()
        self._consecutive_fails = 0
        # Note: _running은 stop()으로 별도 제어

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def chat_history(self) -> list[dict]:
        """현재 대화 히스토리 (읽기용)."""
        return list(self._chat_history)
