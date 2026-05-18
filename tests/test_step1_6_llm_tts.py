"""
Step 1-6 테스트: LLM 클라이언트 + TTS 캐시 + narration
실행: python tests/test_step1_6_llm_tts.py
API 키 불필요 — mock/구조 테스트만 수행.
"""

import sys
import os
import asyncio
import hashlib
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


def test_llm_client_structure():
    """LLM 클라이언트 모듈 구조 테스트 (API 호출 없음)."""
    print("=" * 50)
    print("Step 1-6a: LLM 클라이언트 구조 테스트")
    print("=" * 50)

    # Case 1: import 가능
    from ai_core.llm_client import init, call_async, _call_sync, SYSTEM_PROMPT
    print("[PASS] Case 1: llm_client import 성공")

    # Case 2: SYSTEM_PROMPT 존재 + 길이
    assert isinstance(SYSTEM_PROMPT, str), "SYSTEM_PROMPT는 str이어야 함"
    assert len(SYSTEM_PROMPT) > 20, f"SYSTEM_PROMPT가 너무 짧음: {len(SYSTEM_PROMPT)}"
    assert "시아" in SYSTEM_PROMPT, "SYSTEM_PROMPT에 '시아' 포함 필요"
    print(f"[PASS] Case 2: SYSTEM_PROMPT 정상 (len={len(SYSTEM_PROMPT)})")

    # Case 3: call_async가 coroutine 함수인지
    assert asyncio.iscoroutinefunction(call_async), "call_async는 async 함수여야 함"
    print("[PASS] Case 3: call_async는 coroutine 함수")

    # Case 4: _call_sync는 일반 함수
    assert not asyncio.iscoroutinefunction(_call_sync), "_call_sync는 동기 함수여야 함"
    print("[PASS] Case 4: _call_sync는 동기 함수")

    print()


def test_tts_cache():
    """TTS 캐시 세션 라이프사이클 테스트 (API 호출 없음)."""
    print("=" * 50)
    print("Step 1-6b: TTS 캐시 세션 테스트")
    print("=" * 50)

    from ai_core.tts import TTSCache

    # 임시 디렉토리 사용
    tmp_root = tempfile.mkdtemp(prefix="tts_test_")
    try:
        cache = TTSCache(cache_root=tmp_root)

        # Case 1: start_session → 디렉토리 생성
        cache.start_session("test_session_001")
        session_dir = cache._session_dir
        assert session_dir.exists(), "세션 디렉토리가 생성되어야 함"
        print(f"[PASS] Case 1: 세션 디렉토리 생성 → {session_dir}")

        # Case 2: 캐시 MISS → None
        result = cache.get("안녕하세요")
        assert result is None, f"캐시 MISS에서 None이어야 함: {result}"
        print("[PASS] Case 2: 캐시 MISS → None")

        # Case 3: hash 일관성
        h1 = cache._hash("테스트 텍스트")
        h2 = cache._hash("테스트 텍스트")
        h3 = cache._hash("다른 텍스트")
        assert h1 == h2, "같은 텍스트는 같은 해시"
        assert h1 != h3, "다른 텍스트는 다른 해시"
        expected = hashlib.md5("테스트 텍스트".encode("utf-8")).hexdigest()
        assert h1 == expected, f"MD5 해시 불일치: {h1} vs {expected}"
        print(f"[PASS] Case 3: 해시 일관성 (md5={h1[:12]}...)")

        # Case 4: 수동으로 캐시 파일 삽입 → get() HIT
        key = cache._hash("수동 캐시 테스트")
        fake_file = session_dir / f"{key}.mp3"
        fake_file.write_bytes(b"fake_mp3_data")
        cache._index[key] = fake_file
        result = cache.get("수동 캐시 테스트")
        assert result == fake_file, f"캐시 HIT 실패: {result}"
        print(f"[PASS] Case 4: 캐시 HIT → {result.name}")

        # Case 5: end_session → 디렉토리 삭제
        cache.end_session()
        assert not session_dir.exists(), "세션 종료 후 디렉토리 삭제되어야 함"
        assert cache._session_dir is None, "세션 종료 후 _session_dir은 None"
        assert len(cache._index) == 0, "세션 종료 후 인덱스 비어야 함"
        print("[PASS] Case 5: end_session → 디렉토리 삭제 완료")

        # Case 6: get_or_create async — 세션 미시작 시 None
        async def _test_no_session():
            return await cache.get_or_create("세션 없음")
        result = asyncio.run(_test_no_session())
        assert result is None, "세션 미시작 시 None이어야 함"
        print("[PASS] Case 6: 세션 미시작 → get_or_create() → None")

    finally:
        # 정리
        if os.path.exists(tmp_root):
            shutil.rmtree(tmp_root)

    print()


def test_narration_structure():
    """narration 모듈 구조 테스트."""
    print("=" * 50)
    print("Step 1-6c: narration 구조 테스트")
    print("=" * 50)

    from ai_core.narration import narrate_async
    assert asyncio.iscoroutinefunction(narrate_async), "narrate_async는 async 함수여야 함"
    print("[PASS] Case 1: narrate_async는 coroutine 함수")

    print()


if __name__ == "__main__":
    test_llm_client_structure()
    test_tts_cache()
    test_narration_structure()
    print(f"[결과] Step 1-6 PASS — LLM/TTS/Narration 구조 테스트 모두 통과")
