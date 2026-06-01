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
# 400 → 1024: gemini-2.5-flash thinking 토큰(≈300~400)이 max_tokens 예산에 포함됨.
# prompt=452 + thinking=385 → 출력 공간 15토큰 → 문장 잘림.
# thinking 비활성화(LLM_THINKING_BUDGET=0)와 병행하여 안전 여유 확보.
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# Gemini 2.5-flash thinking 제어 (0=비활성화, -1=모델 기본값)
# ⚠️ Gemini OpenAI 호환 엔드포인트는 extra_body의 generationConfig를 지원 안 함.
#    0 → reasoning_effort='none' (thinking 완전 비활성화, 문장 잘림 방지)
#   -1 → reasoning_effort 파라미터 생략 (모델 기본값)
LLM_THINKING_BUDGET: int = int(os.getenv("LLM_THINKING_BUDGET", "0"))
# 0.4 → 0.7: 더 자연스럽고 따뜻한 말투를 위해 온도 상향.
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# API 키 (사용하는 공급자 키만 있으면 됨)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# YOLO / 서버 설정
YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF_THRESHOLD: float = float(os.getenv("YOLO_CONF_THRESHOLD", "0.35"))
# 관련성 게이트(Unit 6): 화면 대비 면적이 이 값 미만인 객체는 무시.
# 배경 스크린(동물의숲 등)의 작고 먼 오탐 차단. 0이면 비활성.
RELEVANCE_MIN_AREA: float = float(os.getenv("RELEVANCE_MIN_AREA", "0.01"))
DETECTION_BROADCAST_INTERVAL: float = float(os.getenv("DETECTION_BROADCAST_INTERVAL", "0.1"))
AI_LOOP_SLEEP_SEC: float = float(os.getenv("AI_LOOP_SLEEP_SEC", "0.03"))
DANGER_DISTANCE_CM: float = float(os.getenv("DANGER_DISTANCE_CM", "30"))
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

# 카메라 설정
# 0 = 노트북 내장캠 (기본값), 1+ = 외장 USB 캠
WEBCAM_INDEX: int = int(os.getenv("WEBCAM_INDEX", "0"))


# 카메라 소스 (디바이스 연동)
# int 문자열 = 로컬 웹캠 인덱스, "http..." = ESP32-CAM MJPEG URL
def _parse_cam_source(value: str):
    value = value.strip()
    if value.lower().startswith("http"):
        return value
    return int(value)


# 기본값은 기존 WEBCAM_INDEX와 동일 (디바이스 미연결 시 로컬 웹캠 유지)
CAM_SOURCE = _parse_cam_source(os.getenv("CAM_SOURCE", str(WEBCAM_INDEX)))

# 초음파 (디바이스 폴링)
ULTRASONIC_URL: str = os.getenv("ULTRASONIC_URL", "")
ULTRASONIC_POLL_SEC: float = float(os.getenv("ULTRASONIC_POLL_SEC", "0.3"))
ULTRASONIC_OFFSET_CM: float = float(os.getenv("ULTRASONIC_OFFSET_CM", "0"))

# 마이크 설정
# None = 시스템 기본 마이크, 숫자 = 장치 인덱스
MIC_DEVICE_INDEX = os.getenv("MIC_DEVICE_INDEX")
if MIC_DEVICE_INDEX is not None:
    MIC_DEVICE_INDEX = int(MIC_DEVICE_INDEX)

# VAD 설정
VAD_SILENCE_THRESHOLD: int = int(os.getenv("VAD_SILENCE_THRESHOLD", "100"))
# 0.5s: 발화 종료 판정 무음 시간.
# ⚠️ .env에 이전 값(1.8 등)이 남아있으면 녹음이 길어짐. .env 확인 필수.
VAD_SILENCE_DURATION: float = float(os.getenv("VAD_SILENCE_DURATION", "0.5"))
# 7s: 최대 녹음 시간. 아이 발화가 7초를 넘는 경우는 거의 없음.
VAD_MAX_DURATION: float = float(os.getenv("VAD_MAX_DURATION", "7"))
# 저음량 되묻기(Unit 4): 발화 평균 RMS가 이 값 미만이면 "더 크게 말해줄래?".
# silence_threshold보다 높게 — 들리긴 하나 STT엔 너무 작은 구간. 0이면 비활성.
VAD_LOW_VOLUME_RMS: float = float(os.getenv("VAD_LOW_VOLUME_RMS", "0"))

# STT 설정
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "ko-KR")

# 출력 음성이 마이크에 되먹임되지 않도록 재생 완료 후 잠깐 더 듣기를 멈춘다.
VOICE_OUTPUT_SETTLE_SEC: float = float(os.getenv("VOICE_OUTPUT_SETTLE_SEC", "0.4"))
VOICE_REPROMPT_COOLDOWN_SEC: float = float(os.getenv("VOICE_REPROMPT_COOLDOWN_SEC", "2.0"))
