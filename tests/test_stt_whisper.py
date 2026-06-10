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


def test_whisper_passes_filter_thresholds_to_model():
    """환각 필터는 클라이언트 측 OR-필터가 아니라 faster-whisper 내부에 위임한다.
    (stt.py 주석 참고 — OR-필터는 실제 발화까지 버려서 제거됨)
    계약: 임계값이 model.transcribe() kwargs로 전달돼야 내부 AND 필터가 동작한다."""
    client = WhisperSTTClient(no_speech_threshold=0.7, logprob_threshold=-1.5)
    model = _FakeModel([_Seg("앞에 의자가 있어")])
    client._model = model
    client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))

    _audio, kwargs = model.calls[0]
    assert kwargs["no_speech_threshold"] == 0.7
    assert kwargs["log_prob_threshold"] == -1.5
    assert kwargs["condition_on_previous_text"] is False  # 환각 루프 방지


def test_whisper_no_client_side_segment_filter():
    """내부 필터를 통과해 나온 세그먼트는 확률값과 무관하게 그대로 사용한다.
    (과거의 no_speech_prob/avg_logprob 추가 OR-필터는 의도적으로 제거됨)"""
    client = WhisperSTTClient(no_speech_threshold=0.6, logprob_threshold=-1.0)
    client._model = _FakeModel([_Seg("감사합니다", no_speech_prob=0.95, avg_logprob=-3.0)])
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text == "감사합니다"
    assert client.last_status == "ok"


def test_whisper_empty_segments_returns_unrecognized():
    """내부 필터가 전부 걸러내(세그먼트 없음) 텍스트가 비면 None + unrecognized."""
    client = WhisperSTTClient()
    client._model = _FakeModel([])
    text = client._transcribe_sync(_make_wav(np.zeros(1600, dtype=np.int16)))
    assert text is None
    assert client.last_status == "unrecognized"


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
