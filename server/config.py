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

# 디버그/계측 (Phase 0 측정)
# SIA_DEBUG=1 이면 핫루프 latency print 노출. 기본 꺼짐(스팸 방지). 집계는 항상 수행.
SIA_DEBUG: bool = os.getenv("SIA_DEBUG", "").lower() in ("1", "true", "yes", "on")
# 시연 모드: 호출어 뒤 질문을 키워드/YOLO 장면으로 매칭하고 사전 녹음 음성을 즉시 재생.
# true면 LLM/Gemini TTS 경로를 우회한다.
DEMO_MODE: bool = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes", "on")
# 종료 시 latency_log.json 저장 위치.
LATENCY_LOG_DIR: str = os.getenv("LATENCY_LOG_DIR", "logs")

# TTS 공급자 1순위 (속도 최적화). 실패 시 자동 폴백(edge/gemini/gtts).
#   edge   = Edge-TTS  (~0.6s, 표준 한국어 SunHi) — 기본/권장
#   gemini = Gemini TTS (~5.6s, 프롬프트로 따뜻한 톤)
#   gtts   = gTTS
TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge").lower()

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

# 카메라 영상 회전 (ESP32-CAM 부착 방향 보정)
# 0   = 회전 안 함 (기본값 — 끄면 변경 전과 100% 동일)
# 90  = 시계 방향(CW), 180 = 뒤집기, 270 = 반시계 방향(CCW)
# 회전은 cap.read() 직후 한 곳에서만 적용 → YOLO/bbox/거리추정 모두 회전 기준으로 일관.
def _parse_rotation(value: str) -> int:
    try:
        deg = int(value.strip())
    except (ValueError, AttributeError):
        deg = 0
    if deg not in (0, 90, 180, 270):
        print(f"[config] 경고: CAMERA_ROTATION={value!r} 은 0/90/180/270 만 허용 → 0 사용")
        return 0
    return deg


CAMERA_ROTATION: int = _parse_rotation(os.getenv("CAMERA_ROTATION", "0"))

# 초음파 (디바이스 폴링)
# URL 이 비면 폴링 비활성 → ultrasonic_cm None (디바이스 미연결 시 현행과 동일).
ULTRASONIC_URL: str = os.getenv("ULTRASONIC_URL", "")
ULTRASONIC_POLL_SEC: float = float(os.getenv("ULTRASONIC_POLL_SEC", "0.3"))
ULTRASONIC_OFFSET_CM: float = float(os.getenv("ULTRASONIC_OFFSET_CM", "0"))
# 요청 타임아웃 — 무선이 죽어도 루프가 매달리지 않게 짧게.
ULTRASONIC_TIMEOUT_SEC: float = float(os.getenv("ULTRASONIC_TIMEOUT_SEC", "0.5"))
# 마지막 정상 응답 후 이 시간을 넘으면 거리→None (끊김 시 오래된 값으로 오경보 방지).
ULTRASONIC_STALE_SEC: float = float(os.getenv("ULTRASONIC_STALE_SEC", "1.5"))
# 중앙값 필터 윈도우(최근 N개 날것 측정).
ULTRASONIC_BUFFER_N: int = int(os.getenv("ULTRASONIC_BUFFER_N", "5"))

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

# 적응형 무음 임계(ambient calibration) 킬스위치.
# on(기본): 녹음 시작 시 배경소음 RMS를 측정해 무음 임계를 자동 보정 →
#   부스 배경소음이 커도 발화 끝(무음)을 제대로 감지(max_duration 통녹음 방지).
# off: VAD_SILENCE_THRESHOLD 고정값만 사용(기존 동작).
VAD_ADAPTIVE: bool = os.getenv("VAD_ADAPTIVE", "on").lower() in ("1", "true", "yes", "on")
# 동적 무음 임계 = max(VAD_SILENCE_THRESHOLD, ambient_rms * VAD_AMBIENT_FACTOR).
# 계수가 클수록 무음 기준이 배경소음보다 더 높이 올라간다(1.5~2.0 권장).
VAD_AMBIENT_FACTOR: float = float(os.getenv("VAD_AMBIENT_FACTOR", "2.0"))

# STT 설정
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "ko-KR")

# 출력 음성이 마이크에 되먹임되지 않도록 재생 완료 후 잠깐 더 듣기를 멈춘다.
VOICE_OUTPUT_SETTLE_SEC: float = float(os.getenv("VOICE_OUTPUT_SETTLE_SEC", "0.4"))
VOICE_REPROMPT_COOLDOWN_SEC: float = float(os.getenv("VOICE_REPROMPT_COOLDOWN_SEC", "2.0"))
