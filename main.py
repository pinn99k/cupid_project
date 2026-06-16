"""
SIA MVP 메인 실행 파일.
- _frame_loop: 웹캠 프레임 캡처 전용 (30fps, MJPEG 공급)
- _ai_loop: YOLO 감지 → 위험 판단 → LLM 묘사 (독립 속도)
- FastAPI 서버 시작 + WebSocket
실행: python main.py
"""

import asyncio
import os
import threading
import time
import urllib.request
from collections import deque

import cv2
import httpx
import numpy as np
import uvicorn

from ai_core.vision import load_model, detect, enrich
from ai_core.danger import judge
from ai_core.calibration import process as calib_process
from ai_core.audio_manager import (
    PRIORITY_DANGER,
    PRIORITY_NARRATION,
    get_audio_manager,
)
from ai_core.llm_client import init as llm_init, call_async as llm_call_async, SYSTEM_PROMPT
from ai_core.narration import narrate_async
from ai_core.tts import get_tts_cache
from server.main_server import (
    app,
    clear_scene,
    get_frame,
    get_scene,
    increment_question_count,
    set_cancel_narration,
    set_frame,
    set_scene,
    set_voice_pipeline,
)
from server.websocket_handler import broadcast
from server.config import (SERVER_HOST, SERVER_PORT, WEBCAM_INDEX, CAM_SOURCE,
                           CAMERA_ROTATION,
                           MIC_DEVICE_INDEX, VAD_SILENCE_THRESHOLD,
                           VAD_SILENCE_DURATION, VAD_MAX_DURATION, STT_LANGUAGE,
                           STT_ENGINE, WHISPER_MODEL, WHISPER_DEVICE,
                           WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER,
                           WHISPER_NO_SPEECH_THRESHOLD, WHISPER_LOGPROB_THRESHOLD,
                           RELEVANCE_MIN_AREA, VAD_LOW_VOLUME_RMS,
                           DETECTION_BROADCAST_INTERVAL, AI_LOOP_SLEEP_SEC,
                           DETECT_INTERVAL_SEC,
                           VOICE_OUTPUT_SETTLE_SEC, VOICE_REPROMPT_COOLDOWN_SEC,
                           ULTRASONIC_URL, ULTRASONIC_POLL_SEC, ULTRASONIC_OFFSET_CM,
                           ULTRASONIC_TIMEOUT_SEC, ULTRASONIC_STALE_SEC,
                           ULTRASONIC_BUFFER_N, SIA_DEBUG, LATENCY_LOG_DIR,
                           MANUAL_RECORDING_MODE, MANUAL_RECORDING_MAX_SEC)
from server.mic import MicCapture
from server.stt import create_stt_client
from server.voice_pipeline import VoicePipeline
from server.bluetooth_button_listener import BluetoothButtonListener
from utils.latency_logger import log, elapsed, configure as configure_latency, get_logger

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
# 프리웜/워밍업 킬스위치. SIA_PREWARM=off/false/0/no 면 스킵(기본 on).
def _prewarm_enabled() -> bool:
    return os.environ.get("SIA_PREWARM", "true").strip().lower() not in (
        "0", "false", "off", "no",
    )


MAX_WEBCAM_RETRIES = 5
WEBCAM_RETRY_DELAY = 3.0        # seconds
DANGER_COOLDOWN = 20.0           # 같은 객체 위험 재경고 간격 (초)
NARRATION_INTERVAL = 20.0         # LLM 공간 묘사 간격 (초)

# CAMERA_ROTATION(도) → cv2.rotate 플래그. 0이면 None(회전 안 함).
_ROTATE_FLAGS = {
    90:  cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}
_ROTATE_FLAG = _ROTATE_FLAGS.get(CAMERA_ROTATION)  # 0 → None
# CAM_SOURCE가 URL 문자열이면 네트워크 MJPEG 스트림(ESP32-CAM) → FFmpeg 백엔드 사용
_IS_STREAM_SOURCE = isinstance(CAM_SOURCE, str)

