"""
Fallback 오디오 사전 생성 스크립트 (edge-tts 사용, API 키 불필요).
실행: python audio/generate_fallback.py
생성 위치: audio/fallback/*.mp3
"""

import asyncio
from pathlib import Path

import edge_tts

VOICE = "ko-KR-SunHiNeural"  # ai_core/tts.py 와 동일한 음성
OUTPUT_DIR = Path("audio/fallback")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCRIPTS = {
    # 위험 경고 (5)
    "warn_emergency":   "멈춰!",
    "warn_obstacle":    "조심해, 앞에 뭔가 있어",
    "warn_person":      "앞에 사람이 있어, 천천히",
    "warn_close":       "너무 가까워, 멈춰",
    "warn_stairs":      "계단이야, 조심해",
    # 칭찬 격려 (5)
    "praise_01":        "잘하고 있어!",
    "praise_02":        "대단해, 혼자서 잘 걷고 있어",
    "praise_03":        "아주 잘했어!",
    "praise_04":        "용감하다! 계속 가보자",
    "praise_05":        "완벽해, 그렇게 하면 돼",
    # 세션 (3)
    "session_start":    "안녕! 오늘도 같이 걸어보자",
    "session_end":      "오늘 정말 잘했어, 다음에 또 만나자",
    "session_pause":    "잠깐 쉬었다 가자",
    # 대기 버퍼 (4)
    "buffer_01":        "잠깐만, 보고 있어",
    "buffer_02":        "기다려봐, 확인하고 있어",
    "buffer_03":        "알겠어, 잠깐만",
    "buffer_04":        "음, 한번 볼게",
    # 갈라쇼 전용 (3)
    "gala_01":          "시아와 함께 걸어볼까?",
    "gala_02":          "잘했어, 장애물을 피해서 걸었어",
    "gala_03":          "오늘 연습 끝! 정말 잘했어",
}


async def generate_one(key: str, text: str):
    output_path = OUTPUT_DIR / f"{key}.mp3"
    if output_path.exists():
        print(f"  [SKIP] {key}")
        return
    try:
        tts = edge_tts.Communicate(text=text, voice=VOICE)
        await tts.save(str(output_path))
        print(f"  [OK]   {key}: {text}")
    except Exception as e:
        print(f"  [FAIL] {key}: {e}")


async def main():
    print(f"Fallback 오디오 생성 중... (voice: {VOICE})")
    tasks = [generate_one(k, v) for k, v in SCRIPTS.items()]
    await asyncio.gather(*tasks)
    count = len(list(OUTPUT_DIR.glob("*.mp3")))
    print(f"\n완료: {count}/{len(SCRIPTS)}개 파일 → {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
