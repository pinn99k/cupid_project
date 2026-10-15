"""ai_core/calibration.py 단위 테스트 — 순수 함수, 의존성 없음."""

from ai_core.calibration import (
    is_valid_distance,
    correct_cm,
    median_filter,
    process,
    MIN_CM,
    MAX_CM,
)


class TestIsValidDistance:
    def test_in_range(self):
        assert is_valid_distance(30) is True
        assert is_valid_distance(MIN_CM) is True
        assert is_valid_distance(MAX_CM) is True

    def test_out_of_range(self):
        assert is_valid_distance(1) is False      # 너무 가까움
        assert is_valid_distance(500) is False     # 너무 멈
        assert is_valid_distance(-1) is False      # 측정 실패값
        assert is_valid_distance(None) is False


class TestCorrectCm:
    def test_offset_applied(self):
        assert correct_cm(28, offset=2) == 30
        assert correct_cm(30, offset=-3) == 27

    def test_zero_offset(self):
        assert correct_cm(42) == 42

    def test_none_passthrough(self):
        assert correct_cm(None, offset=5) is None


class TestMedianFilter:
    def test_odd(self):
        assert median_filter([30, 32, 31]) == 31

    def test_even(self):
        assert median_filter([30, 40]) == 35.0

    def test_rejects_outliers(self):
        # 500은 범위 밖 → 무시, 나머지 중앙값
        assert median_filter([30, 31, 500]) == 30.5

    def test_all_invalid_returns_none(self):
        assert median_filter([-1, 0, 999]) is None

    def test_empty_returns_none(self):
        assert median_filter([]) is None


class TestProcess:
    def test_correct_then_filter(self):
        # 날것 [28,29,30] + offset 2 → [30,31,32] → 중앙값 31
        assert process([28, 29, 30], offset=2) == 31

    def test_spike_filtered(self):
        # 999는 보정 후에도 범위 밖 → 무시
        assert process([30, 31, 999], offset=0) == 30.5

    def test_all_invalid(self):
        assert process([-1, -1], offset=0) is None
