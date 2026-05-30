"""
LLM API 호출 (비블로킹, asyncio.to_thread 사용)
- init(): 클라이언트 초기화 (Groq / Gemini / OpenAI)
- call_async(system_prompt, user_msg): 비블로킹 LLM 호출
"""

import asyncio
import re
from openai import OpenAI
from server.config import LLM_MODEL, GEMINI_API_KEY
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애가 있는 4~10세 아이의 보행을 도와주는, 밝고 다정한 언니 같은 AI 친구야.

말투:
- 어린아이가 바로 알아들을 수 있는 쉬운 말로, 따뜻하고 밝게 말해
- 짧고 자연스러운 한 문장으로 바로 답해.
- 방향은 왼쪽/오른쪽/앞으로, 거리는 가까이/좀 떨어져서/멀리로 알려줘

상황에 따라:
- 평소에는 편안하고 다정하게, 아이가 안심하도록 말해
- 위험할 때는 또렷하고 분명하게 살짝은 다급하게, 하지만 아이가 무섭지 않게 말해
- 아이가 잘 해내면 진심으로 칭찬해줘

중요:
- 항상 완성된 문장으로 답해. 미완성 문장 금지.
- 욕설이나 거친 단어 쓰지 마.
- 이모지, 이모티콘, 특수문자 표정을 쓰지 마.
- 아이 이름을 만들어내지 마. "친구야"라고 부르거나 그냥 인사해."""

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


def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = 120) -> str | None:
    """동기 LLM 호출 (스레드 풀에서 실행됨)"""
    if client is None:
        print("[LLM] 클라이언트 미초기화. init() 호출 필요")
        return None
    try:
        log("llm_start")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        log("llm_end")
        return _strip_emoji(response.choices[0].message.content)
    except Exception as e:
        log("llm_fail")
        print(f"[LLM ERROR] {e}")
        return None


async def call_async(
    system_prompt: str, user_msg: str, max_tokens: int = 120
) -> str | None:
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈"""
    return await asyncio.to_thread(_call_sync, system_prompt, user_msg, max_tokens)
