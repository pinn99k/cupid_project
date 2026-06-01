"""
우선순위 기반 오디오 재생 매니저.
- 위험 경고 > 사용자 대화 > 자동 묘사 > 수동 fallback
- 요청별 started / finished 이벤트로 실제 재생 완료까지 대기 가능
"""

import asyncio
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
import queue
import threading
import time
import wave

import pygame

from utils.latency_logger import log

FALLBACK_DIR = Path("audio/fallback")

# 코드는 ".wav"로 음원을 부르지만 사전생성본이 ".mp3"일 수 있다.
# pygame.mixer.music는 둘 다 재생하므로, 요청 확장자가 없으면 대체 확장자를 찾는다.
_AUDIO_EXTS = (".wav", ".mp3", ".ogg")


def _resolve_fallback(filename: str) -> str:
    """fallback 디렉토리에서 음원 경로 해석. 요청 확장자가 없으면 동일 stem의
    다른 확장자(.wav/.mp3/.ogg)를 찾는다. 못 찾으면 요청 경로 그대로 반환."""
    requested = FALLBACK_DIR / filename
    if requested.exists():
        return str(requested)
    for ext in _AUDIO_EXTS:
        alt = FALLBACK_DIR / (requested.stem + ext)
        if alt.exists():
            return str(alt)
    return str(requested)


PRIORITY_DANGER = 0
PRIORITY_CONVERSATION = 10
PRIORITY_NARRATION = 20
PRIORITY_FALLBACK = 30
PLAYBACK_START_GRACE_SEC = 0.15


@dataclass(order=True)
class PlaybackRequest:
    """우선순위 큐에 넣는 오디오 재생 요청."""

    priority: int
    sequence: int
    filepath: str = field(compare=False)
    started: threading.Event = field(default_factory=threading.Event, compare=False)
    finished: threading.Event = field(default_factory=threading.Event, compare=False)
    cancelled: threading.Event = field(default_factory=threading.Event, compare=False)


class AudioManager:
    """오디오를 한 스레드에서 직렬 재생하고 요청별 완료 상태를 제공."""

    def __init__(self):
        self._queue: queue.PriorityQueue[PlaybackRequest] = queue.PriorityQueue()
        self._sequence = count()
        self._running = True
        self._current: PlaybackRequest | None = None
        self._state_lock = threading.Lock()
        pygame.mixer.init()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def play(
        self,
        filename: str,
        *,
        priority: int = PRIORITY_FALLBACK,
        interrupt: bool = False,
    ) -> PlaybackRequest | None:
        """fallback 디렉토리의 음원 재생 요청."""
        return self.play_path(
            _resolve_fallback(filename),
            priority=priority,
            interrupt=interrupt,
        )

    def play_path(
        self,
        filepath: str,
        *,
        priority: int = PRIORITY_CONVERSATION,
        interrupt: bool = False,
    ) -> PlaybackRequest | None:
        """파일 재생 요청. interrupt=True이면 현재 음성과 대기열을 중단."""
        if not Path(filepath).exists():
            print(f"[AUDIO] 파일 없음: {filepath}")
            return None

        if interrupt:
            self.stop(clear_queue=True)

        request = PlaybackRequest(priority, next(self._sequence), filepath)
        self._queue.put(request)
        return request

    async def wait(self, request: PlaybackRequest | None) -> bool:
        """실제 재생 완료까지 비동기 대기. 파일 누락 시 False."""
        if request is None:
            return False
        await asyncio.to_thread(request.finished.wait)
        return not request.cancelled.is_set()

    async def wait_until_idle(self):
        """재생 중이거나 대기 중인 음원이 모두 끝날 때까지 대기."""
        while self.is_playing() or not self._queue.empty():
            await asyncio.sleep(0.05)

    def stop(self, *, clear_queue: bool = False):
        """현재 재생을 중단하고 필요하면 대기 요청도 취소."""
        with self._state_lock:
            current = self._current
            if current is not None:
                current.cancelled.set()
            pygame.mixer.music.stop()
        if clear_queue:
            self.clear_queue()

    def clear_queue(self):
        """대기 중인 모든 음원 요청을 취소."""
        while True:
            try:
                request = self._queue.get_nowait()
            except queue.Empty:
                break
            request.cancelled.set()
            request.finished.set()
            self._queue.task_done()

    def is_playing(self) -> bool:
        """현재 재생 중인 요청이 있는지 여부."""
        with self._state_lock:
            return self._current is not None and not self._current.finished.is_set()

    def _worker(self):
        """Audio Thread 메인 루프."""
        while self._running:
            try:
                request = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if request.cancelled.is_set():
                    continue
                with self._state_lock:
                    self._current = request
                self._play_file(request)
            finally:
                request.finished.set()
                with self._state_lock:
                    if self._current is request:
                        self._current = None
                self._queue.task_done()

    @staticmethod
    def _play_file(request: PlaybackRequest):
        """실제 재생. Audio Thread 내부에서만 호출."""
        try:
            log("audio_play_start")
            pygame.mixer.music.load(request.filepath)
            pygame.mixer.music.play()
            request.started.set()
            # pygame이 play() 직후 아직 busy=False를 반환하는 짧은 구간이 있다.
            # WAV 길이보다 일찍 완료 처리하면 TTS 락이 풀리고 문장 끝이 잘릴 수 있다.
            duration = AudioManager._audio_duration_seconds(request.filepath)
            minimum_end = time.monotonic() + max(duration, PLAYBACK_START_GRACE_SEC)
            clock = pygame.time.Clock()
            while not request.cancelled.is_set():
                if time.monotonic() >= minimum_end and not pygame.mixer.music.get_busy():
                    break
                clock.tick(50)
            log("audio_play_end")
        except Exception as e:
            print(f"[AUDIO ERROR] {request.filepath}: {e}")

    @staticmethod
    def _audio_duration_seconds(filepath: str) -> float:
        """재생 완료 오판 방지를 위한 최소 재생 시간. WAV가 아니면 mixer busy 상태를 사용."""
        if Path(filepath).suffix.lower() != ".wav":
            return 0.0
        try:
            with wave.open(filepath, "rb") as wav:
                return wav.getnframes() / float(wav.getframerate())
        except (OSError, EOFError, wave.Error, ZeroDivisionError):
            return 0.0


_instance: AudioManager | None = None


def get_audio_manager() -> AudioManager:
    """싱글톤 AudioManager 인스턴스 반환."""
    global _instance
    if _instance is None:
        _instance = AudioManager()
    return _instance
