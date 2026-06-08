"""Gemini TTS로 시연용 사전 녹음 음성을 생성."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_core.tts import TTS_MODEL, TTS_VOICE, generate_wav
from server.demo_responses import DEMO_TEXT_MAP

OUTPUT_DIR = Path("server/demo_voices")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_INTERVAL_SECONDS = 6

SCRIPTS = DEMO_TEXT_MAP


def main():
    print(f"Gemini demo voice 생성 중... (model={TTS_MODEL}, voice={TTS_VOICE})")
    generated = 0
    for filename, text in SCRIPTS.items():
        output_path = OUTPUT_DIR / filename
        if output_path.exists() and output_path.stat().st_size > 44:
            print(f"  [SKIP] {filename}")
            generated += 1
            continue
        try:
            if generate_wav(text, output_path):
                print(f"  [OK]   {filename}: {text}")
                generated += 1
            else:
                output_path.unlink(missing_ok=True)
                print(f"  [FAIL] {filename}")
        except Exception as e:
            output_path.unlink(missing_ok=True)
            print(f"  [FAIL] {filename}: {e}")
        time.sleep(REQUEST_INTERVAL_SECONDS)
    print(f"\n완료: {generated}/{len(SCRIPTS)}개 파일 -> {OUTPUT_DIR}/")
    raise SystemExit(0 if generated == len(SCRIPTS) else 1)


if __name__ == "__main__":
    main()
