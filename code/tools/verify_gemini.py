"""
Gemini 키 유료 티어 검증.
- LLM(generate_content) 1회 + TTS(audio) 1회 호출
- 'free_tier' / 'FreeTier' 문구가 429에 보이면 아직 무료 프로젝트
- TTS가 성공하면(오늘 무료 10회 이미 소진했다면) = billing 적용됨

실행: .\venv\Scripts\python.exe tools/verify_gemini.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import GEMINI_API_KEY, LLM_MODEL
from google import genai
from google.genai import types


def _is_free_tier_error(msg: str) -> bool:
    m = msg.lower()
    return "free_tier" in m or "freetier" in m


def check_llm(client) -> str:
    try:
        r = client.models.generate_content(model=LLM_MODEL, contents="한 단어로 인사해")
        return f"LLM OK  ({LLM_MODEL}) → {r.text!r}"
    except Exception as e:
        tier = "  ⚠️ FREE_TIER 한도" if _is_free_tier_error(str(e)) else ""
        return f"LLM 실패{tier}: {str(e)[:160]}"


def check_tts(client) -> str:
    try:
        r = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents="안녕, 반가워",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                    )
                ),
            ),
        )
        data = r.candidates[0].content.parts[0].inline_data.data
        return f"TTS OK  → 오디오 {len(data)} bytes  ✅ (무료 10회 소진 상태에서 성공 = 유료 적용됨)"
    except Exception as e:
        tier = "  ⚠️ FREE_TIER 한도 (= 아직 무료 프로젝트)" if _is_free_tier_error(str(e)) else ""
        return f"TTS 실패{tier}: {str(e)[:200]}"


def main():
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY 비어 있음 — .env 확인")
        return
    print(f"키 끝 4자리: ...{GEMINI_API_KEY[-4:]}")
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(check_llm(client))
    print(check_tts(client))


if __name__ == "__main__":
    main()
