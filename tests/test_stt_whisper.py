"""server/stt.py 의 Whisper(faster-whisper) 경로 단위 테스트.

실제 모델을 로드하지 않는다 — model을 직접 주입(mock)하거나 import만 mock한다.
"""

import io
import sys
import types
import wave

import numpy as np
import pytest

from server.stt import (
    STTClient,
    WhisperSTTClient,
    _wav_to_float32,
    create_stt_client,
)


def _make_wav(samples: np.ndarray, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


class _Seg:
    def __init__(self, text, no_speech_prob=0.0, avg_logprob=0.0):
        self.text = text
        self.no_speech_prob = no_speech_prob
        self.avg_logprob = avg_logprob


class _FakeModel:
    """model.transcribe(audio, ...) → (segments, info) 모방."""

    def __init__(self, segments):
        self._segments = segments
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return iter(self._segments), {"language": "ko"}


# ── _wav_to_float32 ────────────────────────────────────────────────────────

def test_wav_to_float32_decodes_int16_mono():
    samples = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
    audio = _wav_to_float32(_make_wav(samples))
    assert audio.dtype == np.float32
    assert len(audio) == 5
    assert audio[0] == pytest.approx(0.0)
    assert audio[1] == pytest.approx(0.5, abs=1e-3)
    assert -1.0 <= audio.min() and audio.max() <= 1.0


# ── WhisperSTTClient 필터/폴백 ──────────────────────────────────────────────

def test_whisper_returns_joined_text():
    client = WhisperSTTClient()
    client._model = _FakeModel([_Seg("앞에"), _Seg("의자가 있어")])
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text == "앞에 의자가 있어"
    assert client.last_status == "ok"


def test_whisper_filters_high_no_speech_prob():
    client = WhisperSTTClient(no_speech_threshold=0.6)
    # 환각 의심 세그먼트(no_speech_prob 높음) 폐기
    client._model = _FakeModel([_Seg("감사합니다", no_speech_prob=0.95)])
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text is None
    assert client.last_status == "unrecognized"


def test_whisper_filters_low_logprob():
    client = WhisperSTTClient(logprob_threshold=-1.0)
    client._model = _FakeModel([_Seg("어쩌구", avg_logprob=-3.0)])
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text is None


def test_whisper_falls_back_to_google_on_error():
    fallback = STTClient()
    fallback._transcribe_sync = lambda wav: "폴백 결과"
    fallback.last_status = "ok"

    client = WhisperSTTClient(fallback=fallback)

    class _BoomModel:
        def transcribe(self, *a, **k):
            raise RuntimeError("model boom")

    client._model = _BoomModel()
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text == "폴백 결과"
    assert client.last_status == "ok"


def test_whisper_error_without_fallback_returns_none():
    client = WhisperSTTClient(fallback=None)

    class _BoomModel:
        def transcribe(self, *a, **k):
            raise RuntimeError("boom")

    client._model = _BoomModel()
    assert client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16))) is None
    assert client.last_status == "error"


# ── create_stt_client 팩토리 ────────────────────────────────────────────────

def test_factory_returns_google_for_google_engine():
    client = create_stt_client(engine="google", language="ko-KR")
    assert isinstance(client, STTClient)


def test_factory_falls_back_to_google_when_whisper_missing(monkeypatch):
    # faster_whisper import 실패 흉내
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    client = create_stt_client(engine="whisper", language="ko-KR")
    assert isinstance(client, STTClient)


def test_factory_returns_whisper_when_available(monkeypatch):
    # faster_whisper import 성공 흉내 (모델 로드는 transcribe 시점이라 여기선 안 함)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    client = create_stt_client(engine="whisper", language="ko-KR", model_size="small")
    assert isinstance(client, WhisperSTTClient)
    assert client._language == "ko"  # ko-KR → ko 변환
    assert isinstance(client._fallback, STTClient)  # google 폴백 내장
