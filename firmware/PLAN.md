# SIA 펌웨어 작성 계획

> 대상: ESP32-CAM (AI-Thinker) + HC-SR04P 초음파
> 원칙: **펌웨어는 센싱·스트리밍만.** 보정·판단·필터는 전부 서버(`ai_core/calibration.py`, `ai_core/danger.py`).
> 계약 출처: `firmware/README.md`, `docs/architecture_v2.md`, `tools/mock_device.py`

---

## 0. 목표 (한 줄)
실칩이 `mock_device.py`와 **바이트 단위로 호환되는** `/stream`·`/distance`를 내보내, 서버 `.env`의 URL만 바꾸면 가짜↔실칩이 무중단 교체되게 한다.

---

## 1. 서버 계약 (깨면 안 됨)

| 라우트 | 응답 | 비고 |
|--------|------|------|
| `GET /stream` | `multipart/x-mixed-replace;boundary=frame` MJPEG | 파트 헤더 `Content-Type: image/jpeg` |
| `GET /distance` | `{"cm": <float>, "ts": <ms>}` | **보정 안 함(날것).** 무반사 시 `cm=-1.0` |
| `GET /health` | `{"ok": true, ...}` | 부가 — 브링업 점검용 (서버 미사용) |

- 서버 `calibration.py`가 cm를 받아 오프셋·중앙값 필터(유효 2~400cm)를 적용하므로, 펌웨어는 **유효성 검사를 하지 않는다.** 범위 밖/무반사값(`-1.0`)을 그대로 보내면 서버가 버린다.
- `ts`는 `millis()`(부팅 후 ms). 서버는 단조성만 참고.

## 2. 포트 구조 (확정: 2포트 분리)
- **:80** — 제어/센서: `/distance`, `/health`
- **:81** — 영상: `/stream`
- 이유: MJPEG 장기 연결이 같은 소켓 워커를 점유해도 `/distance`가 다른 서버 인스턴스에서 응답 → 끊김 없음 (ESP32-CAM 표준 패턴).
- 서버 `.env` 매핑:
  ```
  CAM_SOURCE=http://<device-ip>:81/stream
  ULTRASONIC_URL=http://<device-ip>:80/distance
  ```

## 3. 배선 (README와 일치)
| 핀 | 연결 |
|----|------|
| GPIO13 | TRIG (출력) |
| GPIO14 | ECHO (입력, HC-SR04**P** 3.3V 로직) |
| 3.3V / GND | VCC / GND |
| 5V/2A + 470µF | 메인 전원 (브라운아웃 방지) |

## 4. 함정 차단 설계
| 함정 | 대책 | 코드 위치 |
|------|------|-----------|
| MJPEG 중 `/distance` 블로킹 | 거리는 `loop()`에서 주기 측정 → 캐시. 핸들러는 캐시값만 반환 | `sia_camera.ino` `measure_distance()` / `distance_handler()` |
| `pulseIn` 무한 대기 | 타임아웃 25ms(≈4.3m) | `sia_distance.h` `SIA_ECHO_TIMEOUT_US` |
| WiFi 끊김 | `loop()`에서 연결 확인 + 재연결 | `ensure_wifi()` |
| 브라운아웃 리셋 | HW(안정 전원+캡) 우선. SW 디텍터 비활성은 **주석으로만** 제공 | `.ino` 상단 |
| URL 변동 | 고정 IP/DHCP 예약 권장 (문서) | `bringup_checklist.md` |

## 5. 파일 구성
```
firmware/
  PLAN.md                         ← 이 문서
  README.md                       ← 규격·배선·브링업 (갱신: 포트 매핑)
  .gitignore                      ← 비밀키/빌드물 제외
  sia_camera/
    sia_camera.ino                ← 본체 (WiFi·카메라·2서버·거리캐시)
    sia_config.h                  ← 핀·포트·주기·프레임 상수 (커밋)
    sia_distance.h                ← 순수 변환 로직 (Arduino 비의존 → 네이티브 테스트 가능)
    sia_secrets.example.h         ← WiFi 자격증명 템플릿 (커밋)
    sia_secrets.h                 ← 실제 자격증명 (gitignore)
  tests/
    README.md                     ← 테스트 3종 설명
    native/
      test_sia_distance.cpp       ← 순수 헤더 단위테스트 (g++)
      run.ps1 / run.sh            ← 빌드+실행
    test_contract.py              ← /distance·/stream 계약 검증 (mock/실칩 URL)
    bringup_checklist.md          ← 실칩 수동 5단계 점검
```

## 6. 테스트 전략 (3층)
1. **네이티브 단위** (`tests/native/`) — `sia_distance.h`의 순수 함수(`pulse_us→cm`, JSON 포맷)를 칩 없이 g++로 검증. 펌웨어 핵심 산술/계약 키를 보장.
2. **계약 통합** (`tests/test_contract.py`) — pytest. `SIA_DEVICE_HOST` 환경변수로 mock(기본) 또는 실칩을 가리켜 `/distance` JSON 스키마·`/stream` Content-Type 검증. 기존 파이썬 pytest 문화와 일치.
3. **수동 브링업** (`bringup_checklist.md`) — LED 블링크·브라우저 스트림 등 사람만 확인 가능한 단계.

## 7. 작업 순서
1. `sia_distance.h` (순수) → 네이티브 테스트로 먼저 검증
2. `sia_config.h`, `sia_secrets.example.h`
3. `sia_camera.ino` (브링업 단계 0→5 순서대로 구현 가능하게 구조화)
4. `tests/` 3종 + README 갱신
5. mock 대상 계약 테스트 통과 확인 → 실칩 굽기 전 코드 레벨 검증 완료

---
_— 계획 끝 —_
