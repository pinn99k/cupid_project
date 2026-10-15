"""반이중 STT/TTS WebSocket 통합 테스트 스크립트."""
import asyncio
import json
import time
import websockets


async def test_halfduplex():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        # 1. 초기 상태 수신
        init = json.loads(await ws.recv())
        print(f"[1] init_state: stage={init.get('stage')}, learning={init.get('learning_active')}")
        assert init["type"] == "init_state", f"Expected init_state, got {init['type']}"

        # 2. start_learning (Stage 1 = 수용)
        await ws.send(json.dumps({"event": "start_learning", "stage": 1}))
        ack = json.loads(await ws.recv())
        print(f"[2] start_learning ack: stage={ack.get('stage')}")
        assert ack["type"] == "ack" and ack["event"] == "start_learning"

        # 3. STT 텍스트 전송 (반이중 테스트 핵심)
        await ws.send(json.dumps({"stt_text": "안녕하세요 시아"}))

        # 4. 응답 메시지들 순서 확인
        received = []
        deadline = time.time() + 30
        expected_types = {"user_stt", "stt_response", "tts_start", "tts_done"}
        seen = set()

        while time.time() < deadline and seen != expected_types:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                received.append(msg)
                seen.add(msg["type"])
                print(f"[4-{len(received)}] {msg['type']}: {msg.get('message', '')[:50]}")
            except asyncio.TimeoutError:
                print(f"[TIMEOUT] 10s timeout. seen={seen}")
                break

        # 5. 순서 검증
        types = [m["type"] for m in received]
        print(f"\n[결과] 수신 순서: {types}")

        if "user_stt" in types:
            print("[PASS] user_stt 수신됨")
        else:
            print("[FAIL] user_stt 없음")

        if "tts_start" in types and "tts_done" in types:
            start_idx = types.index("tts_start")
            done_idx = types.index("tts_done")
            if start_idx < done_idx:
                print("[PASS] tts_start -> tts_done 순서 정상")
            else:
                print("[FAIL] tts_done이 tts_start보다 먼저 옴")

        if "stt_response" in types:
            resp = next(m for m in received if m["type"] == "stt_response")
            print(f"[PASS] LLM 응답: {resp['message'][:80]}...")
        else:
            print("[WARN] stt_response 없음 (LLM 호출 실패 가능)")

        # 6. 세션 리셋
        await ws.send(json.dumps({"event": "stop_learning"}))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print(f"\n[6] stop_learning ack: stage={ack.get('stage')}")

        print("\n=== 반이중 STT/TTS 통합 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(test_halfduplex())
