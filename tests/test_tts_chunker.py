"""server/tts_chunker.py 단위 테스트."""

from server.tts_chunker import split_sentences


def test_empty_returns_empty():
    assert split_sentences("") == []
    assert split_sentences(None) == []
    assert split_sentences("   ") == []


def test_no_punctuation_single_sentence():
    assert split_sentences("앞에 의자가 있어") == ["앞에 의자가 있어"]


def test_splits_korean_sentences():
    result = split_sentences("앞에 신호등이 보여. 오른쪽으로 살짝 비켜갈까?")
    assert result == ["앞에 신호등이 보여.", "오른쪽으로 살짝 비켜갈까?"]


def test_short_fragment_merges_forward():
    # "응!" (짧음) 은 다음 문장과 합쳐진다
    result = split_sentences("응! 같이 가볼까?")
    assert result == ["응! 같이 가볼까?"]


def test_english_punctuation():
    result = split_sentences("Hello there. How are you?")
    assert result == ["Hello there.", "How are you?"]


def test_whitespace_normalized():
    result = split_sentences("첫 문장이야.   두 번째 문장도 충분히 길어.")
    assert result == ["첫 문장이야.", "두 번째 문장도 충분히 길어."]


def test_trailing_short_merges_into_previous():
    result = split_sentences("충분히 긴 첫 문장이야. 끝!")
    assert result == ["충분히 긴 첫 문장이야. 끝!"]
