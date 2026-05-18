"""
오디오 매니저. 별도 스레드에서 pygame 재생, Lock 보호.
- AudioManager: 스레드 분리 오디오 재생 클래스
- get_audio_manager(): 싱글톤 인스턴스 반환
"""

import threading
import queue
import pygame
from pathlib import Path
from utils.latency_logger import log

FALLBACK_DIR = Path("audio/fallback")


class AudioManager:
    """
    별도 스레드에서 오디오 재생. Lock으로 동시 재생 방지.
    모드가 겹치지 않으므로 우선순위 큐 불필요.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._running = True
        pygame.mixer.init()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def play(self, filename: str, interrupt: bool = False):
        """
        Fallback 디렉토리 내 파일 재생 요청.
        interrupt=True: Stage 3 긴급 → 현재 중단 후 즉시 재생.
        """
        filepath = FALLBACK_DIR / filename
        if not filepath.exists():
            print(f"[AUDIO] 파일 없음: {filepath}")
            return
        self._queue.put((str(filepath), interrupt))

    def play_path(self, filepath: str, interrupt: bool = False):
        """절대 경로로 재생 (TTS 캐시 파일용)."""
        if not Path(filepath).exists():
            print(f"[AUDIO] 파일 없음: {filepath}")
            return
        self._queue.put((filepath, interrupt))

    def stop(self):
        """현재 재생 중단."""
        pygame.mixer.music.stop()

    def is_playing(self) -> bool:
        """현재 오디오 재생 중인지."""
        return pygame.mixer.music.get_busy()

    def _worker(self):
        """Audio Thread 메인 루프."""
        while self._running:
            try:
                filepath, interrupt = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            log("audio_play_start")

            if interrupt:
                with self._lock:
                    pygame.mixer.music.stop()
                    self._play_file(filepath)
            else:
                acquired = self._lock.acquire(timeout=0.1)
                if not acquired:
                    print("[AUDIO] Lock 획득 실패, 스킵")
                    continue
                try:
                    self._play_file(filepath)
                finally:
                    self._lock.release()

            log("audio_play_end")

    def _play_file(self, filepath: str):
        """실제 재생 (Audio Thread 내부에서만 호출)."""
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"[AUDIO ERROR] {filepath}: {e}")


# 싱글톤
_instance: AudioManager | None = None


def get_audio_manager() -> AudioManager:
    """싱글톤 AudioManager 인스턴스 반환."""
    global _instance
    if _instance is None:
        _instance = AudioManager()
    return _instance
