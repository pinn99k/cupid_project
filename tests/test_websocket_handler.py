"""server/websocket_handler.py 단위 테스트."""

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.websocket_handler import (
    clients,
    connect,
    disconnect,
    broadcast,
    send_to,
    receive_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_ws(*, open=True):
    """테스트용 Mock WebSocket 생성."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    # hash 가능하게
    ws.__hash__ = MagicMock(return_value=id(ws))
    ws.__eq__ = MagicMock(side_effect=lambda other: ws is other)
    return ws


@pytest.fixture(autouse=True)
def clear_clients():
    """각 테스트 전후로 clients 초기화."""
    clients.clear()
    yield
    clients.clear()


# ---------------------------------------------------------------------------
# connect 테스트
# ---------------------------------------------------------------------------

class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_accepts_and_adds_client(self):
        ws = make_mock_ws()
        await connect(ws)
        ws.accept.assert_awaited_once()
        assert ws in clients

    @pytest.mark.asyncio
    async def test_connect_sends_init_state(self):
        ws = make_mock_ws()
        provider = lambda: {"stage": 2, "learning_active": True}
        await connect(ws, state_provider=provider)
        ws.send_text.assert_awaited_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "init_state"
        assert sent["stage"] == 2

    @pytest.mark.asyncio
    async def test_connect_without_provider_no_init(self):
        ws = make_mock_ws()
        await connect(ws)
        ws.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_connects(self):
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await connect(ws1)
        await connect(ws2)
        assert len(clients) == 2


# ---------------------------------------------------------------------------
# disconnect 테스트
# ---------------------------------------------------------------------------

class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        ws = make_mock_ws()
        await connect(ws)
        assert ws in clients
        await disconnect(ws)
        assert ws not in clients

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_no_error(self):
        ws = make_mock_ws()
        await disconnect(ws)  # should not raise


# ---------------------------------------------------------------------------
# send_to 테스트
# ---------------------------------------------------------------------------

class TestSendTo:
    @pytest.mark.asyncio
    async def test_send_to_success(self):
        ws = make_mock_ws()
        clients.add(ws)
        await send_to(ws, {"type": "test", "msg": "hello"})
        ws.send_text.assert_awaited_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "test"

    @pytest.mark.asyncio
    async def test_send_to_failure_removes_client(self):
        ws = make_mock_ws()
        clients.add(ws)
        ws.send_text.side_effect = Exception("connection closed")
        await send_to(ws, {"type": "test"})
        assert ws not in clients

    @pytest.mark.asyncio
    async def test_send_to_korean_text(self):
        ws = make_mock_ws()
        clients.add(ws)
        await send_to(ws, {"message": "안녕하세요"})
        sent_text = ws.send_text.call_args[0][0]
        assert "안녕하세요" in sent_text  # ensure_ascii=False


# ---------------------------------------------------------------------------
# broadcast 테스트
# ---------------------------------------------------------------------------

class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_all(self):
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        clients.add(ws1)
        clients.add(ws2)
        await broadcast({"type": "test"})
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed(self):
        ws_good = make_mock_ws()
        ws_bad = make_mock_ws()
        ws_bad.send_text.side_effect = Exception("dead")
        clients.add(ws_good)
        clients.add(ws_bad)
        await broadcast({"type": "test"})
        assert ws_good in clients
        assert ws_bad not in clients

    @pytest.mark.asyncio
    async def test_broadcast_empty_clients(self):
        await broadcast({"type": "test"})  # should not raise


# ---------------------------------------------------------------------------
# receive_loop 테스트
# ---------------------------------------------------------------------------

class TestReceiveLoop:
    @pytest.mark.asyncio
    async def test_receive_valid_json(self):
        ws = make_mock_ws()
        handler = AsyncMock()
        from fastapi import WebSocketDisconnect

        # 첫 호출: 유효 JSON, 두 번째: 연결 종료
        ws.receive_text.side_effect = [
            '{"event": "start_learning"}',
            WebSocketDisconnect(),
        ]
        clients.add(ws)
        await receive_loop(ws, handler)
        handler.assert_awaited_once_with({"event": "start_learning"})

    @pytest.mark.asyncio
    async def test_receive_invalid_json_continues(self):
        ws = make_mock_ws()
        handler = AsyncMock()
        from fastapi import WebSocketDisconnect

        ws.receive_text.side_effect = [
            "not json at all",
            '{"event": "stop_learning"}',
            WebSocketDisconnect(),
        ]
        clients.add(ws)
        await receive_loop(ws, handler)
        # invalid JSON은 건너뛰고, 두 번째 유효 메시지만 처리
        handler.assert_awaited_once_with({"event": "stop_learning"})

    @pytest.mark.asyncio
    async def test_receive_handler_error_broadcasts_error(self):
        ws = make_mock_ws()
        handler = AsyncMock(side_effect=[Exception("boom"), None])
        from fastapi import WebSocketDisconnect

        ws2 = make_mock_ws()
        clients.add(ws)
        clients.add(ws2)

        ws.receive_text.side_effect = [
            '{"event": "bad"}',
            WebSocketDisconnect(),
        ]
        await receive_loop(ws, handler)
        # broadcast에서 error 메시지가 전송되었는지 확인
        found_error = False
        for call in ws2.send_text.call_args_list:
            data = json.loads(call[0][0])
            if data.get("type") == "error":
                found_error = True
        assert found_error
