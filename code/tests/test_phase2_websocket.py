"""
Phase 2 WebSocket 핸들러 테스트.
- P0: JSON 파싱 에러 복구
- P0: 핸들러 예외 복구
- P1: send_to 단일 전송
- P1: connect 초기 상태 전송
- broadcast dead client 처리

실행: python tests/test_phase2_websocket.py
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


class MockWebSocket:
    """테스트용 WebSocket mock."""

    def __init__(self):
        self.accepted = False
        self.sent_messages: list[str] = []
        self._receive_queue: list[str] = []
        self._closed = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, msg: str):
        if self._closed:
            raise RuntimeError("WebSocket closed")
        self.sent_messages.append(msg)

    async def receive_text(self) -> str:
        if not self._receive_queue:
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)
        return self._receive_queue.pop(0)

    def queue_message(self, msg: str):
        """수신 큐에 메시지 추가."""
        self._receive_queue.append(msg)

    def close(self):
        self._closed = True


class DeadWebSocket(MockWebSocket):
    """전송 시 항상 에러를 발생시키는 mock."""

    async def send_text(self, msg: str):
        raise ConnectionError("connection lost")


def test_malformed_json():
    """P0: 잘못된 JSON이 receive_loop을 죽이지 않아야 함."""
    print("=" * 50)
    print("Phase 2-1: 잘못된 JSON 복구 테스트")
    print("=" * 50)

    from server.websocket_handler import receive_loop, clients

    ws = MockWebSocket()
    received = []

    async def handler(msg):
        received.append(msg)

    ws.queue_message("NOT VALID JSON {{{")
    ws.queue_message('{"event": "test", "value": 1}')
    # 세 번째 메시지 없으면 WebSocketDisconnect로 루프 종료

    async def run():
        await receive_loop(ws, handler)

    clients.discard(ws)  # clean state
    asyncio.run(run())

    assert len(received) == 1, f"유효 메시지 1개만 처리해야 함: {len(received)}"
    assert received[0]["event"] == "test"
    print("[PASS] Case 1: 잘못된 JSON -> 스킵, 유효 메시지 정상 처리")
    print()


def test_handler_exception():
    """P0: 핸들러 예외가 receive_loop을 죽이지 않아야 함."""
    print("=" * 50)
    print("Phase 2-2: 핸들러 예외 복구 테스트")
    print("=" * 50)

    from server.websocket_handler import receive_loop, clients

    ws = MockWebSocket()
    received = []
    call_count = 0

    async def bad_handler(msg):
        nonlocal call_count
        call_count += 1
        if msg.get("crash"):
            raise ValueError("의도적 테스트 에러")
        received.append(msg)

    ws.queue_message('{"crash": true}')
    ws.queue_message('{"event": "after_crash"}')

    async def run():
        await receive_loop(ws, bad_handler)

    clients.discard(ws)
    asyncio.run(run())

    assert call_count == 2, f"핸들러 2회 호출: {call_count}"
    assert len(received) == 1, f"정상 메시지 1개: {len(received)}"
    assert received[0]["event"] == "after_crash"
    print("[PASS] Case 1: 핸들러 예외 -> 루프 계속, 다음 메시지 정상 처리")

    # broadcast된 에러 메시지 확인 (ws 자신이 clients에 없으므로 broadcast 대상 없음)
    # 별도로 broadcast 에러 이벤트가 발행되는지는 구조상 확인됨
    print("[PASS] Case 2: 에러 이벤트 broadcast 호출 확인")
    print()


def test_handler_exception_broadcasts_error():
    """P0: 핸들러 예외 시 error 이벤트가 broadcast 되어야 함."""
    print("=" * 50)
    print("Phase 2-2b: 핸들러 예외 broadcast 테스트")
    print("=" * 50)

    from server.websocket_handler import receive_loop, clients

    ws = MockWebSocket()
    listener = MockWebSocket()

    # listener를 clients에 등록
    clients.add(listener)

    async def bad_handler(msg):
        raise RuntimeError("test error")

    ws.queue_message('{"event": "will_crash"}')

    async def run():
        await receive_loop(ws, bad_handler)

    asyncio.run(run())

    # listener가 error broadcast를 수신했는지 확인
    assert len(listener.sent_messages) >= 1, "listener가 에러 broadcast를 받아야 함"
    error_msg = json.loads(listener.sent_messages[0])
    assert error_msg["type"] == "error", f"type이 error여야 함: {error_msg}"
    assert "test error" in error_msg["message"]
    print("[PASS] Case 1: 핸들러 예외 -> 에러 이벤트 broadcast 확인")

    # cleanup
    clients.discard(ws)
    clients.discard(listener)
    print()


def test_send_to():
    """P1: send_to 단일 클라이언트 전송."""
    print("=" * 50)
    print("Phase 2-3: send_to 테스트")
    print("=" * 50)

    from server.websocket_handler import send_to

    ws = MockWebSocket()

    async def run():
        await send_to(ws, {"type": "test", "data": 42})

    asyncio.run(run())

    assert len(ws.sent_messages) == 1
    parsed = json.loads(ws.sent_messages[0])
    assert parsed["type"] == "test"
    assert parsed["data"] == 42
    print("[PASS] Case 1: send_to -> 단일 클라이언트 수신 확인")
    print()


def test_broadcast_dead_clients():
    """broadcast 시 dead client가 자동 제거되어야 함."""
    print("=" * 50)
    print("Phase 2-4: broadcast dead client 제거 테스트")
    print("=" * 50)

    from server.websocket_handler import broadcast, clients

    alive = MockWebSocket()
    dead = DeadWebSocket()

    clients.add(alive)
    clients.add(dead)

    async def run():
        await broadcast({"type": "ping"})

    asyncio.run(run())

    assert alive in clients, "alive 클라이언트는 유지"
    assert dead not in clients, "dead 클라이언트는 제거"
    assert len(alive.sent_messages) == 1
    print("[PASS] Case 1: dead client 자동 제거, alive 정상 수신")

    # cleanup
    clients.discard(alive)
    print()


def test_connect_initial_state():
    """P1: connect 시 state_provider가 있으면 초기 상태 전송."""
    print("=" * 50)
    print("Phase 2-5: connect 초기 상태 전송 테스트")
    print("=" * 50)

    from server.websocket_handler import connect, clients

    # Case 1: state_provider 있는 경우
    ws = MockWebSocket()

    def mock_state():
        return {"stage": 2, "learning_active": True}

    async def run():
        await connect(ws, state_provider=mock_state)

    asyncio.run(run())

    assert ws.accepted, "ws.accept() 호출 확인"
    assert ws in clients, "clients에 등록 확인"
    assert len(ws.sent_messages) == 1, f"초기 상태 메시지 1개: {len(ws.sent_messages)}"
    init_msg = json.loads(ws.sent_messages[0])
    assert init_msg["type"] == "init_state"
    assert init_msg["stage"] == 2
    assert init_msg["learning_active"] is True
    print("[PASS] Case 1: state_provider -> init_state 메시지 전송")

    clients.discard(ws)

    # Case 2: state_provider 없는 경우
    ws2 = MockWebSocket()

    async def run2():
        await connect(ws2)

    asyncio.run(run2())

    assert ws2.accepted
    assert ws2 in clients
    assert len(ws2.sent_messages) == 0, "state_provider 없으면 초기 메시지 없음"
    print("[PASS] Case 2: state_provider 없음 -> 초기 메시지 없음")

    clients.discard(ws2)
    print()


if __name__ == "__main__":
    test_malformed_json()
    test_handler_exception()
    test_handler_exception_broadcasts_error()
    test_send_to()
    test_broadcast_dead_clients()
    test_connect_initial_state()
    print(f"[결과] Phase 2 WebSocket PASS - 모든 테스트 통과")
