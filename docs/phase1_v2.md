# SIA MVP — Phase 1: 파이프라인 최소 연결 (v2)

> 목표: 노트북 웹캠으로 소리가 나는 루프 완성. ESP32-CAM 없이.  
> Phase 1 완료 전 Phase 2 진입 금지.  
> v2 핵심 변경: AudioManager 스레드 분리, LLM 비블로킹, TTS 캐시, Stage별 동작 분리

---

## Step 1-1: 웹캠 → YOLO → bbox 원본 출력

**STATUS:** `TODO`  
**파일:** `ai_core/vision.py`  
**의존:** Step 0-1, 0-4

### 작업

```python
# ai_core/vision.py

from ultralytics import YOLO
from server.config import YOLO_MODEL, YOLO_CONF_THRESHOLD
from utils.latency_logger import log

model = None

def load_model():
    global model
    log("yolo_load_start")
    model = YOLO(YOLO_MODEL)
    log("yolo_load_end")

def detect(frame):
    """
    Args: frame (numpy array, BGR)
    Returns: list of dict {label, x, y, w, h, conf}
    """
    log("yolo_detect_start")
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
    log("yolo_detect_end")
    return detections
```

### 테스트

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

### 완료 기준

- [ ] 웹캠 프레임에서 객체 감지 결과 출력
- [ ] `[LATENCY]` 로그 출력 확인

---

## Step 1-2: YOLO bbox 후처리 → enriched JSON

**STATUS:** `TODO`  
**파일:** `ai_core/vision.py` (enrich 함수 추가)  
**의존:** Step 1-1

### 작업

```python
# ai_core/vision.py에 추가

def enrich(detections, frame_w, frame_h, ultrasonic_cm=None):
    """bbox → 방향(left/center/right) + 거리(near/mid/far) + 초음파 매칭."""
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

### 테스트

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

### 완료 기준

- [ ] enriched JSON이 interface_contract 스키마와 일치

---

## Step 1-3: 위험 판단 룰 (Stage 3 전용)

**STATUS:** `TODO`  
**파일:** `ai_core/danger.py`  
**의존:** Step 1-2

### 작업

```python
# ai_core/danger.py

from server.config import DANGER_DISTANCE_CM

DANGER_LABELS = {"person", "car", "bicycle", "motorcycle", "bus", "truck", "dog"}

def judge(enriched_data, current_stage: int):
    """
    Stage 3이 아니면 항상 None 반환 (위험 판단 비활성).
    
    Returns:
        위험 시: {"level": "emergency"|"warning", "object": str, "direction": str, 
                  "distance_cm": float|None, "audio_file": str}
        안전 시: None
    """
    # v2 핵심: Stage 3에서만 위험 판단 활성
    if current_stage != 3:
        return None

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

### 테스트

```python
from ai_core.danger import judge

# Stage 1, 2에서는 항상 None
assert judge({"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"}, current_stage=1) is None
assert judge({"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"}, current_stage=2) is None

# Stage 3: emergency
assert judge({"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"}, current_stage=3)["level"] == "emergency"

# Stage 3: warning
assert judge({"objects": [{"label": "person", "direction": "left", "distance_est": "near", "bbox_ratio": 0.3, "confidence": 0.9}], "ultrasonic_cm": None, "ultrasonic_target": None}, current_stage=3)["level"] == "warning"

# Stage 3: safe
assert judge({"objects": [{"label": "chair", "direction": "center", "distance_est": "far", "bbox_ratio": 0.03, "confidence": 0.8}], "ultrasonic_cm": 200, "ultrasonic_target": "chair"}, current_stage=3) is None

print("[OK] danger.judge 5 cases passed")
```

### 완료 기준

- [ ] Stage 1, 2에서 항상 None
- [ ] Stage 3에서 emergency / warning / safe 3가지 정상 판정

---

## Step 1-4: AudioManager 구현 (스레드 분리)

**STATUS:** `TODO`  
**파일:** `ai_core/audio_manager.py`  
**의존:** Step 0-5

### 작업

