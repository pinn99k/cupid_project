"""AudioManager 재생 완료 판정 단위 테스트."""

import time
import wave
from unittest.mock import MagicMock, patch

from ai_core.audio_manager import AudioManager, PlaybackRequest


def _write_silent_wav(path, duration_sec=0.08, sample_rate=8000):
    frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frames)


def test_play_file_waits_for_wav_duration_when_busy_starts_late(tmp_path):
    """mixer busy=False가 즉시 와도 WAV 문장 끝까지 완료 처리하지 않는다."""
    wav_path = tmp_path / "short.wav"
    _write_silent_wav(wav_path)
    request = PlaybackRequest(priority=10, sequence=0, filepath=str(wav_path))
    clock = MagicMock()
    clock.tick.side_effect = lambda _fps: time.sleep(0.005)

    with patch("ai_core.audio_manager.pygame.mixer.music.load"), \
         patch("ai_core.audio_manager.pygame.mixer.music.play"), \
         patch("ai_core.audio_manager.pygame.mixer.music.get_busy", return_value=False), \
         patch("ai_core.audio_manager.pygame.time.Clock", return_value=clock):
        started = time.monotonic()
        AudioManager._play_file(request)
        elapsed = time.monotonic() - started

    assert request.started.is_set()
    assert elapsed >= 0.07
