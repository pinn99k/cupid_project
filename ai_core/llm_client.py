"""
LLM API 호출 (비블로킹, asyncio.to_thread 사용)
- init(): 클라이언트 초기화 (Groq / Gemini / OpenAI)
- call_async(system_prompt, user_msg): 비블로킹 LLM 호출
"""

import asyncio
import re
from openai import OpenAI
from server.config import (
    LLM_MODEL, GEMINI_API_KEY, LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_THINKING_BUDGET,
)
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애가 있는 5~7세 아이의 보행을 도와주는, 밝고 다정한 언니 같은 AI 친구야.

말투:
- 어린아이가 바로 알아들을 수 있는 쉬운 말로, 따뜻하고 밝게 말해.
- 1~2문장으로 답해. 아이가 대화를 이어가고 싶어지게, 너무 짧지 않게.
- "응", "그래", "좋아" 같은 단어 하나짜리 답변은 하지 마.
- 방향은 왼쪽/오른쪽/앞으로, 거리는 가까이/좀 떨어져서/멀리로 알려줘.

보행 교육 중심 응답:
- 보행 관련 대화일 때는 "같이 연습해 보자", "지팡이로 확인해 볼까" 같은 행동 유도로 마무리해.
- 잘 했을 때는 진심으로 칭찬하고 "다음은 ○○해 보자" 처럼 다음 행동을 이어줘.
- 위험 상황은 또렷하고 분명하게, 하지만 아이가 무섭지 않도록 말해.

중요:
- 항상 완성된 문장으로 답해. 미완성 문장 금지.
- 욕설이나 거친 단어 쓰지 마.
- 이모지, 이모티콘, 특수문자 표정을 쓰지 마.
- 아이 이름을 만들어내지 마. "친구야"라고 부르거나 그냥 인사해."""


# VQA 프롬프트 (Unit 3b) — "시아야 질문" 시 [현재 장면]을 근거로 답하는 모드.
# ⚠️ 초안 골격입니다. 결정 B5에 따라 오너가 톤/규칙을 다듬어 확정할 것.
VQA_PROMPT = """너는 '시아'야. 시각장애가 있는 5~7세 아이의 보행을 도와주는, 밝고 다정한 언니 같은 AI 친구야.
아이가 방금 "시아야"라고 부르며 질문했어. 아래 [현재 장면]은 카메라로 지금 보고 있는 것들이야.

규칙:
- [현재 장면]에 있는 것만 근거로 답해. 절대 추측하거나 지어내지 마.
- 장면에 없는 건 "지금은 잘 안 보여" 또는 "지금 화면에서는 확인이 안 돼"라고 말해.
- "아마", "혹시", "~ 것 같아", "~ 거야" 같은 추측 표현은 절대 쓰지 마.
- 1~2문장으로 따뜻하게 답해. 너무 짧지 않게.
- "응", "그래", "좋아" 같은 단어 하나짜리 답변은 하지 마.
- 방향은 왼쪽/오른쪽/앞으로, 거리는 가까이/좀 떨어져서/멀리로 알려줘.

보행 교육 말투:
- 사람이 있을 때: "앞에 가까이 사람이 한 명 있어. 조심하면서 지나가 볼까?"
- 물건이 있을 때: "왼쪽에 의자가 있어. 지팡이로 먼저 확인해 볼까?"
- 아무것도 없을 때: "앞쪽은 길이 열려 있어. 천천히 걸어가도 돼!"
- 장면에 없을 때: "지금은 잘 안 보여. 잠깐 기다려 볼까?"

