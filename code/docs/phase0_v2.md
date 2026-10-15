# SIA MVP — Phase 0: 환경 세팅 (v2)

> 목표: 팀원 전원이 동일한 환경에서 코드 실행 가능한 상태  
> Phase 0 완료 전 Phase 1 진입 금지  
> v1 대비 변경: 디렉토리 생성을 0-3으로 앞당김, config.py에 검증 추가, .gitignore 보완

---

## Step 0-1: 프로젝트 초기화 + Python 환경

**STATUS:** `TODO`

### 작업

**1. Python 가상환경 생성**

```bash
cd cupid_project

# 가상환경 생성
python -m venv .venv

# 활성화 (Windows)
.venv\Scripts\activate
```

**2. requirements.txt 작성**

```text
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
ultralytics>=8.1.0
opencv-python>=4.8.0
python-dotenv>=1.0.0
openai>=1.12.0
pygame>=2.5.0
numpy>=1.24.0
```

**3. 설치**

```bash
pip install -r requirements.txt
```

### 완료 기준

- [ ] `pip install -r requirements.txt` 에러 없음
- [ ] `python -c "import fastapi, cv2, ultralytics, openai, pygame"` 정상 실행

---

## Step 0-2: 환경변수 + Git 설정

**STATUS:** `TODO`

### 작업

**1. .env.example 생성**

```ini
OPENAI_API_KEY=sk-xxx
GROQ_API_KEY=gsk_xxx
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
YOLO_MODEL=yolov8n.pt
YOLO_CONF_THRESHOLD=0.4
DANGER_DISTANCE_CM=30
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

**2. .gitignore 생성**

```gitignore
# 환경변수
.env

# Python
.venv/
__pycache__/
*.pyc

# YOLO 모델 파일
*.pt