```python
# ai_core/audio_manager.py

import threading
import queue
import pygame
from pathlib import Path
from utils.latency_logger import log

FALLBACK_DIR = Path("audio/fallback")

class AudioManager:
    """
    별도 스레드에서 오디오 재생. Lock으로 동시 재생 방지.
    모드가 겹치지 않으므로 우선순위 큐 불필요.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._running = True
        pygame.mixer.init()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def play(self, filename: str, interrupt: bool = False):
        """
        Fallback 디렉토리 내 파일 재생 요청.
        interrupt=True: Stage 3 긴급 → 현재 중단 후 즉시 재생.
        """
        filepath = FALLBACK_DIR / filename
        if not filepath.exists():
            print(f"[AUDIO] 파일 없음: {filepath}")
            return
        self._queue.put((str(filepath), interrupt))

    def play_path(self, filepath: str, interrupt: bool = False):
        """절대 경로로 재생 (TTS 캐시 파일용)."""
        if not Path(filepath).exists():
            print(f"[AUDIO] 파일 없음: {filepath}")
            return
        self._queue.put((filepath, interrupt))

    def stop(self):
        """현재 재생 중단."""
        pygame.mixer.music.stop()

    def is_playing(self) -> bool:
        """현재 오디오 재생 중인지."""
        return pygame.mixer.music.get_busy()

    def _worker(self):
        """Audio Thread 메인 루프."""
        while self._running:
            try:
                filepath, interrupt = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            log("audio_play_start")

            if interrupt:
                with self._lock:
                    pygame.mixer.music.stop()
                    self._play_file(filepath)
            else:
                acquired = self._lock.acquire(timeout=0.1)
                if not acquired:
                    print("[AUDIO] Lock 획득 실패, 스킵")
                    continue
                try:
                    self._play_file(filepath)
                finally:
                    self._lock.release()

            log("audio_play_end")

    def _play_file(self, filepath: str):
        """실제 재생 (Audio Thread 내부에서만 호출)."""
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)


# 싱글톤 인스턴스
_instance: AudioManager | None = None

def get_audio_manager() -> AudioManager:
    global _instance
    if _instance is None:
        _instance = AudioManager()
    return _instance
```

### 테스트

```python
import time
from ai_core.audio_manager import get_audio_manager

am = get_audio_manager()
# 파일 없어도 크래시 안 나는지 확인
am.play("nonexistent.mp3")
time.sleep(0.5)
print("[OK] AudioManager 초기화 + 에러 핸들링 정상")
```

### 완료 기준

- [ ] AudioManager가 별도 스레드에서 동작
- [ ] `play()` 호출이 메인 스레드를 블로킹하지 않음
- [ ] 파일 없을 때 크래시 없이 로그 출력
- [ ] `interrupt=True` 시 현재 재생 중단 후 즉시 재생

---

## Step 1-5: Fallback 오디오 사전 생성

**STATUS:** `TODO`  
**파일:** `audio/generate_fallback.py`  
**의존:** Step 0-2 (OPENAI_API_KEY)

### 작업

```python
# audio/generate_fallback.py

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
    # 칭찬 격려 (5)
    "praise_01": "잘하고 있어!",
    "praise_02": "대단해, 혼자서 잘 걷고 있어",
    "praise_03": "아주 잘했어!",
    "praise_04": "용감하다! 계속 가보자",
    "praise_05": "완벽해, 그렇게 하면 돼",
    # 세션 (3)
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
            print(f"[SKIP] {key}")
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

### 완료 기준

- [ ] `audio/fallback/`에 20개 mp3 파일 생성
- [ ] 각 파일 재생 정상

---

## Step 1-6: LLM 비블로킹 + TTS 캐시

**STATUS:** `TODO`  
**파일:** `ai_core/llm_client.py`, `ai_core/tts.py`, `ai_core/narration.py`  
**의존:** Step 1-2, 0-2

### 작업

```python
# ai_core/llm_client.py

import asyncio
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

def _call_sync(system_prompt: str, user_msg: str, max_tokens: int = 100) -> str | None:
    """동기 LLM 호출 (스레드 풀에서 실행됨)."""
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

