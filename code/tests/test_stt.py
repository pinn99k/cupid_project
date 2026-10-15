"""
server/stt.py 단위 테스트.
하드웨어 불필요 — speech_recognition mock 사용.
"""

import asyncio
import io
import sys
import os
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# speech_recognition을 import 전에 mock 처리 (패키지 미설치 환경 대비)
import unittest.mock as _mock
_sr_mock = _mock.MagicMock()
_sr_mock.UnknownValueError = type("UnknownValueError", (Exception,), {})
_sr_mock.RequestError = type("RequestError", (Exception,), {})
sys.modules.setdefault("speech_recognition", _sr_mock)

from server.stt import STTClient


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_wav_bytes(sample_rate: int = 16000, duration_frames: int = 8000) -> bytes:
    """테스트용 더미 WAV bytes 생성."""
    audio = np.zeros(duration_frames, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# STTClient.__init__ 테스트
# ---------------------------------------------------------------------------

class TestSTTClientInit:
    """생성자 및 기본값 검증."""

    def test_default_language(self):
        client = STTClient()
        assert client._language == "ko-KR"

    def test_custom_language(self):
        client = STTClient(language="en-US")
        assert client._language == "en-US"

    def test_recognizer_created(self):
        """_recognizer 속성이 생성되는지 확인."""
        client = STTClient()
        assert client._recognizer is not None


# ---------------------------------------------------------------------------
# transcribe() 비동기 테스트
# ---------------------------------------------------------------------------

class TestTranscribeAsync:
    """transcribe()가 비동기이고 _transcribe_sync를 to_thread로 실행하는지 검증."""

    def test_transcribe_is_coroutine(self):
        """transcribe()가 coroutine을 반환하는지 확인."""
        import inspect
        client = STTClient()
        wav = _make_wav_bytes()
        coro = client.transcribe(wav)
        assert inspect.iscoroutine(coro)
        coro.close()

    def test_transcribe_returns_text(self):
        """정상 인식 시 텍스트 반환."""
        client = STTClient()

        with patch.object(client, "_transcribe_sync", return_value="안녕하세요") as mock_sync:
            result = asyncio.run(client.transcribe(_make_wav_bytes()))

        mock_sync.assert_called_once()
        assert result == "안녕하세요"

    def test_transcribe_returns_none_on_failure(self):
        """_transcribe_sync가 None 반환 시 transcribe()도 None."""
        client = STTClient()

        with patch.object(client, "_transcribe_sync", return_value=None):
            result = asyncio.run(client.transcribe(_make_wav_bytes()))

        assert result is None


# ---------------------------------------------------------------------------
# _transcribe_sync() 동기 로직 테스트 (speech_recognition mock)
# ---------------------------------------------------------------------------

class TestTranscribeSync:
    """_transcribe_sync() 세부 동작 검증."""

    def _make_client_with_mock_sr(self):
        """speech_recognition을 mock한 STTClient 반환."""
        import speech_recognition as sr
        client = STTClient()
        return client, sr

    def test_returns_recognized_text(self):
        """정상 인식 시 텍스트 반환."""
        client = STTClient()
        wav = _make_wav_bytes()

        with patch("server.stt.sr") as mock_sr:
            mock_sr.UnknownValueError = Exception
            mock_sr.RequestError = Exception

            mock_recognizer = MagicMock()
            mock_recognizer.record.return_value = MagicMock()
            mock_recognizer.recognize_google.return_value = "  횡단보도  "
            mock_sr.Recognizer.return_value = mock_recognizer
            mock_sr.AudioFile.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sr.AudioFile.return_value.__exit__ = MagicMock(return_value=False)

            client._recognizer = mock_recognizer

            # AudioFile context manager를 올바르게 mock
            audio_mock = MagicMock()
            mock_sr.AudioFile.return_value = audio_mock
            audio_mock.__enter__ = MagicMock(return_value=audio_mock)
            audio_mock.__exit__ = MagicMock(return_value=False)

            result = client._transcribe_sync(wav)

        assert result == "횡단보도"

    def test_returns_none_on_unknown_value_error(self):
        """UnknownValueError (인식 불가) → None 반환."""
        client = STTClient()
        wav = _make_wav_bytes()

        # 실제 sr 모듈의 예외 타입을 사용
        import speech_recognition as sr

        with patch("server.stt.sr") as mock_sr:
            UnknownValueError = type("UnknownValueError", (Exception,), {})
            RequestError = type("RequestError", (Exception,), {})
            mock_sr.UnknownValueError = UnknownValueError
            mock_sr.RequestError = RequestError

            mock_recognizer = MagicMock()
            mock_recognizer.recognize_google.side_effect = UnknownValueError("인식 불가")
            client._recognizer = mock_recognizer

            audio_mock = MagicMock()
            mock_sr.AudioFile.return_value = audio_mock
            audio_mock.__enter__ = MagicMock(return_value=audio_mock)
            audio_mock.__exit__ = MagicMock(return_value=False)

            result = client._transcribe_sync(wav)

        assert result is None

    def test_returns_none_on_request_error(self):
        """RequestError (API 통신 오류) → None 반환."""
        client = STTClient()
        wav = _make_wav_bytes()

        with patch("server.stt.sr") as mock_sr:
            UnknownValueError = type("UnknownValueError", (Exception,), {})
            RequestError = type("RequestError", (Exception,), {})
            mock_sr.UnknownValueError = UnknownValueError
            mock_sr.RequestError = RequestError

            mock_recognizer = MagicMock()
            mock_recognizer.recognize_google.side_effect = RequestError("API 오류")
            client._recognizer = mock_recognizer

            audio_mock = MagicMock()
            mock_sr.AudioFile.return_value = audio_mock
            audio_mock.__enter__ = MagicMock(return_value=audio_mock)
            audio_mock.__exit__ = MagicMock(return_value=False)

            result = client._transcribe_sync(wav)

        assert result is None

    def test_returns_none_on_empty_text(self):
        """빈 문자열 인식 시 None 반환."""
        client = STTClient()
        wav = _make_wav_bytes()

        with patch("server.stt.sr") as mock_sr:
            mock_sr.UnknownValueError = type("UnknownValueError", (Exception,), {})
            mock_sr.RequestError = type("RequestError", (Exception,), {})

            mock_recognizer = MagicMock()
            mock_recognizer.recognize_google.return_value = ""
            client._recognizer = mock_recognizer

            audio_mock = MagicMock()
            mock_sr.AudioFile.return_value = audio_mock
            audio_mock.__enter__ = MagicMock(return_value=audio_mock)
            audio_mock.__exit__ = MagicMock(return_value=False)

            result = client._transcribe_sync(wav)

        assert result is None

    def test_uses_correct_language(self):
        """recognize_google 호출 시 설정한 언어 코드 사용 확인."""
        client = STTClient(language="en-US")
        wav = _make_wav_bytes()

        with patch("server.stt.sr") as mock_sr:
            mock_sr.UnknownValueError = type("UnknownValueError", (Exception,), {})
            mock_sr.RequestError = type("RequestError", (Exception,), {})

            mock_recognizer = MagicMock()
            mock_recognizer.recognize_google.return_value = "hello"
            client._recognizer = mock_recognizer

            audio_mock = MagicMock()
            mock_sr.AudioFile.return_value = audio_mock
            audio_mock.__enter__ = MagicMock(return_value=audio_mock)
            audio_mock.__exit__ = MagicMock(return_value=False)

            client._transcribe_sync(wav)

        mock_recognizer.recognize_google.assert_called_once()
        _, kwargs = mock_recognizer.recognize_google.call_args
        assert kwargs.get("language") == "en-US"
