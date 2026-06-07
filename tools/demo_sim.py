"""
시연 시뮬레이터 — 마이크/웹캠 없이 STT 결과를 주입해 전 경로를 실제 구동.
LLM(gemini)·게이팅·VQA·되묻기는 진짜, TTS 생성만 목킹(유료 회피).
실행: venv/Scripts/python.exe tools/demo_sim.py
"""
import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_core.llm_client import init as llm_init
from server.voice_pipeline import VoicePipeline


class FakeMic:
    def __init__(self):
        self.last_rms = 2000.0
        self.last_error = None
        self._next = b"WAV"  # None이면 무음/오류

    async def listen(self):
        return self._next


class FakeSTT:
    def __init__(self):
        self.last_status = "ok"
        self._next = None  # 주입할 STT 텍스트

    async def transcribe(self, wav):
        return self._next


class FakeAudio:
    """오디오 매니저 목 — 실제 재생 없이 즉시 완료."""
    def play(self, *a, **k):
        return object()

    def play_path(self, *a, **k):
        return object()

    async def wait(self, req):
        return True

    async def wait_until_idle(self):
        return


class FakeTTS:
    async def get_or_create(self, text):
        return None  # 파일 없음 → 재생 스킵 (유료 TTS 회피)


SCENE_PERSON = {"objects": [{"label": "person", "direction": "center", "distance_est": "near"}],
                "ultrasonic_cm": None, "ultrasonic_target": None}
SCENE_CHAIR = {"objects": [{"label": "chair", "direction": "left", "distance_est": "mid"},
                           {"label": "bottle", "direction": "right", "distance_est": "near"}],
               "ultrasonic_cm": None, "ultrasonic_target": None}


async def main():
    llm_init()

    mic = FakeMic()
    stt = FakeSTT()
    audio = FakeAudio()
    scene_holder = {"scene": None, "ts": 0.0}
    qcount = {"n": 0}

    vp = VoicePipeline(
        mic=mic, stt=stt, tts_lock=asyncio.Lock(),
        audio_manager=audio,
        scene_provider=lambda: (scene_holder["scene"], scene_holder["ts"]),
        count_question=lambda: qcount.__setitem__("n", qcount["n"] + 1),
        scene_fresh_sec=2.0,
        low_volume_rms=800.0,
    )
    vp.start()  # 청취 활성화

    # 시나리오: (제목, stt텍스트, mic음량, stt상태, 장면, 장면나이초)
    NOW = lambda: time.time() * 1000
    scenarios = [
        ("1. 비호출(잡음)",        "오늘 날씨 정말 좋다",      2000, "ok",          None,         None),
        ("2. 호출+일반대화",        "시아야 안녕 잘 지냈어?",    2000, "ok",          None,         None),
        ("3. 호출어 오인식(시아)",   "시아 지금 뭐해",          2000, "ok",          None,         None),
        ("4. 호출만(질문없음)",      "시아야",                 2000, "ok",          None,         None),
        ("5. 비전질문+신선장면",     "시아야 앞에 뭐 있어?",     2000, "ok",          SCENE_PERSON, 0.2),
        ("6. 비전질문+장면없음",     "시아야 뭐가 보여?",        2000, "ok",          None,         None),
        ("7. 비전질문+오래된장면",   "시아야 앞에 뭐 있어?",     2000, "ok",          SCENE_CHAIR,  7.0),
        ("8. STT 시스템오류",       None,                    2000, "error",       None,         None),
        ("9. STT 인식불가(잡음)",    None,                    2000, "unrecognized",None,         None),
        ("10. 저음량",             "시아야 안녕",             300,  "ok",          None,         None),
        ("11. 캐시히트(2번 반복)",   "시아야 안녕 잘 지냈어?",    2000, "ok",          None,         None),
        ("12. 러시아(중간 '시아')",  "러시아 음식 좋아해",       2000, "ok",          None,         None),
    ]

    results = []
    for title, text, rms, status, scene, age in scenarios:
        # 입력 주입
        mic.last_rms = float(rms)
        mic._next = b"WAV" if (text is not None or status != "ok") else b"WAV"
        if status != "ok" and text is None:
            stt._next = None
        else:
            stt._next = text
        stt.last_status = status
        if scene is not None:
            scene_holder["scene"] = scene
            scene_holder["ts"] = NOW() - age * 1000
        else:
            scene_holder["scene"] = None
            scene_holder["ts"] = 0.0

        # 시나리오 간 쿨다운 리셋 (실제론 턴이 수초 간격이라 무관)
        vp._last_reprompt_at = 0.0

        # broadcast 캡처
        events = []
        async def cap(msg):
            events.append(msg)

        print("\n" + "=" * 70)
        print(f"▶ {title}   STT주입={text!r}")
        with patch("server.voice_pipeline.broadcast", side_effect=cap), \
             patch("ai_core.tts.get_tts_cache", return_value=FakeTTS()):
            await vp._run_one_turn()

        # 결과 요약
        types = [e["type"] for e in events]
        user_stt = next((e["message"] for e in events if e["type"] == "user_stt"), None)
        resp = next((e["message"] for e in events if e["type"] == "stt_response"), None)
        reprompt = next((e["reason"] for e in events if e["type"] == "voice_reprompt"), None)
        err = next((e["message"] for e in events if e["type"] == "error"), None)
        outcome = (
            f"되묻기[{reprompt}]={resp!r}" if reprompt else
            f"응답={resp!r}" if resp else
            f"오류={err}" if err else
            "무시(응답 없음)"
        )
        results.append((title, user_stt, outcome))
        print(f"   질문추출={user_stt!r}")
        print(f"   결과: {outcome}")

    lines = ["=" * 72, "시연 요약 (실제 LLM 호출)", "=" * 72]
    for title, q, outcome in results:
        lines.append(f"{title:26s} | 질문추출={q!r}")
        lines.append(f"{'':26s} | {outcome}")
    lines.append("")
    lines.append(f"질문 카운트(성공 답변 수): {qcount['n']}")
    report = "\n".join(lines)
    Path("tools/demo_out.txt").write_text(report, encoding="utf-8")
    print("\n[리포트 저장] tools/demo_out.txt")


if __name__ == "__main__":
    asyncio.run(main())
