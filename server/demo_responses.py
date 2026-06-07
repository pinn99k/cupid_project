"""시연용 키워드 매칭 + 장면 기반 사전 음성 선택."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

DEMO_VOICE_DIR = Path("server/demo_voices")

SCENARIO_KEYWORDS: dict[str, str] = {
    r"안녕|반가워": "greeting.wav",
    r"누구|뭐야|설명|소개": "intro.wav",
    r"같이|가자": "lets_go.wav",
    r"뭐 있|뭐가 있|보여|있어": "_scene_aware",
    r"다 왔|도착": "arrival.wav",
}

_TRAFFIC_LABELS = {"traffic light", "traffic_light", "stop light", "signal", "신호등"}
_PERSON_LABELS = {"person", "사람", "friend", "친구"}


def find_response(question: str, scene_objects, voice_history: Iterable[str] | None = None) -> str:
    """질문을 키워드로 매칭해 재생할 demo voice 파일명을 반환."""
    normalized = " ".join((question or "").split())
    history = set(voice_history or [])
    for pattern, filename in SCENARIO_KEYWORDS.items():
        if re.search(pattern, normalized):
            if filename == "_scene_aware":
                return find_scene_voice(scene_objects, history)
            return filename
    return "fallback.wav"


def find_scene_voice(detected_objects, voice_history: Iterable[str] | None = None) -> str:
    """YOLO 장면에서 가장 적절한 demo voice 파일명을 선택."""
    objects = _objects_list(detected_objects)
    history = set(voice_history or [])

    close_person = _select_person(objects, close=True)
    if close_person:
        return f"person_{get_position(close_person.get('bbox'))}_close.wav"

    if "traffic_light.wav" not in history and any(_is_traffic_light(obj) for obj in objects):
        return "traffic_light.wav"

    far_person = _select_person(objects, close=False)
    if far_person:
        return f"person_{get_position(far_person.get('bbox'))}_far.wav"

    return "all_clear.wav"


def get_position(bbox) -> str:
    """bbox 중심 x좌표로 left/center/right 판정. bbox는 정규화 좌표를 기대한다."""
    if not isinstance(bbox, dict):
        return "center"
    try:
        center_x = float(bbox.get("x", 0.0)) + float(bbox.get("w", 0.0)) / 2
    except (TypeError, ValueError):
        return "center"
    if center_x < 0.33:
        return "left"
    if center_x <= 0.66:
        return "center"
    return "right"


def voice_path(filename: str) -> Path:
    """demo voice 파일 경로."""
    return DEMO_VOICE_DIR / filename


def _objects_list(detected_objects) -> list[dict]:
    if isinstance(detected_objects, dict):
        detected_objects = detected_objects.get("objects", [])
    return [obj for obj in detected_objects or [] if isinstance(obj, dict)]


def _is_person(obj: dict) -> bool:
    return str(obj.get("label", "")).lower() in _PERSON_LABELS


def _is_traffic_light(obj: dict) -> bool:
    return str(obj.get("label", "")).lower() in _TRAFFIC_LABELS


def _bbox_area(obj: dict) -> float:
    if "bbox_ratio" in obj:
        try:
            return float(obj["bbox_ratio"])
        except (TypeError, ValueError):
            pass
    bbox = obj.get("bbox") or {}
    try:
        return float(bbox.get("w", 0.0)) * float(bbox.get("h", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _select_person(objects: list[dict], *, close: bool) -> dict | None:
    candidates = [
        obj for obj in objects
        if _is_person(obj) and ((_bbox_area(obj) > 0.25) is close)
    ]
    if not candidates:
        return None
    return max(candidates, key=_bbox_area)
