"""지연 측정 유틸. 이 모듈은 실제 구현 (placeholder 아님)."""

import time

_timestamps = {}


def log(label: str):
    """타임스탬프 기록 + 콘솔 출력."""
    ts = time.time() * 1000
    _timestamps[label] = ts
    print(f"[LATENCY] {label}: {ts:.0f}ms")


def elapsed(start_label: str, end_label: str):
    """두 라벨 간 경과 시간(ms) 계산 + 출력."""
    s = _timestamps.get(start_label)
    e = _timestamps.get(end_label)
    if s and e:
        diff = e - s
        print(f"[LATENCY] {start_label} → {end_label}: {diff:.0f}ms")
        return diff
    return None
