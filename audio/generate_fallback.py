"""
Gemini TTS 기반 fallback 오디오 사전 생성.
실행: venv/bin/python audio/generate_fallback.py
생성 위치: audio/fallback/*.wav
"""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_core.tts import TTS_MODEL, TTS_VOICE, generate_wav

OUTPUT_DIR = Path("audio/fallback")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_INTERVAL_SECONDS = 7

SCRIPTS = {
    # 시연 필수 음원을 먼저 생성
    "warn_emergency": "멈춰!",
    "warn_object": "앞에 장애물이 있어, 조심해",
    "warn_person": "앞에 사람이 있어, 천천히",
    "buffer_01": "잠깐만, 보고 있어",
    "praise_01": "잘하고 있어!",
    "gala_01": "시아와 함께 걸어볼까?",
    "gala_03": "오늘 연습 끝! 정말 잘했어",
    "warn_obstacle": "조심해, 앞에 뭔가 있어",
    "warn_close": "너무 가까워, 멈춰",
    "warn_stairs": "계단이야, 조심해",
    "praise_02": "대단해, 혼자서 잘 걷고 있어",
    "praise_03": "아주 잘했어!",
    "praise_04": "용감하다! 계속 가보자",
    "praise_05": "완벽해, 그렇게 하면 돼",
    "session_start": "안녕! 오늘도 같이 걸어보자",
    "session_end": "오늘 정말 잘했어, 다음에 또 만나자",
    "session_pause": "잠깐 쉬었다 가자",
    "buffer_02": "기다려봐, 확인하고 있어",
    "buffer_03": "알겠어, 잠깐만",
    "buffer_04": "음, 한번 볼게",
    "gala_02": "잘했어, 장애물을 피해서 걸었어",
}


def main():
    print(f"Gemini fallback 오디오 생성 중... (model={TTS_MODEL}, voice={TTS_VOICE})")
    for stale in OUTPUT_DIR.glob("*.mp3"):
        if stale.stat().st_size == 0:
            stale.unlink()
    generated = 0
    for key, text in SCRIPTS.items():
        output_path = OUTPUT_DIR / f"{key}.wav"
        if output_path.exists() and output_path.stat().st_size > 44:
            print(f"  [SKIP] {key}")
            generated += 1
            continue
        try:
            if generate_wav(text, output_path):
                print(f"  [OK]   {key}: {text}")
                generated += 1
            else:
                output_path.unlink(missing_ok=True)
                print(f"  [FAIL] {key}")
        except Exception as e:
            output_path.unlink(missing_ok=True)
            print(f"  [FAIL] {key}: {e}")
        time.sleep(REQUEST_INTERVAL_SECONDS)
    print(f"\n완료: {generated}/{len(SCRIPTS)}개 파일 -> {OUTPUT_DIR}/")
    raise SystemExit(0 if generated == len(SCRIPTS) else 1)


if __name__ == "__main__":
    main()
