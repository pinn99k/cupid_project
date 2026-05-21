# SIA MVP 프로젝트 요약

> 최종 업데이트: 2026-05-21

---

## 1. 프로젝트 개요

- **프로젝트명**: SIA (시아) - 시각장애 유아 AI 보행 교육 파트너
- **목표**: 갈라쇼 3분 시연 데모
- **핵심 기능**: 웹캠으로 주변 환경 인식 -> AI가 음성으로 안내
- **레포**: https://github.com/pinn99k/cupid_project

---

## 2. 기술 스택

| 분류 | 기술 | 용도 |
|------|------|------|
| 백엔드 | Python 3.12 + FastAPI | 서버 + API |
| 실시간 통신 | WebSocket | 대시보드 <-> 서버 |
| 객체 인식 | YOLOv8 (ultralytics) | 웹캠 장애물 감지 |
| TTS | edge-tts (무료) | 한국어 음성 합성 (ko-KR-SunHiNeural) |
| LLM | OpenAI / Groq | 환경 묘사 + 대화 |
| 오디오 | pygame | 스피커 재생 (별도 스레드) |
| 프론트엔드 | React + Vite | 대시보드 UI |
| STT | Web Speech API | 브라우저 음성 인식 (Chrome) |

---

## 3. 아키텍처 요약

```
[웹캠] -> YOLO detect -> enrich(방향/거리) -> danger judge
                                                |
                          Stage 3: emergency -> AudioManager(별도 스레드) -> 스피커
                          Stage 2: LLM narration(비블로킹) -> edge-tts 캐시 -> 스피커
                          Stage 1: YOLO 비활성, 대화만

[대시보드] <-> WebSocket <-> FastAPI 서버
   | STT (Web Speech API)
   | 세션 관리 (Stage 전환, 캐시 초기화)
   | Fallback 수동 재생
```

**스레딩 모델:**
- Main Thread: asyncio 이벤트 루프 (FastAPI + YOLO + LLM + TTS)
- Audio Thread: pygame mixer 전용 daemon 스레드 (Lock 보호)

---

## 4. Stage별 동작

| Stage | YOLO | LLM | 긴급 경보 | 대화 (STT) | 용도 |
|-------|------|-----|-----------|------------|------|
| **1** | OFF | OFF | OFF | ON | 아이와 대화만 |
| **2** | ON | ON (묘사) | OFF | ON | 주변 환경 학습 |
| **3** | ON | OFF | ON | ON | 실전 보행 (위험 감지) |

---

## 5. 디렉토리 구조

```
cupid_project/
|-- main.py                    # 서버 시작 + 감지 루프 엔트리
|-- requirements.txt           # Python 패키지 목록
|-- .env.example               # 환경변수 템플릿
|
|-- ai_core/                   # [AI학과 담당] AI 파이프라인
|   |-- vision.py              #   YOLO detect + bbox enrich
|   |-- danger.py              #   Stage 3 위험 판단
|   |-- audio_manager.py       #   스레드 분리 오디오 재생
|   |-- llm_client.py          #   OpenAI/Groq LLM 호출 (비블로킹)
|   |-- tts.py                 #   edge-tts 세션 기반 캐시
|   |-- narration.py           #   환경 묘사 LLM 프롬프트
|
|-- server/                    # [풀스택 담당] 서버
|   |-- config.py              #   환경변수 로드 (fail-fast)
|   |-- main_server.py         #   FastAPI + 이벤트 핸들러
|   |-- websocket_handler.py   #   WebSocket 연결 관리
|
|-- dashboard/src/             # [풀스택 담당] React 대시보드
|   |-- App.jsx                #   메인 UI
|   |-- components/            #   SessionControl, FallbackPanel
|   |-- hooks/                 #   useWebSocket, useSpeechRecognition
|
|-- utils/                     # 공용 유틸
|   |-- latency_logger.py      #   지연시간 측정
|
|-- audio/                     # 오디오 관련
|   |-- generate_fallback.py   #   Fallback mp3 생성 스크립트
|   |-- fallback/              #   mp3 파일 저장 (gitignore)
|
|-- tests/                     # 단위 테스트 6개
|-- scripts/                   # 환경 점검 스크립트
|-- docs/                      # 설계 문서
```

---

## 6. 역할 분담

| 영역 | 담당 | 파일 | 비고 |
|------|------|------|------|
| AI 파이프라인 | AI학과 | `ai_core/*` | YOLO, LLM, TTS, danger, audio |
| 서버 + 통합 | 풀스택 | `server/*`, `main.py`, `utils/*` | FastAPI, WebSocket, 상태 관리 |
| 대시보드 | 풀스택 | `dashboard/*` | React UI, STT, 세션 관리 |
| 설정/환경 | 공동 | `requirements.txt`, `.env`, `config.py` | |
| 문서 | 공동 | `docs/*` | |

> git 충돌 방지: 각자 담당 영역만 수정

---

## 7. 현재 진행 상태

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 0 | 완료 | 환경 세팅, 디렉토리, placeholder, config |
| Phase 1 | 완료 | 전체 파이프라인 구현 + 테스트 6개 PASS |
| Phase 2 | 진행 중 | 서버 안정화, 대시보드, 통합 테스트 |
| Phase 3 | 미착수 | 갈라쇼 시연 준비 |

---

## 8. 실행 방법

### 환경 세팅 (최초 1회)
```bash
git clone https://github.com/pinn99k/cupid_project.git
cd cupid_project
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # API 키 입력
```

### 서버 실행
```bash
python main.py
# -> http://0.0.0.0:8000 (Health: GET /health)
```

### 대시보드 실행
```bash
cd dashboard
npm create vite@latest . -- --template react   # 최초 1회
npm install                                     # 최초 1회
npm run dev
# -> http://localhost:5173
```

### 테스트 실행
```bash
python tests/test_step1_1_vision_detect.py --dummy
python tests/test_step1_2_vision_enrich.py
python tests/test_step1_3_danger.py
python tests/test_step1_4_audio_manager.py
python tests/test_step1_6_llm_tts.py
python tests/test_step1_8_server.py
```

---

## 9. 주요 설계 결정

| 결정 | 이유 |
|------|------|
| **edge-tts** (OpenAI TTS 대신) | 무료, API 키 불필요, 한국어 품질 좋음 |
| **Audio Thread 분리** | pygame + asyncio 충돌 방지, Lock으로 동시 재생 차단 |
| **세션 기반 TTS 캐시** | 같은 문장 재요청 시 API 호출 없이 즉시 재생, 시연 끝나면 삭제 |
| **LLM 비블로킹** | asyncio.to_thread()로 감싸서 YOLO 루프 차단 방지 |
| **Stage 분리** | Stage별 기능 ON/OFF로 시연 시나리오 유연하게 대응 |
| **Fallback mp3** | LLM/TTS 실패 시 미리 만든 mp3로 즉시 대체 |
| **config fail-fast** | 서버 시작 시 환경변수 누락 즉시 에러 (런타임 디버깅 방지) |

---

## 10. 참고 문서

| 문서 | 내용 |
|------|------|
| `docs/architecture_v2.md` | v2 아키텍처 상세 |
| `docs/phase0_v2.md` | Phase 0 작업 내용 |
| `docs/phase1_v2.md` | Phase 1 작업 + 완료 체크리스트 |
| `docs/review_v1_to_v2.md` | v1 -> v2 변경 이유 + 항목별 점수 |
| `docs/interface_contract.md` | JSON 스키마 3종 |
| `docs/api_specification.md` | API 규격서 (REST + WebSocket) |
| `docs/dashboard_guide.md` | 대시보드 개발 가이드 |
