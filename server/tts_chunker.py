"""TTS용 문장 분할.

긴 LLM 응답을 한 번에 합성하면 첫 소리까지 오래 걸리고 발화가 부자연스럽다.
문장 단위로 쪼개 첫 문장을 먼저 합성·재생하고, 재생 중 다음 문장을 합성한다.
"""

from __future__ import annotations

import re

# 문장 끝 부호(한/영) 뒤 공백에서 분할. 부호는 앞 문장에 붙는다.
_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
# 너무 짧은 조각(감탄사 "응!", "그래." 등)은 인접 문장과 합쳐 끊김을 줄인다.
_MIN_LEN = 6


def split_sentences(text: str | None, min_len: int = _MIN_LEN) -> list[str]:
    """문장 리스트 반환.

    - 문장 끝 부호(. ! ? 。 ！ ？) 기준 분할, 부호는 앞 문장에 유지.
    - min_len 미만의 짧은 조각은 다음 조각과 병합(자연스러운 발화).
    - 부호가 없으면 전체를 한 문장으로 반환.
    - 빈 입력 → 빈 리스트.
    """
    if not text:
        return []
    normalized = " ".join(text.split())
    if not normalized:
        return []

    parts = _SPLIT_RE.split(normalized)

    merged: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        buf = f"{buf} {part}".strip() if buf else part
        if len(buf) >= min_len:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] = f"{merged[-1]} {buf}".strip()
        else:
            merged.append(buf)

    return merged or [normalized]
