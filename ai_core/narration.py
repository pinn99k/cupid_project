"""
환경 묘사 LLM 호출.
- narrate_async(enriched_data): enriched JSON → LLM 공간 묘사 텍스트 (비블로킹)
"""

from ai_core.llm_client import call_async, SYSTEM_PROMPT


async def narrate_async(enriched_data) -> str | None:
    """enriched JSON → LLM 공간 묘사 텍스트. 실패 시 None."""
    objects_desc = []
    for obj in enriched_data.get("objects", []):
        dir_kr = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}[obj["direction"]]
        dist_kr = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}[obj["distance_est"]]
        objects_desc.append(f"{dir_kr} {dist_kr} {obj['label']}")

    uc = enriched_data.get("ultrasonic_cm")
    ut = enriched_data.get("ultrasonic_target")
    us_desc = f"\n정면 {uc}cm 거리에 {ut}이(가) 있음." if uc and ut else ""

    user_msg = (
        f"현재 감지된 물체: "
        f"{', '.join(objects_desc) if objects_desc else '없음'}"
        f"{us_desc}"
    )

    return await call_async(SYSTEM_PROMPT, user_msg)
