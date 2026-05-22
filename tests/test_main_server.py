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

    def test_to_dict(self):
        state = AppState(current_stage=2, learning_active=True, session_id="s1")
        d = state.to_dict()
        assert d == {
            "current_stage": 2,
            "learning_active": True,
            "session_id": "s1",
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
        mock_broadcast.assert_awaited_once()
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "ack"
        assert sent["event"] == "stop_learning"

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
        mock_broadcast.assert_awaited_once()
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "ack"
        assert sent["event"] == "new_session"

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
    async def test_stt_empty_text_ignored(self, mock_broadcast):
        msg = {"stt_text": "   "}
        await handle_dashboard_message(msg)
        mock_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("server.main_server.broadcast", new_callable=AsyncMock)
    async def test_stt_broadcasts_user_text_first(self, mock_broadcast):
        """STT 수신 시 user_stt를 먼저 브로드캐스트하는지 검증."""
        msg = {"stt_text": "안녕하세요"}
        await handle_dashboard_message(msg)
        # 최소 1번은 호출 (user_stt)
        assert mock_broadcast.await_count >= 1
        first_sent = mock_broadcast.call_args_list[0][0][0]
        assert first_sent["type"] == "user_stt"
        assert first_sent["message"] == "안녕하세요"

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
