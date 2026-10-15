# firmware/tests — 펌웨어 테스트 3층

> 펌웨어 본체(`.ino`)는 C++/임베디드라 파이썬 pytest 직접 대상이 아니다(README §).
> 대신 **순수 로직은 네이티브로**, **계약은 살아있는 엔드포인트로**, **나머지는 사람이** 검증한다.

| 층 | 파일 | 칩 필요? | 무엇을 보장 |
|----|------|:--------:|-------------|
| 1. 네이티브 단위 | `native/test_sia_distance.cpp` | ❌ | `sia_distance.h` 산술·JSON 키(`cm`/`ts`) |
| 2. 계약 통합 | `test_contract.py` | ❌(mock) / ✅(실칩) | `/distance` 스키마·범위, `/stream` Content-Type |
| 3. 수동 브링업 | `bringup_checklist.md` | ✅ | LED·스트림 화면 등 사람만 확인 |

## 1) 네이티브 단위테스트
g++ 만 있으면 칩 없이 즉시 실행.
```powershell
# Windows
powershell -File firmware/tests/native/run.ps1
```
```bash
# Linux/macOS/WSL
bash firmware/tests/native/run.sh
```
g++ 가 없으면 자동으로 "건너뜀" 안내 후 종료(0).

## 2) 계약 테스트 (mock 으로 칩 없이)
한 터미널에서 가짜 디바이스를 띄우고:
```powershell
python tools/mock_device.py --port 9000
```
다른 터미널에서 같은 포트를 가리켜 실행:
```powershell
$env:SIA_DEVICE_HOST="127.0.0.1"
$env:SIA_PORT_CONTROL="9000"
$env:SIA_PORT_STREAM="9000"
pytest firmware/tests/test_contract.py -v
```
실칩이면:
```powershell
$env:SIA_DEVICE_HOST="192.168.0.50"   # 기본 포트 80/81
pytest firmware/tests/test_contract.py -v
```
대상이 응답하지 않으면 실패가 아니라 **skip** 된다(디바이스 부재 시 CI 안전).

## 3) 수동 브링업
실칩을 처음 구웠을 때 `bringup_checklist.md` 를 0→5단계 순서로 따라간다.
