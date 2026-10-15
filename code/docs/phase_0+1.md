# SIA MVP — Phase 0+1: 환경 세팅 + 파이프라인 최소 연결

> audience: Claude Code (AI) 선행 문서: `SIA_넘버링_가이드.md` 목표: 노트북 웹캠으로 장애물 감지 → 소리가 나는 루프 완성. ESP32-CAM 없이. 작업 방식: 한 자리에서 같이 모니터링하며 순서대로 진행.

---

## Phase 0 — 환경 세팅

### Step 0-1: 프로젝트 초기화 + Python 환경 [필수]

STATUS: TODO

작업:

- `cupid_project/` 루트 디렉토리 생성
- `넘버링_가이드.md`의 디렉토리 구조대로 폴더 생성
- Python 3.10+ 가상환경 생성
- `requirements.txt` 작성 및 설치

```
# requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
ultralytics>=8.1.0       # YOLOv8
opencv-python>=4.8.0
python-dotenv>=1.0.0
openai>=1.12.0            # LLM + TTS
pygame>=2.5.0             # 로컬 오디오 재생
numpy>=1.24.0
```

완료 기준:

- `pip install -r requirements.txt` 에러 없음
- `python -c "import ultralytics; print(ultralytics.__version__)"` 정상 출력

---

### Step 0-2: 환경변수 + Git 설정 [필수]

STATUS: TODO

작업:

- `.env.example` 생성
- `.gitignore` 생성