# shutdown 시 cancel 용
_frame_task: asyncio.Task | None = None
_ai_task: asyncio.Task | None = None
_ultrasonic_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# 초음파 거리 (디바이스 /distance 폴링 → 공유 슬롯)
# 펌웨어는 '날것 cm'만 보낸다. 보정/필터/끊김판정은 전부 여기(서버). (refactor §0)
# ULTRASONIC_URL 이 비면 폴링 자체를 안 띄움 → ultrasonic_cm None (현행과 100% 동일).
# 핫패스(영상/AI) 재작성 없이 값만 옆에서 공급 → 시연 안전.
# ---------------------------------------------------------------------------
_latest_distance: float | None = None
_distance_lock = threading.Lock()


def _set_distance(cm):
    global _latest_distance
    with _distance_lock:
        _latest_distance = cm


def _get_distance():
    """_ai_loop용 — 최신 보정거리(cm) 또는 None."""
    with _distance_lock:
        return _latest_distance


class _UltrasonicState:
    """초음파 원시값 버퍼 + 보정/중앙값 필터 + 끊김(STALE) 판정. 순수(시간 주입 → 테스트 가능).

    - push(raw, now): /distance 1회 수신 성공 시 호출.
    - value(now): 보정·필터된 cm. 마지막 응답이 stale_sec 넘게 없으면 None
      (센서 끊김 시 오래된 값으로 긴급정지 Rule1 이 오작동하지 않게).
    """

    def __init__(self, buffer_n: int, offset_cm: float, stale_sec: float):
        self._buf: deque = deque(maxlen=max(1, buffer_n))
        self._offset = offset_cm
        self._stale_sec = stale_sec
        self._last_push_t: float | None = None

    def push(self, raw_cm: float, now: float):
        # 끊겼다 복구된 경우 오래된 버퍼는 버린다(과거값 혼입 방지).
        if self._last_push_t is not None and (now - self._last_push_t) > self._stale_sec:
            self._buf.clear()
        self._buf.append(raw_cm)
        self._last_push_t = now

    def value(self, now: float):
        if self._last_push_t is None or (now - self._last_push_t) > self._stale_sec:
            return None  # 응답 없음(끊김) → None
        # calib_process: 오프셋 보정 + 중앙값 필터 + 유효성(2~400). 무반사(-1)는 자동 탈락.
        return calib_process(list(self._buf), offset=self._offset)


async def _ultrasonic_loop():
    """디바이스 /distance 주기 폴링 → 보정거리를 공유 슬롯에 채운다.

    시연 안전:
    - URL 미설정이면 즉시 종료(비활성).
    - 요청 타임아웃 + 매 이터레이션 예외 무시 → 루프 불사.
    - 끊김 시 STALE→None (오래된 값으로 오경보 금지).
    """
    if not ULTRASONIC_URL:
        print("[MAIN] ULTRASONIC_URL 미설정 → 초음파 폴링 비활성 (ultrasonic_cm=None 유지)")
        return

    state = _UltrasonicState(ULTRASONIC_BUFFER_N, ULTRASONIC_OFFSET_CM, ULTRASONIC_STALE_SEC)
    fail_streak = 0
    print(f"[MAIN] 초음파 폴링 시작: {ULTRASONIC_URL} "
          f"(주기 {ULTRASONIC_POLL_SEC}s, 타임아웃 {ULTRASONIC_TIMEOUT_SEC}s, "
          f"STALE {ULTRASONIC_STALE_SEC}s)")
    async with httpx.AsyncClient(timeout=ULTRASONIC_TIMEOUT_SEC) as client:
        while True:
            try:
                resp = await client.get(ULTRASONIC_URL)
                raw = float(resp.json()["cm"])
                state.push(raw, time.monotonic())
                if fail_streak:
                    print("[MAIN] 초음파 응답 복구")
                fail_streak = 0
            except Exception as e:
                fail_streak += 1
                if fail_streak == 1 or fail_streak % 20 == 0:
                    print(f"[MAIN] 초음파 폴링 실패({fail_streak}회째 → STALE 후 None): {e}")
            _set_distance(state.value(time.monotonic()))
            await asyncio.sleep(ULTRASONIC_POLL_SEC)
_voice_task: asyncio.Task | None = None
_bt_button_listener = None  # 이어폰 가운데 버튼 리스너
_warmup_task: asyncio.Task | None = None
_narration_in_progress = False
_narration_task: asyncio.Task | None = None

