"""
SIA MVP 메인 실행 파일.
- detection_loop: YOLO 감지 → 위험 판단 → 오디오/LLM (비블로킹)
- FastAPI 서버 시작 + WebSocket
실행: python main.py
"""

import asyncio
import time
import cv2
import uvicorn

from ai_core.vision import load_model, detect, enrich
from ai_core.danger import judge
from ai_core.audio_manager import get_audio_manager
from ai_core.llm_client import init as llm_init
from ai_core.narration import narrate_async
from ai_core.tts import get_tts_cache
from server.main_server import app
from server.websocket_handler import broadcast
from server.config import SERVER_HOST, SERVER_PORT
from utils.latency_logger import log, elapsed

# ---------------------------------------------------------------------------
# P0 #9: 웹캠 복구 상수
# ---------------------------------------------------------------------------
MAX_WEBCAM_RETRIES = 5
WEBCAM_RETRY_DELAY = 3.0  # seconds
MAX_FRAME_FAILS = 30       # 연속 프레임 실패 허용 횟수

# 감지 루프 태스크 참조 (shutdown 시 cancel 용)
_detection_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# P0 #9: 웹캠 연결 헬퍼
# ---------------------------------------------------------------------------
async def _open_camera() -> cv2.VideoCapture | None:
    """웹캠 연결 시도. 실패 시 재시도 후 None 반환."""
    for attempt in range(1, MAX_WEBCAM_RETRIES + 1):
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print(f"[MAIN] 웹캠 연결 성공 (시도 {attempt})")
            return cap
        print(f"[MAIN] 웹캠 연결 실패 (시도 {attempt}/{MAX_WEBCAM_RETRIES})")
        cap.release()
        await asyncio.sleep(WEBCAM_RETRY_DELAY)
    return None


# ---------------------------------------------------------------------------
# P1 #6: 백그라운드 태스크 에러 콜백
# ---------------------------------------------------------------------------
def _task_done_callback(task: asyncio.Task):
    """백그라운드 태스크 완료/에러 콜백. 예외를 로깅한다."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        print(f"[MAIN] 백그라운드 태스크 오류: {type(exc).__name__}: {exc}")


async def detection_loop():
    """메인 감지 루프. 30fps 제한, LLM은 비블로킹 태스크로 분리."""
    # P0 #9: 웹캠 연결 — 실패 시 graceful 종료
    cap = await _open_camera()
    if cap is None:
        print("[MAIN] 웹캠 연결 불가. 감지 루프 비활성화 (대화 모드만 가능)")
        await broadcast({
            "type": "error",
            "message": "웹캠 연결 실패. Stage 1(대화) 모드만 가능합니다.",
        })
        return

    audio = get_audio_manager()
    tts = get_tts_cache()

    # main_server의 상태를 참조하기 위해 import
    import server.main_server as srv

    fail_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # P0 #9: 연속 프레임 실패 → 웹캠 재연결
                fail_count += 1
                if fail_count >= MAX_FRAME_FAILS:
                    print("[MAIN] 프레임 읽기 연속 실패. 웹캠 재연결 시도...")
                    cap.release()
                    cap = await _open_camera()
                    if cap is None:
                        print("[MAIN] 웹캠 재연결 실패. 감지 루프 종료.")
                        await broadcast({
                            "type": "error",
                            "message": "웹캠 재연결 실패. 감지 루프가 종료되었습니다.",
                        })
                        return
                    fail_count = 0
                await asyncio.sleep(0.1)
                continue
            fail_count = 0

            # Stage 1에서는 YOLO 비활성
            if srv.current_stage == 1:
                await asyncio.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            log("detect_start")
            # P1: YOLO detect를 스레드로 — 이벤트 루프 블로킹 방지
            dets = await asyncio.to_thread(detect, frame)
            enriched = enrich(dets, w, h)
            log("detect_end")

            # 위험 판단 (Stage 3 전용)
            danger = judge(enriched, srv.current_stage)
            if danger:
                log("danger_detected")
                audio.play(danger["audio_file"], interrupt=True)
                await broadcast({
                    "type": "danger",
                    "object": danger["object"],
                    "direction": danger["direction"],
                    "distance_cm": danger["distance_cm"],
                    "message": f"위험: {danger['object']}",
                    "stage": srv.current_stage,
                    "audio_file": danger["audio_file"],
                    "timestamp": int(time.time() * 1000)
                })
                elapsed("detect_start", "danger_detected")
                await asyncio.sleep(1)
                continue

            # 학습 모드: LLM 공간 묘사 (비블로킹 태스크)
            if srv.learning_active and len(enriched["objects"]) > 0:
                # P1 #6: 에러 콜백 등록
                task = asyncio.create_task(
                    _handle_narration(enriched, tts, audio, srv.current_stage)
                )
                task.add_done_callback(_task_done_callback)
                await asyncio.sleep(5)  # 5초 간격
            else:
                await asyncio.sleep(0.033)  # 30fps 제한
    finally:
        if cap is not None:
            cap.release()
        print("[MAIN] 카메라 해제")


async def _handle_narration(enriched, tts, audio, stage):
    """LLM + TTS를 백그라운드 태스크로 처리."""
    text = await narrate_async(enriched)
    if text:
        filepath = await tts.get_or_create(text)
        if filepath:
            audio.play_path(str(filepath))
        await broadcast({
            "type": "narration",
            "objects": enriched["objects"],
            "message": text,
            "stage": stage,
            "timestamp": int(time.time() * 1000)
        })
    else:
        audio.play("buffer_01.mp3")  # LLM 실패 → Fallback


@app.on_event("startup")
async def startup():
    """서버 시작 시 초기화."""
    global _detection_task
    print("[SIA] 초기화 시작...")
    load_model()
    llm_init()
    tts = get_tts_cache()
    tts.start_session(f"session_{int(time.time())}")
    _detection_task = asyncio.create_task(detection_loop())
    print("[SIA] 초기화 완료. 감지 루프 시작.")


@app.on_event("shutdown")
async def shutdown():
    """서버 종료 시 리소스 해제."""
    global _detection_task
    print("[SIA] 서버 종료 시작...")
    if _detection_task and not _detection_task.done():
        _detection_task.cancel()
        try:
            await _detection_task
        except asyncio.CancelledError:
            pass
    # TTS 세션 종료
    try:
        tts = get_tts_cache()
        tts.end_session()
    except Exception as e:
        print(f"[SIA] TTS 세션 종료 오류: {e}")
    print("[SIA] 서버 종료 완료.")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
