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
    # 호출어 게이팅(Unit 2) 통과용 — 처리되면 query는 "안녕하세요"로 추출됨
    stt.transcribe = AsyncMock(return_value="시아야 안녕하세요")
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
    async def test_llm_failure_skips_response_tts(self, mock_mic, mock_stt, tts_lock):
        """call_async가 None 반환 → 응답 TTS 생성 없음, 히스토리 저장 없음.
        (LLM 실패 시엔 폴백 음성을 재생하므로 tts_start/done 자체는 발생할 수 있음)"""
        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_am.wait_until_idle = AsyncMock()
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value=None)
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock, audio_manager=mock_am)
        vp._cooldown_steps = [0]  # 쿨다운 sleep 제거(테스트 속도)

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value=None)), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        # 응답 자체는 TTS로 만들어지지 않음
        mock_tts_cache.get_or_create.assert_not_called()
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


# ---------------------------------------------------------------------------
# TestVQA (Unit 3b) — scene_provider / 신선도 / question_count
# ---------------------------------------------------------------------------

import time as _time


class TestVQA:
    def _mocks(self):
        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value=None)
        return mock_am, mock_tts_cache

    @pytest.mark.asyncio
    async def test_fresh_scene_uses_vqa_prompt(self, mock_mic, mock_stt, tts_lock):
        """신선한 장면이 있으면 VQA_PROMPT + 장면 텍스트로 LLM 호출."""
        scene = {"objects": [{"label": "person", "direction": "center", "distance_est": "near"}]}
        provider = lambda: (scene, _time.time() * 1000)  # 방금 갱신 = 신선
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock, scene_provider=provider)

        captured = {}
        async def fake_call(system_prompt, user_msg, *a, **k):
            captured["sys"] = system_prompt
            return "응답"

        mock_am, mock_tts = self._mocks()
        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=fake_call), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        assert "[현재 장면]" in captured["sys"]
        assert "사람" in captured["sys"]  # scene_to_korean 결과 포함

    @pytest.mark.asyncio
    async def test_stale_scene_uses_system_prompt(self, mock_mic, mock_stt, tts_lock):
        """장면이 오래되면(stale) VQA 대신 일반 대화 프롬프트."""
        scene = {"objects": [{"label": "person", "direction": "center", "distance_est": "near"}]}
        provider = lambda: (scene, _time.time() * 1000 - 9999)  # 오래됨
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock,
                           scene_provider=provider, scene_fresh_sec=2.0)

        captured = {}
        async def fake_call(system_prompt, user_msg, *a, **k):
            captured["sys"] = system_prompt
            return "응답"

        mock_am, mock_tts = self._mocks()
        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=fake_call), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        assert "[현재 장면]" not in captured["sys"]

    @pytest.mark.asyncio
    async def test_count_question_called_on_success(self, mock_mic, mock_stt, tts_lock):
        """답변 성공 시 count_question 콜백 1회 호출."""
        counter = MagicMock()
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock, count_question=counter)

        mock_am, mock_tts = self._mocks()
        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value="응답")), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        counter.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_question_not_called_on_llm_failure(self, mock_mic, mock_stt, tts_lock):
        """LLM 실패 시 count_question 미호출."""
        counter = MagicMock()
        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_am.wait_until_idle = AsyncMock()
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock,
                           count_question=counter, audio_manager=mock_am)
        vp._cooldown_steps = [0]

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value=None)), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        counter.assert_not_called()
