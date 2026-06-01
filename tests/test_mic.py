"""
server/mic.py 단위 테스트.
하드웨어 불필요 — sounddevice mock 사용.
"""

import asyncio
import io
import wave
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# 프로젝트 루트를 sys.path에 추가
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# sounddevice를 import 전에 mock 처리 (하드웨어 없는 환경 대비)
import unittest.mock as _mock
_sd_mock = _mock.MagicMock()
sys.modules.setdefault("sounddevice", _sd_mock)

from server.mic import MicCapture


# ---------------------------------------------------------------------------
# MicCapture.__init__ 테스트
# ---------------------------------------------------------------------------

class TestMicCaptureInit:
    """생성자 파라미터 및 기본값 검증."""

    def test_default_params(self):
        mic = MicCapture()
        assert mic.device_index is None
        assert mic.sample_rate == 16000
        assert mic.silence_threshold == 100
        assert mic.silence_duration == 1.5
        assert mic.max_duration == 10

    def test_custom_params(self):
        mic = MicCapture(
            device_index=2,
            sample_rate=44100,
            silence_threshold=300,
            silence_duration=2.0,
            max_duration=20,
        )
        assert mic.device_index == 2
        assert mic.sample_rate == 44100
        assert mic.silence_threshold == 300
        assert mic.silence_duration == 2.0
        assert mic.max_duration == 20

    def test_device_index_none_by_default(self):
        mic = MicCapture()
        assert mic.device_index is None


# ---------------------------------------------------------------------------
# _to_wav_bytes 테스트
# ---------------------------------------------------------------------------

class TestToWavBytes:
    """numpy array → WAV bytes 변환 검증."""

    def test_returns_bytes(self):
        mic = MicCapture()
        audio = np.zeros(16000, dtype=np.int16)
        result = mic._to_wav_bytes(audio)
        assert isinstance(result, bytes)

    def test_valid_wav_header(self):
        """반환된 bytes가 올바른 WAV 파일인지 wave 모듈로 검증."""
        mic = MicCapture()
        audio = np.random.randint(-1000, 1000, 8000, dtype=np.int16)
        wav_bytes = mic._to_wav_bytes(audio)

        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2       # int16 = 2 bytes
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 8000

    def test_custom_sample_rate(self):
        """sample_rate가 WAV 헤더에 반영되는지 확인."""
        mic = MicCapture(sample_rate=44100)
        audio = np.zeros(1000, dtype=np.int16)
        wav_bytes = mic._to_wav_bytes(audio)

        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 44100

    def test_nonempty_output(self):
        mic = MicCapture()
        audio = np.array([100, 200, -100], dtype=np.int16)
        result = mic._to_wav_bytes(audio)
        assert len(result) > 44  # WAV 헤더(44 bytes) 이상


# ---------------------------------------------------------------------------
# list_devices 테스트
# ---------------------------------------------------------------------------

class TestListDevices:
    """list_devices() 반환값 검증."""

    def test_returns_list(self):
        """반환 타입이 list인지 확인."""
        with patch("server.mic.sd") as mock_sd:
            # 입력 장치 1개, 출력 전용 1개
            mock_sd.query_devices.return_value = [
                {"name": "Mic A", "max_input_channels": 2, "default_samplerate": 44100.0},
                {"name": "Speaker B", "max_input_channels": 0, "default_samplerate": 44100.0},
            ]
            result = MicCapture.list_devices()

        assert isinstance(result, list)

    def test_filters_output_only_devices(self):
        """출력 전용 장치는 목록에서 제외되는지 확인."""
        with patch("server.mic.sd") as mock_sd:
            mock_sd.query_devices.return_value = [
                {"name": "Mic A", "max_input_channels": 2, "default_samplerate": 44100.0},
                {"name": "Speaker B", "max_input_channels": 0, "default_samplerate": 44100.0},
                {"name": "Mic C", "max_input_channels": 1, "default_samplerate": 16000.0},
            ]
            result = MicCapture.list_devices()

        assert len(result) == 2
        names = [d["name"] for d in result]
        assert "Mic A" in names
        assert "Mic C" in names
        assert "Speaker B" not in names

    def test_dict_has_required_keys(self):
        """반환 dict에 필수 키가 포함되는지 확인."""
        with patch("server.mic.sd") as mock_sd:
            mock_sd.query_devices.return_value = [
                {"name": "Mic A", "max_input_channels": 2, "default_samplerate": 44100.0},
            ]
            result = MicCapture.list_devices()

        assert len(result) == 1
        dev = result[0]
        assert "index" in dev
        assert "name" in dev
        assert "max_input_channels" in dev
        assert "default_samplerate" in dev

    def test_empty_when_no_input_devices(self):
        """입력 장치가 없으면 빈 리스트 반환."""
        with patch("server.mic.sd") as mock_sd:
            mock_sd.query_devices.return_value = [
                {"name": "Speaker", "max_input_channels": 0, "default_samplerate": 44100.0},
            ]
            result = MicCapture.list_devices()

        assert result == []


