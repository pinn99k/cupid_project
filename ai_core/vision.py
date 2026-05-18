"""
YOLO 객체 인식 + bbox 후처리 모듈.
- load_model(): YOLO 모델 로드
- detect(frame): 프레임에서 객체 감지 → raw detections
- enrich(detections, frame_w, frame_h, ultrasonic_cm): 방향/거리 추정 → enriched JSON
"""


def load_model():
    """YOLO 모델 로드."""
    raise NotImplementedError("Step 1-1에서 구현")


def detect(frame):
    """웹캠 프레임에서 객체 감지. Returns: list of dict {label, x, y, w, h, conf}"""
    raise NotImplementedError("Step 1-1에서 구현")


def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    """bbox → 방향(left/center/right) + 거리(near/mid/far) + 초음파 매칭."""
    raise NotImplementedError("Step 1-2에서 구현")
