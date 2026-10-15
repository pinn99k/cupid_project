# SIA 소스 코드

[← 프로젝트 소개로](../README.md)

모든 명령은 이 `code/` 폴더에서 실행합니다.

## 준비물
- Python 3.12, Node.js 18+
- LLM API 키 1개 이상 (Groq / Gemini / OpenAI 중 하나)
- 카메라: 노트북 웹캠, ESP32-CAM, 또는 가짜 디바이스(아래 참고)

## 설치

```bash
python -m venv venv
venv/Scripts/activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에서 최소한 아래를 채웁니다.

| 항목 | 설명 |
|---|---|
| `LLM_PROVIDER` | `groq` / `gemini` / `openai` |
| `GROQ_API_KEY` · `GEMINI_API_KEY` · `OPENAI_API_KEY` | 고른 공급자의 키 |

YOLO 모델(`yolov8n.pt`)은 처음 실행할 때 자동으로 내려받습니다.

## 실행

터미널 두 개가 필요합니다.

```bash
python main.py                   # 서버 · http://localhost:8000
```

```bash
cd dashboard
npm install                      # 처음 1회
npm run dev                      # 대시보드 · http://localhost:5173
```

대시보드에서 학습 단계를 고르고 시작한 뒤 "시아야"라고 부르면 대화가 시작됩니다.

| 단계 | 동작 |
|---|---|
| 1 · 수용 | 대화만 합니다 (객체 탐지 꺼짐) |
| 2 · 방향정위 | 객체 탐지 + 질문하면 장면 설명 |
| 3 · 기술 교육 | 탐지 + 가까운 장애물 위험 경고 |

## 카메라와 센서 설정

| 상황 | `.env` |
|---|---|
| 노트북 웹캠 (기본) | `CAM_SOURCE` 비우기. 다른 웹캠이면 `WEBCAM_INDEX=1` |
| ESP32-CAM | `CAM_SOURCE=http://<디바이스 IP>:81/stream`<br>`ULTRASONIC_URL=http://<디바이스 IP>:80/distance` |
| 가짜 디바이스 | 아래 참고 |

### 하드웨어 없이 실행 (가짜 ESP32)

```bash
python tools/mock_device.py                     # 합성 영상
python tools/mock_device.py --video clip.mp4    # 영상 파일을 카메라처럼 송출
```

```
CAM_SOURCE=http://127.0.0.1:9000/stream
ULTRASONIC_URL=http://127.0.0.1:9000/distance
```

## 자주 쓰는 설정

| 항목 | 기본 | 설명 |
|---|---|---|
| `STT_ENGINE` | `whisper` | `whisper`(로컬 faster-whisper) 또는 `google` |
| `TTS_PROVIDER` | `edge` | Edge-TTS (무료) |
| `DEMO_MODE` | `false` | `true`면 1단계에서 LLM 대신 미리 만든 답변 사용 |
| `DANGER_DISTANCE_CM` | `30` | 위험 경고 거리 |

전체 항목은 `.env.example`과 `server/config.py`를 참고하세요.

## 폴더

| 폴더 | 내용 |
|---|---|
| `ai_core/` | YOLO 탐지, 위험 판단, LLM, TTS, 오디오 재생 |
| `server/` | FastAPI·WebSocket 서버, 마이크·STT·호출어·음성 파이프라인 |
| `dashboard/` | React 모니터링 대시보드 |
| `firmware/` | ESP32-CAM + 초음파 센서 펌웨어 (Arduino) |
| `tools/` | 가짜 디바이스, 데모 시뮬레이터 |
| `scripts/` | 음성 파일 생성, 장치 점검 |
| `tests/` | pytest 테스트 |
| `docs/` | 개발 문서, ADR, API 명세 |

## 테스트

```bash
python -m pytest
```

> 일부 테스트는 실제 카메라를 기다리며 멈추거나 현재 동작과 맞지 않아 실패합니다. 정리 예정입니다.
