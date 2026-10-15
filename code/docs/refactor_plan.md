# SIA 리팩토링 & 디바이스 연동 계획

> 목적: "시아야" 호출 시에만 영상 분석(LLM/TTS)하는 온디맨드 구조로 전환 + ESP32-CAM/초음파 디바이스 연동.
> 원칙: 코드베이스 현행 계약을 깨지 않고, 안전(fail-safe)과 테스트 가능성을 우선한다.

---

## 0. 설계 철학 (3원칙)

1. **디바이스는 멍청하게, 판단은 서버에서.** 펌웨어는 영상·거리 센싱/송신만. 위험·정보 판단은 전부 서버.
2. **침묵 ≠ 안전.** 센서가 죽거나 데이터가 오래되면 "안전, 가도 돼"라고 절대 말하지 않는다. 모르면 "잠깐 멈춰".
3. **비싼 건 온디맨드, 싼 건 주기, 즉답은 사전녹음.** LLM/TTS=질문 시에만, YOLO=주기(대시보드용), 위험경고=사전녹음 .wav 자율.

---

## 1. 소크라테스식 사전 결정 (이거 안 지키면 깨짐)

| ID | 쟁점 | 결정 | 근거 |
|----|------|------|------|
| **D1** | 체험 단계 stage 번호 | **체험 = Stage 3** (착용 = Stage 1) | `danger.judge()`는 `current_stage != 3 → None`. `test_step1_3_danger`도 "Stage 2 → None" 단언. 체험을 2로 두면 위험 경고 안 울림 |
| **D2** | `question_count` 추가 | `AppState.question_count` + `to_dict`/`get_state` 반영 시 **테스트 동시 수정** | `test_main_server.py::test_to_dict`가 정확히 3키 단언 |
| **D3** | 웨이크워드 도입 | `test_integration::test_broadcast_order_in_full_turn` STT phrase를 `"시아야 ..."`로 갱신 | 현재 mock은 "안녕하세요 시아"(시아야 아님) → 게이팅 시 None 처리되어 순서 단언 실패 |
| **D4** | 카메라 소스 | `WEBCAM_INDEX`(int) → `CAM_SOURCE`(int\|url) 파싱 | ESP32-CAM은 `http://...` URL. `int()` 크래시 방지 |
| **D5** | 질문 시 장면 출처 | **`_ai_loop`이 만든 최신 enriched를 공유 슬롯(`latest_scene`)에 저장 → scene_provider는 읽기만** (YOLO 재실행 X) | 음성 경로에서 YOLO를 또 돌리면 전역 `model` 동시접근 race + CPU 낭비. 캐시는 0.1~0.25s라 VQA엔 충분히 신선 |
| **D6** | 초음파 전송 | **디바이스=HTTP 서버(`/distance` 노출), 파이썬=폴러** | 펌웨어를 순수 서버로 유지(인바운드 엔드포인트 불필요), 펌웨어 단순화 |
| **D7** | 거리 보정 위치 | **서버에서 보정**(칩은 날것 cm 송신) | 재플래싱 없이 현장 즉석 튜닝 가능 |
| **D8** | 응답 지연 UX | 호출어 감지 즉시 **"잠깐만"류 사전녹음 재생**(LLM 대기 중) | STT+LLM+TTS 합 4~8s. 무응답 침묵은 고장처럼 보임 |
| **D9** | 보정 cm 적용 범위 | **정면(center) 객체 한정** — 위험판단(emergency 임계) + 묘사 텍스트에만 반영 | 초음파는 단일 정면 빔이라 좌우 거리 못 잼. 좌우는 YOLO가 담당 |

---

## 2. 시스템 구성

```
┌──────────────┐   /stream (MJPEG)   ┌──────────────┐   WebSocket   ┌──────────────┐
│  ESP32-CAM   │ ──────────────────▶ │    서버       │ ◀───────────▶ │   대시보드     │
│  + 초음파(HC- │   /distance (JSON)  │ (FastAPI+WS)  │   (이벤트/통지) │  (운영자 모니터) │
│   SR04P)     │ ◀── 폴링 ────────── │               │               └──────────────┘
└──────────────┘                     └──────────────┘
   (날것 cm 송신)                    (보정·융합·판단)      이어폰 ◀── 오디오 재생
```

