# AI Core 핸드오프 문서

## 1. 프로젝트 개요

**SIA**는 시각장애 아동의 보행을 도와주는 AI 친구입니다.

- 아이와 **대화**(Stage 1), 주변 환경 **학습 묘사**(Stage 2), **위험 경고**(Stage 3)를 단계별로 수행합니다.
- 아키텍처: `server/` (완료) <-> `ai_core/` (구현 필요) <-> `dashboard/` (완료)

## 2. 현재 진행 상황

| 모듈 | 상태 | 설명 |
|------|------|------|
| `server/` | 완료 | FastAPI + WebSocket + VoicePipeline |
| `dashboard/` | 완료 | React 대시보드 |
| `ai_core/` | **인터페이스만 정의** | 각 모듈의 함수 시그니처와 호출 규약 확정, 내부 구현 필요 |
| `tests/` | 완료 | 47개 통합 테스트 통과 |

## 3. 아키텍처 흐름도

### 3-1. Voice Pipeline (Stage 1: 대화)

```
마이크 → MicCapture.listen()
       → STTClient.transcribe(audio_data)
       → llm_client.call_async(system_prompt, user_msg)
       → tts.get_or_create(response_text) → AudioManager.play_path(filepath)
```

- 한 턴이 끝나야 다음 턴 시작 (직렬 실행)
- `voice_pipeline.py`의 `_run_one_turn()`이 한 턴 전체를 처리
- TTS 재생 시 `_tts_lock`을 획득하여 narration/danger와 경합 방지

### 3-2. AI Loop (Stage 2-3: 학습/위험)

```
웹캠 프레임 (get_frame())
  → vision.detect(frame)          # YOLO 객체 감지
  → vision.enrich(dets, w, h)     # 방향/거리 추정
  → danger.judge(enriched, stage) # Stage 3 전용 위험 판단
  → narration.narrate_async(enriched)  # Stage 2-3 공간 묘사
  → tts.get_or_create(text) → AudioManager.play_path(filepath)
```

- `main.py`의 `_ai_loop()`에서 실행
- Stage 1이면 AI 분석 건너뜀 (`asyncio.sleep(0.5)`)
- 위험이 감지되면 묘사보다 우선 처리 (continue로 묘사 스킵)
- 묘사는 `NARRATION_INTERVAL = 5.0`초 간격으로 쓰로틀링

## 4. ai_core 모듈별 인터페이스 계약

### 4-1. llm_client.py

**파일 위치:** `ai_core/llm_client.py`

```python
# 모듈 수준 상수
SYSTEM_PROMPT: str  # 시아 캐릭터 프롬프트 (2문장 이내 응답 지시)
client = None       # OpenAI 호환 클라이언트 인스턴스

def init() -> None
async def call_async(system_prompt: str, user_msg: str, max_tokens: int = 100) -> str | None
```

| 함수 | 설명 |
|------|------|
| `init()` | OpenAI 호환 클라이언트 초기화. `LLM_PROVIDER`에 따라 Groq/Gemini/OpenAI 엔드포인트 설정. API 키 미설정 시 경고만 출력 (에러 아님). |
| `call_async()` | 비블로킹 LLM 호출. 내부적으로 `asyncio.to_thread(_call_sync, ...)`로 동기 호출을 감쌈. 실패 시 `None` 반환. |

**호출 시점:**
- `voice_pipeline.py` `_run_one_turn()` 라인 83: `response = await call_async(context, text)`
- `narration.py` `narrate_async()` 라인 27: `return await call_async(SYSTEM_PROMPT, user_msg)`

**내부 동작 (`_call_sync`):**
- `client.chat.completions.create()` 호출 (OpenAI SDK)
- `model=LLM_MODEL`, `temperature=0.7`, `max_tokens=100`
- 예외 발생 시 `None` 반환 (caller 쪽에서 fallback 처리)

**import 방식:**
```python
from ai_core.llm_client import call_async, SYSTEM_PROMPT  # voice_pipeline.py
from ai_core.llm_client import init as llm_init           # main.py
```

---

### 4-2. tts.py

**파일 위치:** `ai_core/tts.py`

