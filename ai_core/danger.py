"""
위험 판단 로직. Stage 3 전용.
- judge(enriched_data, current_stage): 위험 판정 → dict | None
"""


def judge(enriched_data, current_stage: int):
    """
    Stage 3이 아니면 항상 None (위험 판단 비활성).
    Stage 3: 초음파 < 30cm → emergency, YOLO near + 위험 라벨 → warning.
    """
    raise NotImplementedError("Step 1-3에서 구현")
