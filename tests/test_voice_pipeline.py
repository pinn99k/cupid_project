"""
VoicePipeline 단위 테스트.
모든 외부 의존성(mic, stt, llm, tts, audio, broadcast)은 Mock으로 대체.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.voice_pipeline import VoicePipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mic():
    mic = MagicMock()
    mic.listen = AsyncMock(return_value=b"fake_wav_data")
    return mic


@pytest.fixture
def mock_stt():
    stt = MagicMock()
    stt.transcribe = AsyncMock(return_value="안녕하세요")
    return stt


@pytest.fixture
def tts_lock():
    return asyncio.Lock()


@pytest.fixture
def pipeline(mock_mic, mock_stt, tts_lock):
    return VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)


# ---------------------------------------------------------------------------
# TestVoicePipelineInit
# ---------------------------------------------------------------------------

class TestVoicePipelineInit:
    def test_init_stores_dependencies(self, mock_mic, mock_stt, tts_lock):
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        assert vp._mic is mock_mic
        assert vp._stt is mock_stt
        assert vp._tts_lock is tts_lock

    def test_init_empty_history(self, mock_mic, mock_stt, tts_lock):
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        assert vp.chat_history == []

    def test_init_not_running(self, mock_mic, mock_stt, tts_lock):
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        assert vp.is_running is False


# ---------------------------------------------------------------------------
# TestBuildContext
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_no_history_returns_base(self, pipeline):
        base = "기본 프롬프트"
        result = pipeline._build_context(base)
        assert result == base

    def test_with_history_appends(self, pipeline):
        pipeline._chat_history = [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "반가워요"},
        ]
        base = "기본 프롬프트"
        result = pipeline._build_context(base)
        assert base in result
        assert "[이전 대화]" in result
        assert "안녕" in result
        assert "반가워요" in result

    def test_history_format(self, pipeline):
        pipeline._chat_history = [
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "답변"},
        ]
        result = pipeline._build_context("프롬프트")
        assert "아이: 질문" in result
        assert "시아: 답변" in result


# ---------------------------------------------------------------------------
# TestChatHistory
# ---------------------------------------------------------------------------

class TestChatHistory:
    def test_reset_clears_history(self, pipeline):
        pipeline._chat_history = [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "반가워요"},
        ]
        pipeline.reset()
        assert pipeline.chat_history == []

    def test_history_max_limit(self, pipeline):
        # _max_history = 8, set 10 items manually
        pipeline._chat_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(10)
        ]
        # Simulate the trimming logic from _run_one_turn
        if len(pipeline._chat_history) > pipeline._max_history:
            pipeline._chat_history = pipeline._chat_history[-pipeline._max_history:]

        assert len(pipeline._chat_history) == 8
        # Oldest messages (index 0, 1) should be removed; last 8 remain
        assert pipeline._chat_history[0]["content"] == "msg2"
        assert pipeline._chat_history[-1]["content"] == "msg9"

    def test_chat_history_property_is_copy(self, pipeline):
        pipeline._chat_history = [{"role": "user", "content": "test"}]
        history = pipeline.chat_history
        history.append({"role": "user", "content": "extra"})
        # Original should be unchanged
        assert len(pipeline._chat_history) == 1


# ---------------------------------------------------------------------------
# TestStop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_sets_running_false(self, pipeline):
        pipeline._running = True
        pipeline.stop()
        assert pipeline.is_running is False


# ---------------------------------------------------------------------------
# TestRunOneTurn
# ---------------------------------------------------------------------------

BROADCAST_PATH = "server.voice_pipeline.broadcast"


class TestRunOneTurn:
    @pytest.mark.asyncio
    async def test_full_turn_flow(self, mock_mic, mock_stt, tts_lock):
        """전체 턴 흐름: listen → STT → LLM → TTS. broadcast 순서 검증."""
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)

        broadcast_calls = []

        async def capture_broadcast(msg):
            broadcast_calls.append(msg["type"])

        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value="/tmp/fake.mp3")

        with patch(BROADCAST_PATH, side_effect=capture_broadcast), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value="LLM 응답")), \
             patch("ai_core.llm_client.SYSTEM_PROMPT", "테스트 프롬프트"), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        assert "voice_listening" in broadcast_calls
        assert "voice_processing" in broadcast_calls
        assert "user_stt" in broadcast_calls
        assert "stt_response" in broadcast_calls
        assert "tts_start" in broadcast_calls
        assert "tts_done" in broadcast_calls

        # 순서 검증
        idx = {t: broadcast_calls.index(t) for t in
               ["voice_listening", "voice_processing", "user_stt", "stt_response", "tts_start", "tts_done"]}
        assert idx["voice_listening"] < idx["voice_processing"]
        assert idx["voice_processing"] < idx["user_stt"]
        assert idx["user_stt"] < idx["stt_response"]
        assert idx["stt_response"] < idx["tts_start"]
        assert idx["tts_start"] < idx["tts_done"]

    @pytest.mark.asyncio
    async def test_no_audio_skips_turn(self, mock_stt, tts_lock):
        """mic.listen이 None 반환 → STT/LLM 호출 없음."""
        mic = MagicMock()
        mic.listen = AsyncMock(return_value=None)
        vp = VoicePipeline(mic=mic, stt=mock_stt, tts_lock=tts_lock)

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock()) as mock_llm:
            await vp._run_one_turn()
            mock_llm.assert_not_called()

        assert vp.chat_history == []

    @pytest.mark.asyncio
    async def test_stt_failure_skips_turn(self, mock_mic, tts_lock):
        """stt.transcribe가 None 반환 → LLM 호출 없음."""
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value=None)
        vp = VoicePipeline(mic=mock_mic, stt=stt, tts_lock=tts_lock)

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock()) as mock_llm:
            await vp._run_one_turn()
            mock_llm.assert_not_called()

        assert vp.chat_history == []

    @pytest.mark.asyncio
    async def test_stt_empty_string_skips_turn(self, mock_mic, tts_lock):
        """stt.transcribe가 공백 문자열 반환 → LLM 호출 없음."""
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="   ")
        vp = VoicePipeline(mic=mock_mic, stt=stt, tts_lock=tts_lock)

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock()) as mock_llm:
            await vp._run_one_turn()
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure_skips_tts(self, mock_mic, mock_stt, tts_lock):
        """call_async가 None 반환 → TTS 호출 없음, tts_start/tts_done 없음."""
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        broadcast_calls = []

        async def capture_broadcast(msg):
            broadcast_calls.append(msg["type"])

        with patch(BROADCAST_PATH, side_effect=capture_broadcast), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value=None)), \
             patch("ai_core.llm_client.SYSTEM_PROMPT", "프롬프트"):
            await vp._run_one_turn()

        assert "tts_start" not in broadcast_calls
        assert "tts_done" not in broadcast_calls
        # 히스토리도 저장되지 않아야 함
        assert vp.chat_history == []

    @pytest.mark.asyncio
    async def test_history_grows_after_turn(self, mock_mic, mock_stt, tts_lock):
        """성공적인 턴 후 chat_history에 2개 항목 추가."""
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)

        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value=None)

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value="응답")), \
             patch("ai_core.llm_client.SYSTEM_PROMPT", "프롬프트"), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        assert len(vp.chat_history) == 2
        assert vp.chat_history[0] == {"role": "user", "content": "안녕하세요"}
        assert vp.chat_history[1] == {"role": "assistant", "content": "응답"}
