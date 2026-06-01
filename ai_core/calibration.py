"""
초음파 거리 보정 (서버측).
칩은 날것 cm를 보내고, 서버가 보정/검증/필터링한다.
재플래싱 없이 현장에서 ULTRASONIC_OFFSET_CM만 바꿔 튜닝.

순수 함수 — 하드웨어/네트워크 의존 없음.
"""

# 유효 측정 범위 (HC-SR04 계열 신뢰 구간)
MIN_CM = 2.0
MAX_CM = 400.0


def is_valid_distance(cm) -> bool:
    """측정값이 신뢰 범위 안인지."""
    return cm is not None and MIN_CM <= cm <= MAX_CM


def correct_cm(raw, offset: float = 0.0):
    """날것 cm에 오프셋 보정 적용. raw가 None이면 None."""
    if raw is None:
        return None
    return raw + offset


def median_filter(values) -> float | None:
    """유효값들의 중앙값. 유효값이 없으면 None.

    스파이크(반사 오류) 한 번에 오경보/누락되지 않도록 평활화.
    """
    valid = [v for v in values if is_valid_distance(v)]
    if not valid:
        return None
    s = sorted(valid)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def process(raw_values, offset: float = 0.0) -> float | None:
    """원시 측정 묶음 → 보정 → 필터 → 최종 cm (없으면 None).

    raw_values: 최근 N개 날것 측정값 리스트
    """
    corrected = [correct_cm(v, offset) for v in raw_values]
    return median_filter(corrected)
