# 공유자원 맵 & 락 audit (Unit 1)

> 목적: 비동기 태스크(프레임 루프 / AI 루프 / 음성 파이프라인 / 대시보드 핸들러)와
> 오디오 스레드가 **무엇을 공유하고 어떤 락으로 보호되는지** 명문화.
> Phase 3(게이팅·VQA·온디맨드) 배선 전 동시성 사고 방지판.

## 실행 단위 (동시 실행 주체)
| 주체 | 종류 | 역할 |
|------|------|------|
| `_frame_loop` | asyncio task | 웹캠/CAM → `set_frame` |
| `_ai_loop` | asyncio task | YOLO → enrich → danger / (예정)`set_scene` |
| `VoicePipeline.run` | asyncio task | STT→LLM→TTS 턴 루프 |
| `handle_dashboard_message` | asyncio (WS) | 대시보드 이벤트 → `app_state` 변경 |
| `AudioManager._worker` | **OS 스레드** | 오디오 직렬 재생 |
| `_generate_mjpeg` | asyncio (요청) | 프레임 JPEG 인코딩 |

## 공유자원 표
| 자원 | 위치 | 보호 | 쓰기 | 읽기 | 비고 |
|------|------|------|------|------|------|
| `_latest_frame` | main_server | `_frame_lock`(threading) | `set_frame`(frame loop) | `get_frame`(ai loop), `_encode_frame`(mjpeg) | copy로 격리, OK |
| `_latest_scene` *(Unit 3 예정)* | main_server | `_scene_lock`(threading) | `set_scene`(ai loop) | `get_scene`(voice via scene_provider) | enriched dict, copy 반환 |
| `_latest_ultrasonic` *(HW 후)* | main_server | `_us_lock`(threading) | 폴러 task | ai loop / judge | (cm, ts) |
| `app_state.current_stage` | main_server | **없음** | 대시보드 핸들러 | ai loop, voice | int 읽기 → GIL 원자적. **단순 스칼라만 공유 유지** |
| `app_state.learning_active` | main_server | 없음 | 핸들러 | ai loop | bool, 동상 |
| `app_state.question_count` *(예정)* | main_server | 없음(단일 writer 권장) | voice task만 증가 | get_state | **writer 1개로 한정** |
| `_tts_lock` | main.py | `asyncio.Lock` | — | voice `_speak`/`_play_fallback`, ai_loop narration·danger | **오디오 직렬화 핵심** |
| AudioManager `_queue` | audio_manager | `PriorityQueue`(자체 스레드안전) | 모든 play 호출 | `_worker` | OK |
| AudioManager `_current` | audio_manager | `_state_lock`(threading) | `_worker`, `stop` | `is_playing` | OK |
| `_chat_history` | VoicePipeline | **없음 불필요** | voice task만 | voice task만 | 단일 태스크 소유 → 공유 아님 |
| `_voice_pipeline`, `_cancel_narration` | main_server | 없음 | startup 1회 | reset_session | 시작 시 1회 설정 |

## 규칙 (Phase 3에서 지킬 것)
1. **프레임·장면·초음파는 "최신 1개 슬롯 + 락 + copy 반환"** 패턴 통일 (`_latest_frame`과 동형).
2. **`app_state`는 단순 스칼라만 공유**. 복합 객체 공유 금지(락 필요해짐).
3. **`question_count`는 voice task만 증가**(단일 writer) → 락 불필요.
4. **오디오 재생은 항상 `_tts_lock` 안에서** (voice/narration/danger 경합 차단). danger는 `interrupt=True`로 선점.
5. **블로킹 호출(YOLO/STT/오디오 대기)은 `asyncio.to_thread`** 로 감싸 이벤트 루프 보호.
6. `scene_provider()`는 **YOLO 재실행 금지** — `_ai_loop`이 채운 `_latest_scene`만 읽음(중복 추론·race 방지).

## 알려진 비공유 (안심)
- `_chat_history`, `_consecutive_fails` → VoicePipeline 단일 태스크 소유
- enriched/dets 지역변수 → 루프 지역
