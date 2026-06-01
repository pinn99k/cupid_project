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
from ai_core.audio_manager import (
    PRIORITY_DANGER,
    PRIORITY_NARRATION,
    get_audio_manager,
)
from ai_core.llm_client import init as llm_init
from ai_core.narration import narrate_async
from ai_core.tts import get_tts_cache
from server.main_server import (
    app,
    get_frame,
    get_scene,
    increment_question_count,
    set_cancel_narration,
    set_frame,
    set_scene,
    set_voice_pipeline,
)
from server.websocket_handler import broadcast
from server.config import (SERVER_HOST, SERVER_PORT, WEBCAM_INDEX,
                           MIC_DEVICE_INDEX, VAD_SILENCE_THRESHOLD,
                           VAD_SILENCE_DURATION, VAD_MAX_DURATION, STT_LANGUAGE,
                           RELEVANCE_MIN_AREA, VAD_LOW_VOLUME_RMS,
                           DETECTION_BROADCAST_INTERVAL, AI_LOOP_SLEEP_SEC,
                           VOICE_OUTPUT_SETTLE_SEC, VOICE_REPROMPT_COOLDOWN_SEC)
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
DANGER_COOLDOWN = 20.0           # 같은 객체 위험 재경고 간격 (초)
NARRATION_INTERVAL = 20.0         # LLM 공간 묘사 간격 (초)

# shutdown 시 cancel 용
_frame_task: asyncio.Task | None = None
_ai_task: asyncio.Task | None = None
_voice_task: asyncio.Task | None = None
_narration_in_progress = False
_narration_task: asyncio.Task | None = None

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


def cancel_narration():
    """사용자 대화나 위험 경고가 시작되면 자동 묘사를 중단."""
    global _narration_task
    if _narration_task and not _narration_task.done():
        _narration_task.cancel()
        get_audio_manager().stop(clear_queue=True)
    _narration_task = None


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

    last_danger_time = 0.0
    last_danger_obj = None
    last_detection_broadcast_time = 0.0

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
        enriched = enrich(dets, w, h, min_relevant_area=RELEVANCE_MIN_AREA)
        log("detect_end")

        # 최신 장면을 공유 슬롯에 저장 — "시아야 질문" 시 VQA가 읽음 (Unit 3)
        # YOLO를 음성 경로에서 또 돌리지 않기 위함 (shared_resources.md §6)
        set_scene(enriched)

        now = time.time()

        # 음성 안내와 별도로 대시보드 탐지 상태는 실시간 갱신
        if (now - last_detection_broadcast_time) >= DETECTION_BROADCAST_INTERVAL:
            last_detection_broadcast_time = now
            await broadcast({
                "type": "detections_update",
                "objects": enriched["objects"],
                "timestamp": int(now * 1000),
            })

        # 위험 판단 (Stage 3 전용) — 쿨다운 + 같은 객체 중복 억제
        danger = judge(enriched, srv.app_state.current_stage)
        if danger:
            same_obj = (danger["object"] == last_danger_obj)
            if not same_obj or (now - last_danger_time) >= DANGER_COOLDOWN:
                last_danger_obj = danger["object"]
                last_danger_time = now
                log("danger_detected")
                try:
                    cancel_narration()
                    await broadcast({"type": "tts_start"})
                    request = audio.play(
                        danger["audio_file"],
                        priority=PRIORITY_DANGER,
                        interrupt=True,
                    )
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
                    await audio.wait(request)
                    await broadcast({"type": "tts_done"})
                except Exception as e:
                    print(f"[DANGER] 오디오 재생 실패: {e}")
                    await broadcast({
                        "type": "error",
                        "message": f"위험 경고음 재생 실패",
                        "timestamp": int(time.time() * 1000),
                    })
                    await broadcast({"type": "tts_start"})
                    # Fallback으로 기본 경고음 재생
                    request = audio.play(
                        "warn_emergency.wav",
                        priority=PRIORITY_DANGER,
                        interrupt=True,
                    )
                    await audio.wait(request)
                    await broadcast({"type": "tts_done"})
            # 위험 감지 시에도 프레임은 계속 갱신됨 (별도 루프)
            await asyncio.sleep(0.5)
            continue

        # 자동 공간 묘사(narration)는 Unit 3에서 제거 — 자동 묘사가 대화와 TTS락·
        # quota를 두고 경합해 응답이 밀리던 문제 해소. 최신 장면은 set_scene으로
        # 슬롯에 저장되어 "시아야 질문" 시 VQA가 근거로 사용한다.
        # (_handle_narration/_run_narration 함수는 수동 호출용으로 보존)

        await asyncio.sleep(AI_LOOP_SLEEP_SEC)