- 디바이스: 영상 + 정면 거리(cm, 날것) 공급. 판단 없음.
- 서버: 보정 → YOLO 융합 → 위험판단 / "시아야" 질의응답.
- 대시보드: 운영자 모니터(독립). 꺼져도 서버 정상 동작.

---

## 3. 데이터 흐름 (3경로)

### 경로 A — 사용자 질의응답 (온디맨드, LLM/TTS)
```
마이크 → STT → "시아야" 포함? ─ 아니오 ─▶ [무시] (브로드캐스트 없음)
                  │ 예
                  ▼ 호출어 제거 → 질문 추출
        "잠깐만" 사전녹음 즉시 재생(처리 중 신호, LLM 대기)   # D8
        → 공유 슬롯 latest_scene 읽기(YOLO 재실행 X)          # D5
        → [신선도 검사] 장면/거리 오래됨? ─ 예 ─▶ "잠깐 멈춰, 확인 중" (LLM 호출 안 함)  # 안전게이팅
                  │ 아니오
                  ▼ scene_to_korean → LLM(VQA_PROMPT+장면+히스토리+질문) → TTS 재생
        → 대시보드: user_stt → stt_response, question_count+1
```

### 경로 B — 자율 위험 경고 (LLM 미사용, 사전녹음)
```
보정 초음파 < 임계  또는  YOLO 근접 위험라벨
        → judge() → cancel_narration → 사전녹음 .wav 즉시 재생(interrupt, PRIORITY_DANGER)
        → 대시보드: danger 통지 + 오버레이
```

### 경로 C — 실시간 인지 표시 (대시보드 전용)
```
프레임 → YOLO(주기) → enrich → 0.25s마다 detections_update broadcast (LLM/TTS 없음)
```

---

## 4. 파일별 수정 계획

### 그룹 A — 소프트웨어 코어 (헤드리스 자동 테스트 가능)
| # | 파일 | 변경 | 주의 | 테스트 |
|---|------|------|------|--------|
| A0 | `audio/generate_fallback.py` 실행 | `.wav` 21종 생성 (선행 블로커) | GEMINI_API_KEY 필요 | 수동 |
| A1 | `server/wake_word.py` *(신규)* | `parse_wake_word(text)->str\|None` (유사매칭, 호출어 제거) | "시아야"만 입력 시 빈질문 처리 | 입출력 테이블 ✅ |
| A2 | `server/voice_pipeline.py` | STT 후 게이팅(None이면 즉시 return). 질문 시 `scene_provider()`(공유 슬롯 read) → 신선도 검사 → VQA 컨텍스트 | scene None/stale 가드, "잠깐만" 필러 | mock STT/scene 호출검증 ✅ |
| A3 | `ai_core/scene_text.py` *(신규)* | `narration.py`의 한글변환 추출 → `scene_to_korean(enriched)->str` | 기존 import 보존 | 순수함수 ✅ |
| A4 | `ai_core/llm_client.py` | `VQA_PROMPT` 추가(장면+질문→2문장) | 시그니처 불변 | 스모크 |
| A5 | `main.py::_ai_loop` | 자동 narration 트리거 제거. **최신 enriched를 `latest_scene` 공유 슬롯에 저장**(scene_provider가 읽음). `detections_update`+`danger` 유지 | narration 함수 보존(dead), YOLO 단일 실행 유지 | judge/detections 분리 ✅ |
| A6 | `server/main_server.py` | `AppState.question_count` + reflect, 답변 성공 시 +1, reset 시 0 | **D2 테스트 동시수정** | 카운터 단위 ✅ |

