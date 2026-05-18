"""
오디오 매니저. 별도 스레드에서 pygame 재생, Lock 보호.
- AudioManager: 스레드 분리 오디오 재생 클래스
- get_audio_manager(): 싱글톤 인스턴스 반환
"""


class AudioManager:
    """별도 스레드에서 오디오 재생. Lock으로 동시 재생 방지."""

    def __init__(self):
        raise NotImplementedError("Step 1-4에서 구현")

    def play(self, filename: str, interrupt: bool = False):
        """Fallback 디렉토리 내 파일 재생. interrupt=True: Stage 3 긴급."""
        raise NotImplementedError("Step 1-4에서 구현")

    def play_path(self, filepath: str, interrupt: bool = False):
        """절대 경로로 재생 (TTS 캐시 파일용)."""
        raise NotImplementedError("Step 1-4에서 구현")

    def stop(self):
        raise NotImplementedError("Step 1-4에서 구현")


def get_audio_manager():
    """싱글톤 AudioManager 인스턴스 반환."""
    raise NotImplementedError("Step 1-4에서 구현")