# ---------------------------------------------------------------------------
# _record_sync 테스트 (sounddevice mock)
# ---------------------------------------------------------------------------

class TestRecordSync:
    """_record_sync() 블로킹 녹음 로직 검증 (하드웨어 mock)."""

    def _make_chunk(self, rms_value: int, size: int = 1024) -> np.ndarray:
        """지정한 RMS 수준의 chunk를 생성 (근사값)."""
        arr = np.full(size, rms_value, dtype=np.int16)
        return arr.reshape(-1, 1)  # InputStream은 (frames, channels) 반환

    def test_returns_none_when_no_speech(self):
        """무음만 있을 때 None 반환."""
        mic = MicCapture(max_duration=0.1)  # 짧은 max_duration

        silent_chunk = self._make_chunk(0)

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.return_value = (silent_chunk, False)

        with patch("server.mic.sd.InputStream", return_value=mock_stream):
            result = mic._record_sync()

        assert result is None

    def test_returns_wav_bytes_after_speech(self):
        """음성 → 무음 순서로 WAV bytes 반환."""
        mic = MicCapture(
            silence_threshold=100,
            silence_duration=0.1,  # 빠른 종료
            max_duration=5,
        )

        # 음성 chunk (RMS > 100)
        speech_chunk = self._make_chunk(500)
        # 무음 chunk (RMS < 100) — silence_frames_limit 초과 분량
        silent_chunk = self._make_chunk(0)

        # 음성 3번 → 무음 충분히
        chunks = [speech_chunk] * 3 + [silent_chunk] * 20

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.side_effect = [(c, False) for c in chunks]

        with patch("server.mic.sd.InputStream", return_value=mock_stream):
            result = mic._record_sync()

        assert result is not None
        assert isinstance(result, bytes)
        # 유효한 WAV인지 확인
        buf = io.BytesIO(result)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1

    def test_returns_none_on_exception(self):
        """InputStream 오류 시 None 반환 (예외 전파 없음)."""
        mic = MicCapture()

        with patch("server.mic.sd.InputStream", side_effect=Exception("장치 없음")):
            result = mic._record_sync()

        assert result is None
        assert "장치 없음" in mic.last_error

    def test_includes_pre_roll_before_speech(self):
        """임계값을 넘기 직전 오디오를 포함해 호출어 첫 음절 잘림을 방지."""
        mic = MicCapture(
            silence_threshold=100,
            silence_duration=0.1,
            max_duration=5,
        )
        quiet_lead = self._make_chunk(50)
        speech_chunk = self._make_chunk(500)
        silent_chunk = self._make_chunk(0)
        chunks = [quiet_lead, speech_chunk] + [silent_chunk] * 20

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.side_effect = [(chunk, False) for chunk in chunks]

        with patch("server.mic.sd.InputStream", return_value=mock_stream):
            result = mic._record_sync()

        with wave.open(io.BytesIO(result), "rb") as wf:
            samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        assert samples[0] == 50

    def test_formats_macos_portaudio_error_with_hints(self):
        """macOS PortAudio 입력 오류에는 권한/장치 안내를 덧붙인다."""
        message = MicCapture._format_recording_error(
            Exception("PaMacCore error -50")
        )

        assert "macOS 마이크 권한" in message
        assert "MIC_DEVICE_INDEX" in message


# ---------------------------------------------------------------------------
# listen() 비동기 테스트
# ---------------------------------------------------------------------------

class TestListen:
    """listen()이 비동기이고 _record_sync를 to_thread로 실행하는지 검증."""

    def test_listen_is_coroutine(self):
        """listen()이 coroutine을 반환하는지 확인."""
        import inspect
        mic = MicCapture()
        coro = mic.listen()
        assert inspect.iscoroutine(coro)
        coro.close()  # 실행 없이 정리

    def test_listen_calls_record_sync(self):
        """listen() 실행 시 _record_sync가 호출되는지 확인."""
        mic = MicCapture()
        expected = b"FAKE_WAV_BYTES"

        with patch.object(mic, "_record_sync", return_value=expected) as mock_sync:
            result = asyncio.run(mic.listen())

        mock_sync.assert_called_once()
        assert result == expected

    def test_listen_returns_none_on_no_speech(self):
        """_record_sync가 None 반환 시 listen()도 None 반환."""
        mic = MicCapture()

        with patch.object(mic, "_record_sync", return_value=None):
            result = asyncio.run(mic.listen())

        assert result is None
