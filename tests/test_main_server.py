"""server/main_server.py 단위 테스트."""

import json
import asyncio
import threading
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.main_server import (
    AppState,
    app_state,
    set_frame,
    get_frame,
    _encode_frame,
    _latest_frame,
    _frame_lock,
    get_state,
    set_scene,
    get_scene,
    increment_question_count,
    reset_session,
    handle_dashboard_message,
)


# ---------------------------------------------------------------------------
# AppState dataclass 테스트
# ---------------------------------------------------------------------------

class TestAppState:
    def test_defaults(self):
        state = AppState()
        assert state.current_stage == 1
        assert state.learning_active is False
        assert state.session_id == ""
        assert state.question_count == 0

    def test_to_dict(self):
        state = AppState(current_stage=2, learning_active=True, session_id="s1")
        d = state.to_dict()
        assert d == {
            "current_stage": 2,
            "learning_active": True,
            "session_id": "s1",
            "question_count": 0,
        }

    def test_mutation(self):
        state = AppState()
        state.current_stage = 3
        state.learning_active = True
        state.session_id = "test_session"
        assert state.current_stage == 3
        assert state.learning_active is True
        assert state.session_id == "test_session"


# ---------------------------------------------------------------------------
# get_state() 테스트
# ---------------------------------------------------------------------------

class TestGetState:
    def test_returns_dict(self):
        state = get_state()
        assert isinstance(state, dict)
        assert "stage" in state
        assert "learning_active" in state
        assert "session_id" in state

    def test_reflects_app_state(self):
        original_stage = app_state.current_stage
        app_state.current_stage = 3
        try:
            state = get_state()
            assert state["stage"] == 3
        finally:
            app_state.current_stage = original_stage


# ---------------------------------------------------------------------------
# 최신 장면 슬롯 테스트 (Unit 3)
# ---------------------------------------------------------------------------

class TestSceneSlot:
    def setup_method(self):
        import server.main_server as mod
        with mod._scene_lock:
            mod._latest_scene = None
            mod._latest_scene_ts = 0.0

    def test_get_scene_none_initially(self):
        scene, ts = get_scene()
        assert scene is None
        assert ts == 0.0

    def test_set_then_get_returns_copy(self):
        enriched = {"objects": [{"label": "person", "direction": "center"}]}
        set_scene(enriched)
        scene, ts = get_scene()
        # get_scene은 다수결 안정화 결과 + 메타키(scene_history_frames)를 반환
        assert scene["objects"] == enriched["objects"]
        assert scene["scene_history_frames"] == 1
        assert ts > 0.0
        # 반환본을 변형해도 슬롯 원본은 불변 (copy 반환)
        scene["objects"][0]["label"] = "X"
        scene2, _ = get_scene()
        assert scene2["objects"][0]["label"] == "person"

    def test_set_scene_isolates_from_source(self):
        enriched = {"objects": [{"label": "car"}]}
        set_scene(enriched)
        enriched["objects"][0]["label"] = "mutated"  # 원본 변형
        scene, _ = get_scene()
        assert scene["objects"][0]["label"] == "car"  # 슬롯은 독립

    def test_set_scene_none(self):
        set_scene({"objects": []})
        set_scene(None)
        scene, ts = get_scene()
        assert scene is None


# ---------------------------------------------------------------------------
# question_count 테스트 (Unit 3)
# ---------------------------------------------------------------------------

class TestQuestionCount:
    def setup_method(self):
        app_state.question_count = 0

    def test_increment_returns_new_value(self):
        assert increment_question_count() == 1
        assert increment_question_count() == 2
        assert app_state.question_count == 2

    def test_get_state_reflects_count(self):
        increment_question_count()
        assert get_state()["question_count"] == 1

    def test_reset_session_zeroes_count(self):
        increment_question_count()
        increment_question_count()
        reset_session()
        assert app_state.question_count == 0


# ---------------------------------------------------------------------------
# MJPEG 프레임 관리 테스트
# ---------------------------------------------------------------------------

