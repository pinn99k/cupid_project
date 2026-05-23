# Phase 2: Dashboard 최적화 & AI 통합

## 개요
**목표**: AI 부분 미구현 상태에서 대시보드가 AI와 완벽하게 상호작용할 수 있도록 최적화

**제약**: 
- AI 모듈 (ai_core/) 건드리지 않음
- 서버-대시보드 간 인터페이스 정의 및 검증에 집중
- Mock AI 활용한 통합 테스트

---

## Phase 2-A: WebSocket 통신 프로토콜 최적화

### 1. 메시지 스키마 정의 (docs/protocol.md)
```
서버 → 대시보드:
  voice_listening       // STT 대기 중
  voice_processing      // STT 처리 중
  user_stt              // STT 결과 수신
  stt_response          // LLM 응답
  tts_start             // TTS 재생 시작
  tts_done              // TTS 재생 완료
  narration             // 공간 묘사
  danger                // 위험 감지
  error                 // 에러 발생

대시보드 → 서버:
  start_learning        // 학습 시작 (stage 포함)
  stop_learning         // 학습 중지
  new_session           // 새 세션 시작
  clear_tts_cache       // TTS 캐시 삭제
  fallback              // Fallback 오디오 재생
```

### 2. 타입 검증 추가
- server/websocket_handler.py: 수신 메시지 검증
- docs/json_schema.json: JSON Schema 정의

### 3. 에러 복원력
- [ ] WebSocket 재연결 (지수 백오프)
- [ ] 메시지 큐잉 (오프라인 대응)
- [ ] 타임아웃 처리

---

## Phase 2-B: Dashboard UI/UX 개선

### 1. 상태 관리 (useWebSocket 개선)
```javascript
// 추가 상태
- connectionStatus: 'connected' | 'disconnecting' | 'disconnected'
- messageQueue: Message[]
- lastPing: timestamp
- reconnectAttempts: number
```

### 2. Stage별 UI 분기
**Stage 1**: 대화 인터페이스
- 텍스트 입력 + 음성 입력
- 대화 히스토리 표시

**Stage 2**: 학습 대기
- "학습 준비 중" 메시지
- 학습 시작 버튼

**Stage 3**: 위험 감지
- 실시간 MJPEG 피드
- 감지 객체 표시
- 위험 수준 시각화

### 3. 실시간 로그 표시
- 턴 단계별 로그 (voice_listening → tts_done)
- 타임스탐프 + 레이턴시 표시
- 색상 구분 (STT=파랑, LLM=초록, TTS=주황)

---

## Phase 2-C: 통합 테스트 (Mock AI 기반)

### 1. Mock Server Setup
```python
# tests/conftest.py
@pytest.fixture
def mock_ai_loop():
    # AI 루프 시뮬레이션
    # YOLO 감지 → 위험 판단 → LLM 묘사 모킹
    pass
```

### 2. 테스트 케이스
- [ ] **TC-001**: WebSocket 연결 → 초기 상태 수신
- [ ] **TC-002**: Stage 1 → 2 → 3 전환
- [ ] **TC-003**: 한 턴 완전 실행 (voice_listening → tts_done)
- [ ] **TC-004**: WebSocket 끊김 → 자동 재연결
- [ ] **TC-005**: 대시보드 오프라인 → 메시지 큐잉
- [ ] **TC-006**: 에러 발생 → 복구

### 3. e2e 테스트 (Playwright)
```bash
# dashboard/tests/e2e
- connection.spec.ts
- stage_transition.spec.ts
- message_flow.spec.ts
```

---

## Phase 2-D: API Contract 검증

### 1. AI Mock 인터페이스
```python
# ai_core/mock.py (테스트용)
class MockVision:
    async def detect(frame): 
        return {"objects": [...], "danger": None}

class MockLLM:
    async def call_async(prompt, text):
        return "흠... 흥미로운 장면이군요."

class MockTTS:
    async def get_or_create(text):
        return "/mock/tts.mp3"
```

### 2. Contract 테스트
- ai_core 인터페이스 정의
- Mock과 실제 구현 간 호환성 검증
- 느슨한 결합 + 강한 계약

---

## 작업 순서

### Week 1: 프로토콜 정의 & 검증
1. docs/protocol.md 작성
2. JSON Schema 정의
3. server/websocket_handler.py 타입 검증 추가
4. docs/interface_contract.md 업데이트

### Week 2: Dashboard 개선
1. useWebSocket.js 재연결 + 큐잉 로직
2. DashboardPage.jsx Stage별 UI 분기
3. 실시간 로그 컴포넌트
4. 에러 UI 추가

### Week 3: 통합 테스트
1. conftest.py + Mock AI 
2. test_integration_e2e.py (18개 TC)
3. Playwright e2e 테스트
4. 성능 테스트 (latency 측정)

---

## 검증 기준

### ✓ 성공 조건
- [ ] 모든 테스트 통과 (16/16)
- [ ] e2e 테스트 통과 (5/5)
- [ ] 평균 레이턴시 < 200ms
- [ ] 재연결 성공률 > 99%

### 🎯 목표 메트릭
- 초기 연결: < 500ms
- 한 턴: < 3초 (STT + LLM + TTS)
- 메시지 처리: < 50ms

---

## 주의사항
- **AI 구현 금지**: ai_core/ 수정 금지, Mock만 사용
- **Backward Compatibility**: 기존 인터페이스 유지
- **Documentation**: 변경 사항마다 문서 업데이트
