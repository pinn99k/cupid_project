# 실칩 브링업 체크리스트 (수동)

> 사람만 확인 가능한 단계. 자동 테스트(native/, test_contract.py)로는 못 잡는 것.
> 한 단계 통과 못 하면 다음으로 가지 말 것. (firmware/README.md §단계별 브링업)

## 굽기 전
- [ ] 아두이노 IDE — Board: **AI Thinker ESP32-CAM**
- [ ] Partition Scheme: **Huge APP (3MB)**
- [ ] PSRAM: **Enabled**
- [ ] `sia_camera/sia_secrets.h` 의 WiFi SSID/PASS 를 현장 값으로 채움
- [ ] 전원: **5V/2A** + 470µF 디커플링 캡 (USB-TTL 5V 만으론 부족할 수 있음)

## 0단계 — Blink + 시리얼
- [ ] 굽고 리셋 → 빨간 LED 3회 깜빡임
- [ ] 시리얼 모니터(115200)에 `[SIA] 부팅` 출력
- 실패 시: 보드/플래싱/IO0 GND 배선 확인

## 1단계 — WiFi + IP
- [ ] 시리얼에 `[WiFi] 연결됨. IP=...` 출력
- [ ] `CAM_SOURCE=...:81/stream`, `ULTRASONIC_URL=...:80/distance` 안내 줄 확인
- [ ] (권장) 공유기에서 이 MAC 에 **DHCP 고정 IP 예약** → URL 고정

## 2단계 — 초음파만
- [ ] 손바닥을 센서 앞 30cm 에 두고:
  ```
  curl http://<ip>:80/distance
  ```
  → `{"cm": ~30, "ts": ...}` (±수 cm 날것, 보정 없음)
- [ ] 센서 앞을 비우면 `cm` 이 커지거나 무반사 시 `-1.0`
- 배선: TRIG=GPIO13, ECHO=GPIO14, VCC=3.3V (HC-SR04**P**)

## 3단계 — 카메라만
- [ ] 브라우저로 `http://<ip>:81/stream` → 영상 보임
- [ ] 깨지거나 멈추면: PSRAM 설정/전원/`SIA_JPEG_QUALITY` 점검

## 4단계 — 스트림 + /distance 동시
- [ ] 브라우저에서 `:81/stream` 틀어둔 채
- [ ] 다른 창에서 `curl :80/distance` 반복 → **둘 다 끊김 없이** 응답
  (2포트 분리가 동작하는지 확인)

## 5단계 — 서버 연결
- [ ] 서버 `.env`:
  ```
  CAM_SOURCE=http://<ip>:81/stream
  ULTRASONIC_URL=http://<ip>:80/distance
  ```
- [ ] 계약 테스트로 교차검증:
  ```
  $env:SIA_DEVICE_HOST="<ip>"; pytest firmware/tests/test_contract.py -v
  ```
- [ ] 서버 파이프라인(YOLO/거리/내레이션) 정상 → 갈라쇼 시연 준비 완료

## 함정 메모
- 부팅 중 반복 리셋 = 브라운아웃. 전원 보강 먼저. 그래도면 `.ino` 상단 brownout 비활성 주석 해제.
- URL 이 자꾸 바뀜 = DHCP. 고정 IP 예약으로 해결.
- 스트림 중 거리 지연 = 2포트 분리 확인(`:80` vs `:81`).
