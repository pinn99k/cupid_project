"""
영어 안내 멘트를 '네이티브 영어 + 차분한 톤'으로 생성.
- 스타일 지시는 영어로 (한국어 프롬프트는 영어를 한국어 억양으로 읽게 만듦).
- 천천히/나긋나긋 같은 과장 제거 -> 자연스러운 보통 속도, 느끼함 없음.
- 마감은 무음 트림 + 끝 페이드만. 과한 시간압축 안 함.
- 차분/따뜻 계열 다국어 보이스 여러 개로 뽑아 비교(Whisper로 발음 검수).

실행: venv/bin/python scripts/make_braille_ment.py
출력: audio/intro/braille_<voice>.mp3
"""

from pathlib import Path
import sys
import time

import numpy as np
import lameenc
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter
from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.config import GEMINI_API_KEY

TEXT = "A braille block is one meter away, near your right foot."
SYLLABLES = 13
TTS_MODEL = "gemini-2.5-flash-preview-tts"
SR = 24000
OUTPUT_DIR = Path("audio/intro")

# 차분/따뜻/또렷 계열. 톤은 프롬프트로 통일하고, 음색만 다르게 비교.
VOICES = ["Achird", "Sulafat", "Callirrhoe", "Despina", "Charon", "Schedar"]

# 너무 느리게 나온 take만 살짝 당김(과압축 방지용 상한). 보통은 트림/페이드만.
SLOW_CAP_S = 4.6        # 이보다 길면
NATURAL_S = 4.1         # 이 길이로 가볍게 당김

# 영어 네이티브 발음 + 차분/따뜻/자연스러움. breathy/syrupy/announcement 금지.
STYLE_PROMPT = (
    "Read this sentence in natural, native American English, the way a real "
    "person would actually say it out loud. Use a calm, warm, friendly tone, "
    "like a helpful companion quietly letting someone know where something is. "
    "Keep a relaxed, natural pace: not rushed, but not dragging either. Sound "
    "clear, grounded, and genuine. Do not sound breathy, syrupy, theatrical, "
    "over-soft, or like a robotic public-address announcement."
)

_client = genai.Client(api_key=GEMINI_API_KEY)


def synth_pcm(voice: str) -> np.ndarray:
    resp = _client.models.generate_content(
        model=TTS_MODEL,
        contents=f'{STYLE_PROMPT}\n\nSentence: "{TEXT}"',
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    raw = resp.candidates[0].content.parts[0].inline_data.data
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def trim(pcm: np.ndarray) -> np.ndarray:
    """앞뒤 무음 컷(여운 보존)."""
    fl = int(SR * 0.02)
    rms = np.array([np.sqrt(np.mean(pcm[i:i + fl] ** 2)) for i in range(0, len(pcm), fl)])
    peak = np.abs(pcm).max()
    sf = np.argmax(rms > peak * 0.03)
    ef = len(rms) - 1 - np.argmax(rms[::-1] > peak * 0.008)
    s = max(0, int(sf * 0.02 * SR - 0.03 * SR))
    e = min(len(pcm), int((ef + 1) * 0.02 * SR + 0.05 * SR))
    return pcm[s:e]


def maybe_speedup(pcm: np.ndarray) -> tuple[np.ndarray, float]:
    """너무 길면 NATURAL_S로 가볍게 당김(음정 유지). 반환 (pcm, 배속)."""
    dur = len(pcm) / SR
    if dur <= SLOW_CAP_S:
        return pcm, 1.0
    speed = dur / NATURAL_S
    r = ArrayReader(pcm.reshape(1, -1)); w = ArrayWriter(channels=1)
    wsola(channels=1, speed=speed).run(r, w)
    return w.data.reshape(-1), speed


def fade_out(pcm: np.ndarray, sec: float = 0.06) -> np.ndarray:
    n = int(SR * sec)
    if len(pcm) < n:
        return pcm
    pcm = pcm.copy()
    pcm[-n:] *= np.cos(np.linspace(0, np.pi / 2, n))
    return pcm


def write_mp3(pcm: np.ndarray, out: Path) -> float:
    i16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(192); enc.set_in_sample_rate(SR)
    enc.set_channels(1); enc.set_quality(2)
    out.write_bytes(enc.encode(i16.tobytes()) + enc.flush())
    return len(i16) / SR


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f'생성: "{TEXT}"  (영어 네이티브 톤)')
    for v in VOICES:
        out = OUTPUT_DIR / f"braille_{v.lower()}.mp3"
        try:
            pcm = trim(synth_pcm(v))
            pcm, speed = maybe_speedup(pcm)
            dur = write_mp3(fade_out(pcm), out)
            tag = f" (x{speed:.2f} 당김)" if speed != 1.0 else ""
            print(f"  [{v:12s}] {out.name}  {dur:.2f}s  {SYLLABLES/dur:.1f}음절/초{tag}")
        except Exception as e:
            out.unlink(missing_ok=True)
            print(f"  [{v:12s}] 실패: {e}")
        time.sleep(3)


if __name__ == "__main__":
    main()
