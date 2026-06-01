"""
턴 기반 음성 파이프라인.
STT → LLM → TTS 직렬 실행. 한 턴이 끝나야 다음 턴 시작.
대시보드와 독립적으로 동작 — broadcast는 일방적 통지.
"""
import asyncio
import re
import time
from ai_core.audio_manager import PRIORITY_CONVERSATION, PRIORITY_FALLBACK
from server.mic import MicCapture
from server.stt import STTClient
from server.websocket_handler import broadcast

# Vision 질문 분류기: 객체 인식 결과가 필요한 질문 패턴
# 이 패턴에 해당하면 → LLM 캐시 제외 + 무조건 VQA(YOLO 장면) 모드로 처리
# "앞에 뭐 있어", "사람 있어", "의자 있어?" 등 카메라 확인이 필요한 모든 질문
_VISION_RE = re.compile(
    r"뭐.*있|있냐|있어|보여|보이|위험|사람|계단|앞|왼|오른|장애물|찾|감지|물체|뭐가|주변|근처"
)

# 되묻기 오디오 → 대화창 표시 텍스트 매핑
_REPROMPT_TEXTS: dict[str, str] = {
    "retry_what.wav":    "응, 불렀어?",
    "retry_louder.wav":  "조금만 더 크게 말해줄래?",
    "retry_unclear.wav": "미안해, 한 번만 더 말해줄래?",
}


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
        scene_provider=None,
        count_question=None,
        scene_fresh_sec: float = 2.0,
        low_volume_rms: float = 0.0,
        output_settle_sec: float = 0.0,
        reprompt_cooldown_sec: float = 2.0,
    ):
        """
        Args:
            mic: MicCapture 인스턴스
            stt: STTClient 인스턴스
            tts_lock: TTS 재생 전역 Lock (narration/danger TTS와 경합 방지)
            scene_provider: () -> (enriched|None, ts_ms). _ai_loop이 채운 최신 장면을
                읽어 VQA 근거로 사용 (YOLO 재실행 금지, shared_resources.md §6).
            count_question: 답변 성공 시 호출할 콜백 (question_count 증가).
            scene_fresh_sec: 장면이 이 시간 이내면 "신선"으로 보고 VQA, 아니면 일반 대화.
        """
        self._mic = mic
        self._stt = stt
        self._tts_lock = tts_lock
        self._cancel_narration = cancel_narration or (lambda: None)
        self._audio_manager = audio_manager
        self._scene_provider = scene_provider
        self._count_question = count_question
        self._scene_fresh_ms = scene_fresh_sec * 1000
        self._low_volume_rms = low_volume_rms
        self._output_settle_sec = output_settle_sec
        self._reprompt_cooldown_sec = reprompt_cooldown_sec
        self._running = False
        self._chat_history: list[dict] = []  # {"role": "user"|"assistant", "content": str}
        self._max_history = 4  # 최근 2턴만 유지해 LLM 응답 지연 최소화
        self._consecutive_fails = 0
        self._cooldown_steps = [2, 5, 10, 30]  # 초 단위 쿨다운 단계
        self._last_mic_error = None
        self._last_reprompt_at = 0.0
        # LLM 응답 캐시 (장면 비의존 질문만) — 같은 질문 반복 시 LLM 생략
        self._response_cache: dict[str, str] = {}
        self._response_cache_max = 10
        # 청취 활성화 플래그 — 서버 시작 시 OFF, 대시보드 시작 버튼으로 ON
        self._active = False

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

        # 대시보드 시작 버튼을 누르기 전까지는 마이크 대기 상태 유지
        if not self._active:
            await asyncio.sleep(0.3)
            return

        if self._audio_manager:
            await self._audio_manager.wait_until_idle()

        # 1. 듣기
        await broadcast({"type": "voice_listening", "timestamp": int(time.time() * 1000)})
        audio_data = await self._mic.listen()

        if audio_data is None:
            mic_error = getattr(self._mic, "last_error", None)
            if mic_error:
                if mic_error != self._last_mic_error:
                    self._last_mic_error = mic_error
                    await broadcast({
                        "type": "error",
                        "message": f"마이크 입력 오류: {mic_error}",
                        "timestamp": int(time.time() * 1000),
                    })
                await asyncio.sleep(1)
            return
        self._last_mic_error = None

        self._cancel_narration()

        # 1-1. 저음량 되묻기 (Unit 4) — 들리긴 했으나 STT엔 너무 작은 경우.
        # STT를 건너뛰고 즉답으로 "더 크게" 요청 (LLM 미사용 → 빠르고 안전).
        rms = getattr(self._mic, "last_rms", None)
        if self._low_volume_rms > 0 and isinstance(rms, (int, float)) and 0 < rms < self._low_volume_rms:
            print(f"[VoicePipeline] 저음량(RMS={rms:.0f}) → 되묻기")
            await self._play_reprompt("retry_louder.wav", "저음량")
            return

        # 2. STT — broadcast "voice_processing"
        await broadcast({"type": "voice_processing", "timestamp": int(time.time() * 1000)})
        stt_started = time.perf_counter()
        text = await self._stt.transcribe(audio_data)
        print(f"[VoicePipeline] STT 완료: {time.perf_counter() - stt_started:.2f}초")
        if not text or not text.strip():
            # STT None: 진짜 못알아들음 vs 시스템 오류 구분
            status = getattr(self._stt, "last_status", "unrecognized")
            if status == "error":
                print("[VoicePipeline] STT 시스템 오류 → 재청취")
                await broadcast({
                    "type": "error",
                    "message": "STT 시스템 오류(네트워크/엔진)",
                    "timestamp": int(time.time() * 1000),
                })
                return
            # UnknownValueError(인식 불가): VAD 노이즈 오인 가능성이 높음.
            # "미안해, 한 번만 더" 반복은 혼잣말처럼 들리므로 조용히 재청취.
            # 호출어까지 STT로 확인된 경우에만 되묻기 수행(아래 wake_word 게이팅 참조).
            print("[VoicePipeline] 인식 불가(잡음 추정) → 조용히 재청취")
            return

        text = text.strip()

        # 2-1. 호출어 게이팅 (결정 A2/A3)
        #  - 호출어 "시아야" 없음(None) → 무시 (대시보드 broadcast도 안 함 = 잡음/에코 차단)
        #  - 호출어만 있고 질문 없음("") → 되묻기 "응? 불렀어?" (Unit 4)
        #  - 질문 있음 → 그 질문으로 진행
        from server.wake_word import parse_wake_word, WAKE_TOKENS
        query = parse_wake_word(text)

        # 호출어 파싱 상세 로그 (#4 진단)
        _compact = "".join(text.split())
        _matched = next((t for t in WAKE_TOKENS if t in _compact), None)
        print(
            f"[VoicePipeline] STT 원문={text!r}"
            f"  매칭토큰={_matched!r}"
            f"  파싱질문={query!r}"
        )

        if query is None:  # 비호출 → 잡음으로 보고 조용히 무시
            return
        if query == "":  # "시아야"만 부르고 질문 없음 → 되묻기
            await self._play_reprompt("retry_what.wav", "호출만")
            return
        text = query

        # 사용자 질문을 대시보드에 표시 (호출어 제거된 질문)
        await broadcast({
            "type": "user_stt",
            "message": text,
            "timestamp": int(time.time() * 1000),
        })

        # 3. LLM 호출
        # ─ Vision 질문("앞에 뭐 있어" 등) → 무조건 VQA(YOLO 장면 근거)
        # ─ 신선한 장면(2초 이내) + 일반 질문 → VQA
        # ─ 그 외 일반 질문 → 일반 대화 (SYSTEM_PROMPT)
        from ai_core.llm_client import call_async, SYSTEM_PROMPT, VQA_PROMPT

        # 3-0. Vision 질문 분류 + LLM 응답 캐시 (일반 질문만 캐시)
        is_vision_query = bool(_VISION_RE.search(text))
        cache_eligible = not is_vision_query

        response: str | None = None
        if cache_eligible:
            response = self._lookup_response_cache(text)
            if response:
                print(f"[VoicePipeline] CACHE HIT: {text!r} → {response!r}")

        if response is None:
            # 장면 데이터 조회 (VQA 여부 결정용)
            scene, scene_ts = (None, 0.0)
            if self._scene_provider:
                scene, scene_ts = self._scene_provider()
            scene_age_ms = time.time() * 1000 - scene_ts
            fresh = scene is not None and scene_age_ms <= self._scene_fresh_ms

            # VQA 모드 선택
            if is_vision_query:
                if scene is not None:
                    # 장면 있음 → 신선도 무관하게 VQA (가장 최근 인식 결과 사용)
                    from ai_core.scene_text import scene_to_korean
                    scene_text = scene_to_korean(scene)
                    base_prompt = f"{VQA_PROMPT}\n\n[현재 장면] {scene_text}"
                    print(
                        f"[VoicePipeline] VQA 모드(Vision 질문, 장면 경과={scene_age_ms:.0f}ms)"
                        f"  system={len(base_prompt)}자 user={len(text)}자 scene={len(scene_text)}자: {scene_text[:80]!r}"
                    )
                else:
                    # 장면 데이터 자체가 없음(카메라 미연결 등) → LLM 없이 직접 응답
                    response = "지금은 화면에서 잘 안 보여. 잠깐 기다려 볼까?"
                    print("[VoicePipeline] Vision 질문 + 장면 없음 → 직접 응답")
            elif fresh:
                from ai_core.scene_text import scene_to_korean
                scene_text = scene_to_korean(scene)
                base_prompt = f"{VQA_PROMPT}\n\n[현재 장면] {scene_text}"
                print(
                    f"[VoicePipeline] VQA 모드(신선한 장면, 경과={scene_age_ms:.0f}ms)"
                    f"  system={len(base_prompt)}자 user={len(text)}자 scene={len(scene_text)}자: {scene_text[:80]!r}"
                )
            else:
                base_prompt = SYSTEM_PROMPT
                print("[VoicePipeline] 일반 대화 모드")

            # LLM 호출 (직접 응답 경로는 이미 response가 설정됨)
            if response is None:
                context = self._build_context(base_prompt)
                try:
                    llm_started = time.perf_counter()
                    response = await call_async(context, text)
                    print(f"[VoicePipeline] LLM 완료: {time.perf_counter() - llm_started:.2f}초")
                    print(f"[VoicePipeline] LLM 응답: {response}")
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

        # LLM 성공 — 연속 실패 카운터 리셋 + 질문 카운트 증가(단일 writer)
        self._consecutive_fails = 0
        if self._count_question:
            self._count_question()

        # 응답 캐시 저장 (장면 비의존 질문만)
        if cache_eligible:
            self._store_response_cache(text, response)

        # 히스토리 저장
        self._chat_history.append({"role": "user", "content": text})
        self._chat_history.append({"role": "assistant", "content": response})
        # 최대 길이 초과 시 오래된 것부터 제거
        if len(self._chat_history) > self._max_history:
            self._chat_history = self._chat_history[-self._max_history:]

        # ── 응답 4단계 추적 (#5 잘림 진단) ─────────────────────────────
        # [LLM RAW]  : llm_client.py에서 출력 (API 원본)
        # [LLM FINAL]: llm_client.py에서 출력 (_strip_emoji 후)
        # [BROADCAST]: 아래 — WebSocket으로 전송되는 텍스트
        # [TTS INPUT]: _speak() 호출 직전 — TTS에 전달되는 텍스트
        print(f"[PIPELINE BROADCAST] {response!r}")
        await broadcast({
            "type": "stt_response",
            "message": response,
            "timestamp": int(time.time() * 1000),
        })

        # 4. TTS 재생 (Lock으로 narration/danger와 경합 방지)
        print(f"[PIPELINE TTS INPUT] {response!r}")
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
                await self._wait_for_output_settle()

            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] TTS 오류: {e}")
            await broadcast({"type": "error", "message": f"TTS 오류: {type(e).__name__}", "timestamp": int(time.time() * 1000)})
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    async def _play_reprompt(self, audio_file: str, reason: str):
        """되묻기 사전녹음 재생 (Unit 4) — LLM 미사용 즉답.
        무음/인식불가/저음량 등 '못 알아들음'에 대한 친절한 재요청.
        대화창에 실제 발화 텍스트를 표시해 음성과 동기화."""
        now = time.monotonic()
        if (now - self._last_reprompt_at) < self._reprompt_cooldown_sec:
            print(f"[VoicePipeline] 되묻기 쿨다운 중 → 생략: {reason}")
            return
        self._last_reprompt_at = now

        # 대화창 동기화: 재생되는 텍스트를 stt_response로 브로드캐스트
        spoken_text = _REPROMPT_TEXTS.get(audio_file, "")
        if spoken_text:
            await broadcast({
                "type": "stt_response",
                "message": spoken_text,
                "timestamp": int(time.time() * 1000),
            })

        await broadcast({
            "type": "voice_reprompt",
            "reason": reason,
            "spoken_text": spoken_text,
            "timestamp": int(time.time() * 1000),
        })
        if not self._audio_manager:
            return  # 오디오 매니저 없으면(테스트 등) 분기만 수행
        try:
            async with self._tts_lock:
                await broadcast({"type": "tts_start", "timestamp": int(time.time() * 1000)})
                request = self._audio_manager.play(audio_file, priority=PRIORITY_FALLBACK)
                await self._audio_manager.wait(request)
                await self._wait_for_output_settle()
                await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] 되묻기 재생 오류: {e}")
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    async def _wait_for_output_settle(self):
        """스피커 출력의 꼬리가 마이크에 되먹임되지 않도록 락 안에서 잠깐 대기."""
        if self._output_settle_sec > 0:
            await asyncio.sleep(self._output_settle_sec)

    async def _cooldown_on_fail(self):
        """연속 LLM 실패 시 점진적 쿨다운 대기."""
        self._consecutive_fails += 1
        idx = min(self._consecutive_fails - 1, len(self._cooldown_steps) - 1)
        delay = self._cooldown_steps[idx]
        print(f"[VoicePipeline] 연속 실패 {self._consecutive_fails}회 → {delay}초 쿨다운")
        await asyncio.sleep(delay)

    async def _play_fallback(self, error_msg: str):
        """에러 발생 시 대시보드에 알리고 다음 청취 턴으로 복귀."""
        try:
            # 에러 메시지 broadcast
            await broadcast({
                "type": "error",
                "message": error_msg,
                "timestamp": int(time.time() * 1000),
            })

            # 시스템 오류일 때 "잠깐만"을 반복하면 정상 처리처럼 들린다.
            # 대시보드에 오류만 알리고 다음 청취 턴으로 복귀한다.
        except Exception as e:
            print(f"[VoicePipeline] Fallback 재생 오류: {e}")
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    # ── 응답 캐시 헬퍼 ────────────────────────────────────────────────────
    def _cache_key(self, query: str) -> str:
        """질문 텍스트를 캐시 키로 정규화 (공백·대소문자 통일)."""
        return " ".join(query.strip().split())

    def _lookup_response_cache(self, query: str) -> str | None:
        """캐시에서 응답 조회. 없으면 None."""
        return self._response_cache.get(self._cache_key(query))

    def _store_response_cache(self, query: str, response: str) -> None:
        """응답을 캐시에 저장. 최대 크기 초과 시 가장 오래된 항목 제거.
        응답이 5자 이하("응", "그래", "좋아", "그럼" 등)면 저장하지 않는다."""
        if len(response.strip()) <= 5:
            print(f"[VoicePipeline] CACHE SKIP (너무 짧음): {response!r}")
            return
        key = self._cache_key(query)
        if len(self._response_cache) >= self._response_cache_max:
            # dict는 Python 3.7+ 삽입 순서 보장 → 첫 번째 = 가장 오래된 것
            oldest = next(iter(self._response_cache))
            del self._response_cache[oldest]
        self._response_cache[key] = response
        print(f"[VoicePipeline] CACHE SAVE: {key!r} → {response!r}")

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

    def start(self):
        """청취 활성화 — 대시보드 시작 버튼 클릭 시 호출."""
        self._active = True
        print("[VoicePipeline] 청취 활성화")

    def stop_listening(self):
        """청취 일시 중지 (파이프라인 루프는 유지). 대시보드 중지 버튼 클릭 시 호출."""
        self._active = False
        print("[VoicePipeline] 청취 일시 중지")

    def stop(self):
        """파이프라인 완전 중지 (루프 종료)."""
        self._active = False
        self._running = False

    def reset(self):
        """세션 리셋 — 히스토리 + 응답 캐시 초기화."""
        self._chat_history.clear()
        self._response_cache.clear()
        self._consecutive_fails = 0
        # Note: _running은 stop()으로 별도 제어

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def chat_history(self) -> list[dict]:
        """현재 대화 히스토리 (읽기용)."""
        return list(self._chat_history)