# TTS 전역 Lock (voice pipeline + narration/danger 공유)
_tts_lock = asyncio.Lock()

# VoicePipeline 인스턴스 (main_server.py에서 import 가능)
voice_pipeline: VoicePipeline | None = None


# 카메라 연결 타임아웃 (FFmpeg, ms) — 무선 지연/끊김 시 오래된 프레임을 붙잡지 않도록 짧게.
_CAM_OPEN_TIMEOUT_MS = 3000
# read 타임아웃은 '최댓값'이다 — 정상 프레임은 0.1초에 와서 즉시 반환된다.
# 같은 ESP32가 초음파(포트80)도 서빙해 스트림(포트81)이 잠깐 버벅일 때(실측 ~1초),
# 1000ms면 그 순간 read 실패 → 무한 재연결에 빠진다. 3000ms로 경합을 견딘다.
_CAM_READ_TIMEOUT_MS = 3000

if _IS_STREAM_SOURCE:
    # ESP32-CAM MJPEG 스트림 지연 최소화. 사용자가 직접 값을 준 경우는 존중한다.
    os.environ.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        "fflags;nobuffer|flags;low_delay|max_delay;0|probesize;32|analyzeduration;0",
    )


class _MjpegHttpCapture:
    """ESP32-CAM MJPEG를 OpenCV VideoCapture 대신 HTTP로 직접 읽는 캡처.

    브라우저에서 /stream은 열리는데 OpenCV/FFmpeg가 "No route to host"나
    "Couldn't read video stream"을 내는 macOS 조합을 우회한다.
    """

    def __init__(self, url: str, timeout_sec: float = 5.0):
        self._url = url
        self._timeout_sec = timeout_sec
        self._response = None
        self._buffer = bytearray()
        self._opened = False
        self._open()

    def _open(self):
        req = urllib.request.Request(
            self._url,
            headers={
                "User-Agent": "SIA-CUPID/1.0",
                "Accept": "multipart/x-mixed-replace,image/jpeg,*/*",
                "Connection": "close",
            },
        )
        self._response = urllib.request.urlopen(req, timeout=self._timeout_sec)
        self._opened = True

    def isOpened(self):
        return self._opened

    def set(self, *_args):
        return False

    def release(self):
        self._opened = False
        if self._response is not None:
            try:
                self._response.close()
            except Exception:
                pass
        self._response = None
        self._buffer.clear()

    def read(self):
        if not self._opened or self._response is None:
            return False, None

        deadline = time.monotonic() + self._timeout_sec
        while time.monotonic() < deadline:
            start = self._buffer.find(b"\xff\xd8")
            end = self._buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
            if start >= 0 and end >= 0:
                jpg = bytes(self._buffer[start:end + 2])
                del self._buffer[:end + 2]
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    return True, frame
                continue

            chunk = self._response.read(4096)
            if not chunk:
                break
            self._buffer.extend(chunk)
            if len(self._buffer) > 2_000_000:
                del self._buffer[:-500_000]
        return False, None


