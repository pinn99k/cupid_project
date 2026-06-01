# SIA 디바이스 펌웨어 (ESP32-CAM + 초음파)

> 칩에 구워 넣는 코드. **우리 파이썬 pytest 대상이 아님** (C++/임베디드).
> 펌웨어는 "센싱·스트리밍만" 한다. 보정·판단은 전부 서버. (refactor_plan §0, §6)

## 디렉토리
```
firmware/
  sia_camera/sia_camera.ino   ← 펌웨어 본체 (작성 예정)
  README.md                   ← 이 문서
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
| 라우트 | 응답 |
|--------|------|
| `GET /stream` | MJPEG (multipart/x-mixed-replace) |
| `GET /distance` | `{"cm": <날것값>, "ts": <ms>}` — **보정 안 함** |

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
