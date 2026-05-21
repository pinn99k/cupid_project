# SIA 대시보드 개발 가이드

> 작성 기준: 2026-05-20
> 대상: SIA MVP React 대시보드를 개발/유지보수하는 풀스택 개발자

---

## 1. 대시보드 초기화 방법

### 1-1. 개발 환경 요구사항

- Node.js 18 이상
- npm 9 이상
- Vite 5.x
- React 18.x
- Chrome 브라우저 (Web Speech API 사용 필수)

### 1-2. 새 프로젝트로 시작하는 경우

```bash
npm create vite@latest dashboard -- --template react
cd dashboard
npm install
```

### 1-3. 기존 소스 파일 연결

`dashboard/src/` 아래에 다음 디렉토리 구조를 그대로 유지해야 한다.

```
dashboard/
  src/
    App.jsx
    main.jsx
    hooks/
      useWebSocket.js
      useSpeechRecognition.js
    components/
      SessionControl.jsx
      FallbackPanel.jsx
```

기존 소스를 받은 경우 `npm install` 후 바로 실행 가능하다.

```bash
npm install
npm run dev
```

기본 개발 서버는 `http://localhost:5173` 에서 실행된다.

### 1-4. 백엔드 서버 동시 실행

대시보드는 `ws://localhost:8000/ws` 에 WebSocket 연결을 시도한다.
React 개발 서버와 별도로 FastAPI 서버를 먼저 실행해야 한다.

