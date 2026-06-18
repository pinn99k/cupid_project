"""YOLO objects -> 보행 방향 안내 힌트.

LLM이 장면을 추상적으로 해석하지 않도록, VQA 프롬프트에 넣을
"방향별 감지 / 막힌 방향 / 권장 이동 / 정답 초안" 구조화 정보를 만든다.
"""

from __future__ import annotations

from ai_core.scene_text import label_kr


_DIR_ORDER = ("left", "center", "right")
_SUMMARY_ORDER = ("center", "left", "right")
_DIR_KR_NOUN = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}
_DIR_KR_MOVE = {"left": "왼쪽", "center": "정면", "right": "오른쪽"}


def get_navigation_hint(objects) -> dict[str, str]:
    """감지 객체 목록을 보행 안내용 요약으로 변환.

    Args:
        objects: [{"label": "...", "direction": "left|center|right", ...}, ...]

    Returns:
        {
            "obstacle_summary": "앞에 사람, 왼쪽에 의자",
            "direction_hint": "오른쪽으로 조금 이동해보자.",
            "answer_text": "앞에 사람이 있고 왼쪽에는 의자가 있어. 오른쪽으로 조금 이동해보자.",
            "prompt_text": "방향별 감지: ...\n막힌 방향: ...\n권장 이동: ...\n정답 초안: ..."
        }
    """
    normalized = [obj for obj in objects or [] if isinstance(obj, dict)]
    direction_map = _direction_map(normalized)
    blocked_dirs = {d for d, items in direction_map.items() if items}

    if normalized:
        obstacle_summary = _summary_from_direction_map(direction_map)
        direction_hint = _direction_hint(blocked_dirs)
    else:
        obstacle_summary = "앞에 특별한 장애물은 보이지 않음"
        direction_hint = "정면으로 천천히 걸어가보자."

    answer_text = _answer_text(obstacle_summary, bool(normalized))
    blocked_text = _blocked_text(blocked_dirs)
    open_text = _open_text(blocked_dirs)

    # 방향정위 단계: 위치만 알려주고 이동 방향("~로 가자")은 말하지 않는다.
    # direction_hint/막힌·열린 방향은 dict에는 남기되(호환), LLM 프롬프트에는 넣지 않아
    # 모델이 이동 안내를 덧붙이지 않게 한다.
    return {
        "obstacle_summary": obstacle_summary,
        "direction_hint": direction_hint,
        "answer_text": answer_text,
        "blocked_directions": blocked_text,
        "open_directions": open_text,
        "prompt_text": (
            f"방향별 감지: {obstacle_summary}\n"
            f"정답 초안: {answer_text}"
        ),
    }


def _direction_map(objects: list[dict]) -> dict[str, list[dict]]:
    grouped = {direction: [] for direction in _DIR_ORDER}
    for obj in objects:
        direction = obj.get("direction")
        if direction in grouped:
            grouped[direction].append(obj)
    for direction in grouped:
        grouped[direction].sort(key=_area, reverse=True)
    return grouped


def _summary_from_direction_map(direction_map: dict[str, list[dict]]) -> str:
    parts = []
    for direction in _SUMMARY_ORDER:
        items = direction_map.get(direction, [])
        if not items:
            continue
        names = _unique_names(items[:2])
        direction_kr = _DIR_KR_NOUN[direction]
        parts.append(f"{direction_kr}에 {'와 '.join(names)}")
    return ", ".join(parts) if parts else "앞에 특별한 장애물은 보이지 않음"


def _unique_names(objects: list[dict]) -> list[str]:
    names = []
    seen = set()
    for obj in objects:
        name = label_kr(str(obj.get("label", "장애물")))
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names or ["장애물"]


def _direction_hint(blocked_dirs: set[str]) -> str:
    if blocked_dirs == {"left", "center", "right"}:
        return "잠깐 멈추고 선생님과 안전한 길을 확인해보자."
    if "center" in blocked_dirs and "right" in blocked_dirs:
        return "왼쪽으로 조금 이동해보자."
    if "center" in blocked_dirs and "left" in blocked_dirs:
        return "오른쪽으로 조금 이동해보자."
    if "center" in blocked_dirs:
        return "오른쪽으로 조금 이동해보자."
    if blocked_dirs == {"left", "right"}:
        return "정면으로 천천히 걸어가보자."
    if "left" in blocked_dirs:
        return "오른쪽으로 이동해보자."
    if "right" in blocked_dirs:
        return "왼쪽으로 이동해보자."
    return "정면으로 천천히 걸어가보자."


def _subject_josa(word: str) -> str:
    """끝 글자 받침 유무로 주격조사 선택(받침 O→'이', X→'가'). 한글 아니면 '이'."""
    if not word:
        return "이"
    last = word[-1]
    if "가" <= last <= "힣":
        return "이" if (ord(last) - 0xAC00) % 28 else "가"
    return "이"


def _answer_text(obstacle_summary: str, has_objects: bool) -> str:
    # 위치만 안내(이동 방향 제외). 예: "왼쪽에 사람, 오른쪽에 사람이 있어."
    if not has_objects:
        return "앞에 특별한 장애물은 보이지 않아."
    return f"{obstacle_summary}{_subject_josa(obstacle_summary)} 있어."


def _blocked_text(blocked_dirs: set[str]) -> str:
    if not blocked_dirs:
        return "없음"
    return ", ".join(_DIR_KR_NOUN[d] for d in _DIR_ORDER if d in blocked_dirs)


def _open_text(blocked_dirs: set[str]) -> str:
    open_dirs = [d for d in _DIR_ORDER if d not in blocked_dirs]
    if not open_dirs:
        return "없음"
    return ", ".join(_DIR_KR_MOVE[d] for d in open_dirs)


def _area(obj: dict) -> float:
    try:
        return float(obj.get("bbox_ratio", 0.0))
    except (TypeError, ValueError):
        return 0.0
