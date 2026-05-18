# SIA 인터페이스 계약서 (Interface Contract)

> 버전: v2.0  
> 작성일: 2026-05-18  
> 상태: 합의 대기 중  
> Phase 1 시작 전에 팀 전체가 이 포맷에 합의해야 한다.

---

## 1. YOLO 후처리 → LLM 입력 (ai_core 내부)

`ai_core/vision.py`의 `enrich()` → `ai_core/narration.py`의 `narrate_async()`에 전달.

```json
{
  "objects": [
    {
      "label": "person",
      "direction": "left",
      "distance_est": "near",
      "bbox_ratio": 0.31,
      "confidence": 0.92
    },
    {
      "label": "chair",
      "direction": "center",
      "distance_est": "mid",
      "bbox_ratio": 0.12,
      "confidence": 0.87
    }
  ],
  "ultrasonic_cm": 45,
  "ultrasonic_target": "chair"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `label` | string | YOLO 인식 객체명 (COCO 80종) |
| `direction` | `"left"` \| `"center"` \| `"right"` | bbox x좌표 기반 방향 (33%/66% 기준) |
| `distance_est` | `"near"` \| `"mid"` \| `"far"` | bbox 면적비 기반 거리 (20%/5% 기준) |
| `bbox_ratio` | float (0~1) | 화면 점유율 |
| `confidence` | float (0~1) | YOLO 인식 신뢰도 |
| `ultrasonic_cm` | float \| null | HC-SR04P 정면 거리 (Phase 1에서는 null) |
| `ultrasonic_target` | string \| null | 초음파와 매칭된 정면 객체 |

---

## 2. 서버 → 대시보드 (WebSocket push)

`server/websocket_handler.py`의 `broadcast()` → React 대시보드.

### 위험 감지

```json
{
  "type": "danger",
  "object": "stairs",
  "direction": "center",
  "distance_cm": 45,
  "message": "멈춰, 앞에 계단이야",
  "stage": 3,
  "audio_file": "warn_stairs.mp3",
  "timestamp": 1715000000000
}
```

### 공간 묘사

```json
{
  "type": "narration",
  "objects": [
    {"label": "person", "direction": "left", "distance_est": "near"},
    {"label": "chair", "direction": "center", "distance_est": "mid"}
  ],
  "message": "왼쪽 가까이에 사람이 있어. 정면에 의자가 보여.",
  "stage": 2,
  "timestamp": 1715000000000
}
```

### STT 응답

```json
{
  "type": "stt_response",
  "message": "앞에는 아무것도 없어, 안전해!",
  "stage": 1,
  "timestamp": 1715000000000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | `"danger"` \| `"narration"` \| `"fallback"` \| `"stt_response"` | 메시지 종류 |
| `message` | string | 시아가 말하는 내용 |
| `stage` | int (1\|2\|3) | 현재 학습 단계 |
| `timestamp` | int (epoch ms) | 지연 측정용 |

---

## 3. 대시보드 → 서버 (WebSocket / HTTP POST)

### 학습 제어

```json
{ "event": "start_learning", "stage": 1 }
{ "event": "stop_learning" }
```

### Fallback 수동 재생

```json
{ "event": "fallback", "audio_file": "fallback_01.mp3" }
```

### 세션 관리 (v2 신규)

```json
{ "event": "new_session" }
```
새 세션 시작. 서버에서 TTS 캐시 초기화 + 새 세션 ID 생성.

```json
{ "event": "clear_tts_cache" }
```
TTS 캐시만 수동 삭제. 세션은 유지.

### STT 텍스트

```json
{ "stt_text": "앞에 뭐 있어?" }
```

---

## 합의 서명

팀원 전원이 이 문서를 읽고 동의해야 Phase 1 진행 가능.

| 역할 | 이름 | 서명 날짜 |
|------|------|----------|
| AI 코어 (경민) | | |
| 서버 + 대시보드 (민구) | | |
| 펌웨어 (은민) | | |

---

_— 인터페이스 계약서 끝 —_