```python
TTS_VOICE = "ko-KR-SunHiNeural"  # edge-tts 한국어 여성 음성

class TTSCache:
    def __init__(self, cache_root: str = "./tts_cache")
    def start_session(self, session_id: str) -> None
    def end_session(self) -> None
    def get(self, text: str) -> Path | None
    async def get_or_create(self, text: str) -> Path | None

def get_tts_cache() -> TTSCache  # 싱글톤
```

| 메서드 | 설명 |
|--------|------|
| `start_session(sid)` | `./tts_cache/{sid}/` 디렉토리 생성. 캐시 인덱스 초기화. |
| `end_session()` | 세션 디렉토리 삭제 (`shutil.rmtree`). |
| `get(text)` | MD5 해시로 캐시 조회. HIT 시 `Path`, MISS 시 `None`. |
| `get_or_create(text)` | 캐시 HIT -> 즉시 반환. MISS -> `edge_tts.Communicate`로 mp3 생성 후 캐시 저장. 실패 시 `None`. |

**호출 시점:**
- `voice_pipeline.py` `_speak()` 라인 124: `filepath = await tts.get_or_create(text)`
- `main.py` `startup()` 라인 282-283: `tts = get_tts_cache(); tts.start_session(...)`
- `main.py` `_handle_narration()` 라인 236: `filepath = await tts.get_or_create(text)`
- `main.py` `shutdown()` 라인 314: `tts.end_session()`

**import 방식:**
```python
from ai_core.tts import get_tts_cache  # main.py, voice_pipeline.py
```

---

### 4-3. audio_manager.py

**파일 위치:** `ai_core/audio_manager.py`

```python
FALLBACK_DIR = Path("audio/fallback")

class AudioManager:
    def play(self, filename: str, interrupt: bool = False) -> None
    def play_path(self, filepath: str, interrupt: bool = False) -> None
    def is_playing(self) -> bool
    def stop(self) -> None

def get_audio_manager() -> AudioManager  # 싱글톤
```

| 메서드 | 설명 |
|--------|------|
| `play(filename, interrupt)` | `audio/fallback/{filename}` 재생. `interrupt=True`이면 현재 재생 중단 후 즉시 재생. |
| `play_path(filepath, interrupt)` | 절대 경로로 재생 (TTS 캐시 파일용). |
| `is_playing()` | `pygame.mixer.music.get_busy()` 래핑. |
| `stop()` | 현재 재생 중단. |

**내부 구조:**
- 별도 데몬 스레드(`_worker`)에서 `queue.Queue` 기반 재생
- `threading.Lock`으로 동시 재생 방지
- `pygame.mixer` 사용

**호출 시점:**
- `voice_pipeline.py` `_speak()` 라인 129-130: `am.play_path(str(filepath))`
- `voice_pipeline.py` `_play_fallback()` 라인 167: `am.play("buffer_01.mp3")`
- `main.py` `_ai_loop()` 라인 167: `audio.play(danger["audio_file"], interrupt=True)`
- `main.py` `_handle_narration()` 라인 239: `audio.play_path(str(filepath))`

**import 방식:**
```python
from ai_core.audio_manager import get_audio_manager  # main.py, voice_pipeline.py
```

---

### 4-4. vision.py

**파일 위치:** `ai_core/vision.py`

```python
model = None  # YOLO 모델 인스턴스

def load_model() -> None
def detect(frame) -> list[dict]
def enrich(detections, frame_w, frame_h, ultrasonic_cm=None) -> dict
```

| 함수 | 설명 |
|------|------|
| `load_model()` | `YOLO(YOLO_MODEL)` 호출. 모듈 변수 `model`에 저장. |
| `detect(frame)` | numpy BGR 프레임 입력. YOLO 추론 후 `[{label, x, y, w, h, conf}, ...]` 반환. |
| `enrich(detections, frame_w, frame_h, ultrasonic_cm)` | bbox 좌표를 방향/거리로 변환. 아래 스키마의 enriched dict 반환. |

**`detect()` 반환값:**
```python
[
    {"label": "person", "x": 100.0, "y": 50.0, "w": 200.0, "h": 300.0, "conf": 0.85},
    ...
]
```

