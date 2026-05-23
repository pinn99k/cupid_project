"""
SIA MVP 메인 실행 파일.
- _frame_loop: 웹캠 프레임 캡처 전용 (30fps, MJPEG 공급)
- _ai_loop: YOLO 감지 → 위험 판단 → LLM 묘사 (독립 속도)
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
from server.main_server import app, set_frame, get_frame
from server.websocket_handler import broadcast
from server.config import (SERVER_HOST, SERVER_PORT, WEBCAM_INDEX,
                           MIC_DEVICE_INDEX, VAD_SILENCE_THRESHOLD,
                           VAD_SILENCE_DURATION, VAD_MAX_DURATION, STT_LANGUAGE)
from server.mic import MicCapture
from server.stt import STTClient
from server.voice_pipeline import VoicePipeline
from utils.latency_logger import log, elapsed

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
MAX_WEBCAM_RETRIES = 5
WEBCAM_RETRY_DELAY = 3.0        # seconds
MAX_FRAME_FAILS = 30             # 연속 프레임 실패 허용 횟수
DANGER_COOLDOWN = 5.0            # 같은 객체 위험 재경고 간격 (초)
NARRATION_INTERVAL = 5.0         # LLM 공간 묘사 간격 (초)

# shutdown 시 cancel 용
_frame_task: asyncio.Task | None = None
_ai_task: asyncio.Task | None = None
_voice_task: asyncio.Task | None = None

# TTS 전역 Lock (voice pipeline + narration/danger 공유)
_tts_lock = asyncio.Lock()

# VoicePipeline 인스턴스 (main_server.py에서 import 가능)
voice_pipeline: VoicePipeline | None = None


# ---------------------------------------------------------------------------
# 웹캠 연결 헬퍼
# ---------------------------------------------------------------------------
async def _open_camera() -> cv2.VideoCapture | None:
    """웹캠 연결 시도. 실패 시 재시도 후 None 반환."""
    for attempt in range(1, MAX_WEBCAM_RETRIES + 1):
        cap = cv2.VideoCapture(WEBCAM_INDEX)
        if cap.isOpened():
            print(f"[MAIN] 웹캠 연결 성공 (시도 {attempt})")
            return cap
        print(f"[MAIN] 웹캠 연결 실패 (시도 {attempt}/{MAX_WEBCAM_RETRIES})")
        cap.release()
        await asyncio.sleep(WEBCAM_RETRY_DELAY)
    return None


# ---------------------------------------------------------------------------
# 백그라운드 태스크 에러 콜백
# ---------------------------------------------------------------------------
def _task_done_callback(task: asyncio.Task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        print(f"[MAIN] 백그라운드 태스크 오류: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 프레임 캡처 루프 (프론트 MJPEG 공급 전용, 항상 30fps)
# ---------------------------------------------------------------------------
async def _frame_loop():
    """웹캠 → set_frame 전용. AI와 독립적으로 동작."""
    cap = await _open_camera()
    if cap is None:
        print("[MAIN] 웹캠 연결 불가. 프레임 루프 비활성화.")
        await broadcast({
            "type": "error",
            "message": "웹캠 연결 실패. 카메라 화면을 사용할 수 없습니다.",
        })
        return

    fail_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                fail_count += 1
                if fail_count >= MAX_FRAME_FAILS:
                    print("[MAIN] 프레임 읽기 연속 실패. 웹캠 재연결 시도...")
                    cap.release()
                    cap = await _open_camera()
                    if cap is None:
                        print("[MAIN] 웹캠 재연결 실패. 프레임 루프 종료.")
                        await broadcast({
                            "type": "error",
                            "message": "웹캠 재연결 실패.",
                        })
                        return
                    fail_count = 0
                await asyncio.sleep(0.033)
                continue
            fail_count = 0
            set_frame(frame)
            await asyncio.sleep(0.033)  # ~30fps
    finally:
        if cap is not None:
            cap.release()
        print("[MAIN] 카메라 해제")


# ---------------------------------------------------------------------------
# AI 파이프라인 루프 (YOLO + 위험 + LLM, 자기 속도)
# ---------------------------------------------------------------------------
async def _ai_loop():
    """프레임을 get_frame()에서 가져와 YOLO/위험/LLM 처리.
    _frame_loop과 독립적으로 동작하므로 프론트 FPS에 영향 없음."""
    import server.main_server as srv

    audio = get_audio_manager()
    tts = get_tts_cache()

    last_narration_time = 0.0
    last_danger_time = 0.0
    last_danger_obj = None

    while True:
        # Stage 1은 대화 전용 — AI 분석 불필요
        if srv.app_state.current_stage == 1:
            await asyncio.sleep(0.5)
            continue

        # 최신 프레임 가져오기 (프레임 루프가 공급)
        frame = get_frame()
        if frame is None:
            await asyncio.sleep(0.1)
            continue

        h, w = frame.shape[:2]
        log("detect_start")
        dets = await asyncio.to_thread(detect, frame)
        enriched = enrich(dets, w, h)
        log("detect_end")

        now = time.time()

        # 위험 판단 (Stage 3 전용) — 쿨다운 + 같은 객체 중복 억제
        danger = judge(enriched, srv.app_state.current_stage)
        if danger:
            same_obj = (danger["object"] == last_danger_obj)
            if not same_obj or (now - last_danger_time) >= DANGER_COOLDOWN:
                last_danger_obj = danger["object"]
                last_danger_time = now
                log("danger_detected")
                async with _tts_lock:
                    await broadcast({"type": "tts_start"})
                    audio.play(danger["audio_file"], interrupt=True)
                    await broadcast({
                        "type": "danger",
                        "object": danger["object"],
                        "direction": danger["direction"],
                        "distance_cm": danger["distance_cm"],
                        "message": f"위험: {danger['object']}",
                        "stage": srv.app_state.current_stage,
                        "audio_file": danger["audio_file"],
                        "timestamp": int(time.time() * 1000),
                    })
                    elapsed("detect_start", "danger_detected")
                    # 위험 오디오 재생 완료 대기 → STT 복귀
                    while await asyncio.to_thread(audio.is_playing):
                        await asyncio.sleep(0.2)
                    await broadcast({"type": "tts_done"})
            # 위험 감지 시에도 프레임은 계속 갱신됨 (별도 루프)
            await asyncio.sleep(0.5)
            continue

        # 공간 묘사 (시간 기반 쓰로틀 — sleep이 아니라 시각 비교)
        if srv.app_state.learning_active and len(enriched["objects"]) > 0:
            if (now - last_narration_time) >= NARRATION_INTERVAL:
                last_narration_time = now
                task = asyncio.create_task(
                    _handle_narration(enriched, tts, audio, srv.app_state.current_stage)
                )
                task.add_done_callback(_task_done_callback)

        await asyncio.sleep(0.1)  # AI 루프는 ~10fps면 충분


async def _handle_narration(enriched, tts, audio, stage):
    """LLM + TTS를 백그라운드 태스크로 처리. tts_lock으로 직렬화."""
    text = await narrate_async(enriched)
    if text:
        await broadcast({
            "type": "narration",
            "objects": enriched["objects"],
            "message": text,
            "stage": stage,
            "timestamp": int(time.time() * 1000),
        })
        async with _tts_lock:
            filepath = await tts.get_or_create(text)
            if filepath:
                await broadcast({"type": "tts_start"})
                audio.play_path(str(filepath))
                while await asyncio.to_thread(audio.is_playing):
                    await asyncio.sleep(0.2)
                await broadcast({"type": "tts_done"})
    else:
        async with _tts_lock:
            await broadcast({"type": "tts_start"})
            audio.play("buffer_01.mp3")
            while await asyncio.to_thread(audio.is_playing):
                await asyncio.sleep(0.2)
            await broadcast({"type": "tts_done"})


# ---------------------------------------------------------------------------
# 서버 생명주기
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    global _frame_task, _ai_task, _voice_task, voice_pipeline
    print("[SIA] 초기화 시작...")
    load_model()
    llm_init()
    tts = get_tts_cache()
    tts.start_session(f"session_{int(time.time())}")
    # 두 루프를 독립적으로 시작
    _frame_task = asyncio.create_task(_frame_loop())
    _ai_task = asyncio.create_task(_ai_loop())
    # VoicePipeline 초기화
    mic = MicCapture(
        device_index=MIC_DEVICE_INDEX,
        silence_threshold=VAD_SILENCE_THRESHOLD,
        silence_duration=VAD_SILENCE_DURATION,
        max_duration=VAD_MAX_DURATION,
    )
    stt = STTClient(language=STT_LANGUAGE)
    voice_pipeline = VoicePipeline(mic=mic, stt=stt, tts_lock=_tts_lock)
    _voice_task = asyncio.create_task(voice_pipeline.run())
    print("[SIA] 초기화 완료. 프레임 루프 + AI 루프 + 음성 파이프라인 시작.")


@app.on_event("shutdown")
async def shutdown():
    global _frame_task, _ai_task, _voice_task, voice_pipeline
    print("[SIA] 서버 종료 시작...")
    if voice_pipeline:
        voice_pipeline.stop()
    for t in (_frame_task, _ai_task, _voice_task):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    try:
        tts = get_tts_cache()
        tts.end_session()
    except Exception as e:
        print(f"[SIA] TTS 세션 종료 오류: {e}")
    print("[SIA] 서버 종료 완료.")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
