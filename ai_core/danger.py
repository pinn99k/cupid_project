"""
위험 판단 로직. Stage 3 전용.
- judge(enriched_data, current_stage): 위험 판정 → dict | None
"""

from server.config import DANGER_DISTANCE_CM

DANGER_LABELS = {"person", "car", "bicycle", "motorcycle", "bus", "truck", "dog"}


def judge(enriched_data, current_stage: int):
    """
    Stage 3이 아니면 항상 None 반환 (위험 판단 비활성).

    Returns:
        위험 시: {"level": "emergency"|"warning", "object": str, "direction": str,
                  "distance_cm": float|None, "audio_file": str}
        안전 시: None
    """
    # v2 핵심: Stage 3에서만 위험 판단 활성
    if current_stage != 3:
        return None

    uc = enriched_data.get("ultrasonic_cm")

    # Rule 1: 초음파 30cm 미만 → 즉시 정지
    if uc is not None and uc < DANGER_DISTANCE_CM:
        target = enriched_data.get("ultrasonic_target", "unknown")
        return {
            "level": "emergency",
            "object": target,
            "direction": "center",
            "distance_cm": uc,
            "audio_file": "warn_emergency.mp3"
        }

    # Rule 2: YOLO near + 위험 라벨
    for obj in enriched_data.get("objects", []):
        if obj["distance_est"] == "near" and obj["label"] in DANGER_LABELS:
            return {
                "level": "warning",
                "object": obj["label"],
                "direction": obj["direction"],
                "distance_cm": uc,
                "audio_file": f"warn_{obj['label']}.mp3"
            }

    return None
