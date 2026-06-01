"""
YOLO 객체 인식 + bbox 후처리
- load_model(): YOLO 모델 로드
- detect(frame): 프레임 → 감지된 물체 목록
- enrich(...): 물체에 방향/거리 정보 추가 → 최종 JSON
"""

from ultralytics import YOLO
from server.config import YOLO_MODEL, YOLO_CONF_THRESHOLD
from utils.latency_logger import log


# 카메라 보정값: 디바이스(ESP32-CAM) 연결 후 실제 테스트로 조정 필요
# 방향 판정 기준 (화면 가로 비율)
LEFT_BOUND = 0.33
RIGHT_BOUND = 0.66

# 거리 판정 기준 (화면 대비 물체 넓이 비율)
NEAR_AREA = 0.20
FAR_AREA = 0.05

model = None


def load_model():
    """YOLO 모델 로드 (프로그램 시작 시 1회)"""
    global model
    log("yolo_load_start")
    model = YOLO(YOLO_MODEL)
    log("yolo_load_end")


def detect(frame):
    """프레임에서 물체 감지 → [{label, x, y, w, h, conf}, ...]"""
    log("yolo_detect_start")
    results = model.predict(source=frame, conf=YOLO_CONF_THRESHOLD, verbose=False)[0]

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


def _get_distance(area_ratio):
    """물체 넓이 비율 → 가까이/중간/멀리"""
    if area_ratio > NEAR_AREA:
        return "near"
    if area_ratio < FAR_AREA:
        return "far"
    return "mid"


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

        # 관련성 게이트: 너무 작은(먼) 객체는 분석 대상에서 제외
        if min_relevant_area > 0 and area_ratio < min_relevant_area:
            continue

        direction = _get_direction(center_x_ratio)
        distance = _get_distance(area_ratio)

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