# ---------------------------------------------------------------------------
# 웹캠 연결 헬퍼 (동기 — 캡처 스레드에서 사용)
# ---------------------------------------------------------------------------
def _open_camera_sync() -> cv2.VideoCapture | None:
    """웹캠 연결 시도(동기). 실패 시 재시도 후 None 반환.

    - URL 소스(ESP32-CAM MJPEG): FFmpeg 백엔드를 먼저 쓰고, 실패하면 기본 백엔드로
      한 번 더 시도한다. 일부 macOS/OpenCV 조합은 브라우저에서는 열리는 MJPEG도
      CAP_FFMPEG로 못 여는 경우가 있어 시연 안정성을 위해 fallback을 둔다.
    - 로컬 웹캠(int 인덱스): 기본 백엔드.
    - 공통: 내부 버퍼 1프레임으로 최신 프레임만 유지.
    """
    for attempt in range(1, MAX_WEBCAM_RETRIES + 1):
        if _IS_STREAM_SOURCE:
            candidates = [
                ("HTTP-MJPEG", lambda: _MjpegHttpCapture(CAM_SOURCE, timeout_sec=5.0)),
                (
                    "FFmpeg",
                    lambda: cv2.VideoCapture(
                        CAM_SOURCE,
                        cv2.CAP_FFMPEG,
                        [
                            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _CAM_OPEN_TIMEOUT_MS,
                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, _CAM_READ_TIMEOUT_MS,
                        ],
                    ),
                ),
                ("기본", lambda: cv2.VideoCapture(CAM_SOURCE)),
            ]
        else:
            candidates = [("기본", lambda: cv2.VideoCapture(CAM_SOURCE))]

        for backend, opener in candidates:
            try:
                cap = opener()
            except Exception as e:
                print(
                    f"[MAIN] 웹캠 연결 실패 (시도 {attempt}/{MAX_WEBCAM_RETRIES}, "
                    f"백엔드={backend}, 오류={type(e).__name__}: {e})"
                )
                continue
            if cap.isOpened():
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                print(
                    f"[MAIN] 웹캠 연결 성공 (시도 {attempt}, 소스={CAM_SOURCE}, 백엔드={backend}, "
                    f"open_timeout={_CAM_OPEN_TIMEOUT_MS}ms, read_timeout={_CAM_READ_TIMEOUT_MS}ms)"
                )
                if _IS_STREAM_SOURCE:
                    print(
                        "[MAIN] FFmpeg low-latency options="
                        f"{os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS', '')}"
                    )
                return cap
            cap.release()
            print(f"[MAIN] 웹캠 연결 실패 (시도 {attempt}/{MAX_WEBCAM_RETRIES}, 백엔드={backend})")

        if _IS_STREAM_SOURCE:
            if attempt == 1:
                print(
                    "[MAIN] 힌트: ESP32-CAM /stream을 브라우저에서 직접 열어둔 탭이 있으면 "
                    "닫고 다시 시도하세요. ESP32-CAM은 동시 스트림 연결에 약합니다."
                )
        time.sleep(WEBCAM_RETRY_DELAY)
    return None


