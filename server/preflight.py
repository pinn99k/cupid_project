"""갈라쇼 시연 전 소프트웨어 상태 점검."""

from pathlib import Path
import importlib.util

from server.config import GEMINI_API_KEY, LLM_MODEL, YOLO_MODEL

REQUIRED_FALLBACK_FILES = [
    "buffer_01.wav",
    "warn_emergency.wav",
    "warn_object.wav",
    "warn_person.wav",
    "retry_what.wav",
    "retry_louder.wav",
    "retry_unclear.wav",
    "praise_01.wav",
    "gala_01.wav",
    "gala_03.wav",
]


def _microphone_available() -> bool:
    """sounddevice가 실제 기본 입력 장치를 열 수 있는 상태인지 확인."""
    try:
        import sounddevice as sd

        device = sd.query_devices(kind="input")
        return bool(device and device.get("max_input_channels", 0) > 0)
    except Exception:
        return False


def run_preflight() -> dict:
    """외부 API 호출 없이 시연 필수 파일과 패키지를 점검."""
    fallback_dir = Path("audio/fallback")
    checks = {
        "gemini_api_key": bool(GEMINI_API_KEY),
        "llm_model": bool(LLM_MODEL),
        "yolo_model_file": Path(YOLO_MODEL).exists(),
        "python_sounddevice": importlib.util.find_spec("sounddevice") is not None,
        "microphone_device": _microphone_available(),
        "python_pygame": importlib.util.find_spec("pygame") is not None,
        "python_ultralytics": importlib.util.find_spec("ultralytics") is not None,
        "dashboard_dependencies": Path("dashboard/node_modules").exists(),
    }
    missing_fallback = [
        filename
        for filename in REQUIRED_FALLBACK_FILES
        if not (fallback_dir / filename).exists()
        or (fallback_dir / filename).stat().st_size <= 44
    ]
    checks["fallback_audio"] = not missing_fallback
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "missing_fallback": missing_fallback,
    }
