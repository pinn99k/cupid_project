"""
TTS 음성 출력 + 세션 기반 캐시 관리
- 공급자 우선순위: Gemini TTS → Edge-TTS → gTTS
- TTSCache: text -> 파일 캐시 (세션 단위로 생성/삭제)
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

from server.config import GEMINI_API_KEY, TTS_PROVIDER
from utils.latency_logger import log

TTS_VOICE = "Aoede"  # 시아 목소리
TTS_MODEL = "gemini-2.5-flash-preview-tts"
EDGE_TTS_VOICE = "ko-KR-SunHiNeural"  # 한국어 여성, 자연스러운 발음

_TTS_PROVIDERS = ("edge", "gemini", "gtts")

# 일반(비데모) 경로에서 실제로 자주 나가는 고정 한국어 문구.
# - voice_pipeline 의 되묻기(_REPROMPT_TEXTS) 표시 텍스트 / 직접응답 fallback
# - 인사·소개 등 세션 시작 시 자주 재생되는 문구
# 프리웜 대상이므로 너무 길지 않게, 실제 발화되는 문구 위주로 유지한다.
PREWARM_TEXTS: list[str] = [
    # 되묻기 (voice_pipeline._REPROMPT_TEXTS)
    "응, 불렀어?",
    "조금만 더 크게 말해줄래?",
    "미안해, 한 번만 더 말해줄래?",
    # VQA 장면 없음 직접응답 (voice_pipeline)
    "지금은 화면에서 잘 안 보여. 잠깐 기다려 볼까?",
    # 인사·소개 (자주 재생되는 고정 안내)
    "안녕! 반가워! 나는 시아야.",
    "응? 다시 한 번 말해줄래?",
]


def _provider_order(primary: str) -> list[str]:
    """1순위 + 나머지 폴백 순서. 알 수 없는 값이면 edge 기본."""
    primary = primary if primary in _TTS_PROVIDERS else "edge"
    return [primary] + [p for p in _TTS_PROVIDERS if p != primary]

# Gemini 클라이언트 (모듈 로드 시 1회 생성)
_genai_client = genai.Client(api_key=GEMINI_API_KEY)


# ── Edge-TTS 헬퍼 ──────────────────────────────────────────────────────────
async def _edge_tts_async(text: str, filepath: Path) -> bool:
    """Edge-TTS로 mp3 생성. 성공 시 True."""
    try:
        import edge_tts  # noqa: PLC0415
        communicate = edge_tts.Communicate(text, voice=EDGE_TTS_VOICE)
        await communicate.save(str(filepath))
        return filepath.exists() and filepath.stat().st_size > 0
    except Exception as e:
        print(f"[TTS] Edge-TTS 오류: {e}")
        filepath.unlink(missing_ok=True)
        return False


# ── gTTS 헬퍼 (동기, to_thread로 래핑) ────────────────────────────────────
def _gtts_sync(text: str, filepath: Path) -> bool:
    """gTTS로 mp3 생성. 성공 시 True."""
    try:
        from gtts import gTTS  # noqa: PLC0415
        gTTS(text=text, lang="ko", slow=False).save(str(filepath))
        return filepath.exists() and filepath.stat().st_size > 0
    except Exception as e:
        print(f"[TTS] gTTS 오류: {e}")
        filepath.unlink(missing_ok=True)
        return False

def _write_wav(filepath, pcm, channels=1, rate=24000, sample_width=2):
    """Gemini가 준 날것 소리 데이터(pcm)를 wav 파일로 포장"""
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def generate_wav(text: str, filepath: str | Path) -> bool:
    """Gemini TTS로 고정 안내 WAV 파일을 생성."""
    pcm = TTSCache()._gemini_tts(text)
    if pcm is None:
        return False
    _write_wav(filepath, pcm)
    return True


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
        prompt = f"어린아이에게 다정하게 말하는 친절한 언니처럼 말해줘. 목소리는 밝고 따뜻하고 살짝 들뜬 느낌으로, 자연스럽고 경쾌한 속도로 말해줘. 아이를 안심시키고 격려하는 느낌이어야 해. 한국어 발음을 정확하게 살려서 또박또박 발음해줘. 특히 받침과 어미를 분명하게 발음해야 해.: {text}"

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
    
    # ── 공급자 단위 생성 (성공 시 파일경로, 실패 시 None) ──────────────
    async def _gen_edge(self, text: str, key: str) -> Path | None:
        filepath = self._session_dir / f"{key}.mp3"
        return filepath if await _edge_tts_async(text, filepath) else None

    async def _gen_gemini(self, text: str, key: str) -> Path | None:
        pcm = await asyncio.to_thread(self._gemini_tts, text)
        if pcm is None:
            return None
        filepath = self._session_dir / f"{key}.wav"
        _write_wav(filepath, pcm)
        return filepath

    async def _gen_gtts(self, text: str, key: str) -> Path | None:
        filepath = self._session_dir / f"{key}_gtts.mp3"
        return filepath if await asyncio.to_thread(_gtts_sync, text, filepath) else None

    async def _generate_and_cache(self, text: str) -> Path | None:
        """TTS 생성 후 캐시에 저장.
        1순위 = config.TTS_PROVIDER, 실패하면 나머지로 자동 폴백.
        """
        if self._session_dir is None:
            print("[TTS] 세션 미시작, start_session() 먼저 호출 필요")
            return None

        log("tts_start")
        key = self._hash(text)
        gens = {"edge": self._gen_edge, "gemini": self._gen_gemini, "gtts": self._gen_gtts}

        for name in _provider_order(TTS_PROVIDER):
            try:
                filepath = await gens[name](text, key)
            except Exception as e:
                print(f"[TTS] {name} 예외: {e}")
                filepath = None
            if filepath:
                self._index[key] = filepath
                log("tts_end")
                print(f"[TTS] {name} 사용 → {filepath.name}")
                return filepath
            print(f"[TTS] {name} 실패 → 다음 공급자")

        log("tts_fail")
        print("[TTS ERROR] 모든 TTS 공급자 실패 (edge / gemini / gtts)")
        return None

    async def get_or_create(self, text: str) -> Path | None:
        """캐시 HIT -> 즉시 반환 / MISS -> TTS 생성 (비블로킹)"""
        cached = self.get(text)
        if cached:
            print("[TTS] 캐시 HIT")
            return cached
        return await self._generate_and_cache(text)

    async def prewarm(self, texts: list[str] | None = None) -> int:
        """고정 문구를 미리 캐시에 생성(프리웜).

        - 각 텍스트에 get_or_create를 호출. 이미 캐시에 있으면 건너뜀.
        - 새로 생성한 개수를 반환.
        - best-effort: 문구 단위로 예외를 잡아 하나 실패해도 나머지 진행.

        texts 미지정 시 모듈 상수 PREWARM_TEXTS 사용.
        """
        texts = PREWARM_TEXTS if texts is None else texts
        created = 0
        for text in texts:
            if not text:
                continue
            try:
                # 이미 있으면 get()으로 즉시 HIT → get_or_create가 재생성 안 함.
                already = self.get(text) is not None
                filepath = await self.get_or_create(text)
                if filepath and not already:
                    created += 1
            except Exception as e:
                print(f"[TTS] 프리웜 실패(건너뜀): {text!r}: {e}")
        return created

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
