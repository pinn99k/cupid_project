"""
턴 기반 음성 파이프라인.
STT → LLM → TTS 직렬 실행. 한 턴이 끝나야 다음 턴 시작.
대시보드와 독립적으로 동작 — broadcast는 일방적 통지.
"""
import asyncio
import time
from server.mic import MicCapture
from server.stt import STTClient
from server.websocket_handler import broadcast


class VoicePipeline:
    """턴 기반 음성 파이프라인. STT→LLM→TTS 직렬 실행.

    한 턴: listen → transcribe → think → speak → (다시 listen)
    어느 시점이든 STT/LLM/TTS 중 하나만 활성.
    """

    def __init__(self, mic: MicCapture, stt: STTClient, tts_lock: asyncio.Lock):
        """
        Args:
            mic: MicCapture 인스턴스
            stt: STTClient 인스턴스
            tts_lock: TTS 재생 전역 Lock (narration/danger TTS와 경합 방지)
        """
        self._mic = mic
        self._stt = stt
        self._tts_lock = tts_lock
        self._running = False
        self._chat_history: list[dict] = []  # {"role": "user"|"assistant", "content": str}
        self._max_history = 20  # 10턴 = 20 메시지

    async def run(self):
        """메인 턴 루프. 한 번에 한 턴만 실행."""
        self._running = True
        print("[VoicePipeline] 파이프라인 시작")

        while self._running:
            try:
                await self._run_one_turn()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VoicePipeline] 턴 오류: {e}")
                await asyncio.sleep(1)  # 에러 시 잠시 대기 후 재시도

        print("[VoicePipeline] 파이프라인 종료")

    async def _run_one_turn(self):
        """한 턴 실행: listen → transcribe → think → speak"""

        # 1. 듣기 — broadcast "voice_listening"
        await broadcast({"type": "voice_listening", "timestamp": int(time.time() * 1000)})
        audio_data = await self._mic.listen()
        if audio_data is None:
            return  # 발화 없음 → 다시 듣기

        # 2. STT — broadcast "voice_processing"
        await broadcast({"type": "voice_processing", "timestamp": int(time.time() * 1000)})
        text = await self._stt.transcribe(audio_data)
        if not text or not text.strip():
            return  # 인식 불가 → 다시 듣기

        text = text.strip()
        print(f"[VoicePipeline] STT 결과: {text}")

        # 사용자 발화를 대시보드에 표시
        await broadcast({
            "type": "user_stt",
            "message": text,
            "timestamp": int(time.time() * 1000),
        })

        # 3. LLM 호출
        from ai_core.llm_client import call_async, SYSTEM_PROMPT

        # 히스토리를 system prompt에 포함
        context = self._build_context(SYSTEM_PROMPT)
        response = await call_async(context, text)

        if not response:
            print("[VoicePipeline] LLM 응답 없음")
            return

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
            filepath = await tts.get_or_create(text)

            await broadcast({"type": "tts_start", "timestamp": int(time.time() * 1000)})

            if filepath:
                am = get_audio_manager()
                am.play_path(str(filepath))
                while await asyncio.to_thread(am.is_playing):
                    if not self._running:
                        am.stop()
                        break
                    await asyncio.sleep(0.2)

            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] TTS 오류: {e}")
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
        # Note: _running은 stop()으로 별도 제어

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def chat_history(self) -> list[dict]:
        """현재 대화 히스토리 (읽기용)."""
        return list(self._chat_history)
