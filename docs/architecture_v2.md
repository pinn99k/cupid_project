# SIA MVP — 아키텍처 설계 v2

> 작성일: 2026-05-17  
> 목표: 갈라쇼 3분 시연 — 끊기지 않는 것이 전부다  
> v1 대비 변경: 스레딩 모델 도입, 오디오 매니저 설계, LLM 비블로킹, TTS 캐시

---

## 1. 시스템 구조 (v2 확정)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Main asyncio Event Loop                       │
│                                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────────┐  │
│  │ YOLO 감지   │   │  WebSocket   │   │   LLM 호출          │  │
│  │  Detection  │──▶│   Handler    │   │ (asyncio.to_thread) │  │
│  │    Loop     │   │              │   │                     │  │
│  └──────┬──────┘   └──────┬───────┘   └──────────┬──────────┘  │
│         │                 │                       │             │
│         └─────────────────┴───────────────────────┘             │
│                           │                                     │
│                    audio_queue.put()                             │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                    ┌───────▼───────┐
                    │  Audio Thread │
                    │               │
                    │  threading.   │
                    │  Lock()       │
                    │               │
                    │  pygame mixer │
                    │  TTS 파일 재생 │
                    └───────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Dashboard (별도 프로세스)                    │
│                                                                 │
│   React  ──  Web Speech API  ──  WebSocket Client               │
│   (음성인식 STT)                  (서버 ↔ 대시보드 연동)           │
└─────────────────────────────────────────────────────────────────┘
```

**데이터 흐름 요약:**

```
카메라 입력
    │
    ▼
YOLO 감지 (asyncio loop)
    │
    ├─── 장애물 감지 → LLM 호출 (to_thread) → TTS 생성 → audio_queue
    │
    ├─── 초음파 < 30cm (Stage 3만) → 긴급 알림 → audio_queue (interrupt=True)
    │
    └─── WebSocket → Dashboard (React) → 화면 업데이트

대시보드 사용자 입력
    │
    ▼
WebSocket 이벤트 → 세션 제어 / LLM 대화 / 캐시 초기화
```

---

## 2. 스레딩 모델

### 스레드 구성

| 스레드 | 담당 작업 | 특징 |
|--------|----------|------|
| **Main Thread** (asyncio) | YOLO 감지 루프, WebSocket 핸들러, LLM 호출 | 단일 이벤트 루프, 논블로킹 |
| **Audio Thread** | pygame mixer 초기화 및 재생, Lock 관리 | 전용 데몬 스레드 |

### 왜 이 구조인가

**문제:** `pygame.mixer`는 내부적으로 블로킹 동작을 사용한다. asyncio 루프 안에서 직접 호출하면 전체 이벤트 루프가 멈춘다. YOLO 감지가 중단되고, WebSocket 응답이 지연된다.

**해결:** Audio Thread를 분리한다.

```
asyncio loop      Audio Thread
    │                  │
    │  queue.put()     │
    │─────────────────▶│  ← 요청만 전달 (논블로킹)
    │                  │
    │  계속 감지 중     │  pygame.mixer.music.play()
    │  (블로킹 없음)    │  (블로킹이어도 괜찮음, 별도 스레드)
```

**LLM 호출:** `asyncio.to_thread()`를 사용하면 LLM API 대기 시간 동안 스레드 풀에서 처리되고, asyncio 루프는 다른 작업(YOLO, WebSocket)을 계속 처리한다.

---

## 3. 오디오 매니저 설계

### 설계 원칙

- 단계별 모드가 겹치지 않으므로 **우선순위 큐 불필요**
- `threading.Lock()` 하나로 충분
- 긴급 상황(Stage 3 초음파) 전용 `interrupt` 플래그

```python
import threading
import queue
import pygame

class AudioManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        pygame.mixer.init()

    def play(self, filepath: str, interrupt: bool = False):
        """
        오디오 재생 요청.
        interrupt=True: 현재 재생 중단 후 즉시 재생 (Stage 3 긴급 전용)
        """
        self._queue.put((filepath, interrupt))

    def _worker(self):
        """Audio Thread 메인 루프."""
        while True:
            filepath, interrupt = self._queue.get()

            if interrupt:
                with self._lock:
                    pygame.mixer.music.stop()
                    self._play_file(filepath)
            else:
                acquired = self._lock.acquire(timeout=0.1)
                if not acquired:
                    continue  # 이미 재생 중이면 스킵 (모드가 안 겹치므로 드문 케이스)
                try:
                    self._play_file(filepath)
                finally:
                    self._lock.release()

    def _play_file(self, filepath: str):
        """실제 pygame 재생."""
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
```

---

## 4. TTS 캐시 설계

### 세션 라이프사이클

```
데모 시작 (대시보드 [새 세션] 버튼)
    │
    ▼
