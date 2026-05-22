"""utils/latency_logger.py 단위 테스트."""

import threading
import time
import tempfile
import json
from pathlib import Path

import pytest

from utils.latency_logger import LatencyLogger, MeasurementStats, log, elapsed, get_logger


# ---------------------------------------------------------------------------
# LatencyLogger 클래스 테스트
# ---------------------------------------------------------------------------

class TestLatencyLoggerInit:
    """생성자 + 초기 상태 검증."""

    def test_default_init(self):
        logger = LatencyLogger()
        assert logger._max_history == 100
        assert logger._log_dir is None
        assert logger._timestamps == {}
        assert logger._history == {}

    def test_custom_max_history(self):
        logger = LatencyLogger(max_history=10)
        assert logger._max_history == 10

    def test_log_dir_creation(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = LatencyLogger(log_dir=str(log_dir))
        assert logger._log_dir == log_dir
        assert log_dir.exists()


class TestLatencyLoggerLog:
    """log() 메서드 검증."""

    def test_log_returns_timestamp_ms(self):
        logger = LatencyLogger()
        before = time.time() * 1000
        ts = logger.log("test_label")
        after = time.time() * 1000
        assert before <= ts <= after

    def test_log_stores_timestamp(self):
        logger = LatencyLogger()
        logger.log("alpha")
        assert "alpha" in logger._timestamps

    def test_log_overwrites_same_label(self):
        logger = LatencyLogger()
        ts1 = logger.log("dup")
        time.sleep(0.01)
        ts2 = logger.log("dup")
        assert ts2 > ts1
        assert logger._timestamps["dup"] == ts2


class TestLatencyLoggerElapsed:
    """elapsed() 메서드 검증."""

    def test_elapsed_returns_diff(self):
        logger = LatencyLogger()
        logger.log("start")
        time.sleep(0.05)
        logger.log("end")
        diff = logger.elapsed("start", "end")
        assert diff is not None
        assert diff >= 40  # ~50ms, 약간의 여유

    def test_elapsed_missing_label_returns_none(self):
        logger = LatencyLogger()
        logger.log("only_start")
        assert logger.elapsed("only_start", "nonexistent") is None
        assert logger.elapsed("nonexistent", "only_start") is None

    def test_elapsed_stores_history(self):
        logger = LatencyLogger()
        logger.log("a")
        logger.log("b")
        logger.elapsed("a", "b")
        key = "a->b"
        assert key in logger._history
        assert len(logger._history[key]) == 1

    def test_elapsed_history_max_limit(self):
        logger = LatencyLogger(max_history=3)
        for i in range(5):
            logger.log(f"s{i}")
            logger.log(f"e{i}")
            logger._timestamps["s"] = i * 10.0
            logger._timestamps["e"] = i * 10.0 + 5.0
            logger.elapsed("s", "e")
        assert len(logger._history["s->e"]) == 3


class TestLatencyLoggerStats:
    """stats() 메서드 검증."""

    def test_stats_empty(self):
        logger = LatencyLogger()
        assert logger.stats() == {}

    def test_stats_calculates_correctly(self):
        logger = LatencyLogger()
        logger._history["x->y"] = [10.0, 20.0, 30.0]
        result = logger.stats("x->y")
        assert "x->y" in result
        s = result["x->y"]
        assert isinstance(s, MeasurementStats)
        assert s.count == 3
        assert s.avg_ms == 20.0
        assert s.min_ms == 10.0
        assert s.max_ms == 30.0
        assert s.last_ms == 30.0

    def test_stats_all_keys(self):
        logger = LatencyLogger()
        logger._history["a->b"] = [5.0]
        logger._history["c->d"] = [10.0]
        result = logger.stats()
        assert len(result) == 2


class TestLatencyLoggerSaveToFile:
    """save_to_file() 메서드 검증."""

    def test_save_without_log_dir_noop(self):
        logger = LatencyLogger()  # no log_dir
        logger._history["x->y"] = [10.0]
        logger.save_to_file()  # should not raise

    def test_save_writes_json(self, tmp_path):
        logger = LatencyLogger(log_dir=str(tmp_path))
        logger._history["a->b"] = [100.0, 200.0]
        logger.save_to_file("test_out.json")
        filepath = tmp_path / "test_out.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert "a->b" in data
        assert data["a->b"]["count"] == 2
        assert data["a->b"]["avg_ms"] == 150.0


class TestLatencyLoggerClear:
    """clear() 메서드 검증."""

    def test_clear_resets_all(self):
        logger = LatencyLogger()
        logger.log("x")
        logger.log("y")
        logger.elapsed("x", "y")
        logger.clear()
        assert logger._timestamps == {}
        assert logger._history == {}


class TestLatencyLoggerThreadSafety:
    """스레드 안전성 검증."""

    def test_concurrent_log_no_crash(self):
        logger = LatencyLogger()
        errors = []

        def worker(label_prefix, count):
            try:
                for i in range(count):
                    logger.log(f"{label_prefix}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"t{t}", 50)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(logger._timestamps) == 200


# ---------------------------------------------------------------------------
# 모듈 레벨 하위호환 함수 테스트
# ---------------------------------------------------------------------------

class TestModuleLevelFunctions:
    """하위 호환 log(), elapsed(), get_logger() 검증."""

    def test_get_logger_returns_singleton(self):
        a = get_logger()
        b = get_logger()
        assert a is b

    def test_module_log_works(self):
        ts = log("module_test")
        assert ts > 0

    def test_module_elapsed_works(self):
        log("mod_start")
        log("mod_end")
        diff = elapsed("mod_start", "mod_end")
        assert diff is not None


# ---------------------------------------------------------------------------
# MeasurementStats dataclass 테스트
# ---------------------------------------------------------------------------

class TestMeasurementStats:
    def test_defaults(self):
        s = MeasurementStats()
        assert s.count == 0
        assert s.avg_ms == 0.0
        assert s.min_ms == float('inf')
        assert s.max_ms == 0.0
