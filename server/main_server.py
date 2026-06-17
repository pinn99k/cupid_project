"""
FastAPI + WebSocket 엔트리.
- MJPEG 프레임 관리 (set_frame / get_frame / encode)
- AppState + reset_session()
- 대시보드 WebSocket 메시지 핸들러
- 세션 초기화 시 오디오/TTS/상태 일괄 리셋
"""

import copy
import time
import threading
import asyncio as _asyncio
from collections import deque
from dataclasses import dataclass, asdict

import cv2
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ai_core.audio_manager import get_audio_manager
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
# 최신 장면 슬롯 (Unit 3) — _ai_loop이 만든 enriched를 저장, 음성 VQA가 읽음
# 규칙: 최신 1개 슬롯 + 락 + copy 반환 (_latest_frame과 동형, shared_resources.md §1)
# YOLO 재실행 금지 — scene_provider는 이 슬롯을 읽기만 한다.
# ---------------------------------------------------------------------------
_latest_scene = None          # enriched dict
_latest_scene_ts = 0.0        # 갱신 시각(ms)
_scene_history = deque(maxlen=5)
_scene_lock = threading.Lock()


def set_scene(enriched: dict):
    """_ai_loop에서 호출 — 최신 장면 저장 (스레드 안전, 단일 writer)."""
    global _latest_scene, _latest_scene_ts
    with _scene_lock:
        _latest_scene = copy.deepcopy(enriched) if enriched is not None else None
        _latest_scene_ts = time.time() * 1000
        if _latest_scene is not None:
            _scene_history.append(copy.deepcopy(_latest_scene))


def get_scene() -> tuple[dict | None, float]:
    """음성 VQA용 — 최근 5프레임 다수결 장면을 즉시 반환. 없으면 (None, 0.0)."""
    with _scene_lock:
        if _latest_scene is None:
            return None, 0.0
        return _majority_scene_locked(), _latest_scene_ts


def _majority_scene_locked() -> dict:
    """최근 3~5프레임 객체 방향을 다수결로 안정화. _scene_lock 안에서만 호출."""
    scenes = list(_scene_history)[-5:]
    if not scenes:
        return copy.deepcopy(_latest_scene)

    votes: dict[tuple[str, str], dict] = {}
    latest_keys = set()
    for idx, scene in enumerate(scenes):
        seen_in_frame = set()
        for obj in scene.get("objects", []):
            if not isinstance(obj, dict):
                continue
            label = str(obj.get("label", ""))
            direction = str(obj.get("direction", ""))
            if not label or direction not in {"left", "center", "right"}:
                continue
            key = (label, direction)
            if key in seen_in_frame:
                continue
            seen_in_frame.add(key)
            if key not in votes:
                votes[key] = {"count": 0, "obj": copy.deepcopy(obj)}
            votes[key]["count"] += 1
            votes[key]["obj"] = copy.deepcopy(obj)
            if idx == len(scenes) - 1:
                latest_keys.add(key)

    stable = [
        data["obj"]
        for key, data in votes.items()
        if data["count"] >= 2 or (len(scenes) < 3 and key in latest_keys)
    ]
    if not stable:
        stable = [
            copy.deepcopy(obj)
            for obj in (_latest_scene or {}).get("objects", [])
            if isinstance(obj, dict)
        ]

    result = copy.deepcopy(_latest_scene)
    result["objects"] = stable
    result["scene_history_frames"] = len(scenes)
    return result


def clear_scene():
    """장면 슬롯 초기화 — Stage 전환·세션 리셋 시 호출.
    이전 Stage 2/3 의 YOLO 탐지 결과가 Stage 1 VQA 응답을 오염시키는 것을 방지."""
    global _latest_scene, _latest_scene_ts
    with _scene_lock:
        if _latest_scene is not None:
            print("[SCENE] 잔류 장면 초기화 (이전 탐지 결과 제거)")
        _latest_scene = None
        _latest_scene_ts = 0.0
        _scene_history.clear()


# ---------------------------------------------------------------------------
# 서버 상태 관리
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    current_stage: int = 1
    learning_active: bool = False
    session_id: str = ""
    question_count: int = 0  # "시아야" 질문-답변 성공 횟수 (voice task만 증가 = 단일 writer)

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
    from server.config import get_runtime_language
    return {
        "stage": app_state.current_stage,
        "learning_active": app_state.learning_active,
        "session_id": app_state.session_id,
        "question_count": app_state.question_count,
        "language": get_runtime_language(),
        "recording_state": (
            getattr(_voice_pipeline, "recording_state", "idle")
            if _voice_pipeline else "idle"
        ),
    }