start_session()          → session_id 생성, 캐시 디렉토리 준비
    │
    ▼
오디오 요청 발생
    │
    ├── 캐시 HIT  → 기존 파일 재생 (즉시)
    └── 캐시 MISS → TTS API 호출 → 파일 저장 → 재생
    │
    ▼
대시보드 [세션 종료] 버튼 클릭
    │
    ▼
WebSocket {"event": "new_session"} → end_session() → 캐시 전체 삭제
```

```python
import hashlib
import shutil
from pathlib import Path

class TTSCache:
    def __init__(self, cache_root: str = "./tts_cache"):
        self._cache_root = Path(cache_root)
        self._session_dir: Path | None = None
        self._index: dict[str, Path] = {}

    def start_session(self, session_id: str):
        """새 데모 세션 시작."""
        self._session_dir = self._cache_root / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._index = {}

    def end_session(self):
        """세션 종료 시 캐시 전체 삭제. 대시보드 버튼으로 호출."""
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir)
        self._index = {}
        self._session_dir = None

    def get(self, text: str) -> Path | None:
        """캐시 HIT 시 파일 경로 반환, MISS 시 None."""
        key = self._hash(text)
        return self._index.get(key)

    def put(self, text: str, filepath: Path):
        """TTS 생성 후 캐시에 등록."""
        key = self._hash(text)
        self._index[key] = filepath

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()
```

---

## 5. LLM 비블로킹 패턴

### v1 문제: 블로킹 호출

```python
# ❌ v1: asyncio 루프가 LLM 응답 대기 중 멈춤
async def detection_loop():
    while True:
        objects = yolo.detect(frame)
        if objects:
            response = llm_client.chat(objects)  # 2~5초 동안 전체 멈춤
```

### v2 해결: asyncio.to_thread() + create_task()

```python
import asyncio

# ✅ v2: LLM 호출을 스레드 풀로 위임
async def call_llm_async(prompt: str) -> str:
    return await asyncio.to_thread(_llm_sync_call, prompt)

async def detection_loop():
    while True:
        objects = yolo.detect(frame)
        if objects:
            asyncio.create_task(handle_detection(objects))  # 백그라운드 실행
        await asyncio.sleep(0.033)  # 30fps 제한

async def handle_detection(objects):
    response = await call_llm_async(build_prompt(objects))  # 스레드 풀
    filepath = tts_cache.get_or_create(response)
    audio_manager.play(filepath)
```

**핵심:**
- `asyncio.to_thread()` = 동기 함수를 ThreadPoolExecutor에서 실행
- `asyncio.create_task()` = 태스크를 백그라운드 등록, 루프는 즉시 다음으로
- LLM 응답 대기 중에도 YOLO 감지 + WebSocket 정상 동작

---

## 6. 3단계별 동작 차이

| 기능 | Stage 1 (수용) | Stage 2 (방향정위) | Stage 3 (기술 교육) |
|------|:--------------:|:-----------------:|:------------------:|
| YOLO 감지 루프 | 비활성 | 활성 | 활성 |
| LLM 공간 묘사 | 비활성 | 활성 | 활성 |
| 초음파 긴급 알림 | 비활성 | 비활성 | **활성** |
| 양방향 대화 (STT) | 활성 | 제한적 | 활성 |
| TTS 캐시 | 활성 | 활성 | 활성 |

### Stage 1 — 수용 단계
AI 친구 시아와 대화. YOLO/초음파 비활성.

### Stage 2 — 방향정위 단계
카메라 환경 인식 + LLM 공간 묘사. 초음파 비활성.

### Stage 3 — 기술 교육 단계
YOLO + 초음파 긴급 + 양방향 대화 전부 활성.

```python
# danger.py에서 stage 체크
def judge(enriched_data, current_stage: int):
    if current_stage != 3:
        return None  # Stage 3이 아니면 위험 판단 비활성
    # ... 기존 로직
```

---

## 7. v1 대비 변경 요약

| 항목 | v1 | v2 | 이유 |
|---|---|---|---|
| 오디오 재생 | asyncio 내 직접 호출 | 별도 Audio Thread + Lock | pygame 블로킹 해결 |
| LLM 호출 | 동기 블로킹 | asyncio.to_thread() | 감지 루프 중단 방지 |
| TTS 파일 | 임시파일 누적 | 세션 기반 캐시 + 대시보드 삭제 | 디스크 관리 + 속도 |
| 긴급 알림 | 항상 활성 | Stage 3 전용 | 모드별 분리 |
| Detection loop | FPS 제한 없음 | 30fps 제한 | CPU 보호 |
| config.py | 검증 없음 | fail-fast 검증 | 디버깅 절약 |

---

_— 아키텍처 v2 문서 끝 —_
