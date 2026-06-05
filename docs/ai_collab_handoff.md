# AI ↔ 풀스택 협업 가이드 (기능별 브랜치 + PR)

> 목적: 같은 레포에서 **여러 사람(풀스택·AI·팀원)이 백엔드/프론트를 동시에** 만져도 충돌이 격리되도록 워크플로우를 고정한다.
> 결정: **폴더 소유권 잠금 아님.** 누구나 어떤 파일이든 고칠 수 있고, **충돌은 "기능별 브랜치 + PR"로 격리**한다.

---

## 1. 협업 모델 — 기능별 브랜치 + PR

깃엔 파일 주인이 없다. 충돌은 **같은 줄을 동시에** 고칠 때만 난다. 그래서 각자 **자기 브랜치**에서 작업하고 **PR로 합친다.**

### 흐름
```bash
# 1) 항상 최신 main에서 분기
git checkout main && git pull --rebase origin main
git checkout -b feat/fe-start-reset

# 2) 작게 자주 커밋
git add <files> && git commit -m "..."

# 3) 브랜치 푸시 → 출력에 뜨는 "Create a pull request" 링크 클릭
git push -u origin feat/fe-start-reset
#   (gh CLI 미설치 → 웹 링크로 PR 생성. 저장소 PR 탭에서도 가능)

# 4) PR 리뷰 → squash 머지 → 브랜치 삭제 → 모두 main 당기기
git checkout main && git pull --rebase origin main
```

### 브랜치 네이밍
| 접두 | 용도 | 예 |
|------|------|----|
| `feat/be-*` | 백엔드 기능 | `feat/be-stage-voice` |
| `feat/fe-*` | 프론트 기능 | `feat/fe-start-reset` |
| `design/*` | 디자인 | `design/mobile-parent-web` |
| `fix/*` · `test/*` · `docs/*` | 버그·테스트·문서 | `fix/be-ws-timeout` |

### 꼬임 방지 규칙 (이게 전부)
- **작게, 자주 PR.** 브랜치를 며칠 묵히면 main과 벌어져 충돌↑.
- **분기 전 `git pull --rebase`**, 머지 후 모두 즉시 main 당기기.
- 같은 함수를 굳이 둘이 동시에 고쳐야 하면 한마디로 조율(브랜치로도 그건 충돌).
- 생성물·비밀파일 커밋 금지(`.theia/`, `sia_secrets.h`, `tools/demo_*` 등).

### 폴더 가이드 (느슨 — 잠금 아님, "주로 누가" 참고용)
| 주로 | 폴더 |
|------|------|
| 🧑 풀스택 | `dashboard/`(React·디자인) + 백엔드도 필요 시 |
| 🤖 AI | `server/`·`main.py`·`ai_core/`·`tests/`·`firmware/`·`docs/` |
> 백엔드는 둘 다 만질 수 있다. **브랜치로 격리**하면 누가 어디를 고치든 안전.

---

## 2. WebSocket 계약 (브랜치 무관 — 통합 접점, 함부로 못 바꿈)

**대시보드 → 서버**
| 이벤트 | 의미 | 서버 불변식 |
|--------|------|-------------|
| `{event:"new_session"}` | 깨끗한 재시작 | stage=1, learning off, scene clear, voice reset, TTS 새 세션 |
| `{event:"start_learning", stage:1}` | 수용단계 | 캠만. **voice 인식 OFF** |
| `{event:"start_learning", stage:2}` | 방향단계 | YOLO 실시간 + **voice ON**("시아야") |
| `{event:"start_learning", stage:3}` | (미사용) | 대시보드가 **안 보냄**(버튼 비활성). 서버 코드 보존 |
| `{event:"stop_learning"}` | 정지 | reset_session |
| `{event:"fallback", audio_file}` | 수동 TTS | 스테이지 무관 즉시 재생 |
| `{stt_text:"..."}` | 음성 텍스트 | narrate/VQA |

**서버 → 대시보드**: `init_state`/`ack`, `detections_update{objects[].bbox}`, `narration`/`stt_response`/`user_stt`/`error`, `tts_start`/`tts_done`, `voice_listening`/`voice_processing`, `danger`(stage3 전용·현재 미사용).

> 계약을 바꿔야 하면 **PR 설명에 명시 + 이 문서/`docs/interface_contract.md` 동시 갱신**.

---

## 3. 이번 작업 분담 (각자 브랜치 → PR)

| 담당 | 변경 | 브랜치 | 상태 |
|------|------|--------|------|
| 🤖 AI | **변경 2** 수용 음성 OFF (`server/main_server.py`) | (이미 main 직푸시됨 — 브랜치 도입 전) | ✅ 완료·머지됨 |
| 🧑 풀스택 | **변경 1** 시작하기→`new_session` (`dashboard/src/App.jsx`) | `feat/fe-start-reset` | ⬜ |
| 🧑 풀스택 | **변경 3** 위험단계 버튼 비활성 (`ControlBar.jsx`) | `feat/fe-hide-stage3` | ⬜ |
| 🧑 풀스택 | 모바일 부모웹 디자인 (`docs/parent_web_design_prompt.md` 기준) | `design/mobile-parent-web` | ⬜ |

### 변경 1·3 구현 메모
- 변경 1: `onStart = () => { send({event:'new_session'}); setStage(1); setPage('dashboard'); }`
- 변경 3: stage 3 버튼은 렌더하되 `onClick`을 `n !== 3 && onStageChange(n)`로(무동작), 흐리게 표시 옵션.

---

## 4. 통합 검증 시나리오 (합류 후 수동)
1. 새로고침 → StartPage → **시작하기** → 서버 stage=1·새 세션 ack
2. 수용단계: 캠만 실시간, **"시아야" 무반응**, 폴백 TTS 버튼은 재생
3. 운영자 **방향단계 전환** → YOLO 박스 + **"시아야" → 응답**
4. **위험단계 버튼 클릭 → 무반응**

---

## 5. 현재 상태
- 브랜치 `main` 최신. 초음파 폴링·단계 음성 게이팅·신규 테스트 머지됨.
- 이 문서부터 **새 작업은 브랜치+PR**로.
- ⚠️ 기존 회귀: `tests/test_phase2_main.py` 5개 깨짐(팀원 `_open_camera` 리네임) — 별도 `fix/*` 브랜치로 수리 권장.
