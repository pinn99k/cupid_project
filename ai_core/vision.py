"""
YOLO 객체 인식 + bbox 후처리 모듈.
- load_model(): YOLO 모델 로드
- detect(frame): 프레임에서 객체 감지 → raw detections
- enrich(detections, frame_w, frame_h, ultrasonic_cm): 방향/거리 추정 → enriched JSON
"""

from ultralytics import YOLO
from server.config import YOLO_MODEL, YOLO_CONF_THRESHOLD
from utils.latency_logger import log

model = None


def load_model():
    """YOLO 모델 로드."""
    global model
    log("yolo_load_start")
    model = YOLO(YOLO_MODEL)
    log("yolo_load_end")


def detect(frame):
    """
    웹캠 프레임에서 객체 감지.

    Args:
        frame: numpy array (BGR)
    Returns:
        list of dict {label, x, y, w, h, conf}
    """
    log("yolo_detect_start")
    results = model.predict(
        source=frame,
        conf=YOLO_CONF_THRESHOLD,
        verbose=False
    )[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "label": model.names[int(box.cls[0])],
            "x": x1,
            "y": y1,
            "w": x2 - x1,
            "h": y2 - y1,
            "conf": float(box.conf[0])
        })
    log("yolo_detect_end")
    return detections


def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    """
    bbox → 방향(left/center/right) + 거리(near/mid/far) + 초음파 매칭.

    Args:
        detections: detect() 반환값
        frame_w, frame_h: 프레임 크기
        ultrasonic_cm: HC-SR04P 거리값 (Phase 1에서는 None)
    Returns:
        interface_contract 스키마의 enriched JSON
    """
    enriched = []
    center_objects = []

    for det in detections:
        cx = (det["x"] + det["w"] / 2) / frame_w
        area = (det["w"] * det["h"]) / (frame_w * frame_h)

        direction = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
        distance_est = "near" if area > 0.20 else ("far" if area < 0.05 else "mid")

        if direction == "center":
            center_objects.append((det["label"], area))

        enriched.append({
            "label": det["label"],
            "direction": direction,
            "distance_est": distance_est,
            "bbox_ratio": round(area, 3),
            "confidence": round(det["conf"], 2)
        })

    ultrasonic_target = None
    if center_objects:
        ultrasonic_target = max(center_objects, key=lambda x: x[1])[0]

    return {
        "objects": enriched,
        "ultrasonic_cm": ultrasonic_cm,
        "ultrasonic_target": ultrasonic_target
    }
