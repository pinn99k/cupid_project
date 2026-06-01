// sia_camera.ino — SIA 디바이스 펌웨어 (ESP32-CAM AI-Thinker + HC-SR04P)
//
// 역할: 센싱·스트리밍만. 보정/판단/필터는 전부 서버.
//   :81  GET /stream    → MJPEG (multipart/x-mixed-replace;boundary=frame)
//   :80  GET /distance  → {"cm":<날것>,"ts":<ms>}  (보정 안 함, 무반사 -1.0)
//   :80  GET /health    → {"ok":true,...}           (브링업 점검용)
//
// 굽는 규격(아두이노 IDE): Board=AI Thinker ESP32-CAM, Partition=Huge APP(3MB), PSRAM=Enabled
// 자세한 설계: ../PLAN.md, ../README.md
//
// 브링업 단계(../tests/bringup_checklist.md):
//   0 Blink+시리얼  1 WiFi+IP  2 초음파만  3 카메라만  4 동시  5 서버연결

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include "esp_timer.h"

// 브라운아웃 디텍터 SW 비활성 (선택). README는 HW(안정 전원+470µF 캡)를 우선한다.
// 전원이 부실해 부팅 중 리셋이 반복되면 아래 두 줄 주석을 풀 것:
// #include "soc/soc.h"
// #include "soc/rtc_cntl_reg.h"

#include "sia_config.h"
#include "sia_secrets.h"
#include "sia_distance.h"

// ---------------------------------------------------------------------------
// AI-Thinker ESP32-CAM 핀맵
// ---------------------------------------------------------------------------
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ---------------------------------------------------------------------------
// 거리 캐시 — loop()가 갱신, /distance 핸들러가 읽기만 (논블로킹)
// ---------------------------------------------------------------------------
static volatile float g_distance_cm = SIA_NO_ECHO;
static volatile uint32_t g_distance_ts = 0;

static httpd_handle_t g_control_httpd = NULL;
static httpd_handle_t g_stream_httpd = NULL;

// MJPEG 경계 문자열 (mock_device.py 와 동일하게 "frame")
static const char *STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// ===========================================================================
// 초음파 측정 (loop에서 주기 호출)
// ===========================================================================
static void measure_distance() {
    // TRIG 10us 펄스
    digitalWrite(SIA_PIN_TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(SIA_PIN_TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(SIA_PIN_TRIG, LOW);

    // ECHO 펄스폭(us). 타임아웃 시 0 반환.
    uint32_t pulse_us = pulseIn(SIA_PIN_ECHO, HIGH, SIA_ECHO_TIMEOUT_US);

    g_distance_cm = sia_pulse_us_to_cm(pulse_us);  // 순수 변환(sia_distance.h)
    g_distance_ts = (uint32_t)millis();
}

// ===========================================================================
// HTTP 핸들러
// ===========================================================================
static esp_err_t distance_handler(httpd_req_t *req) {
    char body[64];
    int n = sia_format_distance_json(body, sizeof(body),
                                     g_distance_cm, g_distance_ts);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, body, n);
}

static esp_err_t health_handler(httpd_req_t *req) {
    char body[96];
    int n = snprintf(body, sizeof(body),
                     "{\"ok\":true,\"uptime_ms\":%lu,\"rssi\":%d}",
                     (unsigned long)millis(), (int)WiFi.RSSI());
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, body, n);
}

static esp_err_t stream_handler(httpd_req_t *req) {
    esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    char part_buf[64];
    while (true) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[STREAM] fb_get 실패");
            res = ESP_FAIL;
            break;
        }

        // JPEG 보장 (PIXFORMAT_JPEG 설정이면 fb->buf 가 곧 JPEG)
        uint8_t *jpg = fb->buf;
        size_t jpg_len = fb->len;
        bool converted = false;
        if (fb->format != PIXFORMAT_JPEG) {
            converted = frame2jpg(fb, 80, &jpg, &jpg_len);
            esp_camera_fb_return(fb);
            fb = NULL;
            if (!converted) {
                Serial.println("[STREAM] JPEG 변환 실패");
                res = ESP_FAIL;
                break;
            }
        }

        // --frame 경계 → 파트 헤더 → JPEG 본문
        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res == ESP_OK) {
            int hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART,
                                (unsigned)jpg_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)jpg, jpg_len);
        }

        if (fb) {
            esp_camera_fb_return(fb);
        } else if (converted) {
            free(jpg);
        }

        if (res != ESP_OK) {
            break;  // 클라이언트 연결 종료
        }
    }
    return res;
}

