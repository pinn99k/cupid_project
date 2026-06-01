"""
Unit 2: 호출어 게이팅 통합 테스트 (헤드리스).
- 비호출 발화 → user_stt/LLM 모두 스킵 (대시보드에도 안 뜸)
- "시아야 ○○" → 호출어 제거된 질문으로 진행 + LLM 호출
오디오 매니저는 mock 주입(pygame 미사용).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def make_pipeline():
    from server.voice_pipeline import VoicePipeline

    def _make(stt_text):
        mic = MagicMock()
        mic.listen = AsyncMock(return_value=b"wav")
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value=stt_text)
        am = MagicMock()
        am.wait_until_idle = AsyncMock()
        am.wait = AsyncMock(return_value=True)
        am.play = MagicMock(return_value=MagicMock())
        am.play_path = MagicMock(return_value=MagicMock())
        return VoicePipeline(mic=mic, stt=stt, tts_lock=asyncio.Lock(), audio_manager=am)

    return _make


def _types(mock_bc):
    return [c[0][0]["type"] for c in mock_bc.call_args_list]


@pytest.mark.asyncio
@patch("server.voice_pipeline.broadcast", new_callable=AsyncMock)
async def test_non_wake_ignored(mock_bc, make_pipeline):
    """호출어 없는 발화 → user_stt/stt_response 없음 (무시)."""
    vp = make_pipeline("안녕하세요 오늘 날씨 좋다")
    await vp._run_one_turn()
    types = _types(mock_bc)
    assert "user_stt" not in types
    assert "stt_response" not in types  # LLM까지 안 감


@pytest.mark.asyncio
@patch("server.voice_pipeline.broadcast", new_callable=AsyncMock)
async def test_wake_only_no_question_ignored(mock_bc, make_pipeline):
    """'시아야'만 (질문 없음) → 무시."""
    vp = make_pipeline("시아야")
    await vp._run_one_turn()
    assert "user_stt" not in _types(mock_bc)


@pytest.mark.asyncio
@patch("ai_core.llm_client.call_async", new_callable=AsyncMock, return_value="응, 반가워!")
@patch("server.voice_pipeline.broadcast", new_callable=AsyncMock)
async def test_wake_triggers_with_query(mock_bc, mock_llm, make_pipeline):
    """'시아야 뭐해' → 호출어 제거된 '뭐해'로 진행 + LLM 호출."""
    vp = make_pipeline("시아야 뭐해")
    await vp._run_one_turn()
    types = _types(mock_bc)
    assert "user_stt" in types
    user_msgs = [
        c[0][0]["message"] for c in mock_bc.call_args_list
        if c[0][0]["type"] == "user_stt"
    ]
    assert user_msgs == ["뭐해"]          # 호출어 제거 확인
    mock_llm.assert_awaited()             # LLM 호출됨
    # LLM에 전달된 user_msg도 호출어 제거된 질문
    assert mock_llm.await_args[0][1] == "뭐해"
