"""
FastAPI + WebSocket 엔트리.
- 대시보드 WebSocket 연결 및 AI 파이프라인 오케스트레이션
- 세션 관리 (new_session, clear_tts_cache 이벤트 처리)
"""

import time
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.websocket_handler import connect, receive_loop, broadcast
from server.config import SERVER_HOST, SERVER_PORT

app = FastAPI(title="SIA MVP Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 상태
current_stage = 1
learning_active = False


async def handle_dashboard_message(msg: dict):
    """대시보드에서 온 WebSocket 메시지 처리."""
    global current_stage, learning_active

    if "event" in msg:
        event = msg["event"]
        print(f"[SERVER] 이벤트 수신: {event}")

        if event == "start_learning":
            learning_active = True
            current_stage = msg.get("stage", 1)
            print(f"[SERVER] 학습 시작: Stage {current_stage}")

        elif event == "stop_learning":
            learning_active = False
            print("[SERVER] 학습 중지")

        elif event == "new_session":
            # v2: 새 세션 → TTS 캐시 초기화
            from ai_core.tts import get_tts_cache
            tts = get_tts_cache()
            tts.end_session()
            tts.start_session(f"session_{int(time.time())}")
            print("[SERVER] 새 세션 시작")

        elif event == "clear_tts_cache":
            # v2: 수동 캐시 삭제
            from ai_core.tts import get_tts_cache
            get_tts_cache().end_session()
            print("[SERVER] TTS 캐시 삭제")

        elif event == "fallback":
            from ai_core.audio_manager import get_audio_manager
            audio_file = msg.get("audio_file", "buffer_01.mp3")
            get_audio_manager().play(audio_file)
            print(f"[SERVER] Fallback 재생: {audio_file}")

    elif "stt_text" in msg:
        # STT 텍스트 → LLM 대화 → TTS
        stt_text = msg["stt_text"]
        print(f"[SERVER] STT 수신: {stt_text}")

        from ai_core.narration import narrate_async
        from ai_core.tts import get_tts_cache
        from ai_core.audio_manager import get_audio_manager

        response = await narrate_async({
            "objects": [],
            "ultrasonic_cm": None,
            "ultrasonic_target": None
        })
        if response:
            tts = get_tts_cache()
            filepath = await tts.get_or_create(response)
            if filepath:
                get_audio_manager().play_path(str(filepath))
            await broadcast({
                "type": "stt_response",
                "message": response,
                "stage": current_stage,
                "timestamp": int(time.time() * 1000)
            })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 엔드포인트."""
    await connect(ws)
    await receive_loop(ws, handle_dashboard_message)


@app.get("/health")
async def health():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "stage": current_stage,
        "learning_active": learning_active
    }