### 그룹 B — 디바이스 연동 (부분 자동 + 수동)
| # | 파일 | 변경 | 주의 | 테스트 |
|---|------|------|------|--------|
| B1 | `server/config.py` | `CAM_SOURCE`(int\|url), `ULTRASONIC_URL`, `ULTRASONIC_POLL_SEC`, `ULTRASONIC_OFFSET_CM` | **D4** int/url 분기 | 파싱 단위 ✅ |
| B2 | `server/main_server.py` | `set_ultrasonic/get_ultrasonic` thread-safe 슬롯(+timestamp) | 락 일관성, 신선도 | set→get ✅ |
| B3 | `main.py` | `_open_camera` URL 허용 + `BUFFERSIZE=1`/grab(stale 드롭). 초음파 폴러 태스크 → 보정 적용 → `set_ultrasonic`. `enrich(...,get_ultrasonic())` 배선 | MJPEG 지연/재연결 | enrich+judge emergency ✅(HW 불필요) |
| B4 | `ai_core/calibration.py` *(신규)* | `correct_cm(raw, offset)->float`, 범위검증[2,400], 중앙값 필터 | 과필터 지연 주의 | 순수함수 ✅ |

### 그룹 C — 대시보드 (시각 검증)
| # | 파일 | 변경 |
|---|------|------|
| C1 | `ChatPanel.jsx` | STT/TTS 버블만 (narration/danger 제거) |
| C2 | `DashboardPage.jsx` | 질문 카운트 위젯, danger 배지/오버레이 유지, **디바이스 생존(heartbeat) 표시** |
| C3 | `useWebSocket.js` | `question_count`/신선도 수신 반영 |

---

## 5. 안전 설계 (fail-safe 게이팅)

**게이팅은 출력이 아니라 입력단에서 한다.** LLM 출력은 자유 텍스트라 "긍정인지"를 서버가 판별할 수 없다. 따라서 **센서가 무효면 LLM을 아예 호출하지 않고** 보류 음성으로 단락(short-circuit)시킨다.

1. **신선도**: `/distance`의 `ts`가 최근 1초 이내 + 프레임이 최근 1초 이내(같은 프레임 고정 = 정지로 간주)
2. **범위검증**: 거리 `[2cm, 400cm]` 밖이면 버림
3. **필터**: 중앙값 3회(스파이크 오경보/누락 방지, ~300ms)
4. **무효 시(입력 게이팅)**: **LLM 호출 안 함** → "잠깐 멈춰, 확인 중" 사전녹음 재생 + 대시보드 `error`
5. **운영자 인-더-루프**: 대시보드 heartbeat 표시 + Fallback 패널 수동 음원(최후 보루)
6. **모의 모드 폴백**: 디바이스 사망 시 `CAM_SOURCE`=노트북 웹캠 + mock 초음파로 즉시 전환

오디오 우선순위: 위험(0) > 대화(10) > 묘사(20) > 폴백(30).

---

## 6. ESP32-CAM + 초음파 펌웨어 설계

### 굽는 규격 (아두이노 IDE)
| 설정 | 값 |
|------|-----|
| Board | AI Thinker ESP32-CAM |
| Partition Scheme | Huge APP (3MB) |
| PSRAM | Enabled |
| 카메라 모델 | `CAMERA_MODEL_AI_THINKER` |

### 하드웨어
| 항목 | 선택 | 이유 |
|------|------|------|
| 초음파 | **HC-SR04P (3.3V)** | ESP32 3.3V 직결, 레벨시프터 불필요 |
| TRIG | GPIO13 | 카메라/SD 미사용 핀 |
| ECHO | GPIO14 | **strapping 핀(0·2·12·15) 회피** — 15도 strapping이라 14 권장 |

> ⚠️ 핀은 보드 개체별 가용 여부를 **단계 2(초음파 단독) 테스트로 반드시 검증**. SD카드 사용 시 12~15가 점유되니 미사용 전제. ECHO는 입력이므로 부팅 시 floating 주의.
| 전원 | 5V/2A + 470µF 디커플링 | 브라운아웃 방지 |
| 플래싱 | USB-TTL, IO0→GND 후 부팅 | ESP32-CAM은 USB 직결 없음 |

### 펌웨어 역할 (멍청하게)
```
setup():
  WiFi 연결(고정 IP 권장) / 카메라 init / 워치독 활성
  라우트: GET /stream  → MJPEG
          GET /distance → {"cm": <날것값>, "ts": <ms>}   # 보정 안 함!
loop/task:
  100~200ms 주기로 TRIG 펄스 → ECHO pulseIn(타임아웃 설정) → cm
  최신값을 전역에 캐시 (MJPEG 핫패스와 분리)
  측정 실패 → -1
```