class TestMjpegFrame:
    def setup_method(self):
        """각 테스트 전 프레임 초기화."""
        import server.main_server as mod
        with mod._frame_lock:
            mod._latest_frame = None

    def test_set_frame_stores_copy(self):
        import server.main_server as mod
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[0, 0] = [255, 0, 0]
        set_frame(frame)
        # 원본 수정해도 저장된 프레임 불변
        frame[0, 0] = [0, 0, 0]
        with mod._frame_lock:
            stored = mod._latest_frame
        assert stored is not None
        assert stored[0, 0, 0] == 255  # 복사본은 원본과 독립

    def test_set_frame_none(self):
        import server.main_server as mod
        set_frame(None)
        with mod._frame_lock:
            assert mod._latest_frame is None

    def test_encode_frame_returns_none_when_no_frame(self):
        result = _encode_frame()
        assert result is None

    def test_encode_frame_returns_jpeg_bytes(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        set_frame(frame)
        result = _encode_frame()
        assert result is not None
        assert isinstance(result, bytes)
        # JPEG 매직 바이트 확인
        assert result[:2] == b'\xff\xd8'

    def test_get_frame_returns_copy(self):
        """get_frame은 독립적인 복사본을 반환하는지 검증."""
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        frame[0, 0] = [100, 200, 255]
        set_frame(frame)
        got = get_frame()
        assert got is not None
        assert got[0, 0, 0] == 100
        # 원본 수정해도 get_frame 결과에 영향 없음
        frame[0, 0] = [0, 0, 0]
        got2 = get_frame()
        assert got2[0, 0, 0] == 100

    def test_get_frame_none_when_no_frame(self):
        assert get_frame() is None

    def test_set_frame_thread_safety(self):
        """다중 스레드에서 set_frame 호출 시 크래시 없음."""
        errors = []

        def writer(val):
            try:
                for _ in range(100):
                    frame = np.full((10, 10, 3), val, dtype=np.uint8)
                    set_frame(frame)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


class TestResetSession:
    def setup_method(self):
        app_state.current_stage = 3
        app_state.learning_active = True
        app_state.session_id = "test_session"

    def test_reset_clears_state(self):
        reset_session()
        assert app_state.current_stage == 1
        assert app_state.learning_active is False
        # session_id는 reset_session에서 변경하지 않음 (new_session에서 별도 처리)
        assert app_state.session_id == "test_session"

    def test_reset_no_crash_without_audio(self):
        """AudioManager 없어도 크래시 없음."""
        reset_session()  # should not raise


# ---------------------------------------------------------------------------
# handle_dashboard_message 테스트
# ---------------------------------------------------------------------------

class TestHandleDashboardMessage:
    def setup_method(self):
        """각 테스트 전 app_state 초기화."""
        app_state.current_stage = 1
        app_state.learning_active = False
        app_state.session_id = ""

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_start_learning(self, mock_broadcast):
        msg = {"event": "start_learning", "stage": 2}
        await handle_dashboard_message(msg)
        assert app_state.learning_active is True
        assert app_state.current_stage == 2
        mock_broadcast.assert_awaited_once()
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "ack"
        assert sent["event"] == "start_learning"
        assert sent["stage"] == 2

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_stop_learning_resets_session(self, mock_broadcast):
        app_state.learning_active = True
        app_state.current_stage = 3
        msg = {"event": "stop_learning"}
        await handle_dashboard_message(msg)
        assert app_state.learning_active is False
        assert app_state.current_stage == 1  # reset_session이 stage도 리셋
        # ack + recording_state(idle, 마이크 버튼 동기화) 2건 전송
        assert mock_broadcast.await_count == 2
        ack = mock_broadcast.await_args_list[0].args[0]
        assert ack["type"] == "ack"
        assert ack["event"] == "stop_learning"
        rec = mock_broadcast.await_args_list[1].args[0]
        assert rec["type"] == "recording_state"
        assert rec["state"] == "idle"

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_start_learning_default_stage(self, mock_broadcast):
        msg = {"event": "start_learning"}  # stage 미지정
        await handle_dashboard_message(msg)
        assert app_state.current_stage == 1  # 기본값

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_new_session_without_ai_core(self, mock_broadcast):
        """ai_core 없어도 크래시 안 나는지 검증."""
        msg = {"event": "new_session"}
        await handle_dashboard_message(msg)
        # ack + recording_state(idle) 2건 전송
        assert mock_broadcast.await_count == 2
        ack = mock_broadcast.await_args_list[0].args[0]
        assert ack["type"] == "ack"
        assert ack["event"] == "new_session"
        rec = mock_broadcast.await_args_list[1].args[0]
        assert rec["type"] == "recording_state"
        assert rec["state"] == "idle"

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_clear_tts_cache_without_ai_core(self, mock_broadcast):
        msg = {"event": "clear_tts_cache"}
        await handle_dashboard_message(msg)
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "ack"
        assert sent["event"] == "clear_tts_cache"

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_stt_text_ignored_by_dashboard_handler(self, mock_broadcast):
        """STT는 서버 VoicePipeline이 처리 — 대시보드 핸들러는 무시."""
        msg = {"stt_text": "안녕하세요"}
        await handle_dashboard_message(msg)
        mock_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_unknown_event_no_crash(self, mock_broadcast):
        msg = {"event": "unknown_event_xyz"}
        await handle_dashboard_message(msg)
        # 알 수 없는 이벤트는 무시 (ack 없음)
        mock_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_empty_message_no_crash(self, mock_broadcast):
        msg = {}
        await handle_dashboard_message(msg)
        mock_broadcast.assert_not_awaited()


# ---------------------------------------------------------------------------
# FastAPI 엔드포인트 통합 테스트
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self):
        from httpx import AsyncClient, ASGITransport
        from server.main_server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "stage" in data
