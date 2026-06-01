// test_sia_distance.cpp — sia_distance.h 순수 함수 네이티브 단위테스트
//
// 칩 없이 호스트 g++로 펌웨어 핵심 산술/계약 키를 검증한다.
// 실행: tests/native/run.ps1  (또는 run.sh)
//
// 프레임워크 없이 작은 assert 매크로만 사용 (의존성 0).
#include <cmath>
#include <cstdio>
#include <cstring>

#include "../../sia_camera/sia_distance.h"

static int g_failures = 0;

#define CHECK(cond, msg)                                          \
    do {                                                          \
        if (!(cond)) {                                            \
            std::printf("  FAIL: %s  (%s:%d)\n", msg, __FILE__,   \
                        __LINE__);                                \
            g_failures++;                                         \
        } else {                                                 \
            std::printf("  ok:   %s\n", msg);                     \
        }                                                         \
    } while (0)

static bool nearly(float a, float b) { return std::fabs(a - b) < 0.05f; }

int main() {
    std::printf("[test] sia_pulse_us_to_cm\n");
    // 무반사(타임아웃) → 센티넬
    CHECK(sia_pulse_us_to_cm(0) == SIA_NO_ECHO, "us=0 -> SIA_NO_ECHO(-1.0)");
    // 58us 왕복 ≈ 1cm
    CHECK(nearly(sia_pulse_us_to_cm(58), 1.0f), "58us -> ~1cm");
    // 1740us ≈ 30cm (서버 위험 임계 근처)
    CHECK(nearly(sia_pulse_us_to_cm(1740), 30.0f), "1740us -> ~30cm");
    // 타임아웃 한계(25000us) ≈ 431cm (서버가 >400으로 버림)
    CHECK(sia_pulse_us_to_cm(SIA_ECHO_TIMEOUT_US) > 400.0f,
          "timeout limit -> >400cm (server rejects)");

    std::printf("[test] sia_format_distance_json\n");
    char buf[64];
    int n = sia_format_distance_json(buf, sizeof(buf), 30.0f, 123456u);
    CHECK(n > 0 && n < (int)sizeof(buf), "json fits buffer");
    // mock_device.py distance_payload() 와 동일 키
    CHECK(std::strstr(buf, "\"cm\":30.0") != NULL, "key cm present, 1 decimal");
    CHECK(std::strstr(buf, "\"ts\":123456") != NULL, "key ts present");
    std::printf("  json = %s\n", buf);

    // 무반사값도 그대로 직렬화 (서버가 판단)
    sia_format_distance_json(buf, sizeof(buf), SIA_NO_ECHO, 1u);
    CHECK(std::strstr(buf, "\"cm\":-1.0") != NULL, "no-echo serialized as -1.0");

    if (g_failures == 0) {
        std::printf("\nALL PASS\n");
        return 0;
    }
    std::printf("\n%d FAILURE(S)\n", g_failures);
    return 1;
}