### 펌웨어 함정 차단
- 브라운아웃: 안정 전원 + 디커플링 캡 (+ 디텍터 비활성은 임시방편)
- MJPEG 중 /distance 블로킹 금지: 측정은 별도 주기, 핸들러는 캐시값만
- pulseIn 무한대기 금지: 최대거리 타임아웃(4m≈23ms)
- WiFi 끊김: 자동 재연결, 워치독으로 행 시 리부트
- 고정 IP/DHCP 예약: URL 안 바뀌게

### 서버 ↔ 디바이스 계약
| 방향 | 채널 | 형식 |
|------|------|------|
| 영상 | `http://<IP>/stream` | MJPEG, `cv2.VideoCapture(url)` |
| 거리 | `http://<IP>/distance` | `{"cm": 28, "ts": 169...}` (날것) |
| 폴링 | `ULTRASONIC_POLL_SEC`(기본 0.3s) | 실패 시 직전값, N회 실패 시 None |

---

## 7. 테스트 전략 (위치 분리가 핵심)

> 규칙: **칩/WiFi 없이도 통과 가능한 것만 pytest. 칩이 필요한 건 수동 스크립트.**
> pytest는 "녹색이면 언제든 신뢰"가 약속 → 하드웨어 의존 테스트가 섞이면 신뢰 붕괴.

### 폴더 구조
```
firmware/
  sia_camera/sia_camera.ino     ← 칩용 코드 (C++, pytest 대상 아님)
  README.md                     ← 배선도 + 굽는 설정 + 실칩 체크리스트
tools/
  mock_device.py                ← 가짜 디바이스 (노트북에서 ESP32 흉내)
  hil_check.py                  ← 실칩 연결 수동 점검 (사람이 눈으로)
tests/
  test_device_ingest.py         ← 자동(pytest), 가짜 디바이스로
  test_wake_word.py             ← 자동
  test_scene_text.py            ← 자동
  test_calibration.py           ← 자동
```

### 가짜 디바이스(mock_device.py)
- `/stream` → 동영상 파일 또는 노트북 웹캠을 MJPEG인 척 송출
- `/distance` → 키보드/스크립트로 cm 주입
- 서버는 진짜/가짜 구분 못 함 → **디바이스 도착 전·고장 시에도 전체 흐름 테스트/폴백 가능**

### 테스트 매트릭스
| 대상 | 위치 | 하드웨어 |
|------|------|----------|
| 웨이크워드/장면텍스트/보정 순수로직 | `tests/` pytest | ❌ |
| 서버가 거리 받아 위험판단 | `tests/` + mock_device | ❌ |
| 전체 흐름(질문→분석→음성) | 노트북 + mock_device | ❌ |
| 펌웨어가 영상/거리 송신 | 칩 + 브라우저/시리얼 | ✅ |
| 실물 통합(데이터 실제 수신) | `tools/hil_check.py` 수동 | ✅ |

---

## 8. 개발 순서 & 의존성

의존성 × 난이도를 합쳐 **5단계**로 재정의. 단계 안의 항목은 서로 독립이라 순서 자유.

### Phase 0 — 문서·스캐폴드  〔혼자 / 위험 0〕
- `demo_scenario.md` stage 2→3 정정 ✅(완료)
- `firmware/`, `tools/` 폴더 + README 골격

### Phase 1 — 격리 부품  〔혼자 / 저위험 / 전부 단위테스트 ✅〕
- A1 `wake_word.py` (+test) — 미연결 신규
- A3 `scene_text.py` (+test) — `narration.py` 원본 보존
- B4 `calibration.py` (+test) — 미연결 신규
- B1 `config.py` `CAM_SOURCE`·`ULTRASONIC_*` (+test) — 추가형(기존 `WEBCAM_INDEX` 유지)
- A4 `llm_client.py` `VQA_PROMPT` 상수 — 추가형(시그니처 불변, Phase 3에서 활성)

### Phase 2 — 인프라  〔혼자 / 저위험 / 기존코드 미변경〕
- `tools/mock_device.py` (가짜 디바이스)
- A0 `.wav` 음원 생성 (스크립트 실행)

