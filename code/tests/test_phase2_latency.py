"""LatencyLogger 테스트 -- P3 history, file output, thread safety."""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

if __name__ != "__main__":
    import pytest

    pytest.skip("standalone latency verification script", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.latency_logger import LatencyLogger, MeasurementStats
from utils import latency_logger as ll_module

passed = 0
failed = 0


def check(name: str, condition: bool):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


# ------------------------------------------------------------------ #
print("=== 1. log() records timestamp ===")
logger = LatencyLogger()
ts = logger.log("test_a")
check("returns float ms", isinstance(ts, float) and ts > 0)
check("timestamp stored", logger._timestamps.get("test_a") == ts)

# ------------------------------------------------------------------ #
print("\n=== 2. elapsed() calculates diff ===")
logger2 = LatencyLogger()
logger2._timestamps["s"] = 1000.0
logger2._timestamps["e"] = 1250.0
diff = logger2.elapsed("s", "e")
check("diff is 250", diff == 250.0)

# ------------------------------------------------------------------ #
print("\n=== 3. elapsed() returns None for missing labels ===")
logger3 = LatencyLogger()
check("missing start", logger3.elapsed("nope", "e") is None)
logger3._timestamps["s"] = 1000.0
check("missing end", logger3.elapsed("s", "nope") is None)

# ------------------------------------------------------------------ #
print("\n=== 4. history stored correctly ===")
logger4 = LatencyLogger()
logger4._timestamps["a"] = 100.0
logger4._timestamps["b"] = 200.0
logger4.elapsed("a", "b")
logger4._timestamps["b"] = 350.0
logger4.elapsed("a", "b")
key = "a->b"
check("history has 2 entries", len(logger4._history[key]) == 2)
check("first entry 100", logger4._history[key][0] == 100.0)
check("second entry 250", logger4._history[key][1] == 250.0)

# ------------------------------------------------------------------ #
print("\n=== 5. stats() returns correct avg/min/max ===")
st = logger4.stats(key)
check("key in stats", key in st)
m = st[key]
check("count 2", m.count == 2)
check("avg 175", m.avg_ms == 175.0)
check("min 100", m.min_ms == 100.0)
check("max 250", m.max_ms == 250.0)
check("last 250", m.last_ms == 250.0)

# ------------------------------------------------------------------ #
print("\n=== 6. max_history limit ===")
logger5 = LatencyLogger(max_history=3)
for i in range(5):
    logger5._timestamps["x"] = 0.0
    logger5._timestamps["y"] = float(i + 1)
    logger5.elapsed("x", "y")
hist = logger5._history["x->y"]
check("trimmed to 3", len(hist) == 3)
check("oldest dropped", hist[0] == 3.0)

# ------------------------------------------------------------------ #
print("\n=== 7. thread safety ===")
logger6 = LatencyLogger(max_history=10000)
errors = []

def worker(tid: int):
    try:
        for i in range(100):
            sl = f"t{tid}_s_{i}"
            el = f"t{tid}_e_{i}"
            logger6.log(sl)
            logger6.log(el)
            logger6.elapsed(sl, el)
    except Exception as exc:
        errors.append(exc)

threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("no exceptions", len(errors) == 0)
all_stats = logger6.stats()
check("stats non-empty", len(all_stats) > 0)

# ------------------------------------------------------------------ #
print("\n=== 8. save_to_file creates JSON ===")
with tempfile.TemporaryDirectory() as tmpdir:
    logger7 = LatencyLogger(log_dir=tmpdir)
    logger7._timestamps["p"] = 0.0
    logger7._timestamps["q"] = 42.0
    logger7.elapsed("p", "q")
    logger7.save_to_file("test_out.json")
    fp = Path(tmpdir) / "test_out.json"
    check("file exists", fp.exists())
    data = json.loads(fp.read_text(encoding="utf-8"))
    check("key in json", "p->q" in data)
    check("avg_ms correct", data["p->q"]["avg_ms"] == 42.0)

# ------------------------------------------------------------------ #
print("\n=== 9. clear() resets everything ===")
logger8 = LatencyLogger()
logger8.log("z")
logger8._timestamps["z2"] = logger8._timestamps["z"] + 10
logger8.elapsed("z", "z2")
logger8.clear()
check("timestamps empty", len(logger8._timestamps) == 0)
check("history empty", len(logger8._history) == 0)

# ------------------------------------------------------------------ #
print("\n=== 10. backward compatibility (module-level functions) ===")
ts_m = ll_module.log("compat_test")
check("module log returns float", isinstance(ts_m, float))
inst = ll_module.get_logger()
check("get_logger returns LatencyLogger", isinstance(inst, LatencyLogger))
check("module elapsed returns None for missing", ll_module.elapsed("no", "no") is None)

# ------------------------------------------------------------------ #
print("\n=== 11. no encoding issues (arrow char) ===")
# elapsed prints '->' not unicode arrow
import io, contextlib
logger9 = LatencyLogger()
logger9._timestamps["aa"] = 0.0
logger9._timestamps["bb"] = 1.0
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    logger9.elapsed("aa", "bb")
output = buf.getvalue()
check("uses ASCII arrow", "->" in output)
check("no unicode arrow", "→" not in output)

# ------------------------------------------------------------------ #
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
