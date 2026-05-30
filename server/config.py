"""
서버 설정. 필수 환경변수 누락 시 즉시 에러 발생 (fail-fast).
LLM_PROVIDER 값으로 Groq / Gemini / OpenAI 전환 가능.
"""

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


def _env_value(key: str, default: str) -> str:
    """환경변수 값에 실수로 들어간 'KEY=' 접두어를 제거."""
    value = os.getenv(key, default).strip()
    prefix = f"{key}="
    while value.startswith(prefix):
        print(f"[config] 경고: {key} 값에 중복 접두어가 있어 보정합니다.")
        value = value[len(prefix):].strip()
    return value


# LLM 공급자 및 모델
# LLM_PROVIDER: groq | gemini | openai
LLM_PROVIDER: str = _env_value("LLM_PROVIDER", "groq")
LLM_MODEL: str = _env_value("LLM_MODEL", "llama-3.3-70b-versatile")

# API 키 (사용하는 공급자 키만 있으면 됨)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# YOLO / 서버 설정
YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF_THRESHOLD: float = float(os.getenv("YOLO_CONF_THRESHOLD", "0.4"))
DANGER_DISTANCE_CM: float = float(os.getenv("DANGER_DISTANCE_CM", "30"))
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

# 카메라 설정
# 0 = 노트북 내장캠 (기본값), 1+ = 외장 USB 캠
WEBCAM_INDEX: int = int(os.getenv("WEBCAM_INDEX", "0"))

# 마이크 설정
# None = 시스템 기본 마이크, 숫자 = 장치 인덱스
MIC_DEVICE_INDEX = os.getenv("MIC_DEVICE_INDEX")
if MIC_DEVICE_INDEX is not None:
    MIC_DEVICE_INDEX = int(MIC_DEVICE_INDEX)

# VAD 설정
VAD_SILENCE_THRESHOLD: int = int(os.getenv("VAD_SILENCE_THRESHOLD", "500"))
VAD_SILENCE_DURATION: float = float(os.getenv("VAD_SILENCE_DURATION", "0.6"))
VAD_MAX_DURATION: float = float(os.getenv("VAD_MAX_DURATION", "10"))

# STT 설정
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "ko-KR")