async def call_async(system_prompt: str, user_msg: str, max_tokens: int = 100) -> str | None:
    """비블로킹 LLM 호출. asyncio.to_thread()로 감쌈."""
    return await asyncio.to_thread(_call_sync, system_prompt, user_msg, max_tokens)
```

```python
# ai_core/tts.py

import asyncio
import hashlib
import shutil
from pathlib import Path
from openai import OpenAI
from server.config import OPENAI_API_KEY
from utils.latency_logger import log

class TTSCache:
    """세션 기반 TTS 캐시. 대시보드 버튼으로 초기화."""

    def __init__(self, cache_root: str = "./tts_cache"):
        self._cache_root = Path(cache_root)
        self._session_dir: Path | None = None
        self._index: dict[str, Path] = {}
        self._client = OpenAI(api_key=OPENAI_API_KEY)

    def start_session(self, session_id: str):
        self._session_dir = self._cache_root / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}
        print(f"[TTS] 세션 시작: {session_id}")

    def end_session(self):
        """대시보드 [새 세션] 버튼 → 캐시 전체 삭제."""
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir)
            print(f"[TTS] 캐시 삭제 완료: {self._session_dir}")
        self._index = {}
        self._session_dir = None

    def get(self, text: str) -> Path | None:
        key = self._hash(text)
        return self._index.get(key)

    def _generate_and_cache(self, text: str) -> Path | None:
        """TTS 생성 후 캐시에 저장 (동기, 스레드 풀에서 실행)."""
        try:
            log("tts_start")
            key = self._hash(text)
            filepath = self._session_dir / f"{key}.mp3"

            response = self._client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=text,
                response_format="mp3"
            )
            response.write_to_file(str(filepath))
            self._index[key] = filepath
            log("tts_end")
            return filepath
        except Exception as e:
            log("tts_fail")
            print(f"[TTS ERROR] {e}")
            return None

    async def get_or_create(self, text: str) -> Path | None:
        """캐시 HIT → 즉시 반환. MISS → TTS 생성 (비블로킹)."""
        cached = self.get(text)
        if cached:
            print(f"[TTS] 캐시 HIT")
            return cached
        return await asyncio.to_thread(self._generate_and_cache, text)

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()


# 싱글톤
_tts_cache: TTSCache | None = None

def get_tts_cache() -> TTSCache:
    global _tts_cache
    if _tts_cache is None:
        _tts_cache = TTSCache()
    return _tts_cache
```

```python
# ai_core/narration.py

from ai_core.llm_client import call_async, SYSTEM_PROMPT

async def narrate_async(enriched_data) -> str | None:
    """enriched JSON → LLM 공간 묘사 텍스트 (비블로킹)."""
    objects_desc = []
    for obj in enriched_data.get("objects", []):
        dir_kr = {"left": "왼쪽", "center": "앞", "right": "오른쪽"}[obj["direction"]]
        dist_kr = {"near": "가까이", "mid": "좀 떨어져서", "far": "멀리"}[obj["distance_est"]]
        objects_desc.append(f"{dir_kr} {dist_kr} {obj['label']}")

    uc = enriched_data.get("ultrasonic_cm")
    ut = enriched_data.get("ultrasonic_target")
    us_desc = f"\n정면 {uc}cm 거리에 {ut}이(가) 있음." if uc and ut else ""

    user_msg = f"현재 감지된 물체: {', '.join(objects_desc) if objects_desc else '없음'}{us_desc}"

    return await call_async(SYSTEM_PROMPT, user_msg)
