"""
Stage 3 : 위험 판단 로직 
- judge(enriched_data, current_stage): 가장 위험한 물체 하나를 골라 판정 → dict | None
"""

from server.config import DANGER_DISTANCE_CM

# 부딪히면 위험한 물체 
DANGER_LABELS = {"person", "chair", "couch", "dining table", "potted plant"}

# 방향별 위험 가중치 
DIRECTION_WEIGHT = {"center": 3, "left": 1, "right": 1}

# 거리별 위험 가중치 
DISTANCE_WEIGHT = {"near": 3, "mid": 1, "far": 0}


def _danger_score(obj) -> int:
    """물체 하나의 위험도 점수 / 높을수록 위험"""
    direction = DIRECTION_WEIGHT.get(obj["direction"], 1)
    distance = DISTANCE_WEIGHT.get(obj["distance_est"], 0)
    return direction + distance


def judge(enriched_data, current_stage: int):
    """
    Stage 3에서만 위험 판단 / 가장 위험한 물체 하나를 반환

    Returns:
        위험 시: {"level", "object", "direction", "distance_cm", "audio_file"}
        안전 시: None
    """
    if current_stage != 3:
        return None

    # Rule 1: 초음파 코앞 → 무조건 긴급 정지 (최우선)
    uc = enriched_data.get("ultrasonic_cm")
    if uc is not None and uc < DANGER_DISTANCE_CM:
        target = enriched_data.get("ultrasonic_target", "unknown")
        return {
            "level": "emergency",
            "object": target,
            "direction": "center",
            "distance_cm": uc,
            "audio_file": "warn_emergency.mp3",
        }

    # Rule 2: 위험 라벨 중 'near'인 것들만 후보로
    candidates = [
        obj for obj in enriched_data.get("objects", [])
        if obj["label"] in DANGER_LABELS and obj["distance_est"] == "near"
    ]
    if not candidates:
        return None

    # 가장 위험한 것 하나 선택
    most_dangerous = max(candidates, key=_danger_score)

    # 구체적 경고 음성이 있는 라벨만 따로, 나머지는 범용
    label = most_dangerous["label"]
    audio_file = "warn_person.mp3" if label == "person" else "warn_object.mp3"

    return {
        "level": "warning",
        "object": label,
        "direction": most_dangerous["direction"],
        "distance_cm": uc,
        "audio_file": audio_file,
    }