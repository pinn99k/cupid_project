// sia_distance.h — 초음파 순수 변환 로직 (Arduino 비의존)
//
// 이 헤더는 하드웨어/네트워크에 의존하지 않는 순수 함수만 담는다.
// 덕분에 칩 없이 호스트(g++)에서 단위테스트할 수 있다. (tests/native/)
//
// 원칙: 펌웨어는 "날것 cm"만 만든다. 유효성·보정은 서버 calibration.py.
#ifndef SIA_DISTANCE_H
#define SIA_DISTANCE_H

#include <stdint.h>
#include <stdio.h>

// HC-SR04 계열: 음속 343m/s 기준 왕복 시간(us) → 편도 거리(cm) = us / 58.0
static const float SIA_US_PER_CM = 58.0f;

// 에코 미수신(타임아웃) 센티넬. 서버 is_valid_distance(2~400cm)가 버린다.
static const float SIA_NO_ECHO = -1.0f;

// pulseIn 타임아웃(us). 400cm 왕복 ≈ 400*58 = 23200us, 여유 두어 25ms.
static const uint32_t SIA_ECHO_TIMEOUT_US = 25000;

// 에코 펄스폭(us) → cm.
//   pulse_us == 0  : pulseIn 타임아웃(무반사) → SIA_NO_ECHO
//   그 외          : us / 58.0  (날것, 보정 없음)
static inline float sia_pulse_us_to_cm(uint32_t pulse_us) {
    if (pulse_us == 0) {
        return SIA_NO_ECHO;
    }
    return (float)pulse_us / SIA_US_PER_CM;
}

// /distance 응답 본문 생성: {"cm":<f.1>,"ts":<ms>}
// mock_device.py 의 distance_payload()와 키·형태가 일치해야 한다.
// 반환: snprintf 규약(쓰였어야 할 문자 수). 성공 시 0 < n < buf_len.
static inline int sia_format_distance_json(char *buf, int buf_len,
                                           float cm, uint32_t ts_ms) {
    return snprintf(buf, (size_t)buf_len,
                    "{\"cm\":%.1f,\"ts\":%lu}",
                    cm, (unsigned long)ts_ms);
}

#endif  // SIA_DISTANCE_H
