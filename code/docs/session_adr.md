# SIA MVP v2 — 세션 아키텍처 결정 기록 (ADR)

## 개요
- **프로젝트**: SIA (시각장애 아동 보행 보조 AI)
- **역할**: 프로젝트 오너 / 아키텍트
- **기간**: 2026-05-23
- **방식**: 소크라테스식 코드 리뷰 + 구조 설계 지시

---

## ADR-001: 메시지 타입 분류 아키텍처

### 문제 발견
초기 구현에서 WebSocket 메시지를 타입 구분 없이 모두 같은 배열에 저장.
실시간 대화 패널에 `voice_listening`, `tts_start` 같은 상태 메시지까지 표시되어
"시아 오전 11:58:22" 같은 무의미한 항목이 화면에 수십 개 반복됨.

### 소크라테스식 분석
> "ChatPanel에서 init_state만 필터링하는데, voice_listening이나 tts_done 같은 상태 메시지는 왜 표시되지?"

원인 추적 결과, 메시지 타입별 역할이 정의되지 않았음. 모든 WebSocket 메시지가 단일 `messages[]` 배열에 무차별 저장되고 있었음.

### 결정
메시지를 3계층으로 분류:
- **대화 메시지**: `user_stt`, `stt_response`, `narration`, `error` → `messages[]`에 저장, UI 표시
- **상태 메시지**: `voice_listening`, `voice_processing`, `tts_start`, `tts_done` → `voiceState`로 관리, UI 미표시
- **감지 메시지**: `narration`, `danger` → `latestObjects`로 관리

### 영향
- **`useWebSocket.js`**: 메시지 분류 저장 로직 전면 재설계. `messages`, `voiceState`, `latestDanger`, `latestObjects`를 별도 상태로 분리. 타입별 조건 분기로 각각의 setter에 라우팅.
- **`ChatPanel.jsx`**: 필터링 로직 단순화. `messages` prop에 이미 대화 메시지만 들어오므로 별도 필터 불필요.
- **`DashboardPage.jsx`**: `useWs`에서 `messages`, `voiceState`, `latestObjects`를 구조 분해하여 각 컴포넌트에 전달. `STTInput`에 `voiceState`, `DirectionPanel`에 `latestObjects`, `ChatPanel`에 `messages` + `stage`.

---

## ADR-002: Stage별 위험 메시지 필터링

### 문제 발견
`danger` 메시지가 Stage 1(대화) 상태에서도 대화 패널에 표시됨.
위험 감지는 Stage 3 전용 기능인데, 모든 Stage에서 동일하게 처리.
사용자(아이)가 대화 중일 때 불필요한 위험 경고가 끼어들어 혼란 유발.

### 결정
`ChatPanel`에 `stage` prop을 전달하여 `danger` 메시지는 `stage === 3`일 때만 표시.

### 영향
- **`ChatPanel.jsx`**: `stage` prop 추가, `visible` 필터에서 `m.type === 'danger'`일 때 `stage === 3` 조건 적용.
- **`DashboardPage.jsx`**: `<ChatPanel messages={messages} stage={stage} />` 형태로 stage 전달.

---

## ADR-003: LLM 에러 Fallback 체계

### 문제 발견
LLM API (Gemini 무료 티어) 할당량 초과 시 서버 로그에 429 에러만 출력되고,
사용자에게는 아무 피드백 없이 다음 턴으로 넘어감.
시각장애 아동 입장에서는 말을 걸었는데 아무 반응이 없는 상황.

### 결정
에러 발생 시 3단계 fallback:
1. **에러 메시지를 대시보드에 broadcast** (`error` 타입) — 모니터링하는 교사에게 알림
2. **Fallback 오디오 (`buffer_01.mp3`) 재생** — 아이에게 최소한의 피드백 제공
3. **`tts_done` broadcast 보장** — 상태 머신이 "responding" 상태에 갇히지 않도록 복원

### 영향
- **`voice_pipeline.py`**: `_play_fallback()` 메서드 추가. `error` broadcast + `tts_start` → fallback 오디오 재생 → `tts_done` 순서 보장.
- **`main.py`**: `_handle_narration()`과 danger 처리 양쪽에 try-except + fallback 적용. TTS 파일 생성 실패, LLM 응답 없음 등 모든 실패 경로에서 `buffer_01.mp3` fallback 재생.

---

## ADR-004: 연속 실패 쿨다운 (지수 백오프)

### 문제 발견 (소크라테스식 분석)
> "LLM이 계속 실패하면 어떻게 되지?"