```
══════ ⬆ 여기까지가 "혼자 가능 한계선" ⬆ ══════
 Phase 0~2 = 모든 부품 + 가짜 디바이스 준비.
 라이브 흐름·테스트 0건 변경. 부품마다 단위테스트로 검증.
```

### Phase 3 — 통합 배선  〔팀과 함께 / 고위험 / 테스트 동시수정〕
- A5 `_ai_loop`: narration 제거 + `latest_scene` 슬롯 (동시성)
- A2 `voice_pipeline`: 게이팅 + scene_provider 연결 (※ A1·A3·A4 선행)
- A6 `question_count` (※ `test_to_dict` 동시수정)
- B2/B3 초음파 슬롯 + 카메라 URL + 폴러 배선 (※ B1·B4 선행)
- 동시수정: `test_broadcast_order`, `test_to_dict`

### Phase 4 — 대시보드  〔팀 / 시각검증〕
- C1~C3 (※ A6 선행)

### Phase 5 — 실디바이스  〔팀 / 하드웨어 수동〕
- firmware FW1 스트림 → FW2 `/distance` → FW3 측정태스크 → `hil_check`

---

## 8.5 "혼자 가능 한계선" 판단

- **혼자 = Phase 0·1·2 전부.** 신규 파일/문서/스크립트 + 추가형 설정뿐이라 **기존 동작·테스트 0건 변경**. 부품마다 단위테스트로 자급자족 검증.
- **팀과 함께 = Phase 3부터.** 부품을 라이브 흐름에 **배선하는 통합 지점**(동시성·외부 I/O·테스트 깨짐). 특히 A2·A5·A6은 **한 PR로 묶어** 테스트와 동시 수정.
- 근거: 위험은 '코드량'이 아니라 **통합 seam**에 있다. Phase 1~2는 leaf 모듈이라 충돌 면적이 0에 가깝다.
- 부수효과: Phase 2의 `mock_device`가 끝나면, **Phase 3 통합조차 디바이스 없이** 노트북에서 테스트 가능 → 팀 작업의 위험도 한 단계 더 낮아짐.

---

## 9. 회귀 테스트 영향 (동시 수정 목록)

1. `test_main_server.py::test_to_dict` — `question_count` 키 추가 (D2)
2. `test_integration.py::test_broadcast_order_in_full_turn` — STT phrase `"시아야 ..."` (D3)
3. `docs/demo_scenario.md` — 체험 stage **2→3** 정정 (D1)
4. narration 자동호출 관련 단언 있으면 제거/수정 (A5)

---

## 10. 결정 사항 (오너 확정)

| ID | 결정 | 적용 위치 |
|----|------|----------|
| A1 | 머무는 장애물: **한 번 경고 후 치워질 때까지 침묵** (20초 반복 아님) | `_ai_loop` 쿨다운 로직 변경 (Phase 3) |
| A2 | 호출어 **"시아야"만** (엄격) | `wake_word.py` ✅ 반영됨 |
| A3 | 호출어 없는 발화 **무시** | `voice_pipeline` 게이팅 (Phase 3) |
| A4 | stage: 착용=1, 체험=3. **VQA(질문-답변)는 체험(3)에서** | 전체 흐름 |
| A5 | 초음파 위험 거리 **30cm** (3m 부스) | `DANGER_DISTANCE_CM` 유지 |
| B1 | TTS: **유료 Gemini 유지 + edge-tts 폴백** | `tts.py` (AI팀) |
| B2 | LLM: **유료 Gemini** (billing 확인됨 ✅) | `.env` |
| B3 | 거리 보정식: **단순 오프셋**(데모) | `calibration.py` ✅ |
| B4 | 초음파 전송: **디바이스 서버 + 파이썬 폴링** | 펌웨어/서버 |
| B5 | VQA 프롬프트: **골격은 오너 작성** | `llm_client.py` |

### 잔여 (나중에)
- C1 음원 생성 / C2 Phase 3 배선 / C3 질문 카운트 용도 — 추후
- A1 "치워질 때까지 침묵"의 정확한 판정(객체 사라짐 감지) 방식 — Phase 3에서 구체화