def _broadcast_threadsafe(loop: asyncio.AbstractEventLoop, payload: dict):
    """캡처 스레드 → 이벤트 루프로 안전하게 broadcast 전달."""
    try:
        asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
    except Exception as e:
        print(f"[MAIN] broadcast 전달 실패: {e}")


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
# 프레임 캡처 (전용 스레드 — 이벤트 루프 블로킹 방지로 딜레이 최소화)
# ---------------------------------------------------------------------------
def _capture_worker(loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
    """별도 스레드에서 카메라를 끊김 없이 읽어 최신 프레임만 유지한다.

    왜 스레드인가:
    - cap.read()/grab()은 블로킹 호출이다. 이걸 asyncio 루프 안에서 돌리면
      프레임 대기 동안 이벤트 루프가 멈춰 브라우저 MJPEG 송출까지 끊긴다(딜레이↑).
    - MJPEG 스트림은 read()가 '다음 프레임 도착'까지만 블로킹하므로, sleep 없이
      타이트하게 읽으면 자연히 카메라 fps에 맞춰 돌며 항상 최신 프레임을 잡는다.
      → 인위적 grab 드레인/버퍼 누적 없이 지연 최소화.

    회전(CAMERA_ROTATION)은 set_frame() 직전 한 곳에서만 적용 → YOLO/bbox/거리추정
    모두 회전된 프레임 기준으로 일관 (다운스트림이 frame.shape에서 치수 재독).
    """
    def _connect_until_ready() -> cv2.VideoCapture | None:
        """stop_event 전까지 무한 재시도로 카메라를 연다. 절대 영구 포기하지 않는다.
        이유: kill -9 로 이전 서버를 강제 종료하면 ESP32 가 죽은 연결을 몇 초~몇십 초
        붙잡고 있어(스트림 슬롯 1개) 바로 켠 새 서버가 못 붙는다. 여기서 포기하지 않고
        계속 재시도하면, 슬롯이 풀리는 순간 자동으로 붙는다(사용자는 그냥 기다리면 됨)."""
        n = 0
        while not stop_event.is_set():
            cap = _open_camera_sync()
            if cap is not None:
                if n > 0:
                    print(f"[MAIN] ✅ 카메라 자동 복구됨 (재시도 {n}회 후 슬롯 확보)")
                return cap
            n += 1
            print(
                f"[MAIN] 카메라 연결 대기중(누적 {n}회) — ESP32가 이전 연결을 놓아줄 때까지 "
                f"자동 재시도. (방금 kill -9 로 껐다면 ~10~20초 기다리면 자동 연결)"
            )
            _broadcast_threadsafe(loop, {
                "type": "error",
                "message": "카메라 연결 대기중... (잠시 후 자동 연결)",
            })
            stop_event.wait(2.0)
        return None

    cap = _connect_until_ready()
    if cap is None:
        return  # 연결 대기 중 서버 종료 → 정상 종료

    if _ROTATE_FLAG is not None:
        print(f"[MAIN] 카메라 회전 적용: {CAMERA_ROTATION}도")

    # 시간 기반 재연결: 마지막 정상 프레임 후 이 시간이 지나면 재연결.
    # ⚠️ read 타임아웃(3초)보다 충분히 커야 한다. 안 그러면 경합으로 read가 한 번
    #    느려질 때마다 재연결을 시도해 오히려 스트림을 끊어 회복을 막는다(무한 재연결).
    RECONNECT_AFTER_SEC = 10.0
    last_ok = time.monotonic()
    try:
        while not stop_event.is_set():
            ret, frame = cap.read()  # 스트림: 다음 프레임까지만 블로킹 → 항상 최신
            if not ret:
                if time.monotonic() - last_ok > RECONNECT_AFTER_SEC:
                    print("[MAIN] 프레임 끊김 → 웹캠 재연결 시도...")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = _connect_until_ready()  # 영구 포기 안 함 → 자동 복구
                    if cap is None:
                        return  # 서버 종료
                    last_ok = time.monotonic()
                else:
                    time.sleep(0.05)
                continue

            last_ok = time.monotonic()
            if _ROTATE_FLAG is not None:
                frame = cv2.rotate(frame, _ROTATE_FLAG)
            set_frame(frame)
    finally:
        if cap is not None:
            cap.release()
        print("[MAIN] 카메라 해제(캡처 스레드)")


async def _frame_loop():
    """캡처 스레드를 띄우고 수명만 관리한다(프레임 읽기는 스레드가 담당)."""
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    worker = threading.Thread(
        target=_capture_worker,
        args=(loop, stop_event),
        name="camera-capture",
        daemon=True,
    )
    worker.start()
    try:
        # 스레드가 살아있는 동안 대기. 태스크 취소(shutdown) 시 finally에서 정지.
        while worker.is_alive():
            await asyncio.sleep(0.5)
    finally:
        stop_event.set()


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
    last_detect_time = 0.0          # P1: 마지막 YOLO 추론 시각
    enriched = None                 # P1: 검출 결과 캐시(주기 사이 재사용)

    while True:
        # Stage 1은 대화 전용 — AI 분석 불필요
        if srv.app_state.current_stage == 1:
            # 이전 Stage 2/3 의 잔류 장면이 VQA 응답을 오염시키지 않도록 즉시 클리어.
            # _latest_scene 이 None 이 되면 voice_pipeline 은 "잘 안 보여"로 직접 응답.
            clear_scene()
            await asyncio.sleep(0.5)
            continue

        now = time.time()

        # P1 디커플링: DETECT_INTERVAL_SEC>0이면 그 간격으로만 YOLO 추론하고
        # 사이엔 직전 결과(enriched)를 재사용 → CPU 절약. 0이면 매 루프 검출(변경 전과 동일).
        # 최초(enriched None)엔 무조건 검출.
        need_detect = (
            DETECT_INTERVAL_SEC <= 0
            or enriched is None
            or (now - last_detect_time) >= DETECT_INTERVAL_SEC
        )
        if need_detect:
            # 최신 프레임 가져오기 (프레임 루프가 공급)
            frame = get_frame()
            if frame is None:
                await asyncio.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            log("detect_start")
            dets = await asyncio.to_thread(detect, frame)
            # 초음파 거리 주입 (폴링 루프가 채움; 미연결/끊김이면 None → 기존 동작과 동일)
            enriched = enrich(dets, w, h, ultrasonic_cm=_get_distance(),
                              min_relevant_area=RELEVANCE_MIN_AREA)
            log("detect_end")
            elapsed("detect_start", "detect_end")  # YOLO 추론시간 집계(P1 측정)
            last_detect_time = now

            # 최신 장면을 공유 슬롯에 저장 — "시아야 질문" 시 VQA가 읽음 (Unit 3)
            # YOLO를 음성 경로에서 또 돌리지 않기 위함 (shared_resources.md §6)
            set_scene(enriched)

        # 음성 안내와 별도로 대시보드 탐지 상태는 실시간 갱신(검출 재사용 시에도 최신 enriched 송신)
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
# 프리웜 / 콜드스타트 워밍업 (백그라운드 — 서버 기동을 지연시키지 않음)
# ---------------------------------------------------------------------------
async def _warmup(tts, stt=None):
    """고정 문구 TTS 프리웜 + LLM 콜드스타트 더미 호출 + STT(Whisper) 모델 로드.

    - 백그라운드 task로 실행 → 서버 기동(루프 시작)을 막지 않음.
    - 전부 best-effort: 실패해도 서버 동작에 지장 없게 예외를 삼킨다.
    """
    try:
        created = await tts.prewarm()
        print(f"[PREWARM] {created}개 생성")
    except Exception as e:
        print(f"[PREWARM] TTS 프리웜 오류(무시): {e}")

    # LLM 콜드스타트 완화 — 짧은 더미 호출 1회.
    try:
        await llm_call_async(SYSTEM_PROMPT, "안녕", max_tokens=16)
        print("[PREWARM] LLM 워밍업 완료")
    except Exception as e:
        print(f"[PREWARM] LLM 워밍업 오류(무시): {e}")

    # STT(Whisper) 모델 로드 워밍업 — 첫 발화 콜드스타트 방지.
    warm = getattr(stt, "warmup", None)
    if warm:
        try:
            await asyncio.to_thread(warm)
        except Exception as e:
            print(f"[PREWARM] STT 워밍업 오류(무시): {e}")


# ---------------------------------------------------------------------------
# 서버 생명주기
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    global _frame_task, _ai_task, _voice_task, _ultrasonic_task, _warmup_task, voice_pipeline, _bt_button_listener
    print("[SIA] 초기화 시작...")
    # Phase 0 계측: print 게이팅(SIA_DEBUG) + latency_log.json 저장 위치 설정
    configure_latency(log_dir=LATENCY_LOG_DIR, verbose=SIA_DEBUG)
    load_model()
    llm_init()
    tts = get_tts_cache()
    tts.start_session(f"session_{int(time.time())}")
    # STT 클라이언트(google | whisper) — 워밍업 대상이라 먼저 생성.
    stt = create_stt_client(
        engine=STT_ENGINE,
        language=STT_LANGUAGE,
        model_size=WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
        beam_size=WHISPER_BEAM_SIZE,
        vad_filter=WHISPER_VAD_FILTER,
        no_speech_threshold=WHISPER_NO_SPEECH_THRESHOLD,
        logprob_threshold=WHISPER_LOGPROB_THRESHOLD,
    )
    # 프리웜/워밍업 — start_session 직후 백그라운드로 (기동 지연 방지).
    # SIA_PREWARM=off 면 스킵.
    if _prewarm_enabled():
        _warmup_task = asyncio.create_task(_warmup(tts, stt))
        _warmup_task.add_done_callback(_task_done_callback)
    else:
        print("[PREWARM] SIA_PREWARM=off → 프리웜/워밍업 스킵")
    # 두 루프를 독립적으로 시작
    _frame_task = asyncio.create_task(_frame_loop())
    _ai_task = asyncio.create_task(_ai_loop())
    _frame_task.add_done_callback(_task_done_callback)
    _ai_task.add_done_callback(_task_done_callback)
    # 초음파 폴링 (URL 미설정이면 루프가 즉시 종료 → 비활성)
    _ultrasonic_task = asyncio.create_task(_ultrasonic_loop())
    _ultrasonic_task.add_done_callback(_task_done_callback)
    # VoicePipeline 초기화
    mic = MicCapture(
        device_index=MIC_DEVICE_INDEX,
        silence_threshold=VAD_SILENCE_THRESHOLD,
        silence_duration=VAD_SILENCE_DURATION,
        max_duration=VAD_MAX_DURATION,
        # TTS/narration 재생 중 골전도 이어폰 echo → silence_reset 방지
        audio_playing_check=get_audio_manager().is_playing,
        manual_max_sec=MANUAL_RECORDING_MAX_SEC,
    )
    if MANUAL_RECORDING_MODE:
        mic.start_manual_capture_stream()
        print(f"[MANUAL] enabled max_sec={MANUAL_RECORDING_MAX_SEC}")
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

    # 골전도 이어폰 가운데 버튼 → 마이크 토글 (수동 모드 전용).
    # macOS/블루투스 프로파일 상태에 따라 같은 버튼도 redial/AVRCP/Siri 계열로 다르게
    # 기록될 수 있으므로 BluetoothButtonListener 쪽에서 실제 이벤트 후보를 넓게 감시한다.
    print(f"[BT_BUTTON] startup manual_mode={MANUAL_RECORDING_MODE}")
    if MANUAL_RECORDING_MODE:
        loop = asyncio.get_running_loop()
        print(
            f"[BT_BUTTON] startup server_loop_id={id(loop)} "
            f"running_loop_id={id(asyncio.get_running_loop())}"
        )

        async def _bt_button_toggle():
            print(
                f"[BT_BUTTON] toggle coroutine entered "
                f"running_loop_id={id(asyncio.get_running_loop())}"
            )
            if voice_pipeline is None:
                print("[BT_BUTTON] toggle ignored: voice_pipeline is None")
                return
            state = voice_pipeline.recording_state
            print(f"[BT_BUTTON] current recording_state={state}")
            if state == "idle":
                print("[BT_BUTTON] calling on_manual_start_recording()")
                await voice_pipeline.on_manual_start_recording()
                print("[BT_BUTTON] toggle -> start_recording")
            elif state == "recording":
                print("[BT_BUTTON] calling on_manual_stop_recording()")
                await voice_pipeline.on_manual_stop_recording()
                print("[BT_BUTTON] toggle -> stop_recording")
            else:
                # processing/speaking: 정상이면 곧 idle 로 풀린다. 그런데 2초 넘게
                # 이 상태면 어딘가 막힌 것 → 운영자 버튼으로 즉시 강제복구(데드락 탈출).
                secs = voice_pipeline.seconds_in_state
                if secs > 2.0:
                    print(f"[BT_BUTTON] state={state} {secs:.1f}s 지속 → 막힘으로 보고 강제복구")
                    await voice_pipeline.force_recover_stuck(reason="operator_button")
                else:
                    print(f"[BT_BUTTON] toggle 무시 (state={state}, {secs:.1f}s — 정상 처리중)")

        # debounce 1.5초: COSY + 버튼을 한 번 눌러도 살짝 길게 눌리면 볼륨업 신호가
        # 여러 번(≈1초 간격) 가서 start→stop 이중 토글되는 실측 문제가 있었다.
        # 의도적 start/stop은 발화(2~3초)를 사이에 두니 1.5초 디바운스가 방해 안 됨.
        _bt_button_listener = BluetoothButtonListener(loop, _bt_button_toggle, debounce_sec=1.5)
        print(f"[BT_BUTTON] created listener ref={_bt_button_listener!r}")
        _bt_button_listener.start()
    else:
        print("[BT_BUTTON] 비활성 (MANUAL_RECORDING_MODE=false)")
    print("[SIA] 초기화 완료. 프레임 루프 + AI 루프 + 음성 파이프라인 시작.")


@app.on_event("shutdown")
async def shutdown():
    global _frame_task, _ai_task, _voice_task, _ultrasonic_task, _warmup_task, voice_pipeline, _bt_button_listener
    print("[SIA] 서버 종료 시작...")
    if _bt_button_listener:
        _bt_button_listener.stop()
        _bt_button_listener = None
    if voice_pipeline:
        voice_pipeline.stop()
    for t in (_frame_task, _ai_task, _voice_task, _ultrasonic_task, _warmup_task):
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
    # Phase 0: 측정 통계를 latency_log.json 으로 저장 (병목 분석용)
    try:
        get_logger().save_to_file("latency_log.json")
    except Exception as e:
        print(f"[SIA] latency 저장 오류: {e}")
    print("[SIA] 서버 종료 완료.")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