```ini
# .env.example
OPENAI_API_KEY=sk-xxx
GROQ_API_KEY=gsk_xxx          # Phase 1-6에서 LLM 응답 3초 초과 시 사용
LLM_PROVIDER=openai            # openai | groq
LLM_MODEL=gpt-4o-mini          # 또는 llama-3.1-8b-instant (Groq)
YOLO_MODEL=yolov8n.pt          # nano 모델 (속도 우선)
YOLO_CONF_THRESHOLD=0.4
DANGER_DISTANCE_CM=30
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

```gitignore
# .gitignore
.env
__pycache__/
*.pyc
venv/
node_modules/
*.pt
audio/fallback/*.wav
audio/fallback/*.mp3
```

```python
# server/config.py
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.4"))
DANGER_DISTANCE_CM = float(os.getenv("DANGER_DISTANCE_CM", "30"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
```

완료 기준:

- `.env` 복사 후 실제 키 입력 가능
- `python -c "from server.config import *; print(LLM_MODEL)"` 정상 출력

---

### Step 0-3: YOLO 모델 다운로드 확인 [필수]

STATUS: TODO

작업:

- YOLOv8n 모델 자동 다운로드 확인 스크립트

```python
# scripts/check_yolo.py
from ultralytics import YOLO
model = YOLO("yolov8n.pt")  # 없으면 자동 다운로드
results = model.predict(source=0, show=False, save=False, verbose=False, stream=True)
frame = next(results)
print(f"[OK] YOLO loaded. Classes: {len(model.names)}")
print(f"[OK] Detected {len(frame.boxes)} objects in webcam frame")
```

완료 기준:

- 스크립트 실행 시 YOLO 모델 로드 + 웹캠 1프레임 감지 성공

---

### Step 0-4: 입출력 디바이스 확인 [필수]

STATUS: TODO

작업:

- 웹캠, 오디오 출력 동작 확인 스크립트

```python
# scripts/check_devices.py
import cv2
import pygame

# 웹캠
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
assert ret, "웹캠 열기 실패"
print(f"[OK] 웹캠: {frame.shape}")
cap.release()

# 오디오 출력
pygame.mixer.init()
print(f"[OK] 오디오 출력 초기화 성공")
pygame.mixer.quit()

print("[INFO] 마이크는 브라우저 Web Speech API로 테스트 (Step 1-7)")
```

완료 기준:

- 웹캠 프레임 읽기 성공
- pygame 오디오 초기화 성공

---

### Step 0-5 ~ 0-6: ESP32-CAM 환경

STATUS: SKIP (Phase 2에서 수행)

---

### Step 0-7: 디렉토리 구조 + placeholder + 초기 push [필수]

STATUS: TODO

작업:

- 확정된 디렉토리 구조대로 빈 파일/폴더 생성
- 각 Python 모듈에 docstring + placeholder 작성
- 초기 커밋 + push

placeholder 예시:

```python
# ai_core/vision.py
"""
YOLO 객체 인식 + bbox 후처리 모듈.
- detect(frame) → raw detections
- enrich(detections, frame_w, frame_h, ultrasonic_cm) → enriched JSON
"""

def detect(frame):
    raise NotImplementedError("Step 1-1에서 구현")

def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    raise NotImplementedError("Step 1-2에서 구현")
```

```python
# ai_core/danger.py
"""위험 판단 로직."""

def judge(enriched_data):
    raise NotImplementedError("Step 1-3에서 구현")
```

```python
# ai_core/audio_player.py
"""로컬 오디오 재생 + Fallback."""

def init():
    raise NotImplementedError("Step 1-4에서 구현")

def play(filename, interrupt=False):
    raise NotImplementedError("Step 1-4에서 구현")
```

```python
# ai_core/llm_client.py
"""LLM API 호출 (OpenAI/Groq 전환)."""

def init():
    raise NotImplementedError("Step 1-6에서 구현")

def narrate(enriched_data):
    raise NotImplementedError("Step 1-6에서 구현")
```

```python
# ai_core/tts.py
"""TTS 음성 출력."""

def speak(text):
    raise NotImplementedError("Step 1-6에서 구현")
```

```python
# server/main_server.py
"""FastAPI + WebSocket 엔트리."""
# Step 1-8에서 구현
```

```python
# utils/latency_logger.py
"""지연 측정 유틸."""

def log(label):
    raise NotImplementedError("Step 1-1에서 구현")
```

완료 기준:

- 모든 모듈 import 에러 없음 (placeholder 상태)
- GitHub push 성공

---

### Step 0-8: 인터페이스 계약 합의 [필수]

STATUS: TODO

작업:

- `docs/interface_contract.md` 작성
- 아래 3종 JSON 스키마 확정

**1) YOLO 후처리 → LLM 입력 (ai_core 내부)**

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
{"event": "start_learning | stop_learning | fallback", "stage": "int", "audio_file": "string (fallback 시)"}
{"stt_text": "string"}
```

완료 기준:

- `docs/interface_contract.md` 작성 완료
- 팀원 리뷰 후 확정 (Claude Code는 문서 생성까지만)

---

## Phase 1 — 파이프라인 최소 연결

> 핵심: 노트북 웹캠 → YOLO → 위험 판단 → 소리. 이 루프가 돌아야 한다. Phase 1 완료 전 Phase 2 진입 금지.

---

### Step 1-1: 웹캠 → YOLO → bbox 원본 출력 [필수]

STATUS: TODO 파일: `ai_core/vision.py` 의존: Step 0-1, 0-3

작업:

1. `YOLO("yolov8n.pt")` 로드
2. 웹캠 프레임 읽기
3. `model.predict(frame)` → detection 결과 파싱
4. 콘솔에 `[label, x, y, w, h, confidence]` 출력

```python
# ai_core/vision.py

from ultralytics import YOLO
from server.config import YOLO_MODEL, YOLO_CONF_THRESHOLD

model = None

def load_model():
    global model
    model = YOLO(YOLO_MODEL)

def detect(frame):
    """
    Args: frame (numpy array, BGR)
    Returns: list of dict {label, x, y, w, h, conf}
    """
    results = model.predict(
        source=frame,
        conf=YOLO_CONF_THRESHOLD,
        verbose=False
    )[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "label": model.names[int(box.cls[0])],
            "x": x1,
            "y": y1,
            "w": x2 - x1,
            "h": y2 - y1,
            "conf": float(box.conf[0])
        })
    return detections
```

테스트:

```bash
python -c "
from ai_core.vision import load_model, detect
import cv2
load_model()
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
dets = detect(frame)
for d in dets:
    print(f'{d[\"label\"]:>12} conf={d[\"conf\"]:.2f}')
cap.release()
"
```

완료 기준:

- 웹캠 프레임에서 객체 감지 결과 콘솔 출력
- COCO 클래스 정상 인식

---

### Step 1-2: YOLO bbox 후처리 → enriched JSON [필수]

STATUS: TODO 파일: `ai_core/vision.py` (enrich 함수 추가) 의존: Step 1-1

작업:

1. bbox x좌표 → 방향 (left/center/right, 33%/66% 기준)
2. bbox 면적비 → 거리 추정 (near/mid/far, 20%/5% 기준)
3. 초음파 매칭 (center 영역 최대 bbox 객체)

```python
# ai_core/vision.py 에 추가

def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    """
    Args:
        detections: detect() 반환값
        frame_w, frame_h: 프레임 크기
        ultrasonic_cm: HC-SR04P 거리값 (Phase 1에서는 None)
    Returns: interface_contract 스키마의 enriched JSON
    """
    enriched = []
    center_objects = []

    for det in detections:
        cx = (det["x"] + det["w"] / 2) / frame_w
        area = (det["w"] * det["h"]) / (frame_w * frame_h)

        direction = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
        distance_est = "near" if area > 0.20 else ("far" if area < 0.05 else "mid")

        if direction == "center":
            center_objects.append((det["label"], area))

        enriched.append({
            "label": det["label"],
            "direction": direction,
            "distance_est": distance_est,
            "bbox_ratio": round(area, 3),
            "confidence": round(det["conf"], 2)
        })

    ultrasonic_target = None
    if center_objects:
        ultrasonic_target = max(center_objects, key=lambda x: x[1])[0]

    return {
        "objects": enriched,
        "ultrasonic_cm": ultrasonic_cm,
        "ultrasonic_target": ultrasonic_target
    }
```

테스트:

```bash
python -c "
from ai_core.vision import load_model, detect, enrich
import cv2, json
load_model()
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
h, w = frame.shape[:2]
result = enrich(detect(frame), w, h)
print(json.dumps(result, indent=2, ensure_ascii=False))
cap.release()
"
```

완료 기준:

- enriched JSON 출력이 interface_contract 스키마와 일치

---

### Step 1-3: 위험 판단 룰 [필수]

STATUS: TODO 파일: `ai_core/danger.py` 의존: Step 1-2

작업:

1. 초음파 < DANGER_DISTANCE_CM → emergency
2. YOLO near + 위험 라벨 → warning
3. 안전 → None

```python
# ai_core/danger.py

from server.config import DANGER_DISTANCE_CM

DANGER_LABELS = {"person", "car", "bicycle", "motorcycle", "bus", "truck", "dog"}

def judge(enriched_data):
    """
    Returns:
        위험 시: {"level": "emergency"|"warning", "object": str, "direction": str, "distance_cm": float|None, "audio_file": str}
        안전 시: None
    """
    uc = enriched_data.get("ultrasonic_cm")

    # Rule 1: 초음파 30cm 미만 → 즉시 정지
    if uc is not None and uc < DANGER_DISTANCE_CM:
        target = enriched_data.get("ultrasonic_target", "unknown")
        return {
            "level": "emergency",
            "object": target,
            "direction": "center",
            "distance_cm": uc,
            "audio_file": "warn_emergency.mp3"
        }

    # Rule 2: YOLO near + 위험 라벨
    for obj in enriched_data.get("objects", []):
        if obj["distance_est"] == "near" and obj["label"] in DANGER_LABELS:
            return {
                "level": "warning",
                "object": obj["label"],
                "direction": obj["direction"],
                "distance_cm": uc,
                "audio_file": f"warn_{obj['label']}.mp3"
            }

    return None
```

테스트 (mock 데이터):

```python
from ai_core.danger import judge

# emergency
assert judge({"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"})["level"] == "emergency"
# warning
assert judge({"objects": [{"label": "person", "direction": "left", "distance_est": "near", "bbox_ratio": 0.3, "confidence": 0.9}], "ultrasonic_cm": None, "ultrasonic_target": None})["level"] == "warning"
# safe
assert judge({"objects": [{"label": "chair", "direction": "center", "distance_est": "far", "bbox_ratio": 0.03, "confidence": 0.8}], "ultrasonic_cm": 200, "ultrasonic_target": "chair"}) is None

print("[OK] danger.judge 3 cases passed")
```

완료 기준:

- emergency / warning / safe 3가지 케이스 정상 판정

---

### Step 1-4: 위험 판단 → 로컬 오디오 즉시 재생 [필수]

STATUS: TODO 파일: `ai_core/audio_player.py` 의존: Step 1-3

작업:

1. pygame.mixer 기반 오디오 재생
2. interrupt=True면 현재 재생 중단 후 즉시 재생 (위험 경고용)
3. 파일 없으면 로그만 출력 (크래시 방지)

```python
# ai_core/audio_player.py

import pygame
from pathlib import Path

AUDIO_DIR = Path("audio/fallback")

def init():
    pygame.mixer.init()

def play(filename, interrupt=False):
    """
    Args:
        filename: audio/fallback/ 내 파일명
        interrupt: True면 현재 재생 중단 후 즉시 (위험 경고용)
    """
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        print(f"[AUDIO] 파일 없음: {filepath}")
        return

    if interrupt:
        pygame.mixer.music.stop()

    if not pygame.mixer.music.get_busy() or interrupt:
        pygame.mixer.music.load(str(filepath))
        pygame.mixer.music.play()

def play_path(filepath, interrupt=False):
    """절대 경로로 재생 (TTS 임시 파일용)."""
    if not Path(filepath).exists():
        print(f"[AUDIO] 파일 없음: {filepath}")
        return
    if interrupt:
        pygame.mixer.music.stop()
    if not pygame.mixer.music.get_busy() or interrupt:
        pygame.mixer.music.load(str(filepath))
        pygame.mixer.music.play()

def stop():
    pygame.mixer.music.stop()
```

Phase 1 테스트용 임시 오디오 생성:

```bash
python -c "
import wave, struct, os
os.makedirs('audio/fallback', exist_ok=True)
for name in ['warn_emergency.mp3', 'warn_person.mp3', 'warn_car.mp3', 'buffer_01.mp3']:
    with wave.open(f'audio/fallback/{name.replace(\".mp3\", \".wav\")}', 'w') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(44100)
        f.writeframes(struct.pack('<h', 0) * 44100)
    print(f'[OK] {name} (임시 wav)')
"
```

> 주의: Step 1-5에서 실제 TTS mp3로 교체. 임시 파일은 .wav로 생성. audio_player에서 mp3/wav 모두 재생 가능 (pygame 지원).

완료 기준:

- `play("warn_emergency.mp3", interrupt=True)` 호출 시 오디오 재생
- 파일 없을 때 크래시 없이 로그 출력

---

### Step 1-5: Fallback 오디오 사전 생성 [필수]

STATUS: TODO 파일: `audio/generate_fallback.py` 의존: Step 0-2 (OPENAI_API_KEY)

작업:

1. 20개 대사 정의 (docs/fallback_messages.md와 동기화)
2. OpenAI TTS API로 일괄 생성 → mp3
3. `audio/fallback/` 에 저장

```python
# audio/generate_fallback.py

import os
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()
OUTPUT_DIR = Path("audio/fallback")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCRIPTS = {
    # 위험 경고 (5)
    "warn_emergency": "멈춰!",
    "warn_obstacle": "조심해, 앞에 뭔가 있어",
    "warn_person": "앞에 사람이 있어, 천천히",
    "warn_close": "너무 가까워, 멈춰",
    "warn_stairs": "계단이야, 조심해",
    # 칭찬·격려 (5)
    "praise_01": "잘하고 있어!",
    "praise_02": "대단해, 혼자서 잘 걷고 있어",
    "praise_03": "아주 잘했어!",
    "praise_04": "용감하다! 계속 가보자",
    "praise_05": "완벽해, 그렇게 하면 돼",
    # 세션 시작·종료 (3)
    "session_start": "안녕! 오늘도 같이 걸어보자",
    "session_end": "오늘 정말 잘했어, 다음에 또 만나자",
    "session_pause": "잠깐 쉬었다 가자",
    # 대기 버퍼 (4)
    "buffer_01": "잠깐만, 보고 있어",
    "buffer_02": "기다려봐, 확인하고 있어",
    "buffer_03": "알겠어, 잠깐만",
    "buffer_04": "음, 한번 볼게",
    # 갈라쇼 전용 (3)
    "gala_01": "시아와 함께 걸어볼까?",
    "gala_02": "잘했어, 장애물을 피해서 걸었어",
    "gala_03": "오늘 연습 끝! 정말 잘했어",
}

def generate():
    for key, text in SCRIPTS.items():
        output_path = OUTPUT_DIR / f"{key}.mp3"
        if output_path.exists():
            print(f"[SKIP] {key} 이미 존재")
            continue
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="mp3"
        )
        response.write_to_file(str(output_path))
        print(f"[OK] {key}: {text}")

if __name__ == "__main__":
    generate()
    print(f"\n총 {len(list(OUTPUT_DIR.glob('*.mp3')))}개 파일 생성 완료")
```

완료 기준:

- `audio/fallback/` 에 20개 mp3 파일 생성
- 각 파일 재생 정상 확인

---

### Step 1-6: enriched JSON → LLM → TTS 공간 묘사 [필수]

STATUS: TODO 파일: `ai_core/llm_client.py`, `ai_core/tts.py`, `ai_core/narration.py` 의존: Step 1-2, 0-2

작업:

1. enriched JSON → LLM 프롬프트 → 공간 묘사 텍스트
2. 텍스트 → TTS → 오디오 재생
3. LLM 실패 시 Fallback 재생
4. 지연 측정 로그 필수

```python
# utils/latency_logger.py

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

```python
# ai_core/llm_client.py

import os
from openai import OpenAI
from server.config import LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, GROQ_API_KEY
from utils.latency_logger import log

SYSTEM_PROMPT = """너는 '시아'야. 시각장애 아이의 보행을 도와주는 친근한 AI 친구야.
주변 상황을 짧고 따뜻하게 알려줘. 2문장 이내로 말해.
방향은 왼쪽/오른쪽/앞으로 알려주고, 거리는 가까이/좀 떨어져서/멀리로 표현해.
위험할 때는 단호하게, 안전할 때는 편안하게 말해."""

client = None

def init():
    global client
    if LLM_PROVIDER == "groq":
        client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)

def call(system_prompt, user_msg, max_tokens=100):
    """범용 LLM 호출. 실패 시 None."""
    try:
        log("llm_start")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        log("llm_end")
        return response.choices[0].message.content.strip()
    except Exception as e:
        log("llm_fail")
        print(f"[LLM ERROR] {e}")
        return None
```

```python
# ai_core/narration.py

from ai_core.llm_client import call, SYSTEM_PROMPT

def narrate(enriched_data):
    """enriched JSON → 공간 묘사 텍스트. 실패 시 None."""
    objects_desc = []
    for obj in enriched_data.get("objects", []):
        dir_kr = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}[obj["direction"]]
        dist_kr = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}[obj["distance_est"]]
        objects_desc.append(f"{dir_kr} {dist_kr} {obj['label']}")

    uc = enriched_data.get("ultrasonic_cm")
    ut = enriched_data.get("ultrasonic_target")
    us_desc = f"\n정면 {uc}cm 거리에 {ut}이(가) 있음." if uc and ut else ""

    user_msg = f"현재 감지된 물체: {', '.join(objects_desc) if objects_desc else '없음'}{us_desc}"

    return call(SYSTEM_PROMPT, user_msg)
```

```python
# ai_core/tts.py

import tempfile
from openai import OpenAI
from server.config import OPENAI_API_KEY
from ai_core.audio_player import play_path
from utils.latency_logger import log

client = None

def init():
    global client
    client = OpenAI(api_key=OPENAI_API_KEY)

def speak(text):
    """텍스트 → TTS → 재생. 실패 시 False."""
    try:
        log("tts_start")
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="mp3"
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            response.write_to_file(f.name)
            log("tts_end")
            play_path(f.name)
            return True
    except Exception as e:
        log("tts_fail")
        print(f"[TTS ERROR] {e}")
        return False
```

Fallback 연동 패턴 (main.py에서 사용):

```python
text = narration.narrate(enriched)
if text:
    tts.speak(text)
else:
    audio_player.play("buffer_01.mp3")  # LLM 실패 → Fallback
```

완료 기준:

- enriched JSON → LLM → TTS 재생 성공
- `[LATENCY] llm_start → llm_end` 3초 이내
- LLM 실패 시 Fallback mp3 재생 확인

> 3초 초과 시 → .env에서 LLM_PROVIDER=groq, LLM_MODEL=llama-3.1-8b-instant로 전환 테스트

---

### Step 1-7: Web Speech API → WebSocket → LLM → TTS [옵션 — Phase 3에서 완성 가능]

STATUS: TODO 파일: `dashboard/src/hooks/useSpeechRecognition.js` 의존: Step 1-8 (WebSocket 서버)

작업:

1. 브라우저 Web Speech API로 한국어 음성 인식
2. 인식 결과 → WebSocket → 서버

```javascript
// dashboard/src/hooks/useSpeechRecognition.js

import { useRef, useCallback } from "react";

export function useSpeechRecognition(ws, enabled = true) {
  const recognitionRef = useRef(null);

  const start = useCallback(() => {
    if (!("webkitSpeechRecognition" in window)) {
      console.error("Web Speech API 미지원 브라우저");
      return;
    }
    const recognition = new window.webkitSpeechRecognition();
    recognition.lang = "ko-KR";
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const last = event.results[event.results.length - 1];
      if (last.isFinal) {
        const text = last[0].transcript.trim();
        console.log(`[STT] "${text}"`);
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ stt_text: text }));
        }
      }
    };
    recognition.onerror = (e) => console.error("[STT Error]", e.error);
    recognition.onend = () => { if (enabled) recognition.start(); };
    recognition.start();
    recognitionRef.current = recognition;
  }, [ws, enabled]);

  const stop = useCallback(() => { recognitionRef.current?.stop(); }, []);

  return { start, stop };
}
```

완료 기준:

- Chrome에서 한국어 음성 인식 → 콘솔 텍스트 출력
- WebSocket 전송 → 서버 수신 확인

---

### Step 1-8: FastAPI + WebSocket 서버 구조 [필수]

STATUS: TODO 파일: `server/main_server.py`, `server/websocket_handler.py`, `main.py` 의존: Step 1-1 ~ 1-6

작업:

1. FastAPI 앱 + WebSocket 엔드포인트
2. 메인 감지 루프 (백그라운드 태스크)
3. WebSocket으로 대시보드에 결과 push

```python
# server/websocket_handler.py

import json
from fastapi import WebSocket, WebSocketDisconnect

clients = set()

async def connect(ws: WebSocket):
    await ws.accept()
    clients.add(ws)

async def disconnect(ws: WebSocket):
    clients.discard(ws)

async def broadcast(data: dict):
    msg = json.dumps(data, ensure_ascii=False)
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except:
            clients.discard(ws)

async def receive_loop(ws: WebSocket, handler):
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            await handler(msg)
    except WebSocketDisconnect:
        await disconnect(ws)
```

```python
# server/main_server.py

import asyncio
import json
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.websocket_handler import connect, disconnect, receive_loop, broadcast
from server.config import SERVER_HOST, SERVER_PORT

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 상태
current_stage = 1
learning_active = False

async def handle_dashboard_message(msg):
    global current_stage, learning_active
    if "event" in msg:
        if msg["event"] == "start_learning":
            learning_active = True
            current_stage = msg.get("stage", 1)
        elif msg["event"] == "stop_learning":
            learning_active = False
        elif msg["event"] == "fallback":
            from ai_core.audio_player import play
            play(msg.get("audio_file", "buffer_01.mp3"))
    elif "stt_text" in msg:
        from ai_core.narration import narrate
        from ai_core.tts import speak
        response = narrate({"objects": [], "ultrasonic_cm": None, "ultrasonic_target": None})
        if response:
            speak(response)
            await broadcast({
                "type": "stt_response",
                "message": response,
                "stage": current_stage,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            })

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await connect(ws)
    await receive_loop(ws, handle_dashboard_message)
```

```python
# main.py — 메인 실행

import asyncio
import cv2
import uvicorn

from ai_core.vision import load_model, detect, enrich
from ai_core.danger import judge
from ai_core.audio_player import init as audio_init, play as audio_play
from ai_core.llm_client import init as llm_init
from ai_core.tts import init as tts_init, speak
from ai_core.narration import narrate
from server.main_server import app, broadcast, learning_active, current_stage
from server.config import SERVER_HOST, SERVER_PORT
from utils.latency_logger import log, elapsed

async def detection_loop():
    cap = cv2.VideoCapture(0)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            log("detect_start")
            dets = detect(frame)
            enriched = enrich(dets, w, h)
            log("detect_end")

            # 위험 판단
            danger = judge(enriched)
            if danger:
                log("danger_detected")
                audio_play(danger["audio_file"], interrupt=True)
                await broadcast({
                    "type": "danger",
                    "object": danger["object"],
                    "direction": danger["direction"],
                    "distance_cm": danger["distance_cm"],
                    "message": f"위험: {danger['object']}",
                    "stage": current_stage,
                    "audio_file": danger["audio_file"],
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                })
                elapsed("detect_start", "danger_detected")
                await asyncio.sleep(1)
                continue

            # 학습 모드: LLM 공간 묘사 (5초 간격)
            if learning_active and len(enriched["objects"]) > 0:
                text = narrate(enriched)
                if text:
                    speak(text)
                    await broadcast({
                        "type": "narration",
                        "objects": enriched["objects"],
                        "message": text,
                        "stage": current_stage,
                        "timestamp": int(asyncio.get_event_loop().time() * 1000)
                    })
                else:
                    audio_play("buffer_01.mp3")
                elapsed("llm_start", "tts_end")
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(0.1)
    finally:
        cap.release()

@app.on_event("startup")
async def startup():
    load_model()
    audio_init()
    llm_init()
    tts_init()
    asyncio.create_task(detection_loop())

if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
```

완료 기준:

- `python main.py` → 서버 시작 + 감지 루프 동작
- 웹캠 장애물 → 오디오 재생
- WebSocket 클라이언트 연결 → 감지 결과 수신

---

### Step 1-9: React 대시보드 기본 구조 + Fallback 버튼 [필수]

STATUS: TODO 파일: `dashboard/` (React 프로젝트) 의존: Step 1-8

작업:

1. Vite + React 프로젝트 초기화
2. WebSocket 연결 hook
3. 기본 레이아웃: 채팅 + Fallback 패널 + 단계 표시
4. Fallback 버튼 → WebSocket → 서버 → 오디오 재생

```bash
cd dashboard
npm create vite@latest . -- --template react
npm install
```

```javascript
// dashboard/src/hooks/useWebSocket.js

import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(url) {
  const wsRef = useRef(null);
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(url);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setMessages((prev) => [...prev.slice(-50), data]);  // 최근 50개 유지
    };
    wsRef.current = ws;
    return () => ws.close();
  }, [url]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { ws: wsRef.current, messages, connected, send };
}
```

```jsx
// dashboard/src/components/FallbackPanel.jsx

const BUTTONS = [
  { file: "warn_emergency.mp3", label: "멈춰!" },
  { file: "warn_obstacle.mp3", label: "앞에 뭔가" },
  { file: "praise_01.mp3", label: "잘하고 있어" },
  { file: "buffer_01.mp3", label: "잠깐만" },
  { file: "gala_01.mp3", label: "시작" },
  { file: "gala_03.mp3", label: "끝" },
];

export default function FallbackPanel({ send, visible }) {
  if (!visible) return null;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
      {BUTTONS.map(({ file, label }) => (
        <button key={file} onClick={() => send({ event: "fallback", audio_file: file })}>
          {label}
        </button>
      ))}
    </div>
  );
}
```

완료 기준:

- `npm run dev` → 대시보드 브라우저 표시
- WebSocket 연결 → 서버 감지 결과 실시간 표시
- Fallback 버튼 클릭 → 서버에서 오디오 재생

---

## Phase 0+1 전체 완료 체크리스트

|#|기준|목표치|측정|
|---|---|---|---|
|1|웹캠 장애물 → 로컬 오디오|200ms 이내|`latency_logger`|
|2|LLM 응답 → TTS 음성|3초 이내|`latency_logger`|
|3|브라우저 음성 → 시아 응답|5초 이내|`latency_logger`|
|4|WebSocket 감지 결과 수신|실시간|대시보드 확인|
|5|Fallback 버튼 → 오디오|즉시|버튼 클릭 테스트|
|6|각 구간 지연 5회 측정|평균값 기록|로그|

> Phase 1 완료 전 Phase 2 진입 금지. LLM 응답 3초 초과 시 → .env에서 Groq 전환 테스트.

---

_— Phase 0+1 문서 끝 —_