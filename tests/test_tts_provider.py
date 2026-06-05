"""TTS 공급자 우선순위(_provider_order) 단위 테스트.

TTS_PROVIDER 로 1순위를 정하고 나머지는 폴백 순서로 따라온다.
속도 최적화(Gemini 5.6s → Edge 0.6s)의 토글 로직을 못박는다.
"""

from ai_core.tts import _provider_order


def test_edge_primary_default():
    assert _provider_order("edge") == ["edge", "gemini", "gtts"]


def test_gemini_primary():
    assert _provider_order("gemini") == ["gemini", "edge", "gtts"]


def test_gtts_primary():
    assert _provider_order("gtts") == ["gtts", "edge", "gemini"]


def test_invalid_falls_back_to_edge():
    assert _provider_order("xxx") == ["edge", "gemini", "gtts"]


def test_order_is_permutation():
    for p in ("edge", "gemini", "gtts", "nonsense"):
        assert sorted(_provider_order(p)) == ["edge", "gemini", "gtts"]
