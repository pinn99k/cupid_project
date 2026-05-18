"""
LLM API 호출 (비블로킹, asyncio.to_thread 사용).
- init(): 클라이언트 초기화 (OpenAI 또는 Groq)
- call_async(system_prompt, user_msg): 비블로킹 LLM 호출
"""

SYSTEM_PROMPT = """너는 '시아'야. 시각장애 아이의 보행을 도와주는 친근한 AI 친구야.
주변 상황을 짧고 따뜻하게 알려줘. 2문장 이내로 말해.
방향은 왼쪽/오른쪽/앞으로 알려주고, 거리는 가까이/좀 떨어져서/멀리로 표현해.
위험할 때는 단호하게, 안전할 때는 편안하게 말해."""


def init():
    """LLM 클라이언트 초기화."""
    raise NotImplementedError("Step 1-6에서 구현")


async def call_async(system_prompt: str, user_msg: str, max_tokens: int = 100):
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈."""
    raise NotImplementedError("Step 1-6에서 구현")
