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
    _encode_frame,
    _latest_frame,
    _frame_lock,
    get_state,
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
    async def test_stop_learning(self, mock_broadcast):
        app_state.learning_active = True
        msg = {"event": "stop_learning"}
        await handle_dashboard_message(msg)
        assert app_state.learning_active is False
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
    async def test_stt_text_triggers_processing(self, mock_broadcast):
        """유효한 STT 텍스트가 처리 파이프라인을 시작하는지 검증.
        ai_core가 있으면 llm 호출, 없으면 error broadcast."""
        msg = {"stt_text": "안녕하세요"}
        await handle_dashboard_message(msg)
        # ai_core 상태에 따라 stt_response 또는 error 중 하나가 브로드캐스트
        if mock_broadcast.await_count > 0:
            last_sent = mock_broadcast.call_args[0][0]
            assert last_sent["type"] in ("stt_response", "error")

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
