"""
LLM API 호출 (비블로킹, asyncio.to_thread 사용).
- init(): 클라이언트 초기화 (OpenAI 또는 Groq)
- call_async(system_prompt, user_msg): 비블로킹 LLM 호출
"""

import asyncio
from openai import OpenAI
from server.config import LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, GROQ_API_KEY
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애 아이의 보행을 도와주는 친근한 AI 친구야.
주변 상황을 짧고 따뜻하게 알려줘. 2문장 이내로 말해.
방향은 왼쪽/오른쪽/앞으로 알려주고, 거리는 가까이/좀 떨어져서/멀리로 표현해.
위험할 때는 단호하게, 안전할 때는 편안하게 말해."""

client = None


def init():
    """LLM 클라이언트 초기화. API 키 없으면 경고만 출력 (TTS는 edge-tts라 키 불필요)."""
    global client
    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )
        print(f"[LLM] 초기화 완료: provider=groq, model={LLM_MODEL}")
    elif OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"[LLM] 초기화 완료: provider=openai, model={LLM_MODEL}")
    else:
        print("[LLM] 경고: API 키 미설정. LLM 기능 비활성 (TTS는 정상 작동)")


def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = 100) -> str | None:
    """동기 LLM 호출 (스레드 풀에서 실행됨)."""
    try:
        log("llm_start")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=max_tokens,
            temperature=0.7
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
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈."""
    return await asyncio.to_thread(_call_sync, system_prompt, user_msg, max_tokens)
