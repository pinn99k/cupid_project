# 통합 테스트 체크리스트

## Current Test Status (Phase 0)

### ✓ 구현된 테스트
1. **test_integration.py** (9개)
   - [x] TestTurnSerialization: 턴 직렬성 검증
   - [x] TestTTSLockContention: TTS Lock 경합 검증
   - [x] TestSessionReset: 세션 리셋 검증
   - [x] TestChatHistoryContext: 대화 히스토리 검증
   - [x] TestDashboardIndependence: 대시보드 독립성
   - [x] TestModuleImports: 모듈 import 검증
   - [x] TestConfigIntegration: Config 통합 검증
   - [x] TestErrorPathTtsDone: 에러 경로 검증
   - [x] TestDashboardHandlerCleanup: 핸들러 cleanup

2. **test_main_server.py** (14개)
   - [x] TestAppState: AppState 기본 동작
   - [x] TestGetState: get_state() 함수
   - [x] TestMjpegFrame: MJPEG 프레임 관리 (8개)
   - [x] TestResetSession: 세션 리셋 (2개)
   - [x] TestHandleDashboardMessage: 대시보드 메시지 (8개)
   - [x] TestHealthEndpoint: 헬스 체크 (1개)

3. **test_voice_pipeline.py** 추가 예정
4. **test_mic.py** 추가 예정
5. **test_stt.py** 추가 예정

---

## Phase 2 테스트 계획

### 2-1. WebSocket 프로토콜 검증

**TC-101**: 초기 연결 및 상태 수신
```python
@pytest.mark.asyncio
async def test_websocket_initial_state():
    """WebSocket 연결 시 초기 AppState 전송"""
    # 예상: {"stage": 1, "learning_active": false, ...}
```

**TC-102**: 메시지 순서 검증
```python
@pytest.mark.asyncio
async def test_message_order_in_full_turn():
    """한 턴: voice_listening → user_stt → stt_response → tts_done"""
```

**TC-103**: 잘못된 메시지 거부
```python
@pytest.mark.asyncio
async def test_invalid_message_rejected():
    """unknown event는 무시"""
```

### 2-2. Stage 전환 검증

**TC-201**: Stage 1 → 2 → 3
```python
@pytest.mark.asyncio
async def test_stage_transitions():
    """start_learning(2) → stop_learning → start_learning(3)"""
```

**TC-202**: 각 Stage의 동작
```python
@pytest.mark.asyncio
async def test_stage_behaviors():
    """Stage 1: 대화만, Stage 3: 위험 감지"""
```

### 2-3. 에러 복원력

**TC-301**: WebSocket 재연결
```python
@pytest.mark.asyncio
async def test_websocket_reconnection():
    """연결 끊김 → 자동 재연결 (지수 백오프)"""
```

**TC-302**: 메시지 큐잉
```python
@pytest.mark.asyncio
async def test_message_queuing_offline():
    """오프라인 상태 → 메시지 큐잉 → 재연결 시 전송"""
```

**TC-303**: 타임아웃 처리
```python
@pytest.mark.asyncio
async def test_timeout_handling():
    """5초 이상 응답 없음 → 재연결"""
```

### 2-4. 대시보드 UI 통합

**TC-401**: 상태 렌더링
```javascript
describe('Dashboard Stage UI', () => {
  test('Stage 1 shows chat interface');
  test('Stage 2 shows learning wait');
  test('Stage 3 shows danger alerts');
});
```

**TC-402**: 실시간 로그
```javascript
describe('Real-time Logs', () => {
  test('Turn logs displayed with timestamps');
  test('Color coding by event type');
});
```

### 2-5. 성능 테스트

**TC-501**: 레이턴시 측정
```python
@pytest.mark.benchmark
async def test_latency_metrics():
    """
    초기 연결: < 500ms
    한 턴: < 3000ms
    메시지 처리: < 50ms
    """
```

**TC-502**: 부하 테스트
```python
@pytest.mark.asyncio
async def test_concurrent_messages():
    """동시 메시지 100개 처리"""
```

---

## Mock AI 인터페이스

### MockVision
```python
class MockVision:
    async def detect(self, frame):
        return {
            "objects": ["person", "cup"],
            "detections": [...]
        }
    
    def enrich(self, dets, w, h):
        return {
            "objects": ["person", "cup"],
            "count": 2
        }

def mock_judge(enriched, stage):
    if stage == 3:
        return {
            "object": "knife",
            "direction": "front",
            "distance_cm": 30,
            "audio_file": "danger_knife.mp3"
        }
    return None
```

### MockLLM
```python
async def mock_call_async(prompt, text):
    responses = {
        "안녕": "안녕! 반가워요!",
        "뭐해": "지금 공부 중이야.",
    }
    return responses.get(text, "흠... 재미있는 말이군!")
```

### MockTTS
```python
class MockTTSCache:
    async def get_or_create(self, text):
        return "/mock/tts_cache/output.mp3"
    
    def start_session(self, sid):
        pass
    
    def end_session(self):
        pass
```

---

## 테스트 실행 명령

### 개별 테스트
```bash
# 특정 테스트만 실행
pytest tests/test_integration.py::TestTurnSerialization::test_broadcast_order_in_full_turn -v

# 특정 마크만 실행
pytest -m "asyncio" -v

# 성능 테스트
pytest -m "benchmark" -v
```

### 전체 통합 테스트
```bash
# 모든 테스트 (mock 포함)
pytest tests/ -v --cov=. --cov-report=html

# e2e 테스트 (Playwright)
cd dashboard && npm test

# 성능 + 커버리지
pytest tests/ -v --benchmark --cov
```

---

## 예상 결과

### Pass 기준
- 모든 테스트: 통과
- 코드 커버리지: > 80%
- 평균 레이턴시: < 200ms
- 에러율: < 1%

### 실패 시 액션
- 에러 메시지 분석
- 로그 검토
- 재현 스크립트 작성
- Root cause 분석 및 수정
