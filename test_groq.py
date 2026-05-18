import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SIA_PROMPT = """너는 시각장애 유아의 친구 '시아'야.

[성격]
- 7살 아이에게 말하듯 따뜻하고 친근하게
- 호기심 자극, 격려

[말투]
- 반말, 친근한 톤
- 2~3문장 이내로 짧게
- 어려운 단어 X
- 시각 표현 X
"""

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[
        {"role": "system", "content": SIA_PROMPT},
        {"role": "user", "content": "시아야 안녕"}
    ]
)

print("🤖 시아:", response.choices[0].message.content)