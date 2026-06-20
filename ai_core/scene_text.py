"""
장면(enriched) → 한국어 묘사 텍스트 변환.
narration.py의 라벨/방향/거리 변환 로직을 추출해 공용화한다.
(VQA 컨텍스트와 자동 묘사 양쪽에서 재사용)

순수 함수 — YOLO/LLM/TTS 의존 없음.
"""

# YOLO 라벨 → 한국어
LABEL_KR = {
    "person": "사람",
    "backpack": "가방", "handbag": "가방", "suitcase": "캐리어",
    "umbrella": "우산", "cell phone": "휴대폰", "laptop": "노트북",
    "book": "책", "bottle": "병", "cup": "컵",
    "chair": "의자", "couch": "소파", "bench": "벤치",
    "dining table": "테이블", "potted plant": "화분", "tv": "티비",
    "keyboard": "키보드", "mouse": "마우스", "clock": "시계",
    "traffic light": "신호등",
    # 시연용 '너구리' 인형 — YOLO가 teddy bear/fire hydrant 어느 쪽으로 잡아도 '너구리'로.
    "teddy bear": "너구리",
    "fire hydrant": "너구리",
}

# 영어 모드에서 '말할 이름'. COCO 라벨이 곧 영어이므로 원문과 다르게 말할 것만 오버라이드.
# (traffic light/person 등은 원문 그대로 → traffic light/person)
LABEL_EN = {
    "teddy bear": "raccoon",
    "fire hydrant": "raccoon",
}

DIRECTION_KR = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}
DISTANCE_KR = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}


def label_kr(label: str) -> str:
    """미등록 라벨은 원문 유지."""
    return LABEL_KR.get(label, label)


def label_speech(label: str) -> str:
    """런타임 언어에 맞는 '말할 이름'.
    - en: LABEL_EN 오버라이드(없으면 원문 = 영어 COCO 라벨)
    - ko: LABEL_KR(없으면 원문)
    영어 모드에서 객체 이름을 확정해 LLM 번역에 기대지 않게 한다(시연 신뢰성).
    """
    from server.config import get_runtime_language  # 지연 import(순수성/순환 회피)
    if get_runtime_language() == "en":
        return LABEL_EN.get(label, label)
    return LABEL_KR.get(label, label)


def scene_to_korean(enriched: dict) -> str:
    """enriched 장면 dict → LLM 입력용 한국어 한 줄.

    예) "현재 감지된 물체: 왼쪽 가까이 사람, 앞 멀리 의자. 정면 30cm 거리에 사람이(가) 있음."
    """
    parts = []
    for obj in enriched.get("objects", []):
        direction = DIRECTION_KR.get(obj.get("direction"), obj.get("direction", ""))
        distance = DISTANCE_KR.get(obj.get("distance_est"), obj.get("distance_est", ""))
        name = label_speech(obj.get("label", ""))
        parts.append(f"{direction} {distance} {name}".strip())

    detected = ", ".join(parts) if parts else "없음"

    cm = enriched.get("ultrasonic_cm")
    target = enriched.get("ultrasonic_target")
    sensor = ""
    if cm and target:
        sensor = f" 정면 {cm}cm 거리에 {label_speech(target)}이(가) 있음."

    return f"현재 감지된 물체: {detected}.{sensor}"
