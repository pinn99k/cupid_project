"""
통합 테스트 (현재 코드 + 갈라 시연 시나리오 기준으로 재작성).

시연 3경로(docs/demo_scenario.md)를 계약 단위로 검증한다:
  경로 A — "시아야" 호출어 게이팅 후 질문 추출 (온디맨드 LLM/TTS 진입조건)
  경로 B — Stage 3 전용 자율 위험 경고 (judge)
  경로 C — 실시간 인지(YOLO) + P1 최적화(검출주기 디커플링 / imgsz)

여기에 더해 시스템 불변식(TTS Lock 직렬화, 세션 리셋 전파, 에러 시 tts_done 보장,
대시보드 독립성, 모듈/설정 무결성)을 검증한다.

하드웨어 불필요 — mic/stt/카메라/오디오는 모두 mock.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np


# ===========================================================================
# 경로 A — 호출어("시아야") 게이팅  (시연 핵심: 부를 때만 응답)
# ===========================================================================

class TestWakeWordGating:
    """parse_wake_word: 호출어 뒤 질문만 추출, 호출 아니면 None(무시)."""

    @pytest.mark.parametrize("utterance,expected", [
        ("시아야 앞에 뭐 있어?", "앞에 뭐 있어"),   # 표준 질의
        ("안녕 시아야 뭐해", "뭐해"),               # 호출어가 중간
        ("시아야 지금 가도 돼?", "지금 가도 돼"),
        ("시아야", ""),                            # 호출만(질문 없음) → 되묻기 트리거
        ("  시아야   방향 맞아  ", "방향 맞아"),     # 공백 정규화
    ])
    def test_wake_extracts_query(self, utterance, expected):
        from server.wake_word import parse_wake_word
        assert parse_wake_word(utterance) == expected

    @pytest.mark.parametrize("utterance", [
        "안녕하세요",          # 호출어 없음 → 무시
        "오늘 날씨 좋다",
        "러시아 갈래",         # 단어 중간 '시아' → 호출어로 보지 않음
        "",                    # 빈 문자열
        None,                  # None 입력
    ])
    def test_non_wake_returns_none(self, utterance):
        from server.wake_word import parse_wake_word
        assert parse_wake_word(utterance) is None

    @pytest.mark.parametrize("variant", [
        "시아야 뭐야",   # 표준
        "시야야 뭐야",   # STT 흔들림
        "씨아야 뭐야",
        "지아야 뭐야",
        "sia 뭐야",      # 영문 표기
        "SIA 뭐야",      # 대문자
    ])
    def test_stt_variants_still_wake(self, variant):
        """STT가 호출어를 흔들어 적어도(시야/씨아/sia 등) 인식되어야 시연이 안 끊긴다."""
        from server.wake_word import parse_wake_word
        assert parse_wake_word(variant) is not None


# ===========================================================================
# 경로 B — 자율 위험 경고 (Stage 3 전용, LLM 미사용)
# ===========================================================================

class TestDangerJudgeStageGating:
    """judge(enriched, stage): Stage 3에서만 위험 판정."""

    def _near_person(self):
        return {
            "objects": [{"label": "person", "direction": "center", "distance_est": "near"}],
            "ultrasonic_cm": None,
            "ultrasonic_target": "person",
        }

    @pytest.mark.parametrize("stage", [1, 2])
    def test_no_danger_outside_stage3(self, stage):
        """수용(1)·방향(2) 단계에서는 코앞 장애물이어도 위험판단 비활성."""
        from ai_core.danger import judge
        scene = {"objects": [], "ultrasonic_cm": 5, "ultrasonic_target": "chair"}
        assert judge(scene, stage) is None

    def test_ultrasonic_emergency_in_stage3(self):
        """초음파 < DANGER_DISTANCE_CM(30) → 긴급 정지(최우선 규칙)."""
        from ai_core.danger import judge
        scene = {"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"}
        result = judge(scene, 3)
        assert result is not None
        assert result["level"] == "emergency"
        assert result["object"] == "chair"
        assert result["audio_file"] == "warn_emergency.wav"

    def test_ultrasonic_takes_precedence_over_label(self):
        """초음파 코앞은 YOLO 라벨 판정보다 우선(Rule 1)."""
        from ai_core.danger import judge
        scene = self._near_person()
        scene["ultrasonic_cm"] = 10  # 코앞
        result = judge(scene, 3)
        assert result["level"] == "emergency"
        assert result["audio_file"] == "warn_emergency.wav"

    def test_near_person_label_warning(self):
        """초음파 없이 person이 near면 사람 경고 음원."""
        from ai_core.danger import judge
        result = judge(self._near_person(), 3)
        assert result["level"] == "warning"
        assert result["object"] == "person"
        assert result["audio_file"] == "warn_person.wav"

    def test_near_object_label_warning(self):
        """위험 라벨(person 외)은 범용 경고 음원."""
        from ai_core.danger import judge
        scene = {
            "objects": [{"label": "chair", "direction": "center", "distance_est": "near"}],
            "ultrasonic_cm": None,
        }
        result = judge(scene, 3)
        assert result["level"] == "warning"
        assert result["audio_file"] == "warn_object.wav"

    def test_far_or_irrelevant_is_safe(self):
        """멀거나 위험 라벨이 아니면 None(안전)."""
        from ai_core.danger import judge
        scene = {
            "objects": [
                {"label": "person", "direction": "left", "distance_est": "far"},
                {"label": "book", "direction": "center", "distance_est": "near"},
            ],
            "ultrasonic_cm": None,
        }
        assert judge(scene, 3) is None


# ===========================================================================
# 경로 C — 실시간 인지(YOLO) + P1 최적화
# ===========================================================================

class TestYoloDetectImgsz:
    """detect(frame, imgsz): imgsz>0이면 추론 해상도 다운스케일, 0이면 모델 기본값."""

    def _fake_model(self):
        m = MagicMock()
        empty = MagicMock()
        empty.boxes = []
        m.predict.return_value = [empty]
        return m

    def test_imgsz_passed_when_set(self):
        import ai_core.vision as vision
        fake = self._fake_model()
        with patch.object(vision, "model", fake):
            vision.detect(np.zeros((48, 64, 3), dtype=np.uint8), imgsz=416)
        assert fake.predict.call_args.kwargs.get("imgsz") == 416

    def test_imgsz_omitted_when_zero(self):
        """0이면 predict에 imgsz를 넘기지 않음 → 변경 전과 100% 동일."""
        import ai_core.vision as vision
        fake = self._fake_model()
        with patch.object(vision, "model", fake):
            vision.detect(np.zeros((48, 64, 3), dtype=np.uint8), imgsz=0)
        assert "imgsz" not in fake.predict.call_args.kwargs


class TestP1ConfigDefaults:
    """P1 노브 기본값은 '꺼짐' — 켜기 전과 동일 동작 보장(킬스위치)."""

    def test_defaults_are_off(self):
        from server.config import YOLO_IMGSZ, DETECT_INTERVAL_SEC
        assert YOLO_IMGSZ == 0
        assert DETECT_INTERVAL_SEC == 0.0


class TestAiLoopDetectionDecoupling:
    """_ai_loop: DETECT_INTERVAL_SEC로 YOLO 추론 빈도를 표시/판단과 디커플링."""

    async def _run_loop_counting_detect(self, detect_interval, max_iters=6):
        """_ai_loop을 결정적(deterministic) 가짜 시계/sleep으로 N바퀴 돌리고
        detect 호출 횟수를 센다. 실제 카메라/오디오/모델 없이 루프 분기만 검증."""
        import main as main_mod
        import server.main_server as srv

        detect_calls = {"n": 0}
        clock = {"t": 1000.0}

        def fake_detect(frame, *a, **k):
            detect_calls["n"] += 1
            return []

        def fake_time():
            return clock["t"]

        async def fake_sleep(dt):
            clock["t"] += dt
            fake_sleep.calls += 1
            if fake_sleep.calls >= max_iters:
                raise asyncio.CancelledError
        fake_sleep.calls = 0

        prev_stage = srv.app_state.current_stage
        srv.app_state.current_stage = 3  # 위험판단/검출 활성 단계
        try:
            with patch.object(main_mod, "get_audio_manager", return_value=MagicMock()), \
                 patch.object(main_mod, "get_frame", return_value=np.zeros((48, 64, 3), dtype=np.uint8)), \
                 patch.object(main_mod, "detect", side_effect=fake_detect), \
                 patch.object(main_mod, "enrich", return_value={"objects": []}), \
                 patch.object(main_mod, "set_scene", MagicMock()), \
                 patch.object(main_mod, "judge", return_value=None), \
                 patch.object(main_mod, "_get_distance", return_value=None), \
                 patch.object(main_mod, "broadcast", new_callable=AsyncMock), \
                 patch.object(main_mod, "AI_LOOP_SLEEP_SEC", 0.03), \
                 patch.object(main_mod, "DETECT_INTERVAL_SEC", detect_interval), \
                 patch("main.time.time", fake_time), \
                 patch("main.asyncio.sleep", fake_sleep):
                try:
                    await main_mod._ai_loop()
                except asyncio.CancelledError:
                    pass
        finally:
            srv.app_state.current_stage = prev_stage
        return detect_calls["n"]

    @pytest.mark.asyncio
    async def test_interval_zero_detects_every_loop(self):
        """기본값(0): 매 루프 검출 → 여러 번 호출(변경 전과 동일)."""
        n = await self._run_loop_counting_detect(detect_interval=0.0)
        assert n >= 3

    @pytest.mark.asyncio
    async def test_large_interval_reuses_detection(self):
        """큰 간격: 첫 검출 1회 후 간격 내에는 직전 결과 재사용 → 추론 1회."""
        n = await self._run_loop_counting_detect(detect_interval=100.0)
        assert n == 1


# ===========================================================================
# TTS Lock 직렬화 — 위험/대화/묘사 음성이 같은 Lock을 공유해 겹치지 않음
# ===========================================================================

class TestTTSLockContention:
    @pytest.fixture
    def tts_lock(self):
        return asyncio.Lock()

    @pytest.fixture
    def pipeline(self, tts_lock):
        from server.voice_pipeline import VoicePipeline
        mic = MagicMock()
        mic.listen = AsyncMock(return_value=b"fake_wav")
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="시아야 안녕")
        return VoicePipeline(mic=mic, stt=stt, tts_lock=tts_lock)

    def test_pipeline_uses_injected_lock(self, pipeline, tts_lock):
        assert pipeline._tts_lock is tts_lock

    @pytest.mark.asyncio
    async def test_lock_serializes_speakers(self, tts_lock):
        order = []

        async def speaker_a():
            async with tts_lock:
                order.append("A_start")
                await asyncio.sleep(0.05)
                order.append("A_end")

        async def speaker_b():
            await asyncio.sleep(0.01)  # A가 먼저 Lock 획득
            async with tts_lock:
                order.append("B_start")
                order.append("B_end")

        await asyncio.gather(speaker_a(), speaker_b())
        assert order == ["A_start", "A_end", "B_start", "B_end"]


# ===========================================================================
# 세션 리셋 전파 — stop_learning / new_session
# ===========================================================================

class TestSessionReset:
    def test_reset_clears_app_state(self):
        """reset_session(): stage→1, question_count→0, learning_active→False."""
        from server.main_server import app_state, reset_session, set_voice_pipeline
        app_state.current_stage = 3
        app_state.learning_active = True
        app_state.question_count = 7
        with patch("server.main_server.get_audio_manager", side_effect=ImportError):
            set_voice_pipeline(None)
            reset_session()
        assert app_state.current_stage == 1
        assert app_state.learning_active is False
        assert app_state.question_count == 0

    def test_reset_calls_pipeline_reset(self):
        """reset_session()이 주입된 voice_pipeline.reset()을 호출."""
        from server.main_server import reset_session, set_voice_pipeline
        mock_pipeline = MagicMock()
        with patch("server.main_server.get_audio_manager", side_effect=ImportError):
            set_voice_pipeline(mock_pipeline)
            reset_session()
            mock_pipeline.reset.assert_called_once()
            set_voice_pipeline(None)

    def test_pipeline_reset_clears_history(self):
        from server.voice_pipeline import VoicePipeline
        vp = VoicePipeline(mic=MagicMock(), stt=MagicMock(), tts_lock=asyncio.Lock())
        vp._chat_history = [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "반가워"},
        ]
        vp.reset()
        assert vp.chat_history == []


# ===========================================================================
# 대시보드 → 서버 이벤트 / 채팅 계약
# ===========================================================================

class TestDashboardEvents:
    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_start_learning_sets_stage(self, mock_broadcast):
        from server.main_server import handle_dashboard_message, app_state
        app_state.current_stage = 1
        await handle_dashboard_message({"event": "start_learning", "stage": 3})
        assert app_state.current_stage == 3
        mock_broadcast.assert_awaited()

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_unknown_message_ignored(self, mock_broadcast):
        """채팅엔 user_stt/stt_response만 남는다 — 폐기된 stt_text는 무시."""
        from server.main_server import handle_dashboard_message
        await handle_dashboard_message({"stt_text": "안녕하세요"})
        mock_broadcast.assert_not_awaited()


# ===========================================================================
# 오디오 우선순위 계약 — 위험(0) > 대화(10) > 묘사(20) > 폴백(30)
# ===========================================================================

class TestAudioPriority:
    def test_priority_ordering(self):
        from ai_core.audio_manager import (
            PRIORITY_DANGER, PRIORITY_CONVERSATION, PRIORITY_NARRATION, PRIORITY_FALLBACK,
        )
        assert PRIORITY_DANGER < PRIORITY_CONVERSATION < PRIORITY_NARRATION < PRIORITY_FALLBACK


# ===========================================================================
# 에러 경로 — TTS 실패해도 tts_done은 반드시 발송(상태 복구)
# ===========================================================================

class TestErrorPathTtsDone:
    @pytest.fixture
    def pipeline(self):
        from server.voice_pipeline import VoicePipeline
        return VoicePipeline(mic=MagicMock(), stt=MagicMock(), tts_lock=asyncio.Lock())

    @pytest.mark.asyncio
    @patch("server.voice_pipeline.broadcast", new_callable=AsyncMock)
    async def test_tts_failure_still_emits_done(self, mock_broadcast, pipeline):
        with patch("ai_core.tts.get_tts_cache", side_effect=Exception("TTS error")):
            await pipeline._speak("테스트 문장")
        types = [c[0][0]["type"] for c in mock_broadcast.call_args_list]
        assert "tts_done" in types, "에러 시에도 tts_done 필수(상태 복구)"


# ===========================================================================
# 대시보드 독립성 — 클라이언트 없어도 서버 파이프라인 정상
# ===========================================================================

class TestDashboardIndependence:
    @pytest.mark.asyncio
    async def test_broadcast_without_clients_no_crash(self):
        from server.websocket_handler import clients, broadcast
        clients.clear()
        await broadcast({"type": "voice_listening"})  # 예외 없으면 통과


# ===========================================================================
# 모듈 / 설정 무결성
# ===========================================================================

class TestModuleAndConfigIntegrity:
    def test_core_modules_import(self):
        from server.main_server import app, handle_dashboard_message, reset_session
        from server.voice_pipeline import VoicePipeline
        from server.websocket_handler import broadcast
        from ai_core.vision import detect, enrich
        from ai_core.danger import judge
        assert all([app, handle_dashboard_message, reset_session,
                    VoicePipeline, broadcast, detect, enrich, judge])

    def test_p1_config_fields_typed(self):
        from server.config import (YOLO_IMGSZ, DETECT_INTERVAL_SEC,
                                   DETECTION_BROADCAST_INTERVAL, AI_LOOP_SLEEP_SEC)
        assert isinstance(YOLO_IMGSZ, int)
        assert isinstance(DETECT_INTERVAL_SEC, float)
        assert isinstance(DETECTION_BROADCAST_INTERVAL, float)
        assert isinstance(AI_LOOP_SLEEP_SEC, float)
