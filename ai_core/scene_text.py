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
}

DIRECTION_KR = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}
DISTANCE_KR = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}


def label_kr(label: str) -> str:
    """미등록 라벨은 원문 유지."""
    return LABEL_KR.get(label, label)


def scene_to_korean(enriched: dict) -> str:
    """enriched 장면 dict → LLM 입력용 한국어 한 줄.

    예) "현재 감지된 물체: 왼쪽 가까이 사람, 앞 멀리 의자. 정면 30cm 거리에 사람이(가) 있음."
    """
    parts = []
    for obj in enriched.get("objects", []):
        direction = DIRECTION_KR.get(obj.get("direction"), obj.get("direction", ""))
        distance = DISTANCE_KR.get(obj.get("distance_est"), obj.get("distance_est", ""))
        name = label_kr(obj.get("label", ""))
        parts.append(f"{direction} {distance} {name}".strip())

    detected = ", ".join(parts) if parts else "없음"

    cm = enriched.get("ultrasonic_cm")
    target = enriched.get("ultrasonic_target")
    sensor = ""
    if cm and target:
        sensor = f" 정면 {cm}cm 거리에 {label_kr(target)}이(가) 있음."

    return f"현재 감지된 물체: {detected}.{sensor}"
