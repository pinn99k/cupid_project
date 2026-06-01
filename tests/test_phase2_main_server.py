"""
Phase 2 테스트: main_server AppState, ack broadcast, stt_text 핸들러
실행: python tests/test_phase2_main_server.py
하드웨어 불필요 - mock 사용.
"""

import sys
import os
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


def test_app_state_dataclass():
    """P2: AppState 데이터클래스 테스트."""
    print("=" * 50)
    print("Phase 2a: AppState 데이터클래스")
    print("=" * 50)

    from server.main_server import AppState

    # Case 1: 기본값
    state = AppState()
    assert state.current_stage == 1
    assert state.learning_active is False
    assert state.session_id == ""
    print("[PASS] Case 1: AppState 기본값 정상")

    # Case 2: to_dict
    d = state.to_dict()
    assert d == {"current_stage": 1, "learning_active": False, "session_id": "", "question_count": 0}
    print(f"[PASS] Case 2: to_dict → {d}")

    # Case 3: 커스텀 값
    state2 = AppState(current_stage=3, learning_active=True, session_id="s1")
    assert state2.to_dict() == {"current_stage": 3, "learning_active": True, "session_id": "s1", "question_count": 0}
    print("[PASS] Case 3: 커스텀 AppState 정상")

    print()


def test_get_state():
    """get_state() 함수 테스트."""
    print("=" * 50)
    print("Phase 2b: get_state() 함수")
    print("=" * 50)

    from server.main_server import get_state, app_state

    app_state.current_stage = 2
    app_state.learning_active = True
    app_state.session_id = "test_session"

    result = get_state()
    assert result["stage"] == 2
    assert result["learning_active"] is True
    assert result["session_id"] == "test_session"
    print(f"[PASS] Case 1: get_state → {result}")

    # 리셋
    app_state.current_stage = 1
    app_state.learning_active = False
    app_state.session_id = ""
    print()


def test_ack_broadcast_start_learning():
    """P1: start_learning ack broadcast 테스트."""
    print("=" * 50)
    print("Phase 2c: ack broadcast - start_learning")
    print("=" * 50)

    from server.main_server import handle_dashboard_message, app_state

    app_state.current_stage = 1
    app_state.learning_active = False

    broadcast_calls = []

    async def mock_broadcast(data):
        broadcast_calls.append(data)

    async def _run():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast):
            await handle_dashboard_message({"event": "start_learning", "stage": 2})

    asyncio.run(_run())

    assert app_state.current_stage == 2, f"stage={app_state.current_stage}"
    assert app_state.learning_active is True
    assert len(broadcast_calls) == 1, f"broadcast 호출 횟수: {len(broadcast_calls)}"
    ack = broadcast_calls[0]
    assert ack["type"] == "ack"
    assert ack["event"] == "start_learning"
    assert ack["stage"] == 2
    print(f"[PASS] Case 1: ack broadcast → {ack}")

    # 리셋
    app_state.current_stage = 1
    app_state.learning_active = False
    print()


def test_ack_broadcast_stop_learning():
    """P1: stop_learning ack broadcast 테스트."""
    print("=" * 50)
    print("Phase 2d: ack broadcast - stop_learning")
    print("=" * 50)

    from server.main_server import handle_dashboard_message, app_state

    app_state.learning_active = True

    broadcast_calls = []

    async def mock_broadcast(data):
        broadcast_calls.append(data)

    async def _run():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast):
            await handle_dashboard_message({"event": "stop_learning"})

    asyncio.run(_run())

    assert app_state.learning_active is False
    assert len(broadcast_calls) == 1
    ack = broadcast_calls[0]
    assert ack["type"] == "ack"
    assert ack["event"] == "stop_learning"
    print(f"[PASS] Case 1: ack broadcast → {ack}")

    app_state.current_stage = 1
    print()