**`enrich()` 반환값 (enriched dict):**
```python
{
    "objects": [
        {
            "label": "person",
            "direction": "left" | "center" | "right",   # cx < 0.33 / 0.33~0.66 / > 0.66
            "distance_est": "near" | "mid" | "far",     # area > 0.20 / 0.05~0.20 / < 0.05
            "bbox_ratio": 0.123,
            "confidence": 0.85
        },
        ...
    ],
    "ultrasonic_cm": None | float,         # HC-SR04P 센서 (Phase 1에서는 None)
    "ultrasonic_target": None | str        # center에서 가장 큰 객체 라벨
}
```

**호출 시점:**
- `main.py` `startup()` 라인 280: `load_model()`
- `main.py` `_ai_loop()` 라인 150-151: `dets = await asyncio.to_thread(detect, frame)` -> `enriched = enrich(dets, w, h)`

**import 방식:**
```python
from ai_core.vision import load_model, detect, enrich  # main.py
```

---

### 4-5. danger.py

**파일 위치:** `ai_core/danger.py`

```python
DANGER_LABELS = {"person", "car", "bicycle", "motorcycle", "bus", "truck", "dog"}

def judge(enriched_data, current_stage: int) -> dict | None
```

| 함수 | 설명 |
|------|------|
| `judge(enriched_data, current_stage)` | Stage 3이 아니면 항상 `None`. Stage 3에서 위험 감지 시 dict 반환. |

**판정 규칙 (우선순위):**
1. 초음파 `< DANGER_DISTANCE_CM` (기본 30cm) -> `level: "emergency"`, `audio_file: "warn_emergency.mp3"`
2. YOLO `distance_est == "near"` + `label in DANGER_LABELS` -> `level: "warning"`, `audio_file: "warn_{label}.mp3"`

**반환값 (위험 시):**
```python
{
    "level": "emergency" | "warning",
    "object": str,           # 감지된 객체 라벨
    "direction": str,        # "left" | "center" | "right"
    "distance_cm": float | None,
    "audio_file": str        # "warn_emergency.mp3" 또는 "warn_{label}.mp3"
}
```

**호출 시점:**
- `main.py` `_ai_loop()` 라인 157: `danger = judge(enriched, srv.app_state.current_stage)`

**import 방식:**
```python
from ai_core.danger import judge  # main.py
```

---

### 4-6. narration.py

**파일 위치:** `ai_core/narration.py`

```python
async def narrate_async(enriched_data) -> str | None
```

| 함수 | 설명 |
|------|------|
| `narrate_async(enriched_data)` | enriched dict를 한국어 묘사 텍스트로 변환하여 LLM에 전달. 결과 문자열 반환. 실패 시 `None`. |

**내부 동작:**
1. `enriched_data["objects"]`를 순회하며 `"{방향} {거리} {label}"` 형태로 변환
   - 방향: `left->왼쪽`, `center->앞`, `right->오른쪽`
   - 거리: `near->가까이`, `mid->좀 떨어져서`, `far->멀리`
2. 초음파 정보가 있으면 추가: `"정면 {cm}cm 거리에 {target}이(가) 있음."`
3. `call_async(SYSTEM_PROMPT, user_msg)` 호출

**호출 시점:**
- `main.py` `_handle_narration()` 라인 216: `text = await narrate_async(enriched)`

**import 방식:**
```python
from ai_core.narration import narrate_async  # main.py
```

## 5. 환경 변수 (.env)

`server/config.py`에서 `dotenv`로 로드합니다.

### LLM 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `"groq"` | LLM 공급자. `groq` / `gemini` / `openai` |
| `LLM_MODEL` | `"llama-3.3-70b-versatile"` | 사용할 모델명 |
| `GROQ_API_KEY` | `""` | Groq API 키 |
| `GEMINI_API_KEY` | `""` | Gemini API 키 |
| `OPENAI_API_KEY` | `""` | OpenAI API 키 |

