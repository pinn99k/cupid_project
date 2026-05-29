"""
TTS 음성 출력 + 세션 기반 캐시 관리
- Gemini TTS 사용 (음성: Aoede)
- TTSCache: text -> wav 캐시 (세션 단위로 생성/삭제)
- get_tts_cache(): 싱글톤 인스턴스 반환
"""

import asyncio
import hashlib
import shutil
import wave
from pathlib import Path
import time

from google import genai
from google.genai import types

from server.config import GEMINI_API_KEY
from utils.latency_logger import log

TTS_VOICE = "Aoede" # 시아 목소리
TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Gemini 클라이언트 (모듈 로드 시 1회 생성)
_genai_client = genai.Client(api_key=GEMINI_API_KEY)

def _write_wav(filepath, pcm, channels=1, rate=24000, sample_width=2):
    """Gemini가 준 날것 소리 데이터(pcm)를 wav 파일로 포장"""
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

class TTSCache:
    """세션 기반 TTS 캐시. 대시보드 [새 세션] 버튼으로 초기화"""

    def __init__(self, cache_root: str = "./tts_cache"):
        self._cache_root = Path(cache_root)
        self._session_dir: Path | None = None
        self._index: dict[str, Path] = {}
    
    def start_session(self, session_id: str):
        """새 데모 세션 시작"""
        self._session_dir = self._cache_root / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}
        print(f"[TTS] 세션 시작: {session_id}")
    
    def end_session(self):
        """세션 종료 시 캐시 전체 삭제. 대시보드 버튼으로 호출"""
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir)
            print(f"[TTS] 캐시 삭제 완료: {self._session_dir}")
        self._index = {}
        self._session_dir = None
    
    def get(self, text: str) -> Path | None:
        """캐시 HIT 시 파일 경로 반환 / MISS 시 None"""
        key = self._hash(text)
        return self._index.get(key)
    
    def _gemini_tts(self, text: str, max_retries: int = 2) -> bytes | None:
        """Gemini로 음성 생성, 날것 소리 데이터(pcm bytes) 반환 / 실패 시 None
        500 INTERNAL 같은 일시적 에러는 자동 재시도
        """
        prompt = f"어린아이에게 다정하게 말하는 친절한 언니처럼 말해줘. 목소리는 밝고 따뜻하고 살짝 들뜬 느낌으로, 천천히 또박또박 말해줘. 아이를 안심시키고 격려하는 느낌이어야 해. 한국어 발음을 정확하게 살려서 또박또박 발음해줘. 특히 받침과 어미를 분명하게 발음해야 해.: {text}"

        for attempt in range(max_retries + 1):
            try:
                response = _genai_client.models.generate_content(
                    model=TTS_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=TTS_VOICE
                                )
                            )
                        ),
                    ),
                )
                return response.candidates[0].content.parts[0].inline_data.data
            except Exception as e:
                error_msg = str(e)
                is_retriable = "500" in error_msg or "INTERNAL" in error_msg or "503" in error_msg

                if attempt < max_retries and is_retriable:
                    wait = (attempt + 1) * 1.5  # 1.5초, 3초
                    print(f"[TTS] 재시도 {attempt + 1}/{max_retries} ({wait}초 대기): {error_msg[:80]}")
                    time.sleep(wait)
                    continue

                print(f"[TTS ERROR] {e}")
                return None

        return None
    
    async def _generate_and_cache(self, text: str) -> Path | None:
        """Gemini로 TTS 생성 후 캐시에 저장"""
        if self._session_dir is None:
            print("[TTS] 세션 미시작, start_session() 먼저 호출 필요")
            return None
        try:
            log("tts_start")
            key = self._hash(text)
            filepath = self._session_dir / f"{key}.wav"

            # Gemini 호출은 동기 함수 / 블로킹 안 되게 별도 스레드에서 실행
            pcm = await asyncio.to_thread(self._gemini_tts, text)
            if pcm is None:
                log("tts_fail")
                return None
            _write_wav(filepath, pcm)

            self._index[key] = filepath
            log("tts_end")
            print(f"[TTS] 생성 완료: {filepath.name}")
            return filepath
        except Exception as e:
            log("tts_fail")
            print(f"[TTS ERROR] {e}")
            return None

    async def get_or_create(self, text: str) -> Path | None:
        """캐시 HIT -> 즉시 반환 / MISS -> TTS 생성 (비블로킹)"""
        cached = self.get(text)
        if cached:
            print("[TTS] 캐시 HIT")
            return cached
        return await self._generate_and_cache(text)

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

# 싱글톤
_tts_cache: TTSCache | None = None


def get_tts_cache() -> TTSCache:
    """싱글톤 TTSCache 인스턴스 반환"""
    global _tts_cache
    if _tts_cache is None:
        _tts_cache = TTSCache()
    return _tts_cache