async def _handle_narration(enriched, tts, audio, stage):
    """LLM + TTS를 백그라운드 태스크로 처리. tts_lock으로 직렬화."""
    global _narration_in_progress, _narration_task
    _narration_in_progress = True
    try:
        await _run_narration(enriched, tts, audio, stage)
    finally:
        _narration_in_progress = False
        _narration_task = None


async def _run_narration(enriched, tts, audio, stage):
    """공간 묘사 생성 및 재생."""
    try:
        text = await narrate_async(enriched)
    except Exception as e:
        print(f"[NARRATION] LLM 에러: {type(e).__name__}: {e}")
        await broadcast({
            "type": "error",
            "message": f"공간 묘사 생성 실패: {type(e).__name__}",
            "timestamp": int(time.time() * 1000),
        })
        text = None

    if text:
        await broadcast({
            "type": "narration",
            "objects": enriched["objects"],
            "message": text,
            "stage": stage,
            "timestamp": int(time.time() * 1000),
        })
        try:
            async with _tts_lock:
                filepath = await tts.get_or_create(text)
                if filepath:
                    await broadcast({"type": "tts_start"})
                    request = audio.play_path(
                        str(filepath),
                        priority=PRIORITY_NARRATION,
                    )
                    await audio.wait(request)
                    await broadcast({"type": "tts_done"})
                else:
                    # TTS 파일 생성 실패 → fallback
                    await broadcast({"type": "tts_start"})
                    request = audio.play("buffer_01.wav", priority=PRIORITY_NARRATION)
                    await audio.wait(request)
                    await broadcast({"type": "tts_done"})
        except Exception as e:
            print(f"[NARRATION] TTS 에러: {e}")
            await broadcast({
                "type": "error",
                "message": f"TTS 재생 실패",
                "timestamp": int(time.time() * 1000),
            })
            async with _tts_lock:
                await broadcast({"type": "tts_start"})
                request = audio.play("buffer_01.wav", priority=PRIORITY_NARRATION)
                await audio.wait(request)
                await broadcast({"type": "tts_done"})
    else:
        # LLM 응답 없음 → fallback
        async with _tts_lock:
            await broadcast({"type": "tts_start"})
            request = audio.play("buffer_01.wav", priority=PRIORITY_NARRATION)
            await audio.wait(request)
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
    _frame_task.add_done_callback(_task_done_callback)
    _ai_task.add_done_callback(_task_done_callback)
    # VoicePipeline 초기화
    mic = MicCapture(
        device_index=MIC_DEVICE_INDEX,
        silence_threshold=VAD_SILENCE_THRESHOLD,
        silence_duration=VAD_SILENCE_DURATION,
        max_duration=VAD_MAX_DURATION,
        # TTS/narration 재생 중 골전도 이어폰 echo → silence_reset 방지
        audio_playing_check=get_audio_manager().is_playing,
    )
    stt = STTClient(language=STT_LANGUAGE)
    voice_pipeline = VoicePipeline(
        mic=mic,
        stt=stt,
        tts_lock=_tts_lock,
        cancel_narration=cancel_narration,
        audio_manager=get_audio_manager(),
        scene_provider=get_scene,
        count_question=increment_question_count,
        low_volume_rms=VAD_LOW_VOLUME_RMS,
        output_settle_sec=VOICE_OUTPUT_SETTLE_SEC,
        reprompt_cooldown_sec=VOICE_REPROMPT_COOLDOWN_SEC,
    )
    set_voice_pipeline(voice_pipeline)
    set_cancel_narration(cancel_narration)
    _voice_task = asyncio.create_task(voice_pipeline.run())
    _voice_task.add_done_callback(_task_done_callback)
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