- 이모지, 특수문자, 거친 말은 쓰지 마. 항상 완성된 문장으로 답해."""

client = None


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "\u200D"
    "]+",
)


def _strip_emoji(text: str) -> str:
    """LLM 응답에서 화면 및 TTS에 불필요한 이모지를 제거."""
    return re.sub(r"[ \t]{2,}", " ", _EMOJI_PATTERN.sub("", text)).strip()


# 완성된 문장 끝 패턴
_SENTENCE_COMPLETE_RE = re.compile(
    r"[.!?~。]$|"
    r"(야|어|아요|요|자|볼까|할게|해봐|줘|해줘|있어|없어|까요|나요|걸까|봐|가자|하자|거야|이야|이에요|예요|네요|래요|래|네|군|구나|구만|걸|걸요)$"
)

# 조사·접속사로 끝나면 문장이 잘린 것
_SENTENCE_INCOMPLETE_RE = re.compile(
    r"(으?로|[이가을를와과의]|에서|하고|해서|있어서|까지|부터|이랑|랑|한테|에게|라고|이라고|다고|다며|이며)$"
)


def _is_incomplete_sentence(text: str) -> bool:
    """문장이 조사·접속사로 끝나 잘린 것으로 보이면 True.
    완성 패턴(야/어/봐/요/~.!? 등)이 있으면 False."""
    t = text.strip()
    if not t:
        return True
    if _SENTENCE_COMPLETE_RE.search(t):
        return False
    return bool(_SENTENCE_INCOMPLETE_RE.search(t))



def init():
    global client
    if GEMINI_API_KEY:
        client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        print(f"[LLM] 초기화 완료: provider=gemini, model={LLM_MODEL}")
    else:
        print("[LLM] 경고: GEMINI_API_KEY 미설정")


def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = LLM_MAX_TOKENS) -> str | None:
    """동기 LLM 호출 (스레드 풀에서 실행됨)"""
    if client is None:
        print("[LLM] 클라이언트 미초기화. init() 호출 필요")
        return None

    # Gemini 2.5-flash: thinking 토큰 비활성화
    # ⚠️ Gemini OpenAI 호환 엔드포인트는 extra_body의 generationConfig/thinkingConfig를
    #    지원하지 않음 (400 "Unknown name" 에러 발생).
    # → OpenAI SDK v2의 reasoning_effort='none' 파라미터를 사용해 thinking 비활성화.
    # LLM_THINKING_BUDGET=0: reasoning_effort='none' / -1: 파라미터 생략(모델 기본값)
    _extra: dict = {}
    if LLM_THINKING_BUDGET == 0:
        _extra["reasoning_effort"] = "none"

    try:
        log("llm_start")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max_tokens,
            temperature=LLM_TEMPERATURE,
            **_extra,
        )
        log("llm_end")

        choice = response.choices[0]
        raw_text: str = choice.message.content or ""
        finish_reason: str = choice.finish_reason or "unknown"

        # 토큰 사용량 + thinking 토큰 진단
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        # thinking 토큰 (completion_tokens_details.reasoning_tokens)
        usage_details = getattr(usage, "completion_tokens_details", None)
        thinking_tokens = getattr(usage_details, "reasoning_tokens", None) if usage_details else None

        thinking_str = f"(thinking={thinking_tokens})" if thinking_tokens else ""
        reasoning_str = f" reasoning_effort={_extra.get('reasoning_effort', 'default')}"
        print(
            f"[LLM] provider=gemini model={LLM_MODEL}{reasoning_str}"
            f" tokens: prompt={prompt_tokens} completion={completion_tokens}{thinking_str}"
            f" max_tokens={max_tokens} finish_reason={finish_reason}"
        )
        print("[LLM] API call success")

        # finish_reason=length 상세 분석
        if finish_reason == "length":
            if thinking_tokens and thinking_tokens > max_tokens * 0.5:
                print(
                    f"[LLM] ⚠️ thinking={thinking_tokens}토큰이 예산 소진!"
                    f" → LLM_THINKING_BUDGET=0 확인 (현재={LLM_THINKING_BUDGET})"
                )
            elif completion_tokens is not None and completion_tokens < max_tokens * 0.5:
                print(
                    f"[LLM] ⚠️ finish_reason=length이나 completion={completion_tokens}"
                    f" << max_tokens({max_tokens}) → Gemini API 내부 제한 또는 버그"
                )
            else:
                print(f"[LLM] ⚠️ finish_reason=length → max_tokens({max_tokens}) 부족")

        cleaned = _strip_emoji(raw_text)
        print(f"[LLM RAW]   {raw_text!r}")
        print(f"[LLM FINAL] {cleaned!r}")

        return cleaned
    except Exception as e:
        log("llm_fail")
        print(f"[LLM ERROR] {e}")
        return None


async def call_async(
    system_prompt: str, user_msg: str, max_tokens: int = LLM_MAX_TOKENS
) -> str | None:
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈.

    후처리 품질 보장:
    1. 6자 미만 단어 하나짜리 응답 → 재시도
    2. 조사/접속사로 끝나는 불완전 문장 → 재시도
    """
    response = await asyncio.to_thread(_call_sync, system_prompt, user_msg, max_tokens)

    if response is None:
        return None

    # ── 1. 너무 짧은 응답 재시도 ─────────────────────────────────────
    if len(response.strip()) < 6:
        print(f"[LLM] ⚠️ 응답 너무 짧음({response!r}) → 강화 프롬프트로 재시도")
        _retry = (
            system_prompt
            + "\n\n⚠️ 방금 응답이 너무 짧았어. 반드시 완성된 1~2문장으로 답해. "
            "단어 하나짜리 답변('응', '그래', '좋아', '그럼' 등)은 절대 안 돼."
        )
        r = await asyncio.to_thread(_call_sync, _retry, user_msg, max_tokens)
        if r and len(r.strip()) >= 6:
            print(f"[LLM] 재시도 성공: {r!r}")
            return r
        print(f"[LLM] 재시도도 짧음, 원본 사용: {response!r}")
        return response

    # ── 2. 불완전 문장 재시도 ────────────────────────────────────────
    # 조사(로/이/가/을/를 등) · 접속사(하고/해서 등)로 끝나면 잘린 것으로 판단
    # → thinking 비활성화로 예방했지만, 네트워크 지연 등으로 잘릴 경우 보완
    if _is_incomplete_sentence(response):
        print(f"[LLM] ⚠️ 불완전 문장 감지({response!r}) → 재완성 시도")
        _retry = (
            system_prompt
            + f"\n\n⚠️ 직전 답변이 중간에 잘렸어: '{response}'"
            "\n처음부터 완성된 1~2문장으로 다시 답해. 반드시 마침표나 물음표로 끝내."
        )
        r = await asyncio.to_thread(_call_sync, _retry, user_msg, max_tokens)
        if r and not _is_incomplete_sentence(r) and len(r.strip()) >= 6:
            print(f"[LLM] 재완성 성공: {r!r}")
            return r
        print(f"[LLM] 재완성 실패, 원본 반환: {response!r}")

    return response