def test_stt_empty_text_ignored():
    """P0: 빈 STT 텍스트 무시."""
    print("=" * 50)
    print("Phase 2e: 빈 STT 텍스트 무시")
    print("=" * 50)

    from server.main_server import handle_dashboard_message

    broadcast_calls = []

    async def mock_broadcast(data):
        broadcast_calls.append(data)

    # Case 1: 빈 문자열
    async def _run_empty():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast):
            await handle_dashboard_message({"stt_text": ""})

    asyncio.run(_run_empty())
    assert len(broadcast_calls) == 0, "빈 텍스트 → broadcast 없어야 함"
    print("[PASS] Case 1: 빈 stt_text → 무시")

    # Case 2: 공백만
    async def _run_whitespace():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast):
            await handle_dashboard_message({"stt_text": "   "})

    asyncio.run(_run_whitespace())
    assert len(broadcast_calls) == 0, "공백 텍스트 → broadcast 없어야 함"
    print("[PASS] Case 2: 공백 stt_text → 무시")

    # Case 3: None
    async def _run_none():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast):
            await handle_dashboard_message({"stt_text": None})

    asyncio.run(_run_none())
    assert len(broadcast_calls) == 0, "None 텍스트 → broadcast 없어야 함"
    print("[PASS] Case 3: None stt_text → 무시")

    print()


def test_stt_text_is_ignored_by_dashboard_handler():
    """음성 대화는 VoicePipeline이 담당하므로 대시보드 stt_text는 무시."""
    print("=" * 50)
    print("Phase 2f: dashboard stt_text → 무시")
    print("=" * 50)

    from server.main_server import handle_dashboard_message, app_state
    app_state.current_stage = 2

    broadcast_calls = []

    async def mock_broadcast(data):
        broadcast_calls.append(data)

    mock_call_async = AsyncMock(return_value="안녕! 시아가 도와줄게.")
    mock_tts = MagicMock()
    mock_tts.get_or_create = AsyncMock(return_value="/tmp/test.mp3")
    mock_audio = MagicMock()

    async def _run():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast), \
             patch.dict("sys.modules", {
                 "ai_core": MagicMock(),
                 "ai_core.llm_client": MagicMock(
                     call_async=mock_call_async,
                     SYSTEM_PROMPT="test_prompt",
                 ),
                 "ai_core.tts": MagicMock(get_tts_cache=MagicMock(return_value=mock_tts)),
                 "ai_core.audio_manager": MagicMock(get_audio_manager=MagicMock(return_value=mock_audio)),
             }):
            await handle_dashboard_message({"stt_text": "안녕하세요"})

    asyncio.run(_run())

    mock_call_async.assert_not_called()
    mock_tts.get_or_create.assert_not_called()
    mock_audio.play_path.assert_not_called()
    assert broadcast_calls == []
    print("[PASS] Case 1: VoicePipeline 외부의 stt_text는 처리하지 않음")

    app_state.current_stage = 1
    print()


def test_health_uses_app_state():
    """Health 엔드포인트가 AppState 사용하는지 테스트."""
    print("=" * 50)
    print("Phase 2g: health → AppState")
    print("=" * 50)

    from server.main_server import health, app_state

    app_state.current_stage = 5
    app_state.learning_active = True

    result = asyncio.run(health())
    assert result["stage"] == 5, f"stage={result['stage']}"
    assert result["learning_active"] is True
    print(f"[PASS] Case 1: health → {json.dumps(result)}")

    # 리셋
    app_state.current_stage = 1
    app_state.learning_active = False
    print()


def test_new_session_error_handling():
    """P1: new_session ai_core 실패 시 크래시 안 함."""
    print("=" * 50)
    print("Phase 2h: new_session 에러 핸들링")
    print("=" * 50)

    from server.main_server import handle_dashboard_message

    broadcast_calls = []

    async def mock_broadcast(data):
        broadcast_calls.append(data)

    async def _run():
        with patch("server.main_server.broadcast", side_effect=mock_broadcast), \
             patch.dict("sys.modules", {
                 "ai_core": MagicMock(),
                 "ai_core.tts": MagicMock(
                     get_tts_cache=MagicMock(side_effect=RuntimeError("TTS 모듈 로드 실패"))
                 ),
             }):
            await handle_dashboard_message({"event": "new_session"})

    asyncio.run(_run())

    # 크래시 없이 ack broadcast 전송
    assert len(broadcast_calls) == 1
    ack = broadcast_calls[0]
    assert ack["type"] == "ack"
    assert ack["event"] == "new_session"
    print(f"[PASS] Case 1: ai_core 에러 → 크래시 없이 ack 전송: {ack}")

    print()


if __name__ == "__main__":
    test_app_state_dataclass()
    test_get_state()
    test_ack_broadcast_start_learning()
    test_ack_broadcast_stop_learning()
    test_stt_empty_text_ignored()
    test_stt_text_is_ignored_by_dashboard_handler()
    test_health_uses_app_state()
    test_new_session_error_handling()
    print(f"[결과] Phase 2 PASS - AppState/ack/stt/health/에러핸들링 모두 통과")
