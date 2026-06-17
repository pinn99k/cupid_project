"""
시아 인사말 한 줄("안녕 나는 시아야")을 Gemini TTS로 mp3 생성.
- 톤: 친근하고 차분하고, 기계 같지 않게 자연스러운 느낌 (스타일 프롬프트로 유도)
- 여러 목소리 후보를 한 번에 뽑아 비교 후 고를 수 있게 한다.
- Gemini PCM(24kHz/16bit/mono) -> lameenc 로 mp3 인코딩 (ffmpeg 불필요)

실행: venv/bin/python scripts/make_sia_intro.py
출력: audio/intro/sia_intro_<voice>.mp3
"""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lameenc
from google import genai
from google.genai import types

from server.config import GEMINI_API_KEY

TEXT = "안녕 나는 시아야"
TTS_MODEL = "gemini-2.5-flash-preview-tts"

# 차분 + 친근 + AI 티 안 나는 자연스러움을 유도하는 스타일 프롬프트.
# 들뜬/경쾌한 느낌을 확실히 빼고 톤을 낮춰 차분하게 가도록 강하게 지시.
STYLE_PROMPT = (
    "다음 문장을 아주 차분하고 나직한 목소리로 말해줘. 들뜨거나 신나거나 "
    "경쾌한 느낌은 전부 빼고, 톤을 살짝 낮춰서 편안하고 느긋하게. 문장 끝을 "
    "올리지 말고 차분하게 내려서, 친한 사람에게 조용히 인사를 건네듯 부드럽고 "
    "나긋나긋하게, 사람이 말하듯 자연스러운 호흡으로 천천히 말해줘. 밝고 들뜬 "
    "느낌이나 안내방송 같은 느낌은 절대 들어가면 안 돼."
)

# 시아 목소리(Aoede) 단일. TTS가 매번 달라서 같은 톤으로 여러 take를 뽑아 고른다.
VOICE = "Aoede"
TAKES = 3

OUTPUT_DIR = Path("audio/intro")
REQUEST_INTERVAL_SECONDS = 3

_client = genai.Client(api_key=GEMINI_API_KEY)


def synth_pcm(voice: str) -> bytes:
    """Gemini TTS 호출 -> 날것 PCM(24kHz/16bit/mono) 반환."""
    resp = _client.models.generate_content(
        model=TTS_MODEL,
        contents=f"{STYLE_PROMPT}\n\n문장: {TEXT}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    return resp.candidates[0].content.parts[0].inline_data.data


def pcm_to_mp3(pcm: bytes, out_path: Path, sample_rate: int = 24000) -> None:
    """PCM(16bit mono) -> mp3 파일."""
    enc = lameenc.Encoder()
    enc.set_bit_rate(192)
    enc.set_in_sample_rate(sample_rate)
    enc.set_channels(1)
    enc.set_quality(2)  # 0=best/slow, 9=worst/fast
    mp3 = enc.encode(pcm) + enc.flush()
    out_path.write_bytes(mp3)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f'생성: "{TEXT}"  (voice={VOICE}, 차분 take {TAKES}개)')
    ok = 0
    for take in range(1, TAKES + 1):
        out = OUTPUT_DIR / f"sia_intro_calm_{take}.mp3"
        try:
            pcm = synth_pcm(VOICE)
            pcm_to_mp3(pcm, out)
            size_kb = out.stat().st_size / 1024
            print(f"  [OK]   take {take} -> {out}  ({size_kb:.0f} KB)")
            ok += 1
        except Exception as e:
            out.unlink(missing_ok=True)
            print(f"  [FAIL] take {take}: {e}")
        time.sleep(REQUEST_INTERVAL_SECONDS)
    print(f"\n완료: {ok}/{TAKES}개 -> {OUTPUT_DIR}/")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
