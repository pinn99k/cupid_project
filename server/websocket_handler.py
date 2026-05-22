"""
WebSocket 연결 핸들러.
- connect/disconnect: 클라이언트 관리
- broadcast: 전체 클라이언트에 메시지 송신
- send_to: 단일 클라이언트에 메시지 송신
- receive_loop: 대시보드 이벤트 수신 (에러 복구 포함)
"""

import json
import traceback
from typing import Callable, Optional

from fastapi import WebSocket, WebSocketDisconnect

clients: set[WebSocket] = set()


async def send_to(ws: WebSocket, data: dict):
    """단일 클라이언트에 메시지 전송."""
    try:
        msg = json.dumps(data, ensure_ascii=False)
        await ws.send_text(msg)
    except Exception:
        clients.discard(ws)


async def connect(ws: WebSocket, state_provider: Optional[Callable] = None):
    """WebSocket 연결 수락 및 초기 상태 전송."""
    await ws.accept()
    clients.add(ws)
    if state_provider:
        state = state_provider()
        await send_to(ws, {"type": "init_state", **state})
    print(f"[WS] 클라이언트 연결 (총 {len(clients)}개)")


async def disconnect(ws: WebSocket):
    """WebSocket 연결 해제."""
    clients.discard(ws)
    print(f"[WS] 클라이언트 해제 (총 {len(clients)}개)")


async def broadcast(data: dict):
    """모든 연결된 클라이언트에 메시지 전송."""
    msg = json.dumps(data, ensure_ascii=False)
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            clients.discard(ws)


async def receive_loop(ws: WebSocket, handler):
    """대시보드 -> 서버 이벤트 수신 루프 (에러 복구 포함)."""
    try:
        while True:
            data = await ws.receive_text()

            # P0: JSON 파싱 에러 처리
            try:
                msg = json.loads(data)
            except json.JSONDecodeError as e:
                print(f"[WS] JSON 파싱 에러: {e}")
                continue

            # P0: 핸들러 예외 처리
            try:
                await handler(msg)
            except Exception as e:
                print(f"[WS] 핸들러 에러: {e}")
                traceback.print_exc()
                await broadcast({
                    "type": "error",
                    "message": f"handler error: {e}"
                })
    except WebSocketDisconnect:
        await disconnect(ws)
