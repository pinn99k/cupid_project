"""
FastAPI + WebSocket 엔트리.
- 대시보드 WebSocket 연결 및 AI 파이프라인 오케스트레이션
- 세션 관리 (new_session, clear_tts_cache 이벤트 처리)
- AppState 데이터클래스로 서버 상태 관리
"""

import time
import threading
import asyncio as _asyncio
from dataclasses import dataclass, asdict

import cv2
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from server.websocket_handler import connect, receive_loop, broadcast
from server.config import SERVER_HOST, SERVER_PORT


# ---------------------------------------------------------------------------
# MJPEG 프레임 저장 (스레드 안전)
# ---------------------------------------------------------------------------
_latest_frame = None
_frame_lock = threading.Lock()


def set_frame(frame):
    """detection_loop에서 호출 - 최신 프레임 저장 (스레드 안전)."""
    global _latest_frame
    with _frame_lock:
        _latest_frame = frame.copy() if frame is not None else None


def _encode_frame():
    """최신 프레임을 JPEG로 인코딩."""
    with _frame_lock:
        frame = _latest_frame
    if frame is None:
        return None
    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buffer.tobytes() if ret else None


# ---------------------------------------------------------------------------
# P2: 상태를 dataclass로 관리
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    current_stage: int = 1
    learning_active: bool = False
    session_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


app_state = AppState()

# 하위 호환: 모듈 레벨 변수 참조용 (기존 테스트 지원)
current_stage = app_state.current_stage
learning_active = app_state.learning_active

app = FastAPI(title="SIA MVP Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_state() -> dict:
    """현재 서버 상태를 dict로 반환 (WebSocket 초기 상태 전송용)."""
    return {
        "stage": app_state.current_stage,
        "learning_active": app_state.learning_active,
        "session_id": app_state.session_id,
    }


async def handle_dashboard_message(msg: dict):
    """대시보드에서 온 WebSocket 메시지 처리."""
    global current_stage, learning_active

    if "event" in msg:
        event = msg["event"]
        print(f"[SERVER] 이벤트 수신: {event}")

        if event == "start_learning":
            app_state.learning_active = True
            app_state.current_stage = msg.get("stage", 1)
            # 하위 호환
            current_stage = app_state.current_stage
            learning_active = app_state.learning_active
            print(f"[SERVER] 학습 시작: Stage {app_state.current_stage}")
            # P1: ack broadcast
            await broadcast({
                "type": "ack",
                "event": "start_learning",
                "stage": app_state.current_stage,
            })

        elif event == "stop_learning":
            app_state.learning_active = False
            # 하위 호환
            learning_active = app_state.learning_active
            print("[SERVER] 학습 중지")
            await broadcast({
                "type": "ack",
                "event": "stop_learning",
            })

        elif event == "new_session":
            # P1: try/except — ai_core 실패 시 크래시 방지
            try:
                from ai_core.tts import get_tts_cache
                tts = get_tts_cache()
                tts.end_session()
                new_sid = f"session_{int(time.time())}"
                tts.start_session(new_sid)
                app_state.session_id = new_sid
                print(f"[SERVER] 새 세션 시작: {new_sid}")
            except Exception as e:
                print(f"[SERVER] new_session 처리 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "new_session",
                "session_id": app_state.session_id,
            })

        elif event == "clear_tts_cache":
            try:
                from ai_core.tts import get_tts_cache
                get_tts_cache().end_session()
                print("[SERVER] TTS 캐시 삭제")
            except Exception as e:
                print(f"[SERVER] clear_tts_cache 처리 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "clear_tts_cache",
            })

        elif event == "fallback":
            try:
                from ai_core.audio_manager import get_audio_manager
                audio_file = msg.get("audio_file", "buffer_01.mp3")
                get_audio_manager().play(audio_file)
                print(f"[SERVER] Fallback 재생: {audio_file}")
            except Exception as e:
                print(f"[SERVER] fallback 처리 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "fallback",
            })

    elif "stt_text" in msg:
        # P0 #10 fix: STT 텍스트를 LLM에 직접 전달 (대화 모드)
        stt_text = msg["stt_text"]
        if not stt_text or not stt_text.strip():
            return  # 빈 텍스트 무시

        print(f"[SERVER] STT 수신: {stt_text}")

        try:
            from ai_core.llm_client import call_async, SYSTEM_PROMPT
            from ai_core.tts import get_tts_cache
            from ai_core.audio_manager import get_audio_manager

            response = await call_async(SYSTEM_PROMPT, stt_text)
            if response:
                tts = get_tts_cache()
                filepath = await tts.get_or_create(response)
                if filepath:
                    get_audio_manager().play_path(str(filepath))
                await broadcast({
                    "type": "stt_response",
                    "message": response,
                    "stage": app_state.current_stage,
                    "timestamp": int(time.time() * 1000),
                })
        except Exception as e:
            print(f"[SERVER] STT 처리 오류: {e}")
            await broadcast({
                "type": "error",
                "message": f"stt processing error: {e}",
            })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 엔드포인트."""
    await connect(ws, state_provider=get_state)
    await receive_loop(ws, handle_dashboard_message)


@app.get("/health")
async def health():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "stage": app_state.current_stage,
        "learning_active": app_state.learning_active,
    }


# ---------------------------------------------------------------------------
# MJPEG 비디오 스트림
# ---------------------------------------------------------------------------
async def _generate_mjpeg():
    while True:
        jpeg = await _asyncio.to_thread(_encode_frame)
        if jpeg:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
        await _asyncio.sleep(0.042)  # ~24fps


@app.get("/video_feed")
async def video_feed():
    """MJPEG 비디오 스트림 - 대시보드 카메라 뷰용."""
    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