// ===========================================================================
// 서버 기동 (2포트 분리)
// ===========================================================================
static void start_servers() {
    // --- 제어 서버 :80 (/distance, /health) ---
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = SIA_PORT_CONTROL;
    cfg.ctrl_port = 32080;
    if (httpd_start(&g_control_httpd, &cfg) == ESP_OK) {
        httpd_uri_t u_dist = {.uri = "/distance", .method = HTTP_GET,
                              .handler = distance_handler, .user_ctx = NULL};
        httpd_uri_t u_health = {.uri = "/health", .method = HTTP_GET,
                                .handler = health_handler, .user_ctx = NULL};
        httpd_register_uri_handler(g_control_httpd, &u_dist);
        httpd_register_uri_handler(g_control_httpd, &u_health);
        Serial.printf("[HTTP] 제어 서버 :%d  /distance /health\n", SIA_PORT_CONTROL);
    } else {
        Serial.println("[HTTP] 제어 서버 기동 실패");
    }

    // --- 스트림 서버 :81 (/stream) — 별도 인스턴스로 분리 ---
    httpd_config_t scfg = HTTPD_DEFAULT_CONFIG();
    scfg.server_port = SIA_PORT_STREAM;
    scfg.ctrl_port = 32081;
    if (httpd_start(&g_stream_httpd, &scfg) == ESP_OK) {
        httpd_uri_t u_stream = {.uri = "/stream", .method = HTTP_GET,
                                .handler = stream_handler, .user_ctx = NULL};
        httpd_register_uri_handler(g_stream_httpd, &u_stream);
        Serial.printf("[HTTP] 스트림 서버 :%d  /stream\n", SIA_PORT_STREAM);
    } else {
        Serial.println("[HTTP] 스트림 서버 기동 실패");
    }
}

// ===========================================================================
// 카메라 초기화
// ===========================================================================
static bool init_camera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.grab_mode = CAMERA_GRAB_LATEST;  // 항상 최신 프레임
    config.fb_location = CAMERA_FB_IN_PSRAM;

    if (psramFound()) {
        config.frame_size = FRAMESIZE_VGA;  // 640x480 (mock 프레임과 동일)
        config.jpeg_quality = SIA_JPEG_QUALITY;
        config.fb_count = SIA_FB_COUNT;
    } else {
        Serial.println("[CAM] PSRAM 없음 → QVGA 폴백");
        config.frame_size = FRAMESIZE_QVGA;  // 320x240
        config.jpeg_quality = 15;
        config.fb_count = 1;
        config.fb_location = CAMERA_FB_IN_DRAM;
    }

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[CAM] 초기화 실패 0x%x\n", err);
        return false;
    }
    return true;
}

// ===========================================================================
// WiFi
// ===========================================================================
static void connect_wifi() {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);  // 스트리밍 지연 줄이기
    WiFi.begin(SIA_WIFI_SSID, SIA_WIFI_PASS);
    Serial.printf("[WiFi] '%s' 연결 중", SIA_WIFI_SSID);
    while (WiFi.status() != WL_CONNECTED) {
        delay(SIA_WIFI_RETRY_MS);
        Serial.print(".");
    }
    Serial.println();
    Serial.printf("[WiFi] 연결됨. IP=%s\n", WiFi.localIP().toString().c_str());
    Serial.printf("       CAM_SOURCE=http://%s:%d/stream\n",
                  WiFi.localIP().toString().c_str(), SIA_PORT_STREAM);
    Serial.printf("       ULTRASONIC_URL=http://%s:%d/distance\n",
                  WiFi.localIP().toString().c_str(), SIA_PORT_CONTROL);
}

static void ensure_wifi() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    Serial.println("[WiFi] 끊김 → 재연결 시도");
    WiFi.disconnect();
    WiFi.begin(SIA_WIFI_SSID, SIA_WIFI_PASS);
}

// ===========================================================================
// setup / loop
// ===========================================================================
void setup() {
    // 전원 부실 시 브라운아웃 리셋 방지(선택). 위 include 주석과 함께 사용.
    // WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    Serial.setDebugOutput(false);
    Serial.println("\n[SIA] 부팅");

    pinMode(SIA_PIN_LED, OUTPUT);
    digitalWrite(SIA_PIN_LED, HIGH);  // LED off (LOW=on)
    pinMode(SIA_PIN_TRIG, OUTPUT);
    pinMode(SIA_PIN_ECHO, INPUT);
    digitalWrite(SIA_PIN_TRIG, LOW);

    // 0단계 블링크: 보드/플래싱 살아있음 신호
    for (int i = 0; i < 3; i++) {
        digitalWrite(SIA_PIN_LED, LOW);
        delay(100);
        digitalWrite(SIA_PIN_LED, HIGH);
        delay(100);
    }

    if (!init_camera()) {
        Serial.println("[SIA] 카메라 없이 계속 (초음파만 동작)");
    }

    connect_wifi();
    start_servers();
    Serial.println("[SIA] 준비 완료");
}

void loop() {
    static uint32_t last_poll = 0;
    static uint32_t last_wifi = 0;
    uint32_t now = millis();

    if (now - last_poll >= SIA_POLL_MS) {
        last_poll = now;
        measure_distance();
    }
    if (now - last_wifi >= SIA_WIFI_CHECK_MS) {
        last_wifi = now;
        ensure_wifi();
    }
    delay(1);  // WDT 양보
}
