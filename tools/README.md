# tools/ — 개발·시연 보조 도구

> 운영 코드 아님. 디바이스 없이 개발/테스트하거나 시연 폴백용.

## mock_device.py — 가짜 ESP32-CAM
실제 칩 없이 서버/파이프라인 전체를 테스트하거나, 시연 중 디바이스 사망 시 폴백.

```bash
python tools/mock_device.py                  # 합성 프레임 (움직이는 사각형)
python tools/mock_device.py --video clip.mp4 --port 9000
```

서버 연결 (.env):
```
CAM_SOURCE=http://127.0.0.1:9000/stream
ULTRASONIC_URL=http://127.0.0.1:9000/distance
```

거리값 주입:
```bash
curl -X POST "http://127.0.0.1:9000/set_distance?cm=30"
```

코어 로직(`MockDevice`)은 `tests/test_mock_device.py`에서 포트 없이 단위테스트.

## hil_check.py — 실칩 연결 점검 (작성 예정)
실제 디바이스 연결 시 `/stream`·`/distance` 수신을 사람이 눈으로 확인하는 수동 스크립트.
**pytest 아님** (하드웨어 필요).
