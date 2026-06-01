# SIA 디바이스 펌웨어 (ESP32-CAM + 초음파)

> 칩에 구워 넣는 코드. **우리 파이썬 pytest 대상이 아님** (C++/임베디드).
> 펌웨어는 "센싱·스트리밍만" 한다. 보정·판단은 전부 서버. (refactor_plan §0, §6)

## 디렉토리
```
firmware/
  PLAN.md                       ← 작성 계획·설계 근거
  README.md                     ← 이 문서 (규격·배선·브링업)
  sia_camera/
    sia_camera.ino              ← 펌웨어 본체
    sia_config.h                ← 핀·포트·주기 상수
    sia_distance.h              ← 순수 변환 로직(네이티브 테스트 대상)
    sia_secrets.example.h       ← WiFi 자격증명 템플릿 (→ sia_secrets.h 로 복사)
  tests/
    native/test_sia_distance.cpp  ← 칩 없이 g++ 단위테스트
    test_contract.py              ← /distance·/stream 계약(mock/실칩)
    bringup_checklist.md          ← 실칩 수동 5단계
```

## 굽는 규격 (아두이노 IDE)
| 설정 | 값 |
|------|-----|
| Board | AI Thinker ESP32-CAM |
| Partition Scheme | Huge APP (3MB) |
| PSRAM | Enabled |
| 카메라 모델 define | `CAMERA_MODEL_AI_THINKER` |

## 배선 (HC-SR04P, 3.3V 로직)
| 핀 | 연결 | 비고 |
|----|------|------|
| TRIG | GPIO13 | 출력 |
| ECHO | GPIO14 | 입력. strapping 핀(0·2·12·15) 회피 |
| VCC | 3.3V | HC-SR04**P**(3.3V) 사용 — 일반 SR04면 ECHO 분압 필요 |
| GND | GND | 공통 |
| 전원 | 5V/2A + 470µF | 브라운아웃 방지 |

> SD카드 사용 시 GPIO12~15 점유됨 → 미사용 전제. 핀은 단계2 테스트로 검증.

## 엔드포인트 계약 (서버와 합의)
> **2포트 분리**: 스트림(:81)이 장기 연결돼도 /distance(:80)가 안 끊김. (PLAN.md §2)

| 포트 | 라우트 | 응답 |
|------|--------|------|
| :81 | `GET /stream` | MJPEG (multipart/x-mixed-replace;boundary=frame) |
| :80 | `GET /distance` | `{"cm": <날것값>, "ts": <ms>}` — **보정 안 함**. 무반사 시 `cm=-1.0` |
| :80 | `GET /health` | `{"ok": true, ...}` — 브링업 점검용(서버 미사용) |

서버 `.env` 매핑:
```
CAM_SOURCE=http://<device-ip>:81/stream
ULTRASONIC_URL=http://<device-ip>:80/distance
```

## 단계별 브링업 (실칩 수동 테스트)
0. Blink+시리얼 hello → 보드/플래싱 확인
1. WiFi 연결, IP 출력
2. **초음파만**(카메라 끔) → 시리얼에 cm
3. **카메라만** → 브라우저 `/stream`
4. 스트림 + `/distance` 동시
5. 서버 연결 (`tools/hil_check.py`)

## 함정 차단
- 브라운아웃: 안정 전원 + 디커플링 캡
- MJPEG 중 /distance 블로킹 금지 (측정은 별도 주기, 핸들러는 캐시값)
- pulseIn 타임아웃 설정 (4m≈23ms)
- WiFi 재연결 + 워치독
- 고정 IP/DHCP 예약 (URL 고정)
