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
from server.config import DEMO_MODE
from utils.latency_logger import record as _rec

# Vision 질문 분류기: 객체 인식 결과가 필요한 질문 패턴
# 이 패턴에 해당하면 → LLM 캐시 제외 + 무조건 VQA(YOLO 장면) 모드로 처리
# "앞에 뭐 있어", "사람 있어", "의자 있어?" 등 카메라 확인이 필요한 모든 질문
_VISION_RE = re.compile(
    r"뭐.*있|있냐|있어|보여|보이|위험|사람|계단|앞|왼|오른|장애물|찾|감지|물체|뭐가|주변|근처"
)

# VQA 에서 허용하는 장면 최대 나이.
# Stage 전환 후 _ai_loop 이 set_scene(None)으로 클리어하지만,
# YOLO가 느릴 때 오래된 장면이 남아있는 경우를 이중으로 방어.
_MAX_SCENE_AGE_MS: float = 5_000  # 5초

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
        self._voice_history: list[str] = []
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

        _turn_start = time.perf_counter()  # 턴 시작(=녹음 시작) 시각

        # 1. 듣기 — 이 구간 동안 마이크가 사용자 발화를 녹음(처리/재생 아님)
        print("[MIC_STATE] listening 시작 (마이크 녹음 대기/수집)")
        await broadcast({"type": "voice_listening", "timestamp": int(time.time() * 1000)})
        audio_data = await self._mic.listen()

        # 발화 종료 시점 — 여기부터가 '진짜' 처리 지연(STT+LLM+TTS)의 시작.
        # 이전엔 "오디오 시작까지"를 _turn_start 기준으로 재서 녹음시간이 섞여 9초로 보였음.
        _speech_end = time.perf_counter()
        _rec_dur = getattr(self._mic, "last_record_sec", _speech_end - _turn_start)
        _exit = getattr(self._mic, "last_exit_reason", "?")
        print(
            f"[MIC_STATE] 녹음 종료 duration={_rec_dur:.2f}s 종료원인={_exit}"
            + ("  ⚠️ max_duration 도달=VAD가 발화끝 미감지(부스소음 추정) → 녹음이 지연의 주범"
               if _exit == "max_duration" else "")
        )
        print("[MIC_STATE] disabled (이유: 처리/재생 시작 — 이 구간 새 발화 수집 안 됨)")

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
        rms = getattr(self._mic, "last_rms", None)
        if self._low_volume_rms > 0 and isinstance(rms, (int, float)) and 0 < rms < self._low_volume_rms:
            print(f"[VoicePipeline] 저음량(RMS={rms:.0f}) → 되묻기")
            await self._play_reprompt("retry_louder.wav", "저음량")
            return

        # 2. STT
        await broadcast({"type": "voice_processing", "timestamp": int(time.time() * 1000)})
        _stt_start = time.perf_counter()
        text = await self._stt.transcribe(audio_data)
        _stt_elapsed = time.perf_counter() - _stt_start
        _rec("stt_ms", _stt_elapsed * 1000)
        print(f"[TIMING] STT={_stt_elapsed:.2f}s")

        if not text or not text.strip():
            status = getattr(self._stt, "last_status", "unrecognized")
            if status == "error":
                print("[VoicePipeline] STT 시스템 오류 → 재청취")
                await broadcast({
                    "type": "error",
                    "message": "STT 시스템 오류(네트워크/엔진)",
                    "timestamp": int(time.time() * 1000),
                })
                return
            print("[VoicePipeline] 인식 불가(잡음 추정) → 조용히 재청취")
            return

        text = text.strip()

        # 2-1. 호출어 게이팅
        from server.wake_word import parse_wake_word, WAKE_TOKENS
        query = parse_wake_word(text)

        _compact = "".join(text.split())
        _matched = next((t for t in WAKE_TOKENS if t in _compact), None)
        print(f"[STT OUTPUT]     {text!r}")
        print(f"[VoicePipeline] 매칭토큰={_matched!r}  파싱질문={query!r}")

        if query is None:
            return
        if query == "":
            await self._play_reprompt("retry_what.wav", "호출만")
            return
        text = query
        print(f"[PARSED QUESTION] {text!r}")

        await broadcast({
            "type": "user_stt",
            "message": text,
            "timestamp": int(time.time() * 1000),
        })

        # 파이프라인 상태 플래그 — 응답 직전 한눈에 진단
        _am_playing = bool(self._audio_manager and self._audio_manager.is_playing())
        print(
            f"[PIPELINE_STATE] flags: demo={DEMO_MODE}"
            f" listening={self._active} speaking(tts_lock)={self._tts_lock.locked()}"
            f" audio_playing={_am_playing}"
        )

        if DEMO_MODE:
            await self._run_demo_response(text, _speech_end)
            return

        # 3. LLM 호출
        from ai_core.llm_client import call_async, SYSTEM_PROMPT, VQA_PROMPT

        is_vision_query = bool(_VISION_RE.search(text))
        cache_eligible = not is_vision_query

        response: str | None = None
        if cache_eligible:
            response = self._lookup_response_cache(text)
            if response:
                print(f"[VoicePipeline] CACHE HIT: {text!r} → {response!r}")

        _llm_elapsed = 0.0
        if response is None:
            scene, scene_ts = (None, 0.0)
            if self._scene_provider:
                scene, scene_ts = self._scene_provider()
            scene_age_ms = time.time() * 1000 - scene_ts
            fresh = scene is not None and scene_age_ms <= self._scene_fresh_ms

            # ── VQA 모드 선택 ────────────────────────────────────────────
            # Vision 질문이더라도 장면이 _MAX_SCENE_AGE_MS(5초) 이상 오래된 경우
            # "잘 안 보여"로 직접 응답 — Stage 전환 후 잔류 데이터 오염 방지.
            if is_vision_query:
                scene_valid = (
                    scene is not None
                    and scene_age_ms <= _MAX_SCENE_AGE_MS
                )
                if scene_valid:
                    from ai_core.scene_text import scene_to_korean
                    scene_text = scene_to_korean(scene)
                    base_prompt = f"{VQA_PROMPT}\n\n[현재 장면] {scene_text}"
                    print(
                        f"[VoicePipeline] VQA 모드(Vision 질문, 장면 경과={scene_age_ms:.0f}ms)"
                        f"  system={len(base_prompt)}자 user={len(text)}자"
                        f" scene={len(scene_text)}자: {scene_text[:80]!r}"
                    )
                else:
                    age_str = f"{scene_age_ms:.0f}ms" if scene is not None else "없음"
                    print(
                        f"[VoicePipeline] Vision 질문 + 장면 없음/만료"
                        f"(경과={age_str}, 한계={_MAX_SCENE_AGE_MS:.0f}ms) → 직접 응답"
                    )
                    response = "지금은 화면에서 잘 안 보여. 잠깐 기다려 볼까?"
            elif fresh:
                from ai_core.scene_text import scene_to_korean
                scene_text = scene_to_korean(scene)
                base_prompt = f"{VQA_PROMPT}\n\n[현재 장면] {scene_text}"
                print(
                    f"[VoicePipeline] VQA 모드(신선한 장면, 경과={scene_age_ms:.0f}ms)"
                    f"  system={len(base_prompt)}자 user={len(text)}자"
                    f" scene={len(scene_text)}자: {scene_text[:80]!r}"
                )
            else:
                base_prompt = SYSTEM_PROMPT
                print("[VoicePipeline] 일반 대화 모드")

            if response is None:
                context = self._build_context(base_prompt)
                try:
                    _llm_start = time.perf_counter()
                    response = await call_async(context, text)
                    _llm_elapsed = time.perf_counter() - _llm_start
                    _rec("llm_ms", _llm_elapsed * 1000)
                    print(f"[TIMING] LLM={_llm_elapsed:.2f}s")
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

        self._consecutive_fails = 0
        if self._count_question:
            self._count_question()

        if cache_eligible:
            self._store_response_cache(text, response)

        self._chat_history.append({"role": "user", "content": text})
        self._chat_history.append({"role": "assistant", "content": response})
        if len(self._chat_history) > self._max_history:
            self._chat_history = self._chat_history[-self._max_history:]

        # ── 텍스트 → 브라우저 즉시 전송 (음성보다 먼저 표시됨) ──────────
        print(f"[PIPELINE BROADCAST] {response!r}")
        await broadcast({
            "type": "stt_response",
            "message": response,
            "timestamp": int(time.time() * 1000),
        })
        _text_delay = time.perf_counter() - _turn_start
        print(f"[TIMING] 텍스트 표시까지={_text_delay:.2f}s (STT+LLM)")

        # ── TTS 생성: lock 밖에서 먼저 실행 (병목 핵심 수정) ───────────
        # 이전 코드: lock 안에서 TTS 생성 → 텍스트 표시 직후 1~3초 대기
        # 수정 후:   lock 밖에서 TTS 생성 → 재생만 lock 안에서 직렬화
        # 효과: lock 경합(danger 오디오 재생 중 등)이 있을 때 TTS 생성이 병렬 실행
        print(f"[PIPELINE TTS INPUT] {response!r}")
        from ai_core.tts import get_tts_cache
        _tts_start = time.perf_counter()
        tts_filepath = await get_tts_cache().get_or_create(response)
        _tts_elapsed = time.perf_counter() - _tts_start
        _is_cache = _tts_elapsed < 0.05  # 50ms 이하면 캐시 HIT로 판정
        _rec("tts_cache_ms" if _is_cache else "tts_gen_ms", _tts_elapsed * 1000)
        # 발화종료 기준 처리 지연 = STT+LLM+TTS (녹음시간 제외 → 체감 지연의 실제값)
        _proc_delay = time.perf_counter() - _speech_end
        print(
            f"[TIMING] TTS={'캐시' if _is_cache else '생성'}={_tts_elapsed:.2f}s"
            f" → 발화종료후 오디오시작까지={_proc_delay:.2f}s (녹음 {_rec_dur:.2f}s 제외)"
        )

        # ── 재생만 lock 안에서 (narration/danger와 경합 방지) ──────────
        async with self._tts_lock:
            await self._play_tts_file(tts_filepath)

        _total = time.perf_counter() - _turn_start
        _rec("text_delay_ms", _text_delay * 1000)
        _rec("turn_total_ms", _total * 1000)
        print(
            f"[TIMING 요약]"
            f" 녹음={_rec_dur:.2f}s({_exit})"
            f" STT={_stt_elapsed:.2f}s"
            f" LLM={_llm_elapsed:.2f}s"
            f" TTS={'캐시' if _is_cache else '생성'}({_tts_elapsed:.2f}s)"
            f" | 처리={_proc_delay:.2f}s 턴전체={_total:.2f}s"
        )
        # 재생 끝 → 다음 루프에서 즉시 재청취. 마이크가 영구 차단되지 않음을 명시.
        print("[MIC_STATE] enabled (재생 완료 → 다음 턴 재청취 준비)")

    async def _play_tts_file(self, filepath, interrupt: bool = False):
        """이미 생성된 TTS 파일을 재생. tts_start/tts_done broadcast.
        interrupt=True면 진행 중인 재생/큐를 즉시 중단하고 이 파일을 재생(데모 단일재생)."""
        try:
            from ai_core.audio_manager import get_audio_manager
            await broadcast({"type": "tts_start", "timestamp": int(time.time() * 1000)})
            if filepath:
                am = self._audio_manager or get_audio_manager()
                _play_start = time.perf_counter()
                request = am.play_path(
                    str(filepath), priority=PRIORITY_CONVERSATION, interrupt=interrupt,
                )
                await am.wait(request)
                print(f"[TIMING] 재생={time.perf_counter() - _play_start:.2f}s")
                await self._wait_for_output_settle()
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})
        except Exception as e:
            print(f"[VoicePipeline] TTS 재생 오류: {e}")
            await broadcast({"type": "error", "message": f"TTS 오류: {type(e).__name__}", "timestamp": int(time.time() * 1000)})
            await broadcast({"type": "tts_done", "timestamp": int(time.time() * 1000)})

    async def _run_demo_response(self, question: str, turn_start: float):
        """DEMO_MODE 전용: LLM/TTS 없이 키워드+장면으로 사전 음성 즉시 재생."""
        from server.demo_responses import find_response, voice_path

        scene = None
        if self._scene_provider:
            scene, _scene_ts = self._scene_provider()
        scene_objects = scene.get("objects", []) if isinstance(scene, dict) else []
        voice_file = find_response(question, scene_objects, self._voice_history)
        self._voice_history.append(voice_file)

        await broadcast({
            "type": "stt_response",
            "message": f"[DEMO] {voice_file}",
            "audio_file": voice_file,
            "timestamp": int(time.time() * 1000),
        })

        if self._count_question:
            self._count_question()

        filepath = voice_path(voice_file)
        if not filepath.exists():
            print(f"[DEMO] 음성 파일 없음: {filepath}")
            await broadcast({
                "type": "error",
                "message": f"DEMO 음성 파일 없음: {voice_file}",
                "timestamp": int(time.time() * 1000),
            })
            return

        # 데모: 진행 중 재생을 즉시 끊고 새 응답 재생 (단일 재생 보장)
        async with self._tts_lock:
            await self._play_tts_file(filepath, interrupt=True)

        print(f"[DEMO] {question!r} → {voice_file} (발화종료후 {time.perf_counter() - turn_start:.2f}s)")

    async def _speak(self, text: str):
        """TTS 생성 + 오디오 재생 (reprompt 경로용 — _play_tts_file 직접 호출 불가 시 사용)."""
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
        """세션 리셋 — 히스토리 + 응답 캐시 + demo voice history 초기화."""
        self._chat_history.clear()
        self._response_cache.clear()
        self._voice_history.clear()
        self._consecutive_fails = 0
        # Note: _running은 stop()으로 별도 제어

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def chat_history(self) -> list[dict]:
        """현재 대화 히스토리 (읽기용)."""
        return list(self._chat_history)

    @property
    def voice_history(self) -> list[str]:
        """시연 세션 동안 재생한 demo voice 파일명."""
        return list(self._voice_history)
