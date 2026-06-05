"""초음파 폴링 신규 로직 단위/통합 테스트.

대상: main._UltrasonicState (보정·중앙값·끊김 판정) + danger.judge 연동.
하드웨어/네트워크 비의존 — 시간(now)을 주입해 끊김/복구를 결정적으로 검증한다.

시연 함정을 테스트로 못박는다:
  1) 끊김(STALE) → None  (오래된 값으로 긴급정지 오작동 방지)
  2) 반사 스파이크 1회 → 중앙값이 흡수
  3) 무반사(-1) → 유효성에서 탈락
  4) 거리 주입 시 danger Rule1(긴급정지) 실제로 켜짐 / None이면 안 켜짐
"""

import main
from ai_core.vision import enrich
from ai_core.danger import judge
from server.config import DANGER_DISTANCE_CM


def _state(buffer_n=5, offset=0.0, stale=1.5):
    return main._UltrasonicState(buffer_n=buffer_n, offset_cm=offset, stale_sec=stale)


class TestUltrasonicState:
    def test_empty_is_none(self):
        assert _state().value(now=100.0) is None

    def test_median_of_valid(self):
        s = _state()
        for i, cm in enumerate([30.0, 31.0, 29.0]):
            s.push(cm, now=100.0 + i * 0.1)
        assert s.value(now=100.2) == 30.0

    def test_single_spike_absorbed_by_median(self):
        # 반사 오류 200cm 1회가 끼어도 중앙값은 ~30 유지
        s = _state()
        for i, cm in enumerate([29.0, 30.0, 200.0, 31.0, 30.0]):
            s.push(cm, now=100.0 + i * 0.1)
        assert abs(s.value(now=100.4) - 30.0) <= 1.0

    def test_no_echo_minus_one_rejected(self):
        # 무반사 -1 은 유효범위(2~400) 밖 → 필터에서 제외, 나머지로 판단
        s = _state()
        for i, cm in enumerate([30.0, -1.0, 30.0, -1.0, 30.0]):
            s.push(cm, now=100.0 + i * 0.1)
        assert s.value(now=100.4) == 30.0

    def test_all_invalid_is_none(self):
        s = _state()
        for i in range(3):
            s.push(-1.0, now=100.0 + i * 0.1)
        assert s.value(now=100.2) is None

    def test_offset_applied(self):
        s = _state(offset=5.0)
        s.push(30.0, now=100.0)
        assert s.value(now=100.0) == 35.0  # 보정 +5

    # ---- 끊김/복구 (시연 핵심) ----
    def test_stale_returns_none(self):
        s = _state(stale=1.5)
        s.push(25.0, now=100.0)
        assert s.value(now=100.5) == 25.0           # 최근 → 값 유지
        assert s.value(now=102.0) is None            # 1.5s 초과 → 끊김으로 간주, None

    def test_recovery_clears_stale_buffer(self):
        # 25cm 받다가 끊김(>stale) 후 100cm 복구 → 옛 25 혼입 없이 100 반영
        s = _state(stale=1.5)
        s.push(25.0, now=100.0)
        # 긴 공백 후 복구
        s.push(100.0, now=200.0)
        s.push(101.0, now=200.1)
        s.push(99.0, now=200.2)
        assert abs(s.value(now=200.2) - 100.0) <= 1.0

    def test_buffer_window_limited(self):
        # 최근 N개만 — 오래된 값이 윈도우 밖으로 밀려남
        s = _state(buffer_n=3)
        for i, cm in enumerate([10.0, 10.0, 50.0, 50.0, 50.0]):
            s.push(cm, now=100.0 + i * 0.1)
        assert s.value(now=100.4) == 50.0


class TestDangerIntegration:
    """거리 주입이 Stage 3 긴급정지(Rule1)를 실제로 켜는지 — 이게 빠져 있었음."""

    def _enriched(self, ultrasonic_cm):
        # 객체 없이 거리값만 — Rule1(초음파 코앞) 격리 검증
        return enrich([], 640, 480, ultrasonic_cm=ultrasonic_cm)

    def test_close_distance_triggers_emergency(self):
        cm = DANGER_DISTANCE_CM - 5  # 임계 미만 → 긴급
        result = judge(self._enriched(cm), current_stage=3)
        assert result is not None
        assert result["level"] == "emergency"
        assert result["distance_cm"] == cm

    def test_none_distance_no_emergency(self):
        # 끊김(None)이면 Rule1 안 켜짐 — 객체도 없으니 전체 None
        assert judge(self._enriched(None), current_stage=3) is None

    def test_far_distance_no_emergency(self):
        far = DANGER_DISTANCE_CM + 50
        assert judge(self._enriched(far), current_stage=3) is None

    def test_stage_not_3_ignores_distance(self):
        cm = DANGER_DISTANCE_CM - 5
        assert judge(self._enriched(cm), current_stage=2) is None
