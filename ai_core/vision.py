"""
YOLO 객체 인식 + bbox 후처리
- load_model(): YOLO 모델 로드
- detect(frame): 프레임 → 감지된 물체 목록
- enrich(...): 물체에 방향/거리 정보 추가 → 최종 JSON
"""

from ultralytics import YOLO
from server.config import (
    YOLO_MODEL, YOLO_CONF_THRESHOLD, YOLO_IMGSZ,
    DIST_NEAR_AREA, DIST_FAR_AREA,
    DIST_USE_HEIGHT, DIST_NEAR_HEIGHT, DIST_FAR_HEIGHT,
    DIST_USE_BOTTOM_Y, DIST_NEAR_BOTTOM_Y, DIST_DEBUG,
)
from utils.latency_logger import log


# 카메라 보정값: 디바이스(ESP32-CAM) 연결 후 실제 테스트로 조정 필요
# 방향 판정 기준 (화면 가로 비율)
LEFT_BOUND = 0.33
RIGHT_BOUND = 0.66

# 거리 판정 기준(화면 대비 물체 넓이 비율). config에서 주입 — 실측값은 .env로 보정.
# (이름은 호환 위해 유지. 기본값은 기존 0.20/0.05과 동일.)
NEAR_AREA = DIST_NEAR_AREA
FAR_AREA = DIST_FAR_AREA

model = None


def load_model():
    """YOLO 모델 로드 (프로그램 시작 시 1회)"""
    global model
    log("yolo_load_start")
    model = YOLO(YOLO_MODEL)
    log("yolo_load_end")


def detect(frame, imgsz=YOLO_IMGSZ):
    """프레임에서 물체 감지 → [{label, x, y, w, h, conf}, ...]

    imgsz>0이면 추론 입력 해상도를 그 값으로 다운스케일(빠름, 품질 약간↓).
    0이면 모델 기본값. 출력 bbox는 항상 원본 프레임 좌표라 enrich()는 그대로 동작.
    """
    log("yolo_detect_start")
    predict_kwargs = {"source": frame, "conf": YOLO_CONF_THRESHOLD, "verbose": False}
    if imgsz and imgsz > 0:
        predict_kwargs["imgsz"] = imgsz
    results = model.predict(**predict_kwargs)[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "label": model.names[int(box.cls[0])],
            "x": x1,
            "y": y1,
            "w": x2 - x1,
            "h": y2 - y1,
            "conf": float(box.conf[0]),
        })
    log("yolo_detect_end")
    return detections


def _get_direction(center_x_ratio):
    """물체 중심의 가로 위치 → 왼쪽/가운데/오른쪽"""
    if center_x_ratio < LEFT_BOUND:
        return "left"
    if center_x_ratio > RIGHT_BOUND:
        return "right"
    return "center"


def _get_distance(area_ratio, height_ratio=None, bottom_y=None):
    """물체의 거리 추정 → near/mid/far.

    기본은 면적비(현행). DIST_USE_HEIGHT / DIST_USE_BOTTOM_Y 가 켜지면 보강 신호로
    판정을 조정한다. 둘 다 off(기본)면 면적-only → 기존 동작과 100% 동일.

    Args:
        area_ratio:   bbox 넓이 / 화면 넓이.
        height_ratio: bbox 높이 / 화면 높이 (세로 물체 안정용, 옵션).
        bottom_y:     bbox 아랫변 y(정규화 0~1). 1에 가까울수록 화면 하단=가까움(옵션).
    """
    # 1) 면적비 (현행 기준)
    if area_ratio > NEAR_AREA:
        dist = "near"
    elif area_ratio < FAR_AREA:
        dist = "far"
    else:
        dist = "mid"

    # 2) (옵션) 높이비 보강 — 세로 물체는 면적보다 높이가 거리에 덜 흔들린다.
    if DIST_USE_HEIGHT and height_ratio is not None:
        if height_ratio > DIST_NEAR_HEIGHT:
            dist = "near"
        elif height_ratio < DIST_FAR_HEIGHT and dist != "near":
            dist = "far"

    # 3) (옵션) 바닥 접점 y 보강 — 아랫변이 화면 하단이면 가까운 바닥 장애물.
    if DIST_USE_BOTTOM_Y and bottom_y is not None and bottom_y > DIST_NEAR_BOTTOM_Y:
        dist = "near"

    return dist


def enrich(detections, frame_w, frame_h, ultrasonic_cm=None, min_relevant_area=0.0):
    """각 물체에 방향/거리 정보를 더한 최종 JSON 반환.

    min_relevant_area > 0이면 화면 대비 면적이 그 미만인 객체는 무시한다
    (Unit 6 관련성 게이트 — 배경 스크린의 작고 먼 오탐 차단).
    기본값 0 = 필터 없음(기존 동작 보존, 순수 기하 테스트용).
    """
    objects = []
    center_objects = []

    for det in detections:
        center_x_ratio = (det["x"] + det["w"] / 2) / frame_w
        area_ratio = (det["w"] * det["h"]) / (frame_w * frame_h)
        height_ratio = det["h"] / frame_h
        bottom_y = (det["y"] + det["h"]) / frame_h  # bbox 아랫변(접점) — 클수록 가까움

        # 관련성 게이트: 너무 작은(먼) 객체는 분석 대상에서 제외
        if min_relevant_area > 0 and area_ratio < min_relevant_area:
            continue

        direction = _get_direction(center_x_ratio)
        distance = _get_distance(area_ratio, height_ratio, bottom_y)

        # 보정용 로그(DIST_DEBUG=on): 위험/안전 거리에서 이 값들을 읽어 .env 임계 튜닝.
        if DIST_DEBUG:
            print(
                f"[DIST] {det['label']:14s} area={area_ratio:.3f} h={height_ratio:.3f}"
                f" bottom_y={bottom_y:.3f} dir={direction} → {distance}"
            )

        if direction == "center":
            center_objects.append((det["label"], area_ratio))

        objects.append({
            "label": det["label"],
            "direction": direction,
            "distance_est": distance,
            "bbox_ratio": round(area_ratio, 3),
            "bbox": {
                "x": round(det["x"] / frame_w, 4),
                "y": round(det["y"] / frame_h, 4),
                "w": round(det["w"] / frame_w, 4),
                "h": round(det["h"] / frame_h, 4),
            },
            "confidence": round(det["conf"], 2),
        })

    # 정면 물체 중 가장 큰(가까운) 것을 초음파 매칭 대상으로
    ultrasonic_target = None
    if center_objects:
        ultrasonic_target = max(center_objects, key=lambda x: x[1])[0]

    return {
        "objects": objects,
        "ultrasonic_cm": ultrasonic_cm,
        "ultrasonic_target": ultrasonic_target,
    }