```

### 완료 기준

- [ ] `call_async()` 호출이 asyncio 루프를 블로킹하지 않음
- [ ] `[LATENCY] llm_start → llm_end` 3초 이내
- [ ] TTS 캐시 HIT 시 API 호출 없이 즉시 파일 경로 반환
- [ ] `end_session()` 호출 시 캐시 디렉토리 삭제 확인
- [ ] LLM 실패 시 None 반환 (크래시 없음)

> 3초 초과 시 → .env에서 LLM_PROVIDER=groq, LLM_MODEL=llama-3.1-8b-instant로 전환

---

## Step 1-7: Web Speech API → WebSocket → LLM → TTS

**STATUS:** `TODO`  
**파일:** `dashboard/src/hooks/useSpeechRecognition.js`  
**의존:** Step 1-8 (WebSocket 서버)

### 작업

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

### 완료 기준

- [ ] Chrome에서 한국어 음성 인식 → 콘솔 텍스트 출력
- [ ] WebSocket 전송 → 서버 수신 확인

---

## Step 1-8: FastAPI + WebSocket 서버 (비블로킹)

**STATUS:** `TODO`  
**파일:** `server/main_server.py`, `server/websocket_handler.py`, `main.py`  
**의존:** Step 1-1 ~ 1-6

### 작업

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
import time
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.websocket_handler import connect, receive_loop, broadcast
from server.config import SERVER_HOST, SERVER_PORT

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 상태
current_stage = 1
learning_active = False

async def handle_dashboard_message(msg):
    """대시보드에서 온 WebSocket 메시지 처리."""
    global current_stage, learning_active

    if "event" in msg:
        event = msg["event"]

        if event == "start_learning":
            learning_active = True
            current_stage = msg.get("stage", 1)

        elif event == "stop_learning":
            learning_active = False

        elif event == "new_session":
            # v2: 새 세션 → TTS 캐시 초기화
            from ai_core.tts import get_tts_cache
            tts = get_tts_cache()
            tts.end_session()
            tts.start_session(f"session_{int(time.time())}")

        elif event == "clear_tts_cache":
            # v2: 수동 캐시 삭제
            from ai_core.tts import get_tts_cache
            get_tts_cache().end_session()

        elif event == "fallback":
            from ai_core.audio_manager import get_audio_manager
            get_audio_manager().play(msg.get("audio_file", "buffer_01.mp3"))

    elif "stt_text" in msg:
        # STT 텍스트 → LLM 대화 → TTS
        from ai_core.narration import narrate_async
        from ai_core.tts import get_tts_cache
        from ai_core.audio_manager import get_audio_manager

        response = await narrate_async({"objects": [], "ultrasonic_cm": None, "ultrasonic_target": None})
        if response:
            tts = get_tts_cache()
            filepath = await tts.get_or_create(response)
            if filepath:
                get_audio_manager().play_path(str(filepath))
            await broadcast({
                "type": "stt_response",
                "message": response,
                "stage": current_stage,
                "timestamp": int(time.time() * 1000)
            })

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await connect(ws)
    await receive_loop(ws, handle_dashboard_message)
```

```python
# main.py

import asyncio
import time
import cv2
import uvicorn

from ai_core.vision import load_model, detect, enrich
from ai_core.danger import judge
from ai_core.audio_manager import get_audio_manager
from ai_core.llm_client import init as llm_init
from ai_core.narration import narrate_async
from ai_core.tts import get_tts_cache
from server.main_server import app, broadcast, current_stage, learning_active
from server.config import SERVER_HOST, SERVER_PORT
from utils.latency_logger import log, elapsed

async def detection_loop():
    """메인 감지 루프. 30fps 제한, LLM은 비블로킹 태스크로 분리."""
    cap = cv2.VideoCapture(0)
    audio = get_audio_manager()
    tts = get_tts_cache()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue

            # Stage 1에서는 YOLO 비활성
            if current_stage == 1:
                await asyncio.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            log("detect_start")
            dets = detect(frame)
            enriched = enrich(dets, w, h)
            log("detect_end")

            # 위험 판단 (Stage 3 전용)
            danger = judge(enriched, current_stage)
            if danger:
                log("danger_detected")
                audio.play(danger["audio_file"], interrupt=True)
                await broadcast({
                    "type": "danger",
                    "object": danger["object"],
                    "direction": danger["direction"],
                    "distance_cm": danger["distance_cm"],
                    "message": f"위험: {danger['object']}",
                    "stage": current_stage,
                    "audio_file": danger["audio_file"],
                    "timestamp": int(time.time() * 1000)
                })
                elapsed("detect_start", "danger_detected")
                await asyncio.sleep(1)
                continue

            # 학습 모드: LLM 공간 묘사 (비블로킹 태스크)
            if learning_active and len(enriched["objects"]) > 0:
                asyncio.create_task(_handle_narration(enriched, tts, audio))
                await asyncio.sleep(5)  # 5초 간격
            else:
                await asyncio.sleep(0.033)  # 30fps 제한
    finally:
        cap.release()

async def _handle_narration(enriched, tts, audio):
    """LLM + TTS를 백그라운드 태스크로 처리."""
    text = await narrate_async(enriched)
    if text:
        filepath = await tts.get_or_create(text)
        if filepath:
            audio.play_path(str(filepath))
        await broadcast({
            "type": "narration",
            "objects": enriched["objects"],
            "message": text,
            "stage": current_stage,
            "timestamp": int(time.time() * 1000)
        })
    else:
        audio.play("buffer_01.mp3")  # LLM 실패 → Fallback

@app.on_event("startup")
async def startup():
    load_model()
    llm_init()
    tts = get_tts_cache()
    tts.start_session(f"session_{int(time.time())}")
    asyncio.create_task(detection_loop())

if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=int(SERVER_PORT))
```

