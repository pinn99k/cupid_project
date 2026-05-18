"""
TTS 음성 출력 + 세션 기반 캐시 관리.
- TTSCache: text → mp3 캐시. 세션 단위로 생성/삭제.
- get_tts_cache(): 싱글톤 인스턴스 반환
"""

import asyncio
import hashlib
import shutil
from pathlib import Path
from openai import OpenAI
from server.config import OPENAI_API_KEY
from utils.latency_logger import log


class TTSCache:
    """세션 기반 TTS 캐시. 대시보드 [새 세션] 버튼으로 초기화."""

    def __init__(self, cache_root: str = "./tts_cache"):
        self._cache_root = Path(cache_root)
        self._session_dir: Path | None = None
        self._index: dict[str, Path] = {}
        self._client = OpenAI(api_key=OPENAI_API_KEY)

    def start_session(self, session_id: str):
        """새 데모 세션 시작."""
        self._session_dir = self._cache_root / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}
        print(f"[TTS] 세션 시작: {session_id}")

    def end_session(self):
        """세션 종료 시 캐시 전체 삭제. 대시보드 버튼으로 호출."""
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir)
            print(f"[TTS] 캐시 삭제 완료: {self._session_dir}")
        self._index = {}
        self._session_dir = None

    def get(self, text: str) -> Path | None:
        """캐시 HIT 시 파일 경로 반환, MISS 시 None."""
        key = self._hash(text)
        return self._index.get(key)

    def _generate_and_cache(self, text: str) -> Path | None:
        """TTS 생성 후 캐시에 저장 (동기, 스레드 풀에서 실행)."""
        if self._session_dir is None:
            print("[TTS] 세션 미시작. start_session() 먼저 호출 필요.")
            return None
        try:
            log("tts_start")
            key = self._hash(text)
            filepath = self._session_dir / f"{key}.mp3"

            response = self._client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=text,
                response_format="mp3"
            )
            response.write_to_file(str(filepath))
            self._index[key] = filepath
            log("tts_end")
            return filepath
        except Exception as e:
            log("tts_fail")
            print(f"[TTS ERROR] {e}")
            return None

    async def get_or_create(self, text: str) -> Path | None:
        """캐시 HIT → 즉시 반환. MISS → TTS 생성 (비블로킹)."""
        cached = self.get(text)
        if cached:
            print("[TTS] 캐시 HIT")
            return cached
        return await asyncio.to_thread(self._generate_and_cache, text)

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()


# 싱글톤
_tts_cache: TTSCache | None = None


def get_tts_cache() -> TTSCache:
    """싱글톤 TTSCache 인스턴스 반환."""
    global _tts_cache
    if _tts_cache is None:
        _tts_cache = TTSCache()
    return _tts_cache
