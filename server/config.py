"""서버 설정. 필수 환경변수 누락 시 즉시 에러 발생 (fail-fast)."""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """환경변수가 없거나 비어있으면 RuntimeError."""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"[config] 필수 환경변수 '{key}' 미설정. .env 파일 확인 필요."
        )
    return value


# LLM API 키 (둘 중 하나는 있어야 LLM 사용 가능, TTS는 edge-tts라 키 불필요)
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF_THRESHOLD: float = float(os.getenv("YOLO_CONF_THRESHOLD", "0.4"))
DANGER_DISTANCE_CM: float = float(os.getenv("DANGER_DISTANCE_CM", "30"))
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
