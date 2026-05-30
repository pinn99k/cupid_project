"""
FastAPI + WebSocket 엔트리.
- MJPEG 프레임 관리 (set_frame / get_frame / encode)
- AppState + reset_session()
- 대시보드 WebSocket 메시지 핸들러
- 세션 초기화 시 오디오/TTS/상태 일괄 리셋
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
    """_frame_loop에서 호출 — 최신 프레임 저장 (스레드 안전)."""
    global _latest_frame
    with _frame_lock:
        _latest_frame = frame.copy() if frame is not None else None


def get_frame():
    """AI 파이프라인용 — 최신 프레임 복사본 반환."""
    with _frame_lock:
        return _latest_frame.copy() if _latest_frame is not None else None


def _encode_frame():
    """최신 프레임을 JPEG로 인코딩."""
    with _frame_lock:
        frame = _latest_frame
    if frame is None:
        return None
    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buffer.tobytes() if ret else None


# ---------------------------------------------------------------------------
# 서버 상태 관리
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    current_stage: int = 1
    learning_active: bool = False
    session_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


app_state = AppState()
_voice_pipeline = None
_cancel_narration = lambda: None

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


def set_voice_pipeline(pipeline):
    """세션 리셋 대상 음성 파이프라인을 등록."""
    global _voice_pipeline
    _voice_pipeline = pipeline


def set_cancel_narration(callback):
    """세션 정지 시 자동 묘사를 취소할 콜백을 등록."""
    global _cancel_narration
    _cancel_narration = callback


# ---------------------------------------------------------------------------
# 세션 리셋 — 오디오/상태를 한 번에 정리
# ---------------------------------------------------------------------------
def reset_session():
    """세션 초기화: 오디오 정지+큐비우기, 상태 리셋.
    stop_learning, new_session 양쪽에서 호출."""
    app_state.learning_active = False
    app_state.current_stage = 1
    _cancel_narration()

    # Voice pipeline 히스토리 리셋
    if _voice_pipeline:
        _voice_pipeline.reset()

    # 오디오 리셋
    try:
        from ai_core.audio_manager import get_audio_manager
        am = get_audio_manager()
        am.stop(clear_queue=True)
    except Exception as e:
        print(f"[SERVER] 오디오 리셋 오류: {e}")


# ---------------------------------------------------------------------------
# 대시보드 메시지 핸들러
# ---------------------------------------------------------------------------
async def handle_dashboard_message(msg: dict):
    """대시보드에서 온 WebSocket 메시지 처리."""

    if "event" in msg:
        event = msg["event"]
        print(f"[SERVER] 이벤트 수신: {event}")

        if event == "start_learning":
            app_state.learning_active = True
            app_state.current_stage = msg.get("stage", 1)
            print(f"[SERVER] 학습 시작: Stage {app_state.current_stage}")
            await broadcast({
                "type": "ack",
                "event": "start_learning",
                "stage": app_state.current_stage,
            })

        elif event == "stop_learning":
            reset_session()
            print("[SERVER] 학습 중지 + 세션 리셋")
            await broadcast({
                "type": "ack",
                "event": "stop_learning",
                "stage": app_state.current_stage,
            })

        elif event == "new_session":
            reset_session()
            try:
                from ai_core.tts import get_tts_cache
                tts = get_tts_cache()
                tts.end_session()
                new_sid = f"session_{int(time.time())}"
                tts.start_session(new_sid)
                app_state.session_id = new_sid
                print(f"[SERVER] 새 세션: {new_sid}")
            except Exception as e:
                print(f"[SERVER] new_session TTS 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "new_session",
                "session_id": app_state.session_id,
                "stage": app_state.current_stage,
            })

        elif event == "clear_tts_cache":
            try:
                from ai_core.tts import get_tts_cache
                get_tts_cache().end_session()
                print("[SERVER] TTS 캐시 삭제")
            except Exception as e:
                print(f"[SERVER] clear_tts_cache 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "clear_tts_cache",
            })

        elif event == "fallback":
            try:
                from ai_core.audio_manager import PRIORITY_DANGER, PRIORITY_FALLBACK, get_audio_manager
                audio_file = msg.get("audio_file", "buffer_01.wav")
                urgent = audio_file.startswith("warn_")
                get_audio_manager().play(
                    audio_file,
                    priority=PRIORITY_DANGER if urgent else PRIORITY_FALLBACK,
                    interrupt=urgent,
                )
                print(f"[SERVER] Fallback 재생: {audio_file}")
            except Exception as e:
                print(f"[SERVER] fallback 오류: {e}")
            await broadcast({
                "type": "ack",
                "event": "fallback",
            })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await connect(ws, state_provider=get_state)
    await receive_loop(ws, handle_dashboard_message)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "stage": app_state.current_stage,
        "learning_active": app_state.learning_active,
    }


@app.get("/preflight")
async def preflight():
    from server.preflight import run_preflight

    return run_preflight()


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
    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