### 완료 기준

- [ ] `python main.py` → 서버 시작 + 감지 루프 동작
- [ ] Stage 2/3: 웹캠 장애물 → 오디오 재생
- [ ] Stage 1: YOLO 비활성 확인
- [ ] WebSocket 연결 → 감지 결과 수신
- [ ] `new_session` 이벤트 → TTS 캐시 초기화 확인
- [ ] LLM 호출 중에도 YOLO 감지가 멈추지 않음 (비블로킹 확인)

---

## Step 1-9: React 대시보드 + 세션 관리

**STATUS:** `TODO`  
**파일:** `dashboard/`  
**의존:** Step 1-8

### 작업

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
      setMessages((prev) => [...prev.slice(-50), data]);
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
// dashboard/src/components/SessionControl.jsx

export default function SessionControl({ send }) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <button onClick={() => send({ event: "new_session" })}>
        🔄 새 세션 (캐시 초기화)
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 1 })}>
        Stage 1
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 2 })}>
        Stage 2
      </button>
      <button onClick={() => send({ event: "start_learning", stage: 3 })}>
        Stage 3
      </button>
      <button onClick={() => send({ event: "stop_learning" })}>
        정지
      </button>
    </div>
  );
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

export default function FallbackPanel({ send }) {
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

### 완료 기준

- [ ] `npm run dev` → 대시보드 브라우저 표시
- [ ] [새 세션] 버튼 → 서버 TTS 캐시 초기화
- [ ] Stage 버튼 → 서버 모드 전환
- [ ] Fallback 버튼 → 서버에서 오디오 재생
- [ ] WebSocket 연결 → 실시간 메시지 표시

---

## Phase 1 전체 완료 체크리스트

| # | 기준 | 목표치 | 측정 방법 |
|---|---|---|---|
| 1 | 웹캠 장애물 → 로컬 오디오 | 200ms 이내 | `latency_logger` |
| 2 | LLM 응답 → TTS 음성 | 3초 이내 | `latency_logger` |
| 3 | TTS 캐시 HIT → 재생 | 즉시 (API 호출 없음) | 로그 확인 |
| 4 | 브라우저 음성 → 시아 응답 | 5초 이내 | `latency_logger` |
| 5 | WebSocket 감지 결과 수신 | 실시간 | 대시보드 확인 |
| 6 | Fallback 버튼 → 오디오 | 즉시 | 버튼 클릭 테스트 |
| 7 | 새 세션 → 캐시 삭제 | 즉시 | 디렉토리 확인 |
| 8 | LLM 호출 중 YOLO 정상 | 비블로킹 | 동시 동작 확인 |
| 9 | Stage 1에서 YOLO 비활성 | 감지 없음 | 로그 확인 |
| 10 | 각 구간 지연 5회 측정 | 평균값 기록 | 로그 |

> Phase 1 완료 전 Phase 2 진입 금지.  
> LLM 응답 3초 초과 시 → .env에서 Groq 전환 테스트.

---

_— Phase 1 v2 문서 끝 —_
