"""
환경 묘사 LLM 호출
- narrate_async(enriched_data): 감지 물체 정보 → 시아 안내 문장 (비블로킹)
"""

from ai_core.llm_client import call_async, SYSTEM_PROMPT

# YOLO 라벨
LABEL_KR = {
    "person": "사람",
    "backpack": "가방", "handbag": "가방", "suitcase": "캐리어",
    "umbrella": "우산", "cell phone": "휴대폰", "laptop": "노트북",
    "book": "책", "bottle": "병", "cup": "컵",
    "chair": "의자", "couch": "소파", "bench": "벤치",
    "dining table": "테이블", "potted plant": "화분", "tv": "티비",
    "keyboard": "키보드", "mouse": "마우스", "clock": "시계",
}

# 방향
DIRECTION_KR = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}

# 거리
DISTANCE_KR = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}


async def narrate_async(enriched_data) -> str | None:
    """감지된 물체 정보를 한국어 안내 문장으로 변환 / 실패 시 None"""

    objects_desc = []
    for obj in enriched_data.get("objects", []):
        direction = DIRECTION_KR[obj["direction"]]
        distance = DISTANCE_KR[obj["distance_est"]]
        name = LABEL_KR.get(obj["label"], obj["label"]) # 미등록 라벨은 영어 그대로
        objects_desc.append(f"{direction} {distance} {name}")

    distance_cm = enriched_data.get("ultrasonic_cm")
    target = enriched_data.get("ultrasonic_target")
    if distance_cm and target:
        target_kr = LABEL_KR.get(target, target)
        sensor_desc = f"\n정면 {distance_cm}cm 거리에 {target_kr}이(가) 있음."
    else:
        sensor_desc = ""

    detected = ", ".join(objects_desc) if objects_desc else "없음"
    user_msg = f"현재 감지된 물체: {detected}{sensor_desc}"

    return await call_async(SYSTEM_PROMPT, user_msg)