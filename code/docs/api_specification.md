# SIA MVP - API 명세서 (API Specification)

> 버전: v1.1
> 작성일: 2026-05-21
> 대상: 프론트엔드(React 대시보드) <-> 백엔드(FastAPI) 통신 규격
> 기반 소스: server/main_server.py, server/websocket_handler.py, main.py

---

## 목차

1. REST API 목록
2. WebSocket 프로토콜
3. 상태 관리
4. 에러 처리 규격
5. 시퀀스 다이어그램

---

## 1. REST API 목록

**Base URL:** `http://localhost:8000`

---

### 1.1 GET /health

서버 생존 확인 및 기본 상태 조회. 현재 구현됨.

**요청**

```
GET /health
```

요청 바디 없음.

**응답 (200 OK)**

```json
{
  "status": "ok",
  "stage": 1,
  "learning_active": false
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | 항상 `"ok"` (서버 정상) |
| `stage` | int (1\|2\|3) | 현재 학습 단계 |
| `learning_active` | bool | 학습 모드 활성화 여부 |

---

### 1.2 GET /api/status (제안)

현재 서버 상태를 상세하게 조회한다. `/health`보다 많은 정보를 반환.

**요청**

```
GET /api/status
```

요청 바디 없음.

**응답 (200 OK)**

```json
{
  "stage": 2,
  "learning_active": true,
  "connected_clients": 1,
  "session_id": "session_1716200000",
  "uptime_sec": 3721
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `stage` | int (1\|2\|3) | 현재 학습 단계 |
| `learning_active` | bool | 학습 모드 활성화 여부 |
| `connected_clients` | int | 현재 WebSocket 연결 수 |
| `session_id` | string | 현재 TTS 세션 ID |
| `uptime_sec` | int | 서버 가동 시간 (초) |

---

### 1.3 GET /api/latency (제안)

최근 감지 파이프라인 지연 측정값을 반환한다. 대시보드의 성능 모니터링에 사용.

**요청**

```
GET /api/latency
```

요청 바디 없음.

**응답 (200 OK)**

```json
{
  "detect_ms": 42,
  "narration_ms": 1230,
  "tts_ms": 310,
  "total_ms": 1582,
  "measured_at": 1716200000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `detect_ms` | int | YOLO 감지 소요 시간 (ms) |
| `narration_ms` | int | LLM 내레이션 생성 소요 시간 (ms) |
| `tts_ms` | int | TTS 변환 소요 시간 (ms, 캐시 히트 시 0에 가까움) |
| `total_ms` | int | detect_start - danger_detected 전체 소요 시간 (ms) |
| `measured_at` | int | 측정 시각 (epoch ms) |

---

### 1.4 POST /api/stage (제안)

HTTP를 통해 Stage를 직접 변경한다. WebSocket 연결 없이도 Stage 전환 가능.

**요청**

```
POST /api/stage
Content-Type: application/json
```

```json
{
  "stage": 2
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `stage` | int (1\|2\|3) | 필수 | 변경할 Stage 번호 |

**응답 (200 OK)**

```json
{
  "success": true,
  "stage": 2,
  "previous_stage": 1
}
```

**응답 (400 Bad Request)**

```json
{
  "success": false,
  "error": "invalid_stage",
  "message": "stage는 1, 2, 3 중 하나여야 합니다."
}
```

---

### 1.5 POST /api/fallback (제안)

HTTP를 통해 Fallback 오디오를 즉시 재생한다.

**요청**

```
POST /api/fallback
Content-Type: application/json
```

```json
{
  "audio_file": "buffer_01.mp3"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `audio_file` | string | 선택 (기본값: `"buffer_01.mp3"`) | 재생할 오디오 파일명 |

**응답 (200 OK)**

```json
{
  "success": true,
  "audio_file": "buffer_01.mp3"
}
```

**응답 (404 Not Found)**

```json
{
  "success": false,
  "error": "file_not_found",
  "message": "audio_file 'unknown.mp3'을 찾을 수 없습니다."
}
```

---

## 2. WebSocket 프로토콜

**엔드포인트:** `ws://localhost:8000/ws`

메시지 포맷은 모두 JSON 문자열. `ensure_ascii=False`로 직렬화되므로 한글이 그대로 전송됨.

---

### 2.1 연결/해제 흐름

```
클라이언트                    서버
    |                          |
    |--- WS 연결 요청 -------->|
    |                          |  clients.add(ws) - 내부 등록
    |<--- 연결 수락 (accept) --|
    |                          |
    |--- (메시지 송수신) -------|
    |                          |
    |--- WS 연결 닫기 -------->|
    |                          |  clients.discard(ws) - 내부 해제
    |                          |
```

- 서버는 연결 수락 시 별도의 환영 메시지를 보내지 않는다.
- 클라이언트가 비정상 종료하면 `broadcast()` 에서 전송 실패를 감지하여 자동으로 `clients`에서 제거한다.
- 다수의 클라이언트가 동시에 연결 가능하다 (set 관리).

---

### 2.2 Client -> Server 메시지

대시보드에서 서버로 전송하는 메시지. 모두 JSON 객체.

---

#### 2.2.1 start_learning - 학습 시작

```json
{
  "event": "start_learning",
  "stage": 2
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `event` | string | 필수 | `"start_learning"` 고정 |
| `stage` | int (1\|2\|3) | 선택 (기본값: 1) | 시작할 Stage 번호 |

**서버 동작:**
- `learning_active = True` 설정
- `current_stage` 를 수신한 `stage` 값으로 업데이트
- 별도 응답 없음 (단방향 이벤트)

---

#### 2.2.2 stop_learning - 학습 중지

```json
{
  "event": "stop_learning"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `event` | string | 필수 | `"stop_learning"` 고정 |

**서버 동작:**
- `learning_active = False` 설정
- 별도 응답 없음

---

#### 2.2.3 new_session - 새 세션 시작

```json
{
  "event": "new_session"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `event` | string | 필수 | `"new_session"` 고정 |

**서버 동작:**
- 현재 TTS 세션을 종료 (`tts.end_session()`)
- 새 세션 ID 생성 후 시작 (`session_{epoch_seconds}` 형식)
- TTS 캐시 초기화 포함
- 별도 응답 없음

---

#### 2.2.4 clear_tts_cache - TTS 캐시 수동 삭제

```json
{
  "event": "clear_tts_cache"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `event` | string | 필수 | `"clear_tts_cache"` 고정 |

**서버 동작:**
- TTS 캐시만 삭제 (`tts.end_session()`)
- 세션 ID는 유지됨
- 별도 응답 없음

`new_session` vs `clear_tts_cache` 차이:
- `new_session`: 세션 ID 교체 + 캐시 초기화
- `clear_tts_cache`: 캐시만 초기화, 세션 ID 유지

---

#### 2.2.5 fallback - Fallback 오디오 재생

```json
{
  "event": "fallback",
  "audio_file": "fallback_01.mp3"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `event` | string | 필수 | `"fallback"` 고정 |
| `audio_file` | string | 선택 (기본값: `"buffer_01.mp3"`) | 재생할 오디오 파일명 |

**서버 동작:**
- `audio_manager.play(audio_file)` 호출하여 즉시 재생
- 별도 응답 없음

---

#### 2.2.6 stt_text - STT 텍스트 전달

WebSocket 이벤트 키가 `"event"`가 아닌 `"stt_text"`인 별도 포맷.

```json
{
  "stt_text": "앞에 뭐 있어?"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `stt_text` | string | 필수 | 사용자 음성 인식 결과 텍스트 |

**서버 동작:**
1. LLM `narrate_async()` 호출 (현재 감지 결과 기반 응답 생성)
2. 응답 텍스트를 TTS로 변환 후 오디오 재생
3. `stt_response` 메시지를 broadcast로 전체 클라이언트에 전송

---

### 2.3 Server -> Client 메시지

서버가 `broadcast()`를 통해 모든 연결된 클라이언트에 전송하는 메시지.

---

#### 2.3.1 danger - 위험 감지 경보

Stage 3에서 YOLO + 초음파 센서로 위험 물체를 감지했을 때 전송.

```json
{
  "type": "danger",
  "object": "stairs",
  "direction": "center",
  "distance_cm": 28.5,
  "message": "멈춰, 앞에 계단이야",
  "stage": 3,
  "audio_file": "warn_stairs.mp3",
  "timestamp": 1716200000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | string | `"danger"` 고정 |
| `object` | string | 감지된 위험 객체명 (YOLO 레이블) |
| `direction` | `"left"` \| `"center"` \| `"right"` | 객체 방향 |
| `distance_cm` | float | 초음파 센서 측정 거리 (cm). Phase 1에서는 추정값 |
| `message` | string | 시아가 말하는 위험 알림 텍스트 |
| `stage` | int (1\|2\|3) | 발생 시점 Stage |
| `audio_file` | string | 재생된 오디오 파일명 |
| `timestamp` | int | 이벤트 발생 시각 (epoch ms) |

**대시보드 처리 권장:**
- 빨간색 경고 UI 표시
- `distance_cm`이 `DANGER_DISTANCE_CM` (기본 30cm) 이하면 긴급 강조

---

#### 2.3.2 narration - 공간 묘사

Stage 2/3에서 `learning_active = true`일 때 LLM이 주변 공간을 묘사한 내용.
감지된 객체가 1개 이상일 때만 전송 (5초 간격).

```json
{
  "type": "narration",
  "objects": [
    {
      "label": "person",
      "direction": "left",
      "distance_est": "near"
    },
    {
      "label": "chair",
      "direction": "center",
      "distance_est": "mid"
    }
  ],
  "message": "왼쪽 가까이에 사람이 있어. 정면에 의자가 보여.",
  "stage": 2,
  "timestamp": 1716200000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | string | `"narration"` 고정 |
| `objects` | array | 감지된 객체 목록 (label, direction, distance_est 포함) |
| `objects[].label` | string | YOLO 객체명 |
| `objects[].direction` | string | `"left"` \| `"center"` \| `"right"` |
| `objects[].distance_est` | string | `"near"` \| `"mid"` \| `"far"` |
| `message` | string | LLM 생성 공간 묘사 텍스트 |
| `stage` | int | 발생 시점 Stage |
| `timestamp` | int | 이벤트 발생 시각 (epoch ms) |

---

#### 2.3.3 stt_response - STT 대화 응답

클라이언트의 `stt_text` 메시지에 대한 LLM 응답.

```json
{
  "type": "stt_response",
  "message": "앞에는 아무것도 없어, 안전해!",
  "stage": 1,
  "timestamp": 1716200000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | string | `"stt_response"` 고정 |
| `message` | string | LLM이 생성한 응답 텍스트 |
| `stage` | int | 발생 시점 Stage |
| `timestamp` | int | 이벤트 발생 시각 (epoch ms) |

---

#### 2.3.4 status_update - 상태 변경 알림 (제안)

서버 상태가 변경될 때 (stage 변경, learning on/off) 자동으로 push. 현재 미구현.

```json
{
  "type": "status_update",
  "stage": 2,
  "learning_active": true,
  "timestamp": 1716200000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | string | `"status_update"` 고정 |
| `stage` | int | 변경된 Stage |
| `learning_active` | bool | 학습 모드 활성화 여부 |
| `timestamp` | int | 변경 시각 (epoch ms) |

---

## 3. 상태 관리

### 3.1 current_stage

| 값 | 이름 | 설명 |
|---|---|---|
| `1` | Stage 1: 자유 탐색 | YOLO 비활성. STT 대화만 가능. 카메라 감지 없음. |
| `2` | Stage 2: 학습 모드 | YOLO 활성. `learning_active=true`이면 5초마다 narration 생성. 위험 판단 없음. |
| `3` | Stage 3: 실전 모드 | YOLO 활성. 위험 판단 활성 (`judge()` 호출). `DANGER_DISTANCE_CM` 이하 접근 시 즉시 경보. |

### 3.2 learning_active

| 값 | 의미 |
|---|---|
| `true` | Stage 2/3에서 LLM 내레이션 주기적 생성 활성화 |
| `false` | 내레이션 생성 중지. 위험 감지는 Stage 3이면 계속 동작. |

### 3.3 Stage별 활성 기능 정리

| 기능 | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| YOLO 감지 | 비활성 | 활성 | 활성 |
| narration 생성 | 비활성 | learning_active일 때 | learning_active일 때 |
| 위험 판단 (danger) | 비활성 | 비활성 | 활성 |
| STT 대화 | 활성 | 활성 | 활성 |
| Fallback 재생 | 활성 | 활성 | 활성 |

### 3.4 상태 전환 규칙

- Stage 변경은 WebSocket `start_learning` 이벤트 또는 제안된 `POST /api/stage`로 수행.
- `stop_learning`은 Stage를 변경하지 않고 `learning_active`만 `false`로 설정.
- 서버 재시작 시 `current_stage = 1`, `learning_active = false`로 초기화.

---

## 4. 에러 처리 규격

### 4.1 REST API 에러 응답 포맷

모든 에러 응답은 아래 공통 포맷을 따른다.

```json
{
  "success": false,
  "error": "에러_코드",
  "message": "사람이 읽을 수 있는 한글 설명"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `success` | bool | 항상 `false` |
| `error` | string | 기계가 읽는 에러 코드 (snake_case) |
| `message` | string | 사람이 읽는 에러 설명 (한글) |

### 4.2 HTTP 상태 코드 규칙

| 상태 코드 | 사용 상황 |
|---|---|
| `200 OK` | 정상 처리 |
| `400 Bad Request` | 요청 파라미터 오류 (잘못된 stage 값 등) |
| `404 Not Found` | 리소스 없음 (파일 없음 등) |
| `500 Internal Server Error` | 서버 내부 오류 (LLM 실패, TTS 실패 등) |

### 4.3 주요 에러 코드 목록

| 에러 코드 | 상태 코드 | 설명 |
|---|---|---|
| `invalid_stage` | 400 | stage가 1, 2, 3이 아닌 경우 |
| `file_not_found` | 404 | 요청한 오디오 파일이 없는 경우 |
| `llm_unavailable` | 500 | LLM API 호출 실패 |
| `tts_failed` | 500 | TTS 변환 실패 |
| `camera_error` | 500 | 카메라 장치를 열 수 없는 경우 |

### 4.4 WebSocket 에러 처리

WebSocket은 별도의 에러 메시지 포맷 없이 연결 종료로 에러를 표현.

| 상황 | 동작 |
|---|---|
| 클라이언트 비정상 종료 | `broadcast()` 내부에서 감지 후 `clients`에서 자동 제거 |
| JSON 파싱 오류 | `receive_loop()`에서 예외 발생 - 현재 미처리 (개선 권장) |
| 핸들러 내부 오류 | 현재 예외 전파로 연결 종료될 수 있음 (try/except 추가 권장) |

**WebSocket 에러 메시지 포맷 제안 (현재 미구현):**

```json
{
  "type": "error",
  "error": "parse_error",
  "message": "JSON 파싱에 실패했습니다.",
  "timestamp": 1716200000000
}
```

---

## 5. 시퀀스 다이어그램

### 5.1 Stage 2 학습 흐름

```
대시보드                서버 (main_server)         감지 루프 (main.py)       AI 코어
    |                        |                           |                     |
    |--start_learning------->|                           |                     |
    |  { event, stage:2 }    |                           |                     |
    |                        | current_stage=2           |                     |
    |                        | learning_active=true      |                     |
    |                        |                           |                     |
    |                        |              (5초 주기 루프)                    |
    |                        |                           |--detect(frame)----->|
    |                        |                           |<--enriched---------|
    |                        |                           |                     |
    |                        |                           |--narrate_async()--->|
    |                        |                           |<--text(LLM 응답)----|
    |                        |                           |                     |
    |                        |                           |--tts.get_or_create->|
    |                        |                           |<--filepath(mp3)-----|
    |                        |                           |                     |
    |                        |                           |--audio.play_path()  |
    |                        |                           |                     |
    |                        |<--broadcast(narration)----|                     |
    |<--narration 메시지-----|                           |                     |
    | { type, objects,       |                           |                     |
    |   message, stage,      |                           |                     |
    |   timestamp }          |                           |                     |
    |                        |                           |                     |
    |--stop_learning-------->|                           |                     |
    |                        | learning_active=false     |                     |
```

---

### 5.2 Stage 3 긴급 경보 흐름

```
대시보드                서버 (main_server)         감지 루프 (main.py)       AI 코어
    |                        |                           |                     |
    |--start_learning------->|                           |                     |
    |  { event, stage:3 }    | current_stage=3           |                     |
    |                        |                           |                     |
    |                        |              (매 프레임 루프)                   |
    |                        |                           |--detect(frame)----->|
    |                        |                           |<--enriched----------|
    |                        |                           |                     |
    |                        |                           |--judge(enriched)--->|
    |                        |                           | danger != None      |
    |                        |                           |                     |
    |                        |                           |--audio.play(interrupt=True)
    |                        |                           |                     |
    |                        |<--broadcast(danger)-------|                     |
    |<--danger 메시지--------|                           |                     |
    | { type:"danger",       |                           |                     |
    |   object, direction,   |                           |                     |
    |   distance_cm,         |                           |                     |
    |   message, stage,      |                           |                     |
    |   audio_file,          |                           |                     |
    |   timestamp }          |                           |                     |
    |                        |                           |                     |
    |  [1초 대기 후 루프 재개]|                           |                     |
```

---

### 5.3 STT 대화 흐름

```
대시보드                서버 (main_server)                        AI 코어
    |                        |                                        |
    |--stt_text 메시지------>|                                        |
    | { "stt_text": "..." }  |                                        |
    |                        |                                        |
    |                        |--narrate_async({objects:[], ...})----->|
    |                        |<--text (LLM 응답)----------------------|
    |                        |                                        |
    |                        |--tts.get_or_create(text)-------------->|
    |                        |<--filepath (mp3)---------------------- |
    |                        |                                        |
    |                        |--audio.play_path(filepath)             |
    |                        |  (실제 스피커 재생)                    |
    |                        |                                        |
    |                        |--broadcast(stt_response)               |
    |<--stt_response 메시지--|                                        |
    | { type:"stt_response", |                                        |
    |   message,             |                                        |
    |   stage,               |                                        |
    |   timestamp }          |                                        |
    |                        |                                        |
```

---

## 부록: 메시지 타입 요약표

### Client -> Server 이벤트

| 이벤트 / 키 | 설명 | 주요 파라미터 |
|---|---|---|
| `start_learning` | 학습 시작 | `stage` (1\|2\|3) |
| `stop_learning` | 학습 중지 | 없음 |
| `new_session` | 새 TTS 세션 시작 | 없음 |
| `clear_tts_cache` | TTS 캐시 삭제 | 없음 |
| `fallback` | Fallback 오디오 재생 | `audio_file` |
| `stt_text` | STT 텍스트 전달 | `stt_text` (string) |

### Server -> Client 메시지

| type | 설명 | 발생 조건 |
|---|---|---|
| `danger` | 위험 감지 경보 | Stage 3, judge() 양성, 즉시 |
| `narration` | 공간 묘사 | Stage 2/3, learning_active, 5초마다 |
| `stt_response` | STT 대화 응답 | stt_text 수신 후 LLM 처리 완료 |
| `status_update` | 상태 변경 알림 | (제안) Stage/learning 변경 시 |
| `error` | WebSocket 에러 | (제안) 처리 실패 시 |

---

_API 명세서 끝 - v1.0_
