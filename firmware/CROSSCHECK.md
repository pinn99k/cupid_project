# SIA 펌웨어 교차검증 가이드 (팀원용)

> 목적: 다른 팀원이 `firmware/` 코드를 **계약·안전·함정** 관점에서 독립 검증한다.
> 사용법 2가지 —
> (A) 사람이 직접 아래 체크리스트를 따라간다.
> (B) AI에게 맡긴다: 아래 **「AI 검증 프롬프트」** 블록을 통째로 복사해 붙여넣는다.
>
> 작성자 셀프체크는 통과 상태(계약 테스트 3/3 PASS). 교차검증은 **작성자를 의심하는 입장**에서 본다.

---

## 0. 배경 (5줄)
- 디바이스: **ESP32-CAM(AI-Thinker) + HC-SR04P**. 역할은 **센싱·스트리밍만**.
- 보정·판단·필터는 전부 서버(`ai_core/calibration.py`, `ai_core/danger.py`). 펌웨어는 **날것 cm**만 보낸다.
- 계약 기준 문서: `firmware/README.md`, `firmware/PLAN.md`, 그리고 가짜 디바이스 `tools/mock_device.py`(= 정답지).
- 펌웨어 본체는 `firmware/sia_camera/sia_camera.ino`. 순수 로직은 `sia_distance.h`.
- 핵심 합격 기준: **실칩이 `mock_device.py`와 바이트 호환** → 서버 `.env` URL만 바꿔 무중단 교체.

---

## 1. 계약 (이걸 깨면 무조건 반려)
| 포트 | 라우트 | 응답 | 검증 포인트 |
|------|--------|------|-------------|
| :81 | `GET /stream` | `multipart/x-mixed-replace;boundary=frame` | 파트 헤더 `Content-Type: image/jpeg`, boundary 문자열 `frame` |
| :80 | `GET /distance` | `{"cm": <float>, "ts": <ms>}` | **보정 금지**, 무반사 시 `cm=-1.0` |
| :80 | `GET /health` | `{"ok": true, ...}` | 부가(서버 미사용) |

서버 `.env` 매핑:
```
CAM_SOURCE=http://<ip>:81/stream
ULTRASONIC_URL=http://<ip>:80/distance
```

---

## 2. 자동 검증 (칩 없이, 5분)

### 2-1. 네이티브 단위테스트 (순수 로직)
```powershell
powershell -File firmware/tests/native/run.ps1     # Windows
# bash firmware/tests/native/run.sh                # Linux/macOS/WSL
```
- 기대: `ALL PASS`. (g++ 없으면 "건너뜀" → MinGW/MSYS2 설치 후 재실행)
- 무엇을 보장: `펄스(us)→cm` 산술, JSON 키(`cm`/`ts`), 무반사 `-1.0` 직렬화.

### 2-2. 계약 테스트 (mock 디바이스 = 정답지와 대조)
터미널 1:
```powershell
python tools/mock_device.py --port 9000
```
터미널 2:
```powershell
$env:SIA_DEVICE_HOST="127.0.0.1"; $env:SIA_PORT_CONTROL="9000"; $env:SIA_PORT_STREAM="9000"
pytest firmware/tests/test_contract.py -v
```
- 기대: `3 passed`. (디바이스 미응답 시 fail 아니라 skip)

---

## 3. 코드 리뷰 체크리스트 (사람 눈)
펌웨어는 g++/pytest로 다 못 잡는다. `sia_camera.ino`를 열고 아래를 **직접** 확인:

