// sia_config.h — 핀/포트/주기/프레임 상수 (커밋됨, 비밀 없음)
#ifndef SIA_CONFIG_H
#define SIA_CONFIG_H

// ---- 카메라 보드 모델 (아두이노 IDE Board: "AI Thinker ESP32-CAM") ----
#define CAMERA_MODEL_AI_THINKER 1

// ---- 초음파 핀 (firmware/README.md 배선표와 일치) ----
#define SIA_PIN_TRIG 13  // 출력
#define SIA_PIN_ECHO 14  // 입력. strapping 핀(0·2·12·15) 회피

// ---- 온보드 LED (브링업 0단계 블링크) ----
#define SIA_PIN_LED 33  // AI-Thinker 빨간 LED (LOW=켜짐)

// ---- HTTP 포트 (2포트 분리: 계약/PLAN.md §2) ----
#define SIA_PORT_CONTROL 80  // /distance, /health
#define SIA_PORT_STREAM 81   // /stream (MJPEG)

// ---- 거리 측정 주기 (loop에서 캐시 갱신) ----
#define SIA_POLL_MS 100  // 10Hz. 서버 ULTRASONIC_POLL_SEC(0.3s)보다 촘촘

// ---- WiFi 재연결 ----
#define SIA_WIFI_RETRY_MS 500    // 최초 연결 시 점 찍는 간격
#define SIA_WIFI_CHECK_MS 5000   // loop에서 연결 상태 점검 간격

// ---- 카메라 프레임 (PSRAM Enabled 전제) ----
// 시연 화질/대역 균형. PSRAM 없으면 자동으로 더 작은 프레임으로 폴백.
#define SIA_JPEG_QUALITY 12      // 0(최고)~63(최저). 10~14 권장
#define SIA_FB_COUNT 2           // PSRAM 있을 때 프레임버퍼 2개(파이프라인)

#endif  // SIA_CONFIG_H
