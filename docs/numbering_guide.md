# SIA MVP — 넘버링 가이드

> audience: Claude Code (AI) 이 문서는 Phase별 개발 문서의 인덱스이자 컨벤션 정의다.

## 프로젝트 개요

시각장애 아동 보행 훈련 AI 시스템 "시아(SIA)" 갈라쇼 MVP. 목표: 3분 시연 끊기지 않는 것이 전부.

## Phase 구조

|Phase|문서|핵심 목표|
|---|---|---|
|0+1|`SIA_Phase0-1.md`|환경 세팅 + 파이프라인 최소 연결 (소리 나는 루프)|
|2|`SIA_Phase2.md` (미작성)|ESP32-CAM 하드웨어 연결|
|3|`SIA_Phase3.md` (미작성)|3단계 커리큘럼 + 대시보드 완성|
|4|`SIA_Phase4.md` (미작성)|갈라쇼 리허설 + 안정화|

## 역할 분담

|영역|담당|폴더|
|---|---|---|
|AI 코어 (YOLO, LLM, 위험판단, TTS)|경민|`ai_core/`|
|서버 + 대시보드 (FastAPI, WS, React)|민구|`server/`, `dashboard/`|
|펌웨어 (ESP32-CAM, 센서)|은민|`firmware/`|
|메인 실행 + 통합|경민|`main.py`|

Phase 0+1은 한 자리에서 순서대로 같이 진행. Phase 2부터 각자 병렬 작업.

## 디렉토리 구조 (확정)

```
cupid_project/
├── .env                          # API 키 (Git 제외)
├── .env.example                  # API 키 템플릿
├── .gitignore
├── README.md
├── requirements.txt
│
├── main.py                       # 메인 실행 (경민)
│
├── ai_core/                      # AI 코드 (경민)
│   ├── __init__.py
│   ├── prompts.py                # 시스템 프롬프트 3개
│   ├── chat.py                   # 시아 대화 (LLM)
│   ├── vision.py                 # YOLO 객체 인식
│   ├── danger.py                 # 위험 판단 로직
│   ├── narration.py              # 환경 묘사 LLM
│   ├── tts.py                    # TTS 음성 출력
│   ├── audio_player.py           # 로컬 오디오 재생 + Fallback
│   └── llm_client.py             # LLM API 호출 (OpenAI/Groq 전환)
│
├── server/                       # 서버 (민구)
│   ├── __init__.py
│   ├── main_server.py            # FastAPI + WebSocket 엔트리
│   ├── websocket_handler.py      # WebSocket 핸들러
│   └── config.py                 # .env 로드, 상수
│
├── dashboard/                    # React 대시보드 (민구)
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── CameraFeed.jsx
│   │   │   ├── ChatBubble.jsx
│   │   │   ├── FallbackPanel.jsx
│   │   │   └── StageIndicator.jsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.js
│   │   │   └── useSpeechRecognition.js
│   │   └── utils/
│   └── package.json
│
├── firmware/                     # ESP32-CAM (은민)
│   ├── esp32_cam.ino
│   ├── distance_sensor.ino
│   └── button_handler.ino
│
├── audio/                        # 음성 파일
│   ├── fallback/                 # 사전 생성 mp3 20개
│   └── generate_fallback.py      # TTS 일괄 생성 스크립트
│
├── docs/                         # 문서
│   ├── interface_contract.md
│   ├── development_flow.md
│   ├── prompts_guide.md
│   └── fallback_messages.md
│
└── utils/                        # 공통 유틸
    └── latency_logger.py         # 지연 측정
```

## 인터페이스 계약 요약

Phase 문서에서 참조하는 JSON 포맷 핵심 3종:

1. **YOLO 후처리 → LLM 입력**: `{objects[], ultrasonic_cm, ultrasonic_target}`
2. **서버 → 대시보드 (WS push)**: `{type, object, direction, distance_cm, message, stage, audio_file, timestamp}`
3. **대시보드 → 서버 (WS/HTTP)**: `{event, stage}` / `{stt_text}`

상세 스키마는 `docs/interface_contract.md` 또는 Phase0-1 문서의 Step 0-8 참고.

## Claude Code 작업 규칙

- Phase 문서의 Step을 순서대로 구현. 넘기지 않는다.
- 각 Step의 `완료 기준`을 통과해야 다음 Step 진행.
- `STATUS`를 업데이트하며 진행: `TODO → IN_PROGRESS → DONE`
- 파일 생성 시 위 디렉토리 구조를 따른다.
- 테스트는 Step 단위로 독립 실행 가능해야 한다.
- 지연 측정이 명시된 구간은 `utils/latency_logger.py`로 반드시 측정 로그 출력.