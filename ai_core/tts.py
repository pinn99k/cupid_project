"""
TTS 음성 출력 + 세션 기반 캐시 관리.
- TTSCache: text → mp3 캐시. 세션 단위로 생성/삭제.
- get_tts_cache(): 싱글톤 인스턴스 반환
"""


class TTSCache:
    """세션 기반 TTS 캐시. 대시보드 [새 세션] 버튼으로 초기화."""

    def __init__(self):
        raise NotImplementedError("Step 1-6에서 구현")

    def start_session(self, session_id: str):
        raise NotImplementedError("Step 1-6에서 구현")

    def end_session(self):
        """대시보드 버튼 → 캐시 전체 삭제."""
        raise NotImplementedError("Step 1-6에서 구현")

    async def get_or_create(self, text: str):
        """캐시 HIT → 즉시 반환. MISS → TTS 생성 (비블로킹)."""
        raise NotImplementedError("Step 1-6에서 구현")


def get_tts_cache():
    """싱글톤 TTSCache 인스턴스 반환."""
    raise NotImplementedError("Step 1-6에서 구현")