def increment_question_count() -> int:
    """질문-답변 성공 시 호출 (voice task 단일 writer). 갱신된 값 반환."""
    app_state.question_count += 1
    return app_state.question_count


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
    app_state.question_count = 0
    _cancel_narration()

    # 장면 슬롯 초기화 — 이전 Stage 탐지 결과가 VQA 응답을 오염시키지 않도록
    clear_scene()

    # Voice pipeline 히스토리 리셋
    if _voice_pipeline:
        _voice_pipeline.reset()

    # 오디오 리셋
    try:
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
            stage = msg.get("stage", 1)
            app_state.learning_active = True
            app_state.current_stage = stage
            print(f"[SERVER] 학습 시작: Stage {stage}")
            # 음성 인식: 모든 단계에서 ON.
            #  수용(1)도 시아와 대화하며 친해지는 단계라 음성 ON(일반 대화만, scene 없음).
            #  방향(2)+ 는 scene 기반 VQA까지. (이전엔 stage1=음성 OFF였으나 대화 가능하게 변경)
            if _voice_pipeline:
                _voice_pipeline.set_stage(stage)  # DEMO_MODE는 수용(1)만 적용
                _voice_pipeline.start()
            await broadcast({
                "type": "ack",
                "event": "start_learning",
                "stage": app_state.current_stage,
            })

        elif event == "stop_learning":
            reset_session()
            # 학습 중지 = 마이크 청취 일시 중지
            if _voice_pipeline:
                _voice_pipeline.stop_listening()
            print("[SERVER] 학습 중지 + 세션 리셋")
            await broadcast({
                "type": "ack",
                "event": "stop_learning",
                "stage": app_state.current_stage,
            })
            await broadcast({
                "type": "recording_state",
                "state": "idle",
                "timestamp": int(time.time() * 1000),
            })

        elif event == "start_pipeline":
            # 대시보드 마이크 시작 버튼 → 청취 활성화
            if _voice_pipeline:
                _voice_pipeline.start()
            print("[SERVER] 파이프라인 청취 활성화")
            await broadcast({"type": "ack", "event": "start_pipeline"})

        elif event == "stop_pipeline":
            # 대시보드 마이크 정지 버튼 → 청취 일시 중지
            if _voice_pipeline:
                _voice_pipeline.stop_listening()
            print("[SERVER] 파이프라인 청취 일시 중지")
            await broadcast({"type": "ack", "event": "stop_pipeline"})

        elif event == "start_recording":
            ok = False
            if _voice_pipeline:
                ok = await _voice_pipeline.on_manual_start_recording()
            await broadcast({
                "type": "ack",
                "event": "start_recording",
                "ok": ok,
            })

        elif event == "stop_recording":
            ok = False
            if _voice_pipeline:
                ok = await _voice_pipeline.on_manual_stop_recording()
            await broadcast({
                "type": "ack",
                "event": "stop_recording",
                "ok": ok,
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
            await broadcast({
                "type": "recording_state",
                "state": "idle",
                "timestamp": int(time.time() * 1000),
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

        elif event == "set_language":
            from server.config import set_runtime_language
            lang = set_runtime_language(msg.get("language", "ko"))
            print(f"[SERVER] 언어 전환 → {lang} (STT/LLM/TTS 동시 적용)")
            await broadcast({
                "type": "language",
                "language": lang,
                "timestamp": int(time.time() * 1000),
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


@app.post("/api/toggle_recording")
@app.get("/api/toggle_recording")
async def toggle_recording():
    """수동 녹음 토글 (Hammerspoon 이어폰 가운데 버튼 등 외부 트리거용).
    현재 상태에 따라 start/stop 호출 — 화면 포커스와 무관하게 동작.
    백그라운드 프로세스 없음(=서버 안정성 영향 없는 단순 라우트)."""
    if not _voice_pipeline:
        return {"ok": False, "reason": "no_pipeline", "state": "idle"}
    state = getattr(_voice_pipeline, "recording_state", "idle")
    if state == "idle":
        ok = await _voice_pipeline.on_manual_start_recording()
        action = "start"
    elif state == "recording":
        ok = await _voice_pipeline.on_manual_stop_recording()
        action = "stop"
    else:
        ok, action = False, "ignored"
    new_state = getattr(_voice_pipeline, "recording_state", "idle")
    print(f"[HTTP] toggle_recording: {state} → {action}(ok={ok}) → {new_state}")
    return {"ok": ok, "action": action, "prev": state, "state": new_state}


@app.post("/api/toggle_language")
@app.get("/api/toggle_language")
async def toggle_language():
    """한국어 ↔ 영어 토글 (운영자용). STT 인식언어·LLM 응답언어·TTS 보이스가 함께 바뀐다.
    외부 트리거(단축키/버튼)에서도 쓸 수 있게 GET/POST 둘 다 허용."""
    from server.config import get_runtime_language, set_runtime_language
    cur = get_runtime_language()
    new = set_runtime_language("en" if cur == "ko" else "ko")
    await broadcast({
        "type": "language",
        "language": new,
        "timestamp": int(time.time() * 1000),
    })
    print(f"[HTTP] toggle_language: {cur} → {new}")
    return {"ok": True, "prev": cur, "language": new}


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
