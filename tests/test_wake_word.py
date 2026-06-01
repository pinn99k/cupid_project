"""server/wake_word.py 단위 테스트 — 하드웨어/오디오 불필요."""

import pytest

from server.wake_word import parse_wake_word, is_wake


class TestParseWakeWord:
    def test_wake_with_question(self):
        assert parse_wake_word("시아야 앞에 뭐 있어?") == "앞에 뭐 있어"

    def test_wake_mid_sentence(self):
        assert parse_wake_word("안녕 시아야 뭐해") == "뭐해"

    def test_wake_only_returns_empty(self):
        # 호출만 하고 질문 없음 → "" (None 아님)
        assert parse_wake_word("시아야") == ""
        assert parse_wake_word("시아야!") == ""

    def test_stt_variants_are_wake(self):
        assert parse_wake_word("시아 지금 가도 돼") == "지금 가도 돼"
        assert parse_wake_word("시야 앞에 뭐 있어?") == "앞에 뭐 있어"
        assert parse_wake_word("씨아야 오른쪽 맞아?") == "오른쪽 맞아"

    def test_embedded_sia_is_not_wake(self):
        assert parse_wake_word("러시아 이야기 해줘") is None

    def test_no_wake_returns_none(self):
        assert parse_wake_word("안녕하세요") is None
        assert parse_wake_word("앞에 뭐 있어") is None

    def test_empty_and_none(self):
        assert parse_wake_word("") is None
        assert parse_wake_word(None) is None
        assert parse_wake_word("   ") is None

    def test_extra_spaces_normalized(self):
        assert parse_wake_word("시아야    앞에   뭐있어") == "앞에 뭐있어"

    def test_punctuation_stripped(self):
        assert parse_wake_word("시아야, 방향 맞아?") == "방향 맞아"

    def test_longer_token_preferred(self):
        # "시아야"를 "시아"+"야"로 자르지 않아야 함
        assert parse_wake_word("시아야 안녕") == "안녕"


class TestIsWake:
    def test_true(self):
        assert is_wake("시아야 안녕") is True
        assert is_wake("시아야") is True  # 빈 질문도 호출은 호출

    def test_false(self):
        assert is_wake("안녕하세요") is False
        assert is_wake(None) is False
