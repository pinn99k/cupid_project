"""
호출어("시아야") 게이팅.
STT 결과에서 호출어를 찾아 질문만 추출한다.
- parse_wake_word(text):
    호출어 없음 → None  (무시)
    호출어 있음 → 그 뒤 질문 문자열 (질문 없으면 "")
"""

# STT가 "시아야"를 "시아", "시야", "씨아"처럼 자주 흔들어 적기 때문에
# 호출어 후보를 넓힌다. 긴 토큰을 먼저 검사해 "시아야"가 "시아"+"야"로 잘리지 않게 한다.
WAKE_TOKENS = (
    "시아야",
    "시야야",
    "씨아야",
    "지아야",
    "치아야",
    "씨야야",
    "시아여",
    "지야야",
    "치야야",
    "시아",
    "시야",
    "씨아",
    "지아",
    "치아",
    "씨야",
)

# 질문 앞뒤로 흔히 붙는 군더더기 문자
_STRIP_CHARS = " ,.!?~。、…"


def _compact_with_index(text: str) -> tuple[str, list[int]]:
    """공백을 제거한 문자열과 compact index -> 원문 index 매핑을 만든다."""
    chars = []
    index_map = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        chars.append(ch)
        index_map.append(idx)
    return "".join(chars), index_map


def _is_korean_or_alnum(ch: str) -> bool:
    return ch.isalnum() or ("가" <= ch <= "힣")


def parse_wake_word(text: str | None) -> str | None:
    """호출어 뒤의 질문을 반환. 호출어가 없으면 None.

    예)
        "시아야 앞에 뭐 있어?" -> "앞에 뭐 있어"
        "안녕 시아야 뭐해"     -> "뭐해"
        "시아야"               -> ""      (호출만, 질문 없음)
        "안녕하세요"           -> None    (호출 아님 → 무시)
    """
    if not text:
        return None

    # 다중 공백 정규화. 원문 index 계산이 쉬워지도록 strip만 먼저 적용한다.
    normalized = " ".join(text.split())
    if not normalized:
        return None

    compact, index_map = _compact_with_index(normalized)

    for token in WAKE_TOKENS:
        start = compact.find(token)
        while start != -1:
            # "러시아"처럼 단어 중간에 들어간 "시아"는 호출어로 보지 않는다.
            original_start = index_map[start]
            if (
                original_start > 0
                and not normalized[original_start - 1].isspace()
                and _is_korean_or_alnum(compact[start - 1])
            ):
                start = compact.find(token, start + 1)
                continue

            compact_end = start + len(token) - 1
            original_end = index_map[compact_end] + 1
            query = normalized[original_end:]

            # 짧은 후보("시아", "시야", "씨아") 뒤에 조사처럼 붙은 "야"가 있으면 제거.
            if token in {"시아", "시야", "씨아"} and query.startswith("야"):
                query = query[1:]
            return query.strip(_STRIP_CHARS)

    return None


def is_wake(text: str | None) -> bool:
    """호출어 포함 여부만 빠르게 확인."""
    return parse_wake_word(text) is not None