### YOLO / 서버 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `YOLO_MODEL` | `"yolov8n.pt"` | YOLO 모델 파일 |
| `YOLO_CONF_THRESHOLD` | `0.4` | 감지 신뢰도 임계값 |
| `DANGER_DISTANCE_CM` | `30` | 초음파 위험 거리 (cm) |
| `SERVER_HOST` | `"0.0.0.0"` | 서버 호스트 |
| `SERVER_PORT` | `8000` | 서버 포트 |

### 하드웨어 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `WEBCAM_INDEX` | `0` | 웹캠 인덱스 (0=내장, 1+=외장) |
| `MIC_DEVICE_INDEX` | `None` | 마이크 장치 인덱스 (None=시스템 기본) |
| `VAD_SILENCE_THRESHOLD` | `500` | VAD 무음 판정 임계값 |
| `VAD_SILENCE_DURATION` | `1.5` | 무음 지속 시간 (초) |
| `VAD_MAX_DURATION` | `10` | 최대 녹음 시간 (초) |
| `STT_LANGUAGE` | `"ko-KR"` | STT 언어 |

## 6. 에러 처리 규약

### LLM 실패

- `voice_pipeline.py`: `call_async()` 예외 또는 `None` 반환 시 -> `_play_fallback()` 호출 (buffer_01.mp3 재생 + error broadcast) -> `_cooldown_on_fail()` (점진적 대기)
- `main.py` `_handle_narration()`: `narrate_async()` 예외 시 -> error broadcast -> fallback 오디오 (buffer_01.mp3)

### TTS 실패

- `voice_pipeline.py` `_speak()`: 예외 시 error broadcast 후 **반드시 `tts_done` broadcast** (대시보드 상태 복구 보장)
- `main.py` `_handle_narration()`: `get_or_create()` 반환값이 `None`이면 buffer_01.mp3 fallback 재생

### 위험 오디오 실패

- `main.py` `_ai_loop()`: `audio.play(danger["audio_file"])` 예외 시 -> error broadcast -> `buffer_01.mp3` fallback 재생

### 연속 실패 쿨다운 (voice_pipeline 전용)

```
1회 실패: 2초 대기
2회 실패: 5초 대기
3회 실패: 10초 대기
4회+ 실패: 30초 대기
```

LLM 성공 시 카운터 리셋 (`self._consecutive_fails = 0`).

## 7. 테스트 방법

```bash
# 전체 테스트 실행 (47개)
pytest tests/ -v

# 서버 단독 실행
python main.py
```

서버 실행 시 `startup()` 이벤트에서 순서대로 초기화:
1. `load_model()` - YOLO 모델 로드
2. `llm_init()` - LLM 클라이언트 초기화
3. `get_tts_cache().start_session(...)` - TTS 세션 시작
4. `_frame_loop` / `_ai_loop` / `VoicePipeline.run()` 태스크 생성

## 8. 주의사항

### TTS Lock 공유

`main.py`에서 생성된 `_tts_lock = asyncio.Lock()`을 VoicePipeline, narration, danger가 모두 공유합니다.
- `VoicePipeline.__init__(tts_lock=)` 으로 전달
- `_handle_narration()`, `_ai_loop()` danger 분기에서 `async with _tts_lock:` 사용
- **동시에 두 곳에서 TTS/오디오를 재생하지 않도록 보장**

### 대화 히스토리

- 최대 20개 메시지 (= 10턴), 슬라이딩 윈도우 방식
- `_build_context()`에서 system prompt + 히스토리를 결합
- 히스토리 형식: `"아이: {user_msg}\n시아: {assistant_msg}"`

### Stage별 동작 정리

| Stage | Voice Pipeline | AI Loop (vision) | Danger | Narration |
|-------|---------------|-------------------|--------|-----------|
| 1 (대화) | 활성 | **비활성** (sleep) | 비활성 | 비활성 |
| 2 (학습) | 활성 | 활성 | 비활성 (judge -> None) | 활성 |
| 3 (위험) | 활성 | 활성 | **활성** | 활성 (위험 없을 때) |

### Fallback 오디오

- `audio/fallback/buffer_01.mp3`: 범용 fallback 경고음
- `audio/fallback/warn_emergency.mp3`: 초음파 긴급 경고
- `audio/fallback/warn_{label}.mp3`: 객체별 경고음 (person, car 등)
