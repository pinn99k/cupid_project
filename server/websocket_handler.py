"""
WebSocket 연결 핸들러.
- connect/disconnect: 클라이언트 관리
- broadcast: 전체 클라이언트에 메시지 송신
- receive_loop: 대시보드 이벤트 수신
"""

import json
from fastapi import WebSocket, WebSocketDisconnect

clients: set[WebSocket] = set()


async def connect(ws: WebSocket):
    """WebSocket 연결 수락."""
    await ws.accept()
    clients.add(ws)
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
    """대시보드 → 서버 이벤트 수신 루프."""
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            await handler(msg)
    except WebSocketDisconnect:
        await disconnect(ws)
