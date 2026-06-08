"""YOLO objects -> 보행 방향 안내 힌트.

LLM이 장면을 추상적으로 해석하지 않도록, VQA 프롬프트에 넣을
"현재 감지 / 권장 이동" 구조화 정보를 만든다.
"""

from __future__ import annotations

from ai_core.scene_text import DIRECTION_KR, label_kr


PERSON_LABELS = {"person", "사람", "friend", "친구"}


def get_navigation_hint(objects) -> dict[str, str]:
    """감지 객체 목록을 보행 안내용 요약으로 변환.

    Args:
        objects: [{"label": "...", "direction": "left|center|right", ...}, ...]

    Returns:
        {
            "obstacle_summary": "앞에 사람",
            "direction_hint": "오른쪽으로 조금 이동해보자.",
            "prompt_text": "현재 감지: ...\n권장 이동: ..."
        }
    """
    normalized = [obj for obj in objects or [] if isinstance(obj, dict)]
    person_dirs = _directions_for_labels(normalized, PERSON_LABELS)

    if person_dirs:
        obstacle_summary, direction_hint = _person_hint(person_dirs)
    elif normalized:
        obstacle_summary, direction_hint = _generic_obstacle_hint(normalized)
    else:
        obstacle_summary = "앞에 특별한 장애물은 보이지 않음"
        direction_hint = "정면으로 천천히 걸어가보자."

    return {
        "obstacle_summary": obstacle_summary,
        "direction_hint": direction_hint,
        "prompt_text": f"현재 감지: {obstacle_summary}\n권장 이동: {direction_hint}",
    }


def _directions_for_labels(objects: list[dict], labels: set[str]) -> set[str]:
    dirs = set()
    for obj in objects:
        label = str(obj.get("label", "")).lower()
        direction = obj.get("direction")
        if label in labels and direction in {"left", "center", "right"}:
            dirs.add(direction)
    return dirs


def _person_hint(dirs: set[str]) -> tuple[str, str]:
    if "center" in dirs and "right" in dirs:
        return "앞과 오른쪽에 사람", "왼쪽으로 이동해보자."
    if "center" in dirs and "left" in dirs:
        return "앞과 왼쪽에 사람", "오른쪽으로 이동해보자."
    if "center" in dirs:
        return "앞에 사람", "오른쪽으로 조금 이동해보자."
    if "left" in dirs:
        return "왼쪽에 사람", "오른쪽으로 이동해보자."
    if "right" in dirs:
        return "오른쪽에 사람", "왼쪽으로 이동해보자."
    return "사람", "잠깐 멈춰서 안전한 방향을 확인해보자."


def _generic_obstacle_hint(objects: list[dict]) -> tuple[str, str]:
    directions = {obj.get("direction") for obj in objects}
    main = _largest_object(objects)
    name = label_kr(str(main.get("label", "장애물")))

    if "center" in directions and "right" in directions:
        return f"앞과 오른쪽에 {name}", "왼쪽으로 이동해보자."
    if "center" in directions and "left" in directions:
        return f"앞과 왼쪽에 {name}", "오른쪽으로 이동해보자."
    if "center" in directions:
        return f"앞에 {name}", "오른쪽으로 조금 이동해보자."
    if "left" in directions:
        return f"왼쪽에 {name}", "오른쪽으로 이동해보자."
    if "right" in directions:
        return f"오른쪽에 {name}", "왼쪽으로 이동해보자."
    return f"{name}", "잠깐 멈춰서 안전한 방향을 확인해보자."


def _largest_object(objects: list[dict]) -> dict:
    def area(obj: dict) -> float:
        try:
            return float(obj.get("bbox_ratio", 0.0))
        except (TypeError, ValueError):
            return 0.0

    return max(objects, key=area) if objects else {}
