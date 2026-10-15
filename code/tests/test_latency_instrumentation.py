"""Phase 0 계측 — latency_logger 신규 기능(record/집계/게이팅/저장) 단위 테스트.

대상: utils.latency_logger 의 record(), verbose 게이팅, save_to_file.
핫패스 비의존 — 순수 로깅 동작만 검증.
"""

import json

from utils.latency_logger import LatencyLogger


def test_record_aggregates_stats():
    lg = LatencyLogger(verbose=False)
    for v in (100.0, 200.0, 300.0):
        lg.record("llm_ms", v)
    s = lg.stats("llm_ms")["llm_ms"]
    assert s.count == 3
    assert s.avg_ms == 200.0
    assert s.min_ms == 100.0
    assert s.max_ms == 300.0
    assert s.last_ms == 300.0


def test_history_window_capped():
    lg = LatencyLogger(max_history=3, verbose=False)
    for v in (1.0, 2.0, 3.0, 4.0, 5.0):
        lg.record("x", v)
    s = lg.stats("x")["x"]
    assert s.count == 3          # 최근 3개만
    assert s.min_ms == 3.0       # 1,2 는 밀려남


def test_verbose_gating_silent(capsys):
    lg = LatencyLogger(verbose=False)
    lg.record("k", 12.0)
    lg.log("label")
    out = capsys.readouterr().out
    assert "[LATENCY]" not in out   # 기본은 조용

    lg.set_verbose(True)
    lg.record("k", 13.0)
    out = capsys.readouterr().out
    assert "[LATENCY]" in out       # 켜면 노출


def test_save_to_file(tmp_path):
    lg = LatencyLogger(verbose=False)
    lg.set_log_dir(str(tmp_path))
    lg.record("tts_gen_ms", 850.0)
    lg.record("tts_gen_ms", 950.0)
    lg.save_to_file("latency_log.json")

    f = tmp_path / "latency_log.json"
    assert f.exists()
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["tts_gen_ms"]["count"] == 2
    assert data["tts_gen_ms"]["avg_ms"] == 900.0


def test_save_noop_without_dir():
    # 디렉토리 미설정이면 저장은 조용히 무시 (예외 없음)
    lg = LatencyLogger(verbose=False)
    lg.record("k", 1.0)
    lg.save_to_file()  # 예외 안 나면 통과
