"""
환경 묘사 LLM 호출
- narrate_async(enriched_data): 감지 물체 정보 → 시아 안내 문장 (비블로킹)
"""

from ai_core.llm_client import call_async

# YOLO 라벨
LABEL_KR = {
    "person": "사람",
    "backpack": "가방", "handbag": "가방", "suitcase": "캐리어",
    "umbrella": "우산", "cell phone": "휴대폰", "laptop": "노트북",
    "book": "책", "bottle": "병", "cup": "컵",
    "chair": "의자", "couch": "소파", "bench": "벤치",
    "dining table": "테이블", "potted plant": "화분", "tv": "티비",
    "keyboard": "키보드", "mouse": "마우스", "clock": "시계",
    "traffic light": "신호등",
    "fire hydrant": "너굴이",  # 시연용 '너굴이' 인형 — YOLO는 fire hydrant로 인식, 말은 너굴이로.
}

# 방향
DIRECTION_KR = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}

# 거리
DISTANCE_KR = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}


# narration 전용 시스템 프롬프트
NARRATION_PROMPT = """너는 시각장애 아동의 보행 교육 파트너 '시아'야. 어린 동생에게 다정하게 말하는 친절한 언니처럼 말해.

지금은 아이가 흰지팡이를 들고 걷고 있고, 너는 카메라로 아이 앞에 뭐가 있는지 보고 알려주는 역할이야.

규칙:
1. 감지된 물체 정보를 받으면, 한 문장으로 완성된 자연스러운 안내를 해줘.
2. 아이의 이름을 부르거나 만들어내지 마. "친구야" 또는 그냥 바로 안내해.
3. 욕설, 거친 단어 절대 쓰지 마.
4. 추측하지 마. 받은 정보 안에서만 말해.
5. 한 문장만. 미완성 문장 금지. "앞에..." 같이 끝맺지 않은 문장 금지.
6. 너무 길지 않게. 15글자 ~ 30글자 내외로.

예시:
입력: "앞 가까이 사람"
출력: "앞에 사람이 가까이 있어, 조심해서 가볼까?"

입력: "왼쪽 좀 떨어져서 의자, 앞 가까이 사람"
출력: "앞에 사람이 있고 왼쪽에는 의자가 있어."

입력: "없음"
출력: "지금은 주변에 아무것도 없어, 안전하게 갈 수 있어."
"""


async def narrate_async(enriched_data) -> str | None:
    """감지된 물체 정보를 한국어 안내 문장으로 변환 / 실패 시 None"""

    objects_desc = []
    for obj in enriched_data.get("objects", []):
        direction = DIRECTION_KR[obj["direction"]]
        distance = DISTANCE_KR[obj["distance_est"]]
        name = LABEL_KR.get(obj["label"], obj["label"])
        objects_desc.append(f"{direction} {distance} {name}")

    distance_cm = enriched_data.get("ultrasonic_cm")
    target = enriched_data.get("ultrasonic_target")
    if distance_cm and target:
        target_kr = LABEL_KR.get(target, target)
        sensor_desc = f", 정면 {distance_cm}cm 거리에 {target_kr}"
    else:
        sensor_desc = ""

    detected = ", ".join(objects_desc) if objects_desc else "없음"
    user_msg = f"감지된 물체: {detected}{sensor_desc}"

    return await call_async(NARRATION_PROMPT, user_msg)
