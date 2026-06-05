# AI ↔ 풀스택 협업 분담 (2단계 데모 로직 변경)

> 목적: 같은 레포에서 **AI와 사람(풀스택)이 충돌 없이 병렬 작업**하도록 소유권·계약·할일을 고정한다.
> 작업 단위: "수용/방향 2단계 데모" 로직 변경 (위험단계 시연 제외).
> 이 문서를 AI 세션에 그대로 붙여 작업을 맡길 수 있다.

---

## 1. 소유권 경계 (레인 — 서로의 레인 파일은 수정 금지)

| 레인 | 폴더/파일 | 역할 |
|------|-----------|------|
| 🤖 **AI** | `main.py`, `server/`, `ai_core/`, `tests/`, `firmware/`, `tools/`, `docs/` | Python 백엔드 · 펌웨어 · 테스트 · 문서. 서버 로직/상태/이벤트 처리. |
| 🧑 **풀스택(나)** | `dashboard/` (React 전체) + 디자인 산출물 | 프론트엔드 UI · 라우팅 · 디자인. 모바일 부모웹 디자인(`docs/parent_web_design_prompt.md`)도 사람 레인. |

**규칙**
- 상대 레인 파일은 **읽기만**. 수정은 소유자만.
- 공유 접점은 아래 **WebSocket 계약**뿐. 계약을 바꿔야 하면 먼저 합의 → 이 문서/`docs/interface_contract.md` 갱신 후 양쪽 동시 반영.
- 각자 자기 레인은 **자기 테스트로 검증**(AI=pytest, 사람=브라우저 수동/필요시 프론트 테스트).

---

## 2. WebSocket 계약 (양쪽이 반드시 지킴)

**대시보드 → 서버**
| 이벤트 | 의미 | 서버 동작(불변식) |
|--------|------|-------------------|
| `{event:"new_session"}` | 깨끗한 재시작 | stage=1, learning off, scene clear, voice reset, TTS 새 세션 |
| `{event:"start_learning", stage:1}` | 수용단계 진입 | 캠만. **voice 인식 OFF** |
| `{event:"start_learning", stage:2}` | 방향단계 진입 | YOLO 실시간 + **voice ON**("시아야" 응답) |
| `{event:"start_learning", stage:3}` | (사용 안 함) | 대시보드가 **보내지 않음**(버튼 비활성). 서버 코드는 보존 |
| `{event:"stop_learning"}` | 정지 | reset_session |
| `{event:"fallback", audio_file}` | 수동 TTS 재생 | 스테이지 무관, 즉시 재생 |
| `{stt_text:"..."}` | 음성 인식 텍스트 | narrate/VQA |

**서버 → 대시보드**: `init_state`/`ack`, `detections_update{objects[].bbox}`, `narration`/`stt_response`/`user_stt`/`error`, `tts_start`/`tts_done`, `voice_listening`/`voice_processing`, `danger`(stage3 전용 — 현재 미사용).

> 핵심 불변식: **stage 1 = 음성 OFF / stage 2 = 음성 ON**은 **서버가 강제**한다(프론트가 실수로 보내도 서버가 보정).

---

## 3. 이번 작업 분담 (확정된 계획)

### 🤖 AI 레인
- **변경 2 — 수용단계 음성 OFF**: `server/main_server.py` `handle_dashboard_message`의 `start_learning`
  - `stage>=2` → `_voice_pipeline.start()`, `stage==1` → `_voice_pipeline.stop_listening()`
  - 단위테스트: stage=1→stop_listening / stage=2→start 호출(가짜 pipeline)
- 검증: pytest 통과 + 회귀 없음.

### 🧑 풀스택 레인
- **변경 1 — 시작하기 → 깨끗한 재시작**: `dashboard/src/App.jsx`
  - `onStart` = `() => { send({event:'new_session'}); setStage(1); setPage('dashboard'); }`
- **변경 3 — 위험단계 버튼 비활성**: `dashboard/src/components/ControlBar.jsx`
  - stage 3 버튼은 렌더하되 `onClick` 무동작(`n !== 3 && onStageChange(n)`), 흐리게 표시(옵션)
- (이후) 모바일 부모웹 디자인: `docs/parent_web_design_prompt.md` 기준.

### 이미 동작 — 둘 다 손대지 않음(검증만)
- 수용(1) YOLO 미실행 + 캠 스트림 ✓ (`_ai_loop`)
- 방향(2) YOLO 실시간 + scene 저장 → "시아야" VQA ✓

---

## 4. 통합 검증 시나리오 (양쪽 합류 후 수동)
1. 새로고침 → StartPage → **시작하기** → 서버 stage=1·새 세션 ack
2. 수용단계: 캠만 실시간, **"시아야" 무반응**, 폴백 TTS 버튼은 재생됨
3. 운영자가 **방향단계로 전환** → YOLO 박스 표시 + **"시아야" 질문 → 응답**
4. **위험단계 버튼 클릭 → 무반응**

---

## 5. 현재 상태 (작업 시작 시점)
- 브랜치 `main`. 초음파 폴링(#1)·신규 테스트는 **AI 레인에서 완료·푸시됨**(게이팅이라 시연 영향 0).
- ⚠️ 기존 회귀: `tests/test_phase2_main.py` 5개 깨짐(팀원 `_open_camera` 리네임) — 팀원 트랙에서 수리 중.
