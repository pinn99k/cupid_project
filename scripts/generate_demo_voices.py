"""Gemini TTS로 시연용 사전 녹음 음성을 생성."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_core.tts import TTS_MODEL, TTS_VOICE, generate_wav

OUTPUT_DIR = Path("server/demo_voices")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_INTERVAL_SECONDS = 6

SCRIPTS = {
    "greeting.wav": "안녕! 반가워! 나는 시아야.",
    "intro.wav": "나는 시아야, 시각장애 친구들이 안전하게 걸을 수 있게 도와주는 AI 친구야. 카메라로 주변을 보고 앞에 위험한 게 있으면 알려줄게!",
    "lets_go.wav": "응! 같이 가자, 흰지팡이 잘 잡고 천천히 가볼까?",
    "traffic_light.wav": "앞에 신호등이 보여! 기둥에 부딪히지 않게 오른쪽으로 살짝 비켜갈까?",
    "person_left_far.wav": "왼쪽에 친구가 보여! 오른쪽으로 가볼까?",
    "person_center_far.wav": "앞에 친구가 보여! 잠깐 멈춰서 비켜갈 길을 찾아볼까?",
    "person_right_far.wav": "오른쪽에 친구가 보여! 왼쪽으로 가볼까?",
    "arrival.wav": "다 왔어! 정말 잘했어!",
    "all_clear.wav": "앞에 아무것도 없어! 안전해, 천천히 가도 돼.",
    "fallback.wav": "응? 다시 한 번 말해줄래?",
    "person_left_close.wav": "잠깐! 왼쪽에 친구가 가까이 있어! 오른쪽으로 비켜가볼까?",
    "person_center_close.wav": "잠깐 멈춰! 앞에 친구가 너무 가까워!",
    "person_right_close.wav": "잠깐! 오른쪽에 친구가 가까이 있어! 왼쪽으로 비켜가볼까?",
}


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
