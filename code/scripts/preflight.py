"""갈라쇼 시연 전 소프트웨어 점검. 실행: venv/bin/python scripts/preflight.py"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.preflight import run_preflight


def main():
    result = run_preflight()
    print("[SIA Preflight]")
    for name, passed in result["checks"].items():
        print(f"  {'OK' if passed else 'FAIL':4} {name}")
    if result["missing_fallback"]:
        print("  누락 fallback:", ", ".join(result["missing_fallback"]))
        print("  생성 명령: venv/bin/python audio/generate_fallback.py")
    print(f"\n결과: {'READY' if result['ok'] else 'NOT READY'}")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