- [ ] **논블로킹 거리**: `/distance` 핸들러(`distance_handler`)가 센서를 *직접 트리거하지 않고* 캐시값(`g_distance_cm`)만 읽는가? 측정은 `loop()`의 `measure_distance()`에서만 일어나는가? (MJPEG 중 블로킹 금지 — README 함정)
- [ ] **pulseIn 타임아웃**: `SIA_ECHO_TIMEOUT_US`(25ms) 인자가 실제로 `pulseIn(...)`에 전달되는가? (무한 대기 차단)
- [ ] **무반사 처리**: 타임아웃(`pulse_us==0`) → `SIA_NO_ECHO(-1.0)`로 직렬화되고, **펌웨어가 버리지 않고** 서버로 보내는가? (유효성은 서버 몫)
- [ ] **2포트 분리**: 제어(:80)와 스트림(:81)이 **별도 httpd 인스턴스**인가? `ctrl_port`가 서로 다른가(32080 vs 32081)? (충돌 시 한쪽 기동 실패)
- [ ] **핀 일치**: `SIA_PIN_TRIG=13`, `SIA_PIN_ECHO=14`가 README 배선표·strapping 회피와 일치하는가?
- [ ] **JPEG 경계**: 스트림 응답이 `mock_device.py`의 `--frame ... Content-Type: image/jpeg` 패턴과 같은가?
- [ ] **WiFi 재연결**: `ensure_wifi()`가 `loop()`에서 주기 호출되는가?
- [ ] **비밀 노출 0**: `sia_secrets.h`가 `.gitignore`에 있고 git에 안 올라갔는가? (`git ls-files firmware | findstr secrets` → `example`만 나와야 함)
- [ ] **보정 흔적 0**: 펌웨어 어디에도 오프셋/중앙값/클램프 같은 *값 가공*이 없는가? (서버 책임 침범 금지)

검증:
```powershell
git ls-files firmware | Select-String secrets   # sia_secrets.example.h 만 나와야 함
```

---

## 4. 반려/통과 기준
- **반려**: 2-1 또는 2-2 실패 / §3 체크 중 하나라도 깨짐 / `sia_secrets.h` 추적됨 / 펌웨어가 cm를 가공함.
- **조건부 통과**: 자동 검증 OK + 코드리뷰 OK. (실칩 미보유면 여기까지가 한계 — 실칩 단계는 `tests/bringup_checklist.md`로 이관)
- **완전 통과**: 위 + 실칩에서 `bringup_checklist.md` 0~5단계 전부 OK.

리뷰 결과는 PR 코멘트 또는 아래 한 줄로:
```
[교차검증] native:PASS  contract:PASS  review:OK/NG(사유)  secrets:safe  → 통과/반려
```

---

## 5. AI 검증 프롬프트 (복사용)
> 아래 블록을 그대로 AI(Claude Code 등)에게 붙여넣으면 독립 검증을 수행한다.

```
역할: 너는 SIA 펌웨어를 교차검증하는 리뷰어다. 작성자를 신뢰하지 말고 계약 위반·안전 함정을 직접 찾아라.

대상 저장소: cupid_project (현재 폴더). 검증 대상: firmware/ 일체.
기준 문서: firmware/README.md, firmware/PLAN.md, firmware/CROSSCHECK.md, 그리고 정답지 tools/mock_device.py.

수행:
1. firmware/sia_camera/sia_camera.ino, sia_distance.h, sia_config.h 를 읽어라.
2. CROSSCHECK.md §3 "코드 리뷰 체크리스트" 9개 항목을 하나씩 코드 근거(file:line)와 함께 OK/NG로 판정하라.
3. 가능하면 자동 검증을 실제로 실행하라:
   - 네이티브: firmware/tests/native/run.ps1 (g++ 없으면 skip 사유 보고)
   - 계약: tools/mock_device.py 를 포트 9000으로 띄우고,
     SIA_PORT_CONTROL/STREAM=9000 으로 pytest firmware/tests/test_contract.py 실행.
   - 끝나면 띄운 mock 프로세스를 정리하라.
4. 핵심 계약을 mock_device.py 의 distance_payload()/stream 응답과 직접 대조하라(키 이름, boundary, -1.0 무반사 규칙).
5. 코드를 수정하지 말 것. 결과만 보고하라.

출력 형식:
- 요약 1줄: [교차검증] native:_ contract:_ review:_ secrets:_ → 통과/반려
- 체크리스트 9항목 판정표 (항목 | OK/NG | 근거 file:line)
- 발견된 문제 목록 (심각도 + 재현/근거 + 제안)
- 자동 검증 실제 출력(요약)
```

---
_— 교차검증 가이드 끝 —_