# 생성된 오디오 (API로 생성하므로 git 제외)
audio/fallback/*.mp3
audio/fallback/*.wav

# TTS 캐시
tts_cache/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

**3. server/config.py (검증 포함)**

```python
"""서버 설정. 필수 환경변수 누락 시 즉시 에러 발생 (fail-fast)."""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """환경변수가 없거나 비어있으면 RuntimeError."""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"[config] 필수 환경변수 '{key}' 미설정. .env 파일 확인 필요."
        )
    return value


# 필수 (없으면 서버 시작 불가)
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")

# 선택 (기본값 있음)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF_THRESHOLD: float = float(os.getenv("YOLO_CONF_THRESHOLD", "0.4"))
DANGER_DISTANCE_CM: float = float(os.getenv("DANGER_DISTANCE_CM", "30"))
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
```

### 완료 기준

- [ ] `.env` 없이 `from server.config import *` 실행 시 RuntimeError 발생
- [ ] `.env`에 실제 키 입력 후 import 성공
- [ ] `.gitignore`에 `*.pt`, `audio/fallback/*.mp3`, `tts_cache/` 포함 확인

---

## Step 0-3: 디렉토리 구조 + Placeholder 생성

**STATUS:** `TODO`

> v1의 Step 0-7이었던 작업을 0-3으로 앞당김.  
> 이유: 폴더 구조 없으면 이후 Step의 import가 안 됨.

### 작업

**1. 폴더 생성**

```bash
mkdir ai_core server dashboard firmware audio audio\fallback docs utils scripts
```

**2. __init__.py 생성**

```bash
type nul > ai_core\__init__.py
type nul > server\__init__.py
type nul > utils\__init__.py
```

**3. Placeholder 파일 생성**

`ai_core/vision.py`
```python
"""YOLO 객체 인식 + bbox 후처리 모듈."""

def load_model():
    raise NotImplementedError("Step 1-1에서 구현")

def detect(frame):
    raise NotImplementedError("Step 1-1에서 구현")

def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    raise NotImplementedError("Step 1-2에서 구현")
```

`ai_core/danger.py`
```python
"""위험 판단 로직. Stage 3 전용."""

def judge(enriched_data, current_stage: int):
    raise NotImplementedError("Step 1-3에서 구현")
```

`ai_core/audio_manager.py`
```python
"""오디오 매니저. 별도 스레드에서 재생, Lock 보호."""

class AudioManager:
    def __init__(self):
        raise NotImplementedError("Step 1-4에서 구현")

    def play(self, filepath: str, interrupt: bool = False):
        raise NotImplementedError("Step 1-4에서 구현")
```

`ai_core/llm_client.py`
```python
"""LLM API 호출 (비블로킹, asyncio.to_thread 사용)."""

def init():
    raise NotImplementedError("Step 1-6에서 구현")

async def call_async(system_prompt: str, user_msg: str):
    raise NotImplementedError("Step 1-6에서 구현")
```

`ai_core/tts.py`
```python
"""TTS 음성 출력 + 캐시 관리."""

class TTSCache:
    def __init__(self):
        raise NotImplementedError("Step 1-6에서 구현")
```

`ai_core/narration.py`
```python
"""환경 묘사 LLM 호출."""

async def narrate_async(enriched_data):
    raise NotImplementedError("Step 1-6에서 구현")
```

`server/main_server.py`
```python
"""FastAPI + WebSocket 엔트리."""
# Step 1-8에서 구현
```

`server/websocket_handler.py`
```python
"""WebSocket 연결 핸들러."""

async def handle_connection(websocket):
    raise NotImplementedError("Step 1-8에서 구현")
```

`utils/latency_logger.py`
```python
"""지연 측정 유틸."""

import time

_timestamps = {}

def log(label):
    ts = time.time() * 1000
    _timestamps[label] = ts
    print(f"[LATENCY] {label}: {ts:.0f}ms")

def elapsed(start_label, end_label):
    s = _timestamps.get(start_label)
    e = _timestamps.get(end_label)
    if s and e:
        diff = e - s
        print(f"[LATENCY] {start_label} → {end_label}: {diff:.0f}ms")
        return diff
    return None
```

`main.py` (루트)
```python
"""SIA MVP 메인 실행 파일."""
# Step 1-8에서 구현
```

**4. import 확인 + 초기 커밋**

```bash
python -c "import ai_core.vision; import ai_core.danger; import server.config; import utils.latency_logger; print('All OK')"

git add .
git commit -m "chore: Phase 0 초기 구조 세팅"
git push origin main
```

### 완료 기준

- [ ] 8개 디렉토리 존재 (ai_core, server, dashboard, firmware, audio/fallback, docs, utils, scripts)
- [ ] 모든 Python 모듈 import 에러 없음
- [ ] GitHub push 성공

---

## Step 0-4: YOLO 모델 다운로드 확인

**STATUS:** `TODO`

### 작업

`scripts/check_yolo.py`
```python
"""YOLO 모델 로드 + 더미 추론 테스트."""

from ultralytics import YOLO
import numpy as np

model = YOLO("yolov8n.pt")  # 없으면 자동 다운로드
dummy = np.zeros((480, 640, 3), dtype="uint8")
results = model(dummy, verbose=False)
print(f"[OK] YOLO 로드 성공. 감지 객체 수: {len(results[0].boxes)}")
```

```bash
python scripts/check_yolo.py
```

### 완료 기준

- [ ] 스크립트 에러 없이 실행
- [ ] `yolov8n.pt` 파일 존재 (git status에 안 뜸)

---

## Step 0-5: 입출력 디바이스 확인

**STATUS:** `TODO`

### 작업

`scripts/check_devices.py`
```python
"""웹캠 + 오디오 출력 확인."""

import cv2
import pygame

# 웹캠
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
assert ret, "웹캠 열기 실패"
print(f"[OK] 웹캠: {frame.shape[1]}x{frame.shape[0]}")
cap.release()

# 오디오
pygame.mixer.init()
print(f"[OK] 오디오: {pygame.mixer.get_init()}")
pygame.mixer.quit()
```

```bash
python scripts/check_devices.py
```

### 완료 기준

- [ ] 웹캠 프레임 읽기 성공
- [ ] pygame mixer 초기화 성공

---

## Step 0-6: 인터페이스 계약 합의

**STATUS:** `TODO`

### 작업

`docs/interface_contract.md` 작성 — 3종 JSON 스키마 확정.

**1) YOLO 후처리 → LLM 입력**

```json
{
  "objects": [
    {
      "label": "string (COCO 80종)",
      "direction": "left | center | right",
      "distance_est": "near | mid | far",
      "bbox_ratio": "float (0~1)",
      "confidence": "float (0~1)"
    }
  ],
  "ultrasonic_cm": "float | null",
  "ultrasonic_target": "string | null"
}
```

**2) 서버 → 대시보드 (WebSocket push)**

```json
{
  "type": "danger | narration | fallback | stt_response",
  "objects": [{"label": "str", "direction": "str", "distance_est": "str"}],
  "message": "string",
  "stage": "int (1|2|3)",
  "audio_file": "string | null",
  "distance_cm": "float | null",
  "timestamp": "int (epoch ms)"
}
```

**3) 대시보드 → 서버**

```json
{"event": "start_learning | stop_learning | fallback | new_session | clear_tts_cache", "stage": "int", "audio_file": "string (fallback 시)"}
{"stt_text": "string"}
```

> v2 추가 이벤트: `new_session` (새 세션 시작 → TTS 캐시 초기화), `clear_tts_cache` (수동 캐시 삭제)

### 완료 기준

- [ ] `docs/interface_contract.md` 작성 완료
- [ ] `new_session`, `clear_tts_cache` 이벤트 포함
- [ ] 팀원 리뷰 후 확정

---

## Phase 0 완료 체크리스트

| # | 항목 | 상태 |
|---|---|---|
| 0-1 | Python 환경 + requirements.txt | ☐ |
| 0-2 | .env + .gitignore + config.py | ☐ |
| 0-3 | 디렉토리 구조 + placeholder + push | ☐ |
| 0-4 | YOLO 모델 확인 | ☐ |
| 0-5 | 웹캠 + 오디오 확인 | ☐ |
| 0-6 | 인터페이스 계약 합의 | ☐ |

**전원 체크 완료 후 Phase 1 진입.**

---

_— Phase 0 v2 문서 끝 —_
