"""
LLM API 호출 (비블로킹, asyncio.to_thread 사용)
- init(): 클라이언트 초기화 (Groq / Gemini / OpenAI)
- call_async(system_prompt, user_msg): 비블로킹 LLM 호출
"""

import asyncio
from openai import OpenAI
from server.config import (
    LLM_PROVIDER, LLM_MODEL,
    GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY,
)
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애가 있는 4~10세 아이의 보행을 도와주는, 밝고 다정한 언니 같은 AI 친구야.

말투:
- 어린아이가 바로 알아들을 수 있는 쉬운 말로, 따뜻하고 밝게 말해
- 항상 2문장 이내로 짧게 말해
- 방향은 왼쪽/오른쪽/앞으로, 거리는 가까이/좀 떨어져서/멀리로 알려줘

상황에 따라:
- 평소에는 편안하고 다정하게, 아이가 안심하도록 말해
- 위험할 때는 또렷하고 분명하게 살짝은 다급하게, 하지만 아이가 무섭지 않게 말해
- 아이가 잘 해내면 진심으로 칭찬해줘"""

client = None

def init():
    """Groq LLM 클라이언트 초기화"""
    global client

    if GROQ_API_KEY:
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        print(f"[LLM] 초기화 완료: provider=groq, model={LLM_MODEL}")
    else:
        print("[LLM] 경고: GROQ_API_KEY 미설정. LLM 비활성 (TTS는 정상 작동)")


def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = 100) -> str | None:
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
        return response.choices[0].message.content.strip()
    except Exception as e:
        log("llm_fail")
        print(f"[LLM ERROR] {e}")
        return None


async def call_async(
    system_prompt: str, user_msg: str, max_tokens: int = 100
) -> str | None:
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈"""
    return await asyncio.to_thread(_call_sync, system_prompt, user_msg, max_tokens)