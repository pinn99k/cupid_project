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
from server.main_server import app, current_stage, learning_active
from server.websocket_handler import broadcast
from server.config import SERVER_HOST, SERVER_PORT
from utils.latency_logger import log, elapsed


async def detection_loop():
    """메인 감지 루프. 30fps 제한, LLM은 비블로킹 태스크로 분리."""
    cap = cv2.VideoCapture(0)
    audio = get_audio_manager()
    tts = get_tts_cache()

    # main_server의 상태를 참조하기 위해 import
    import server.main_server as srv

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue

            # Stage 1에서는 YOLO 비활성
            if srv.current_stage == 1:
                await asyncio.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            log("detect_start")
            dets = detect(frame)
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
                asyncio.create_task(
                    _handle_narration(enriched, tts, audio, srv.current_stage)
                )
                await asyncio.sleep(5)  # 5초 간격
            else:
                await asyncio.sleep(0.033)  # 30fps 제한
    finally:
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
    print("[SIA] 초기화 시작...")
    load_model()
    llm_init()
    tts = get_tts_cache()
    tts.start_session(f"session_{int(time.time())}")
    asyncio.create_task(detection_loop())
    print("[SIA] 초기화 완료. 감지 루프 시작.")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