```bash
# 프로젝트 루트에서 실행
uvicorn server.main_server:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. 현재 소스 파일 구조

### 2-1. App.jsx - 메인 앱 컴포넌트

**역할**: 전체 레이아웃 조립, WebSocket/STT 훅 초기화, 실시간 메시지 로그 렌더링

**사용 훅**:
- `useWebSocket(WS_URL)` - WebSocket 연결 및 메시지 관리
- `useSpeechRecognition(ws)` - 브라우저 음성 인식

**주요 상태/반환값**:
- `ws` - WebSocket 인스턴스 (useSpeechRecognition에 전달)
- `messages` - 서버에서 수신한 메시지 배열 (최근 50개)
- `connected` - 서버 연결 여부 (boolean)
- `send(data)` - 서버로 메시지를 보내는 함수

**렌더링 구성**:
1. 연결 상태 표시 (초록/빨강)
2. `<SessionControl>` - 세션/스테이지 관리 버튼
3. STT 시작/중지 버튼
4. `<FallbackPanel>` - 수동 오디오 재생 버튼
5. 실시간 메시지 로그 (스크롤 영역)

---

### 2-2. components/SessionControl.jsx

**역할**: 학습 세션 및 Stage 전환 제어

**Props**:
- `send` (function) - `useWebSocket`에서 받은 send 함수

**버튼 목록 및 전송 이벤트**:

| 버튼 | 전송 데이터 |
|------|-------------|
| 새 세션 (캐시 초기화) | `{ event: "new_session" }` |
| Stage 1 | `{ event: "start_learning", stage: 1 }` |
| Stage 2 | `{ event: "start_learning", stage: 2 }` |
| Stage 3 | `{ event: "start_learning", stage: 3 }` |
| 정지 | `{ event: "stop_learning" }` |

---

### 2-3. components/FallbackPanel.jsx

**역할**: 갈라쇼/긴급 상황에서 수동으로 오디오 파일을 재생하는 패널

**Props**:
- `send` (function) - `useWebSocket`에서 받은 send 함수

**버튼 목록**:

| 버튼 라벨 | 전송 audio_file |
|-----------|-----------------|
| 멈춰! | `warn_emergency.mp3` |
| 앞에 뭔가 | `warn_obstacle.mp3` |
| 잘하고 있어 | `praise_01.mp3` |
| 잠깐만 | `buffer_01.mp3` |
| 시작 | `gala_01.mp3` |
| 끝 | `gala_03.mp3` |

클릭 시 `{ event: "fallback", audio_file: "<파일명>" }` 형태로 전송한다.

---

### 2-4. hooks/useWebSocket.js

**역할**: WebSocket 연결 생명주기 관리, 메시지 수신/전송 추상화

**파라미터**:
- `url` (string) - WebSocket 서버 주소 (예: `"ws://localhost:8000/ws"`)

**반환값**:
- `ws` - 현재 WebSocket 인스턴스 (ref.current)
- `messages` - 수신 메시지 배열 (최근 50개, JSON 파싱된 객체)
- `connected` - 연결 상태 (boolean)
- `send(data)` - JSON 직렬화 후 전송하는 함수. 연결 상태가 OPEN일 때만 전송

**동작 방식**:
- `useEffect`에서 컴포넌트 마운트 시 WebSocket 연결
- 컴포넌트 언마운트 시 `ws.close()` 자동 호출
- 수신 메시지는 JSON 파싱 후 상태 배열에 추가 (최대 50개 유지)

---

### 2-5. hooks/useSpeechRecognition.js

**역할**: 브라우저 Web Speech API로 한국어 음성을 인식하고 서버에 전송

**파라미터**:
- `ws` - WebSocket 인스턴스 (`useWebSocket`의 `ws` 반환값)
- `enabled` (boolean, 기본값 true) - true이면 인식 종료 후 자동 재시작

**반환값**:
- `start()` - 음성 인식 시작
- `stop()` - 음성 인식 중지

**동작 방식**:
- `webkitSpeechRecognition` 사용 (Chrome 전용)
- 언어: `ko-KR`
- `continuous: true`, `interimResults: false` (최종 결과만 사용)
- 인식 완료 시 `{ stt_text: "<텍스트>" }` 형태로 WebSocket 전송
- `enabled`가 true이면 `onend` 이벤트 발생 시 자동으로 재시작

---

## 3. WebSocket 연결 방식

### 3-1. 연결 주소

```
ws://localhost:8000/ws
```

FastAPI 서버의 `/ws` 엔드포인트에 연결한다.
여러 클라이언트가 동시에 연결할 수 있으며, 서버는 모든 연결된 클라이언트에 broadcast 방식으로 메시지를 보낸다.

### 3-2. 메시지 포맷

모든 메시지는 JSON 문자열로 주고받는다.

**대시보드 -> 서버**:
```json
{ "event": "이벤트명", "필드1": "값1", ... }
```
또는 STT 텍스트:
```json
{ "stt_text": "인식된 텍스트" }
```

**서버 -> 대시보드**:
```json
{ "type": "메시지타입", "message": "내용", ... }
```

---

## 4. 서버에서 보내는 메시지 타입

서버는 `broadcast()` 함수를 통해 모든 연결된 대시보드 클라이언트에 메시지를 전송한다.

### 4-1. danger - 위험 감지 알림

장애물 감지 또는 위험 상황 발생 시 전송된다.

```json
{
  "type": "danger",
  "message": "위험 상황 설명 텍스트",
  "stage": 2,
  "timestamp": 1716123456789
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"danger"` 고정 |
| `message` | string | 위험 내용 또는 TTS로 출력된 내용 |
| `stage` | number | 현재 학습 Stage (1, 2, 3) |
| `timestamp` | number | Unix 밀리초 타임스탬프 |

현재 App.jsx에서 `danger` 타입은 빨간색으로 표시된다.

---

### 4-2. narration - 일반 내레이션

학습 중 AI가 생성한 내레이션 텍스트 전송 시 사용된다.

```json
{
  "type": "narration",
  "message": "내레이션 텍스트",
  "stage": 1,
  "timestamp": 1716123456789
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"narration"` 고정 |
| `message` | string | AI가 생성한 내레이션 텍스트 |
| `stage` | number | 현재 학습 Stage |
| `timestamp` | number | Unix 밀리초 타임스탬프 |

---

### 4-3. stt_response - STT 응답

대시보드에서 `stt_text`를 보냈을 때 LLM이 응답을 생성하면 전송된다.

```json
{
  "type": "stt_response",
  "message": "LLM 응답 텍스트",
  "stage": 1,
  "timestamp": 1716123456789
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"stt_response"` 고정 |
| `message` | string | LLM이 생성한 응답 텍스트 |
| `stage` | number | 응답 생성 시점의 현재 Stage |
| `timestamp` | number | Unix 밀리초 타임스탬프 |

---

## 5. 대시보드에서 보내는 이벤트

### 5-1. start_learning - 학습 시작

```json
{ "event": "start_learning", "stage": 1 }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `"start_learning"` 고정 |
| `stage` | number | 시작할 Stage 번호 (1, 2, 3) |

서버 측 동작: `learning_active = True`, `current_stage = stage`

---

### 5-2. stop_learning - 학습 정지

```json
{ "event": "stop_learning" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `"stop_learning"` 고정 |

서버 측 동작: `learning_active = False`

---

### 5-3. new_session - 새 세션 시작

```json
{ "event": "new_session" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `"new_session"` 고정 |

서버 측 동작: 현재 TTS 캐시 세션을 종료하고 새 세션 ID(`session_<timestamp>`)로 재시작

---

### 5-4. clear_tts_cache - TTS 캐시 수동 삭제

```json
{ "event": "clear_tts_cache" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `"clear_tts_cache"` 고정 |

서버 측 동작: TTS 캐시 세션 종료 (새 세션 시작 없음)
현재 SessionControl.jsx에는 버튼이 없으므로 필요 시 추가 가능

---

### 5-5. fallback - 수동 오디오 재생

```json
{ "event": "fallback", "audio_file": "warn_emergency.mp3" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `event` | string | `"fallback"` 고정 |
| `audio_file` | string | 재생할 mp3 파일명 (서버 오디오 디렉토리 기준) |

서버 측 동작: `audio_manager.play(audio_file)` 호출로 하드웨어 스피커에서 즉시 재생
지원 파일: `warn_emergency.mp3`, `warn_obstacle.mp3`, `praise_01.mp3`, `buffer_01.mp3`, `gala_01.mp3`, `gala_03.mp3`

---

### 5-6. stt_text - 음성 인식 텍스트 전송

`event` 키가 없고 `stt_text` 키로 전송한다.

```json
{ "stt_text": "앞에 뭔가 있어요" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `stt_text` | string | Web Speech API로 인식된 최종 텍스트 |

서버 측 동작: `narrate_async()` 호출 -> TTS 생성 -> 오디오 재생 -> `stt_response` 타입으로 broadcast

---

## 6. UI 개선 방향 제안

현재 대시보드는 기능 중심으로 최소 구현된 상태다. 아래는 실제 현장 사용성을 높이기 위한 개선 방향이다.

### 6-1. Stage 표시

현재 서버 응답 메시지에 `stage` 필드가 포함되어 있지만 대시보드에 별도 표시가 없다.

- 상단 헤더에 현재 Stage를 크게 표시 (예: `Stage 2 - 학습 중`)
- `start_learning` 이벤트 전송 시 로컬 state에도 현재 stage를 저장
- 서버 `/health` 엔드포인트 (`GET http://localhost:8000/health`)를 폴링해서 실제 서버 state와 동기화

```javascript
// /health 응답 예시
{ "status": "ok", "stage": 2, "learning_active": true }
```

---

### 6-2. 위험 경고 시각화

`type === "danger"` 메시지 수신 시 전체 화면 또는 배너 형태의 경고 표시를 추가한다.

- 빨간 배경 오버레이 또는 플래시 효과
- 소리 알림 (브라우저 Audio API)
- 경고 메시지를 별도 패널에 따로 집계

---

### 6-3. 메시지 타입별 색상

현재는 `danger`만 빨간색이다. 타입별로 구분하면 로그 가독성이 올라간다.

| type | 색상 제안 |
|------|-----------|
| `danger` | 빨강 `#e53e3e` |
| `narration` | 파랑 `#3182ce` |
| `stt_response` | 초록 `#38a169` |
| 기타 | 기본 텍스트 |

---

### 6-4. 자동 재연결

현재 `useWebSocket.js`는 연결이 끊어지면 재연결을 시도하지 않는다.
현장에서 네트워크 불안정이나 서버 재시작이 발생할 수 있으므로 자동 재연결 로직을 추가하는 것이 좋다.

```javascript
// 구현 아이디어 - useWebSocket.js 내부
ws.onclose = () => {
  setConnected(false);
  setTimeout(() => reconnect(), 3000); // 3초 후 재연결 시도
};
```

재연결 시도 횟수를 제한하고 UI에 재연결 중 상태를 표시하는 것이 권장된다.

---

### 6-5. 반응형 레이아웃

현재 `maxWidth: 800`의 고정 폭 레이아웃이다.
현장에서 태블릿이나 작은 모니터를 사용할 경우를 고려해 아래를 추가한다.

- CSS Media Query 또는 Tailwind CSS 기반 반응형 그리드
- FallbackPanel 버튼을 터치 영역 기준으로 크게 조정 (최소 44x44px)
- 실시간 메시지 로그 영역 높이를 화면 비율 기반으로 조정 (`calc(100vh - 400px)` 등)

---

## 7. 개발 환경 정리

| 항목 | 버전/값 |
|------|---------|
| Node.js | 18 이상 |
| 빌드 도구 | Vite 5.x |
| UI 프레임워크 | React 18.x |
| 음성 인식 | Web Speech API (Chrome 전용, `webkitSpeechRecognition`) |
| WebSocket 주소 | `ws://localhost:8000/ws` |
| 백엔드 | FastAPI (Python 3.11+) |
| 백엔드 포트 | 8000 |
| 개발 서버 포트 | 5173 (Vite 기본값) |

### 7-1. 주의사항

- Web Speech API는 **Chrome 브라우저에서만 동작**한다. Firefox, Safari 미지원.
- HTTPS 환경에서는 마이크 권한 허용이 필요하다. 로컬 개발 환경(`localhost`)은 예외적으로 HTTP에서도 동작한다.
- FastAPI 서버의 CORS 설정이 `allow_origins=["*"]`로 되어 있어 개발 환경에서는 별도 프록시 설정이 불필요하다.
- WebSocket URL은 `App.jsx` 상단의 `WS_URL` 상수에서 관리한다. 배포 환경에서는 이 값을 환경변수로 관리하는 것을 권장한다.

### 7-2. 빠른 시작 체크리스트

- [ ] Node.js 18 이상 설치 확인
- [ ] `npm install` 완료
- [ ] FastAPI 서버 실행 (`uvicorn server.main_server:app --reload --port 8000`)
- [ ] `npm run dev` 실행
- [ ] Chrome에서 `http://localhost:5173` 접속
- [ ] 대시보드 상단 "서버 연결됨" 초록색 표시 확인
- [ ] Stage 1 버튼 클릭 후 실시간 로그 메시지 수신 확인