추적 결과: `_run_one_turn()`이 fallback 후 정상 return → `while` 루프가 즉시 다음 턴 시작 → API 호출만 계속 쌓여 429 악화.
무료 티어 API의 rate limit을 빠르게 소진시키는 구조적 문제.

### 결정
연속 실패 횟수에 따른 점진적 쿨다운:
| 연속 실패 | 쿨다운 |
|-----------|--------|
| 1회 | 2초 |
| 2회 | 5초 |
| 3회 | 10초 |
| 4회+ | 30초 (최대) |

성공 시 카운터 즉시 리셋.

### 영향
- **`voice_pipeline.py`**: `_consecutive_fails` 카운터, `_cooldown_steps = [2, 5, 10, 30]` 배열, `_cooldown_on_fail()` 메서드 추가. LLM 성공 시 카운터 리셋(`self._consecutive_fails = 0`). `reset()` 시 카운터도 초기화.

---

## ADR-005: TTS 응답 대시보드 표시

### 문제 발견
STT(사용자 입력)만 대시보드에 표시되고, TTS(시아 응답)가 표시되지 않음.
대화 패널이 STT → STT → STT로 일방적이어서 대화 흐름 파악 불가.
교사가 모니터링할 때 시아가 뭐라고 답했는지 알 수 없는 상태.

### 결정
대화 패턴을 STT <-> TTS 교차로 재설계. 메시지 타입별 시각적 구분:

| 타입 | 화자 | 위치 | 스타일 |
|------|------|------|--------|
| `user_stt` | 아이 | 오른쪽 | 보라 배경 (`#EDE7F6`) |
| `stt_response` | 시아 | 왼쪽 | 흰색 배경 + 테두리 |
| `narration` | 시아 (묘사) | 왼쪽 | 연보라 배경 (`#F3E5F5`) |
| `danger` | 시아 (Stage 3) | 왼쪽 | 빨간 배경 (`#FFF0F0`) |
| `error` | 시스템 | 가운데 | 빨간 텍스트 |

### 영향
- **`useWebSocket.js`**: `narration`을 `messages[]`에 추가 저장 (감지 객체와 대화 메시지 이중 저장).
- **`ChatPanel.jsx`**: `MessageRow` 컴포넌트에서 타입별 라벨(`시아`, `시아 (묘사)`), 배경색, 테두리를 조건부 적용.
- **`voice_pipeline.py`**: LLM 응답을 `stt_response` 타입으로 broadcast하여 대시보드에 표시.

---

## ADR-006: AI/서버 계층 분리 원칙

### 결정
> "AI 부분은 못건드니까"

`ai_core/`와 `server/`를 명확히 분리. `server/`는 `ai_core`의 인터페이스만 호출하고, 내부 구현에 의존하지 않는 구조.

### 원칙
- **`server/voice_pipeline.py`**: `call_async()` 호출만 수행. 에러 처리(`try-except` + fallback)는 서버 계층에서 자체적으로 처리.
- **`ai_core/llm_client.py`**: 예외 시 `None` 반환 또는 예외 전파 (내부 처리).
- **`main.py`**: `ai_core`의 `detect`, `judge`, `narrate_async` 등을 호출하되, 모든 실패 경로에 대한 fallback은 `main.py` 내에서 처리.
- **테스트**: `ai_core`를 Mock으로 대체하여 `server/` 독립 테스트 가능한 구조.

---

## 요약: 아키텍처 개선 전후

### Before (초기 구현)
- 모든 WebSocket 메시지가 하나의 배열에 혼재
- 대화 패널에 상태 메시지(`voice_listening`, `tts_start`) 수십 개 반복 표시
- LLM 에러 시 무한 재시도 (쿨다운 없음, API rate limit 즉시 소진)
- TTS 응답이 대시보드에 미표시 (일방향 대화 로그)
- Stage 구분 없이 `danger` 메시지 표시

### After (리뷰 후)
- 메시지 3계층 분류 (대화 / 상태 / 감지) — `useWebSocket.js` 전면 재설계
- Stage별 조건부 표시 — `ChatPanel`에 `stage` prop 전달
- 에러 fallback 3단계 + 지수 백오프 쿨다운 체계 — `voice_pipeline.py`
- STT <-> TTS 교차 대화 패턴 + 타입별 시각적 구분 — `ChatPanel.jsx`
- AI/서버 계층 분리 원칙 확립 — `ai_core/`는 인터페이스만 노출
