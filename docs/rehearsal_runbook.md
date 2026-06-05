# 측정 리허설 런북 (Phase 0 → 병목 판단)

> 목적: 실제 2단계 데모 흐름을 3분 돌려 **`logs/latency_log.json`** 을 만든다.
> 그 숫자로 다음 최적화(P1 YOLO / P2 음성)를 **감이 아니라 데이터로** 정한다.
> 핵심: 계측은 코드에 이미 들어가 있다. 이 문서는 **돌리고 → 파일 받고 → 분석 의뢰**하는 절차다.

---

## 0. 한 번만 — 왜 이렇게 돌리나
- 실행 진입점은 **`python main.py`** (uvicorn 직접 실행 아님 — startup/shutdown 훅이 계측 설정·저장을 함).
- `latency_log.json` 은 **정상 종료(Ctrl+C) 시** 저장된다. 강제 종료(창 닫기)면 안 남는다.
- 집계는 `SIA_DEBUG` 와 무관하게 항상 동작. `SIA_DEBUG=1` 은 **콘솔에 실시간 수치**를 보여줄 뿐.

## 1. 사전 준비 (`.env`)
```
# 측정 리허설용
SIA_DEBUG=1                 # 콘솔 실시간 [LATENCY]/[TIMING] 보기 (선택)
CAM_SOURCE=http://<device-ip>:81/stream   # 실디바이스. 노트북캠이면 0
CAMERA_ROTATION=0          # ESP32 부착 방향에 맞게 0/90/180/270
ULTRASONIC_URL=            # 비움 — 위험단계 시연 안 하므로 초음파 OFF
```
- 마이크 연결 확인("시아야" 질문 인식용).
- 대시보드 띄울 준비(`npm run dev`, Chrome).

## 2. 실행
```powershell
# 1) 서버 (프로젝트 루트)
.\venv\Scripts\python.exe main.py

# 2) 대시보드 (별도 터미널)
cd dashboard ; npm run dev      # Chrome 으로 http://localhost:5173
```
콘솔에 `웹캠 연결 성공`, `초기화 완료` 뜨면 준비 끝.

## 3. 리허설 시나리오 (약 3분 — 실제 데모와 동일하게)
대표 동작을 충분히 섞어야 측정 샘플이 쌓인다.
1. **시작하기** 클릭 → 새 세션(stage=1)
2. **수용단계(1)**: 캠만 30초. (YOLO·음성 없음 — detect 샘플 0이 정상)
3. **방향단계(2)로 전환** → YOLO 박스 뜨는지 확인
4. **"시아야 …" 질문 5~8회** (샘플 확보 핵심):
   - 비전 질문: "시아야 앞에 뭐 있어?", "시아야 왼쪽에 뭐 보여?"
   - 일반 대화: "시아야 안녕", "시아야 잘 지냈어?"
   - 같은 질문 반복도 1~2회(→ TTS 캐시 HIT 측정)
5. 2~3분 채우면 종료.

## 4. 종료 & 수집 (중요)
- 서버 터미널에서 **`Ctrl+C` 한 번** → `[SIA] 서버 종료 완료` 까지 기다림.
- 산출물: **`logs/latency_log.json`** 생성 확인.

## 5. 보고
- `logs/latency_log.json` 내용을 그대로 공유. (키별 count/avg/min/max)
- 읽을 키:
  | 키 | 의미 | 무엇을 가리킴 |
  |----|------|---------------|
  | `detect_start->detect_end` | YOLO 추론시간(ms) | **P1** 후보 |
  | `stt_ms` | 음성인식 | P2 |
  | `llm_ms` | LLM 응답 | **P2** 핵심 |
  | `tts_gen_ms` / `tts_cache_ms` | TTS 생성 / 캐시HIT | **P3**(캐시 적중률) |
  | `text_delay_ms` | 발화→텍스트 표시(STT+LLM) | 체감 끊김 |
  | `turn_total_ms` | 한 턴 전체 | 체감 끊김 |

---

## 6. AI 분석 프롬프트 (복붙용)
> 리허설 후 아래 블록 + `logs/latency_log.json` 내용을 붙여 AI에게 분석 의뢰.

```
역할: SIA 백엔드 성능 분석가. 아래 latency_log.json 을 보고 데모 병목을 짚어라.

데이터(키별 count/avg/min/max, 단위 ms):
<여기에 logs/latency_log.json 내용 붙여넣기>

판단 기준:
- detect_start->detect_end 가 크면 P1(YOLO): imgsz 축소/검출 주기(N프레임마다)로 개선.
- llm_ms / text_delay_ms / turn_total_ms 가 크면 P2(음성 끊김): 체감 직결.
- tts_gen_ms 가 tts_cache_ms 대비 자주 크면 P3: 자주 쓰는 문구 프리웜.

출력:
1. 병목 순위 (키 + 수치 근거)
2. 가장 먼저 칠 것 1개 (P1/P2/P3 중) + 이유
3. 그 최적화의 데모-안전 설계 (킬스위치 env + 폴백, 핫패스 재작성 회피)
4. 기대 이득 / 위험 / 측정 재확인 방법
코드는 아직 수정하지 말 것. 제안만.
```

---
## 붙일 때 체크
- [ ] `python main.py` 로 띄웠나(uvicorn 직접 아님)
- [ ] 방향단계에서 "시아야" 5회+ 했나(샘플 확보)
- [ ] **Ctrl+C 로 정상 종료**해 `logs/latency_log.json` 생겼나
