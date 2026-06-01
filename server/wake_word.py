"""
호출어("시아야") 게이팅.
STT 결과에서 호출어를 찾아 질문만 추출한다.
- parse_wake_word(text):
    호출어 없음 → None  (무시)
    호출어 있음 → 그 뒤 질문 문자열 (질문 없으면 "")
"""

# 결정 A2: "시아야"만 호출어로 인정(엄격). false positive 최소화.
# (STT가 "시아야"를 놓치면 데모서 한 줄로 완화 가능)
WAKE_TOKENS = ("시아야",)

# 질문 앞뒤로 흔히 붙는 군더더기 문자
_STRIP_CHARS = " ,.!?~。、…"


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

    # 다중 공백 정규화
    normalized = " ".join(text.split())

    for token in WAKE_TOKENS:
        idx = normalized.find(token)
        if idx != -1:
            query = normalized[idx + len(token):]
            return query.strip(_STRIP_CHARS)

    return None


def is_wake(text: str | None) -> bool:
    """호출어 포함 여부만 빠르게 확인."""
    return parse_wake_word(text) is not None
