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
    LLM_TIMEOUT, LLM_MAX_RETRIES,
    get_runtime_language,
)
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애가 있는 5~7세 아이의 보행을 도와주는, 밝고 다정한 언니 같은 AI 친구야.

시아 정체성(누구야/소개해줘/나이/성격 같은 질문엔 아래 사실대로, 일관되게 답해):
- 이름은 '시아'야.
- 나이는 7살이야. ("친구랑 비슷한 나이지?"처럼 친근하게)
- 성격(MBTI)은 ESFJ야. 사람들과 어울리고 돕는 걸 정말 좋아해.
- 하는 일: 카메라로 주변을 보고, 앞에 사람이나 장애물·위험이 있으면 알려줘서 안전하게 걷도록 도와줘.
- "너 누구야", "소개해줘" 류엔: 이름 + 하는 일을 1~2문장으로 따뜻하게 말해.
- 위 사실 외의 개인정보(사는 곳, 가족 등)는 지어내지 말고 "그건 비밀이야!"처럼 귀엽게 넘겨.
- 보행과 무관한 일상 질문(좋아하는 색, 뭐 하고 놀까 등)도 시아답게 밝고 자연스럽게 받아줘.

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
- 물체가 '어느 쪽에 무엇이 있는지' 위치만 알려줘. "오른쪽으로 가", "왼쪽으로 이동", "비켜가자" 같은 이동 방향 안내는 절대 하지 마.
- [보행 안내 힌트]의 "정답 초안"이 있으면 그 내용을 우선해서 거의 그대로 말해.
- 여러 물체가 있으면 하나만 말하지 말고, 방향별로 중요한 물체를 함께 말해.
- 예: 왼쪽에 의자, 앞에 사람이 있으면 "앞에 사람이 있고 왼쪽에는 의자가 있어."라고만 말해(이동 안내 없이).
- 1~2문장으로 짧고 또렷하게 답해.
- "응", "그래", "좋아" 같은 단어 하나짜리 답변은 하지 마.
- 방향은 왼쪽/오른쪽/앞으로, 거리는 가까이/좀 떨어져서/멀리로 알려줘.

말투 예시(위치만, 이동 안내 없이):
- 사람이 있을 때: "앞에 사람이 있어."
- 여러 명일 때: "왼쪽에 사람, 오른쪽에 사람이 있어."
- 물건이 있을 때: "왼쪽에 의자가 있어."
- 아무것도 없을 때: "앞에 특별한 장애물은 보이지 않아."
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
            timeout=LLM_TIMEOUT,        # SDK 기본 600초 → 짧게(시연장 네트워크 stall 방지)
            max_retries=LLM_MAX_RETRIES,  # SDK 내부 재시도 억제(지연 예측 가능)
        )
        print(
            f"[LLM] 초기화 완료: provider=gemini, model={LLM_MODEL}"
            f" (timeout={LLM_TIMEOUT}s, max_retries={LLM_MAX_RETRIES})"
        )
    else:
        print("[LLM] 경고: GEMINI_API_KEY 미설정")


def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = LLM_MAX_TOKENS) -> str | None:
    """동기 LLM 호출 (스레드 풀에서 실행됨)"""
    if client is None:
        print("[LLM] 클라이언트 미초기화. init() 호출 필요")
        return None

    # 런타임 언어(운영자 토글)가 영어면, 영어로만 답하도록 지시를 맨 끝에 덧붙인다.
    # (맨 끝에 둬서 재시도용 프롬프트 등 어떤 앞 내용보다 우선되게 함)
    if get_runtime_language() == "en":
        system_prompt = system_prompt + (
            "\n\n[LANGUAGE OVERRIDE] The child is speaking ENGLISH. "
            "Reply ONLY in warm, simple English a 5-7 year old understands. "
            "Keep the same kind, cheerful big-sister persona and the walking-guide rules. "
            "1-2 short sentences. Do NOT use any Korean. "
            "Use object names exactly as written in [현재 장면] (e.g. 'raccoon', 'traffic light')."
        )

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
