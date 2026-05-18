"""
Step 1-8 테스트: FastAPI 서버 + WebSocket 핸들러
실행: python tests/test_step1_8_server.py
하드웨어 불필요 — httpx + WebSocket mock 사용.
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


def test_server_structure():
    """서버 모듈 구조 테스트."""
    print("=" * 50)
    print("Step 1-8a: 서버 구조 테스트")
    print("=" * 50)

    # Case 1: FastAPI app import
    from server.main_server import app, current_stage, learning_active
    assert app is not None, "FastAPI app이 None이면 안 됨"
    print("[PASS] Case 1: FastAPI app import 성공")

    # Case 2: 초기 상태
    assert current_stage == 1, f"초기 stage는 1이어야 함: {current_stage}"
    assert learning_active is False, f"초기 learning_active는 False: {learning_active}"
    print("[PASS] Case 2: 초기 상태 (stage=1, learning=False)")

    # Case 3: CORS 미들웨어 확인
    middlewares = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middlewares, f"CORS 미들웨어 누락: {middlewares}"
    print("[PASS] Case 3: CORS 미들웨어 등록 확인")

    # Case 4: /health 엔드포인트 존재
    routes = [r.path for r in app.routes]
    assert "/health" in routes, f"/health 라우트 누락: {routes}"
    print("[PASS] Case 4: /health 엔드포인트 존재")

    # Case 5: /ws 엔드포인트 존재
    assert "/ws" in routes, f"/ws 라우트 누락: {routes}"
    print("[PASS] Case 5: /ws WebSocket 엔드포인트 존재")

    print()


def test_websocket_handler():
    """WebSocket 핸들러 구조 테스트."""
    print("=" * 50)
    print("Step 1-8b: WebSocket 핸들러 테스트")
    print("=" * 50)

    from server.websocket_handler import clients, connect, disconnect, broadcast

    # Case 1: clients 초기 상태
    assert isinstance(clients, set), f"clients는 set이어야 함: {type(clients)}"
    print(f"[PASS] Case 1: clients set (현재 {len(clients)}개)")

    # Case 2: broadcast — 클라이언트 없을 때 에러 없이 동작
    async def _test_broadcast_empty():
        await broadcast({"type": "test", "message": "hello"})
    asyncio.run(_test_broadcast_empty())
    print("[PASS] Case 2: broadcast() 빈 클라이언트 → 에러 없음")

    # Case 3: connect/disconnect 함수 존재
    assert asyncio.iscoroutinefunction(connect), "connect는 async 함수"
    assert asyncio.iscoroutinefunction(disconnect), "disconnect는 async 함수"
    assert asyncio.iscoroutinefunction(broadcast), "broadcast는 async 함수"
    print("[PASS] Case 3: connect/disconnect/broadcast 모두 async 함수")

    print()


def test_handle_dashboard_message():
    """대시보드 메시지 핸들러 테스트 (일부 이벤트)."""
    print("=" * 50)
    print("Step 1-8c: 대시보드 메시지 핸들러 테스트")
    print("=" * 50)

    import server.main_server as srv
    from server.main_server import handle_dashboard_message

    # 초기 상태 리셋
    srv.current_stage = 1
    srv.learning_active = False

    # Case 1: start_learning 이벤트
    async def _test_start_learning():
        await handle_dashboard_message({
            "event": "start_learning",
            "stage": 2
        })
    asyncio.run(_test_start_learning())
    assert srv.learning_active is True, "start_learning 후 learning_active=True"
    assert srv.current_stage == 2, f"start_learning stage=2: {srv.current_stage}"
    print("[PASS] Case 1: start_learning → stage=2, learning=True")

    # Case 2: stop_learning 이벤트
    async def _test_stop_learning():
        await handle_dashboard_message({"event": "stop_learning"})
    asyncio.run(_test_stop_learning())
    assert srv.learning_active is False, "stop_learning 후 learning_active=False"
    print("[PASS] Case 2: stop_learning → learning=False")

    # Case 3: Stage 3로 변경
    async def _test_stage3():
        await handle_dashboard_message({
            "event": "start_learning",
            "stage": 3
        })
    asyncio.run(_test_stage3())
    assert srv.current_stage == 3, f"Stage 3으로 변경: {srv.current_stage}"
    print("[PASS] Case 3: start_learning stage=3")

    # 리셋
    srv.current_stage = 1
    srv.learning_active = False

    print()


def test_health_endpoint():
    """Health 엔드포인트 응답 테스트."""
    print("=" * 50)
    print("Step 1-8d: Health 엔드포인트 테스트")
    print("=" * 50)

    from server.main_server import health
    result = asyncio.run(health())
    assert result["status"] == "ok", f"status 오류: {result['status']}"
    assert "stage" in result, "stage 필드 누락"
    assert "learning_active" in result, "learning_active 필드 누락"
    print(f"[PASS] Case 1: /health → {json.dumps(result)}")

    print()


if __name__ == "__main__":
    test_server_structure()
    test_websocket_handler()
    test_handle_dashboard_message()
    test_health_endpoint()
    print(f"[결과] Step 1-8 PASS — 서버/WebSocket/핸들러/Health 모두 통과")
