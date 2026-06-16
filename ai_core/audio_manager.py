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
# 무한 재생/대기 방지 상한. BT 이어폰이 재생 중 끊기면 pygame get_busy()가 영영
# True로 남아 워커가 finished.set()을 못 해 wait()가 영구 블록 → 상위 TTS/턴 lock
# 데드락 → 토글 버튼이 완전히 먹통이 된다(실측 증상: "몇 번 되다 갑자기 안 됨").
# 데모 음성은 길어야 수 초이므로 아래 상한이 정상 재생을 자르지 않는다.
PLAYBACK_HARD_MARGIN_SEC = 5.0   # _play_file: 길이 + 이 여유 지나면 강제 종료
MAX_PLAYBACK_WAIT_SEC = 15.0     # wait(): 이 시간 지나면 강제 취소 후 진행


@dataclass(order=True)
class PlaybackRequest:
    """우선순위 큐에 넣는 오디오 재생 요청."""

    priority: int
    sequence: int
    filepath: str = field(compare=False)
    started: threading.Event = field(default_factory=threading.Event, compare=False)
    finished: threading.Event = field(default_factory=threading.Event, compare=False)
    cancelled: threading.Event = field(default_factory=threading.Event, compare=False)
    enqueued_at: float = field(default=0.0, compare=False)  # monotonic ms (대기시간 진단)


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

        request = PlaybackRequest(
            priority, next(self._sequence), filepath,
            enqueued_at=time.monotonic() * 1000,
        )
        self._queue.put(request)
        print(
            f"[AUDIO_QUEUE] enqueue at={request.enqueued_at:.0f}ms"
            f" queue_size={self._queue.qsize()} priority={priority}"
            f" interrupt={interrupt} file={Path(filepath).name}"
        )
        return request

    async def wait(self, request: PlaybackRequest | None) -> bool:
        """실제 재생 완료까지 비동기 대기. 파일 누락 시 False.

        ⚠️ 무한 대기 금지: 재생이 (BT 끊김 등으로) 안 끝나면 finished 가 영영 set 되지
        않아 여기서 영구 블록되고, 이를 감싼 _tts_lock/_manual_turn_lock 이 안 풀려
        토글 버튼이 데드락된다. MAX_PLAYBACK_WAIT_SEC 초과 시 강제 취소하고 진행한다."""
        if request is None:
            return False
        done = await asyncio.to_thread(request.finished.wait, MAX_PLAYBACK_WAIT_SEC)
        if not done:
            print(
                f"[AUDIO] ⚠️ 재생 완료 대기 {MAX_PLAYBACK_WAIT_SEC}s 초과 → "
                f"강제 취소(데드락 방지) file={Path(request.filepath).name}"
            )
            request.cancelled.set()
            try:
                self.stop(clear_queue=True)
            except Exception as e:
                print(f"[AUDIO] 강제 취소 중 stop 오류(무시): {e}")
            # ⚠️ finished.set()은 무슨 일이 있어도 실행돼야 한다(상위 lock 해제 보장).
            request.finished.set()
        return not request.cancelled.is_set()

    async def wait_until_idle(self, timeout: float = 30.0):
        """재생 중이거나 대기 중인 음원이 모두 끝날 때까지 대기.
        timeout(초) 초과 시 강제 반환 — 오디오가 멈춰도 마이크가 영구 차단되지 않게 보장."""
        start = time.monotonic()
        while self.is_playing() or not self._queue.empty():
            if time.monotonic() - start > timeout:
                print(f"[AUDIO] wait_until_idle 타임아웃({timeout}s) → 강제 진행(마이크 재개)")
                self.stop(clear_queue=True)
                return
            await asyncio.sleep(0.02)

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
                _now = time.monotonic() * 1000
                _waited = _now - request.enqueued_at if request.enqueued_at else 0.0
                print(
                    f"[AUDIO_QUEUE] dequeue at={_now:.0f}ms waited={_waited:.0f}ms"
                    f" file={Path(request.filepath).name}"
                )
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
            _pb_start = time.monotonic() * 1000
            print(f"[AUDIO_PLAYBACK] start at={_pb_start:.0f}ms file={Path(request.filepath).name}")
            pygame.mixer.music.load(request.filepath)
            pygame.mixer.music.play()
            request.started.set()
            # pygame이 play() 직후 아직 busy=False를 반환하는 짧은 구간이 있다.
            # WAV 길이보다 일찍 완료 처리하면 TTS 락이 풀리고 문장 끝이 잘릴 수 있다.
            duration = AudioManager._audio_duration_seconds(request.filepath)
            minimum_end = time.monotonic() + max(duration, PLAYBACK_START_GRACE_SEC)
            # 무한 재생 방지 하드 데드라인: 길이 + 여유를 넘기면 강제 종료한다.
            # (BT 끊김으로 get_busy()가 영영 True여도 빠져나와 finally의 finished.set 보장)
            hard_deadline = minimum_end + PLAYBACK_HARD_MARGIN_SEC
            clock = pygame.time.Clock()
            while not request.cancelled.is_set():
                if time.monotonic() >= minimum_end and not pygame.mixer.music.get_busy():
                    break
                if time.monotonic() >= hard_deadline:
                    print(
                        f"[AUDIO] ⚠️ 재생 하드 데드라인 초과 → 강제 종료(데드락 방지)"
                        f" file={Path(request.filepath).name}"
                    )
                    try:
                        pygame.mixer.music.stop()
                    except Exception:
                        pass
                    break
                clock.tick(50)
            log("audio_play_end")
            _pb_end = time.monotonic() * 1000
            print(
                f"[AUDIO_PLAYBACK] end at={_pb_end:.0f}ms"
                f" duration={_pb_end - _pb_start:.0f}ms"
                f" cancelled={request.cancelled.is_set()}"
                f" file={Path(request.filepath).name}"
            )
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
