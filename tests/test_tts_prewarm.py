"""ai_core/tts.py TTSCache.prewarm 단위 테스트.

실제 네트워크/TTS 호출 없이 get_or_create / get 를 mock 해서
prewarm 이 각 문구를 호출하고 새로 생성한 개수를 반환하는지 검증.
"""

import asyncio
from unittest.mock import AsyncMock

from ai_core.tts import PREWARM_TEXTS, TTSCache


def _run(coro):
    return asyncio.run(coro)


def test_prewarm_calls_get_or_create_for_each_text():
    cache = TTSCache()
    cache.get = lambda text: None  # 모두 MISS
    cache.get_or_create = AsyncMock(return_value="dummy.mp3")

    texts = ["문구1", "문구2", "문구3"]
    created = _run(cache.prewarm(texts))

    assert created == 3
    assert cache.get_or_create.await_count == 3
    called = [c.args[0] for c in cache.get_or_create.await_args_list]
    assert called == texts


def test_prewarm_skips_already_cached():
    cache = TTSCache()
    # "있음" 은 이미 캐시, 나머지는 MISS
    cache.get = lambda text: "cached.mp3" if text == "있음" else None
    cache.get_or_create = AsyncMock(return_value="dummy.mp3")

    created = _run(cache.prewarm(["있음", "없음1", "없음2"]))

    # 이미 캐시된 1개는 카운트에서 제외
    assert created == 2
    assert cache.get_or_create.await_count == 3


def test_prewarm_best_effort_continues_on_error():
    cache = TTSCache()
    cache.get = lambda text: None

    async def _flaky(text):
        if text == "터짐":
            raise RuntimeError("boom")
        return "dummy.mp3"

    cache.get_or_create = AsyncMock(side_effect=_flaky)

    created = _run(cache.prewarm(["ok1", "터짐", "ok2"]))

    # 하나 실패해도 나머지 2개는 진행/카운트
    assert created == 2
    assert cache.get_or_create.await_count == 3


def test_prewarm_counts_only_successful_generation():
    cache = TTSCache()
    cache.get = lambda text: None
    # get_or_create 가 None(생성 실패) 반환하면 카운트 안 함
    cache.get_or_create = AsyncMock(return_value=None)

    created = _run(cache.prewarm(["a", "b"]))

    assert created == 0


def test_prewarm_default_uses_module_constant():
    cache = TTSCache()
    cache.get = lambda text: None
    cache.get_or_create = AsyncMock(return_value="dummy.mp3")

    created = _run(cache.prewarm())

    assert created == len(PREWARM_TEXTS)
    assert cache.get_or_create.await_count == len(PREWARM_TEXTS)


def test_prewarm_skips_empty_text():
    cache = TTSCache()
    cache.get = lambda text: None
    cache.get_or_create = AsyncMock(return_value="dummy.mp3")

    created = _run(cache.prewarm(["", "유효", None]))

    assert created == 1
    assert cache.get_or_create.await_count == 1
