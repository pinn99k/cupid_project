"""지연 측정 유틸. 스레드 안전, 히스토리 보관, 파일 출력 지원."""

import os
import time
import json
import threading
from pathlib import Path
from dataclasses import dataclass

# 핫루프 print 스팸 방지: 기본 꺼짐. SIA_DEBUG로 켬. 집계/저장은 플래그와 무관하게 항상 동작.
_ENV_VERBOSE = os.getenv("SIA_DEBUG", "").lower() in ("1", "true", "yes", "on")


@dataclass
class MeasurementStats:
    """측정 통계."""
    count: int = 0
    avg_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    last_ms: float = 0.0


class LatencyLogger:
    """스레드 안전한 지연 측정 로거."""

    def __init__(self, max_history: int = 100, log_dir: str | None = None,
                 verbose: bool | None = None):
        self._lock = threading.Lock()
        self._timestamps: dict[str, float] = {}
        self._history: dict[str, list[float]] = {}  # label -> list of elapsed ms
        self._max_history = max_history
        self._verbose = _ENV_VERBOSE if verbose is None else verbose
        self._log_dir = Path(log_dir) if log_dir else None
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    def set_verbose(self, verbose: bool):
        """print 노출 여부 토글 (집계/저장엔 영향 없음)."""
        self._verbose = verbose

    def set_log_dir(self, log_dir: str):
        """저장 디렉토리 설정 (save_to_file 활성화)."""
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _append(self, key: str, value_ms: float):
        """히스토리에 측정값 누적 (최근 max_history개 유지). 락 안에서 호출 가정."""
        hist = self._history.setdefault(key, [])
        hist.append(value_ms)
        if len(hist) > self._max_history:
            hist.pop(0)

    def record(self, key: str, value_ms: float):
        """이미 측정된 구간 시간(ms)을 직접 집계 (perf_counter 등 외부 측정용)."""
        with self._lock:
            self._append(key, value_ms)
        if self._verbose:
            print(f"[LATENCY] {key}: {value_ms:.0f}ms")

    def log(self, label: str) -> float:
        """타임스탬프 기록. 밀리초 반환."""
        ts = time.time() * 1000
        with self._lock:
            self._timestamps[label] = ts
        if self._verbose:
            print(f"[LATENCY] {label}: {ts:.0f}ms")
        return ts

    def elapsed(self, start_label: str, end_label: str) -> float | None:
        """두 라벨 간 경과시간(ms). 히스토리에 자동 저장."""
        with self._lock:
            s = self._timestamps.get(start_label)
            e = self._timestamps.get(end_label)
        if s is None or e is None:
            return None
        diff = e - s
        key = f"{start_label}->{end_label}"
        with self._lock:
            self._append(key, diff)
        if self._verbose:
            print(f"[LATENCY] {start_label} -> {end_label}: {diff:.0f}ms")
        return diff

    def stats(self, key: str | None = None) -> dict[str, MeasurementStats]:
        """측정 통계 반환. key 없으면 전체."""
        with self._lock:
            keys = [key] if key else list(self._history.keys())
            result = {}
            for k in keys:
                values = self._history.get(k, [])
                if not values:
                    continue
                result[k] = MeasurementStats(
                    count=len(values),
                    avg_ms=sum(values) / len(values),
                    min_ms=min(values),
                    max_ms=max(values),
                    last_ms=values[-1]
                )
        return result

    def save_to_file(self, filename: str = "latency_log.json"):
        """현재 통계를 JSON 파일로 저장."""
        if not self._log_dir:
            return
        stats = self.stats()
        data = {
            k: {
                "count": v.count,
                "avg_ms": round(v.avg_ms, 1),
                "min_ms": round(v.min_ms, 1),
                "max_ms": round(v.max_ms, 1),
                "last_ms": round(v.last_ms, 1)
            }
            for k, v in stats.items()
        }
        filepath = self._log_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[LATENCY] stats saved: {filepath}")

    def clear(self):
        """모든 기록 초기화."""
        with self._lock:
            self._timestamps.clear()
            self._history.clear()


# 기본 인스턴스 (하위 호환)
_default = LatencyLogger(max_history=100)


def log(label: str) -> float:
    """타임스탬프 기록 + 콘솔 출력. (하위 호환 함수)"""
    return _default.log(label)


def elapsed(start_label: str, end_label: str) -> float | None:
    """두 라벨 간 경과 시간(ms) 계산 + 출력. (하위 호환 함수)"""
    return _default.elapsed(start_label, end_label)


def record(key: str, value_ms: float):
    """외부 측정값(ms)을 기본 로거에 집계. (하위 호환 함수)"""
    _default.record(key, value_ms)


def configure(log_dir: str | None = None, verbose: bool | None = None):
    """기본 로거 설정: 저장 디렉토리/print 노출. (앱 시작 시 1회)"""
    if log_dir is not None:
        _default.set_log_dir(log_dir)
    if verbose is not None:
        _default.set_verbose(verbose)


def get_logger() -> LatencyLogger:
    """기본 로거 인스턴스 반환."""
    return _default
