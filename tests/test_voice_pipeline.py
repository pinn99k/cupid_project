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
    # MagicMock은 속성을 자동 생성하므로 숫자/문자 속성을 명시 주입한다
    # (없으면 f"{...:.2f}" 포맷에서 TypeError 발생).
    mic.last_record_sec = 0.0
    mic.last_exit_reason = "ok"
    mic.last_rms = 0.0
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
        # Set more items than the configured history window.
        pipeline._chat_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(10)
        ]
        # Simulate the trimming logic from _run_one_turn
        if len(pipeline._chat_history) > pipeline._max_history:
            pipeline._chat_history = pipeline._chat_history[-pipeline._max_history:]

        assert len(pipeline._chat_history) == pipeline._max_history
        assert pipeline._chat_history[0]["content"] == "msg6"
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
        vp.start()

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

        # 순서 검증 — 자막(stt_response)은 이제 문장별로 음성과 함께 나가므로
        # tts_start 직후, 각 문장 재생 직전에 전송된다.
        idx = {t: broadcast_calls.index(t) for t in
               ["voice_listening", "voice_processing", "user_stt", "stt_response", "tts_start", "tts_done"]}
        assert idx["voice_listening"] < idx["voice_processing"]
        assert idx["voice_processing"] < idx["user_stt"]
        assert idx["user_stt"] < idx["tts_start"]
        # tts_start(1회) → stt_response(문장별) → tts_done(1회)
        assert idx["tts_start"] < idx["stt_response"]
        assert idx["stt_response"] < idx["tts_done"]

    @pytest.mark.asyncio
    async def test_subtitle_broadcast_per_sentence(self, mock_mic, mock_stt, tts_lock):
        """LLM 응답이 여러 문장이면 자막(stt_response)을 문장별로 보낸다.
        각 문장 메시지는 split_sentences 결과와 일치하고, 각 문장 재생 직전에 전송된다."""
        from server.tts_chunker import split_sentences

        llm_response = "안녕! 반가워. 같이 연습해 보자!"
        expected = split_sentences(llm_response)
        assert len(expected) >= 2  # 다문장 응답이어야 의미 있는 검증

        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        vp.start()

        stt_response_msgs = []

        async def capture_broadcast(msg):
            if msg["type"] == "stt_response":
                stt_response_msgs.append(msg["message"])

        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value="/tmp/fake.mp3")

        with patch(BROADCAST_PATH, side_effect=capture_broadcast), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value=llm_response)), \
             patch("ai_core.llm_client.SYSTEM_PROMPT", "테스트 프롬프트"), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache), \
             patch("ai_core.audio_manager.get_audio_manager", return_value=mock_am):
            await vp._run_one_turn()

        # 문장별로 stt_response가 나가고, 통문장 1회 전송은 없어야 한다
        assert stt_response_msgs == expected
        assert llm_response not in stt_response_msgs

    @pytest.mark.asyncio
    async def test_full_turn_does_not_play_waiting_filler(self, mock_mic, mock_stt, tts_lock):
        """정상 질문마다 '잠깐만' 필러를 자동 재생하지 않는다."""
        mock_am = MagicMock()
        mock_am.wait_until_idle = AsyncMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value="/tmp/fake.wav")
        vp = VoicePipeline(
            mic=mock_mic,
            stt=mock_stt,
            tts_lock=tts_lock,
            audio_manager=mock_am,
        )

        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value="LLM 응답")), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache):
            await vp._run_one_turn()

        mock_am.play.assert_not_called()

    @pytest.mark.asyncio
    async def test_mic_error_is_broadcast(self, mock_stt, tts_lock):
        """마이크 장치 오류는 조용히 삼키지 않고 대시보드에 알린다."""
        mic = MagicMock()
        mic.listen = AsyncMock(return_value=None)
        mic.last_record_sec = 0.0
        mic.last_exit_reason = "ok"
        mic.last_error = "Error querying device -1"
        vp = VoicePipeline(mic=mic, stt=mock_stt, tts_lock=tts_lock)
        vp.start()

        with patch(BROADCAST_PATH, new=AsyncMock()) as mock_broadcast, \
             patch("server.voice_pipeline.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await vp._run_one_turn()

        assert any(
            call.args[0]["type"] == "error"
            and "마이크 입력 오류" in call.args[0]["message"]
            for call in mock_broadcast.await_args_list
        )
        mock_sleep.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_reprompt_holds_lock_through_output_settle(self, mock_mic, mock_stt, tts_lock):
        """되묻기 재생과 출력 꼬리 대기가 끝날 때까지 TTS 락을 유지한다."""
        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        vp = VoicePipeline(
            mic=mock_mic,
            stt=mock_stt,
            tts_lock=tts_lock,
            audio_manager=mock_am,
            output_settle_sec=0.4,
        )

        async def assert_locked():
            assert tts_lock.locked()

        settle = AsyncMock(side_effect=assert_locked)
        with patch(BROADCAST_PATH, new=AsyncMock()), \
             patch.object(vp, "_wait_for_output_settle", new=settle):
            await vp._play_reprompt("retry_unclear.wav", "인식불가")

        mock_am.wait.assert_awaited_once()
        settle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reprompt_cooldown_suppresses_immediate_repeat(self, mock_mic, mock_stt, tts_lock):
        """스피커 에코가 다시 들어와도 같은 되묻기를 바로 반복하지 않는다."""
        mock_am = MagicMock()
        mock_am.wait = AsyncMock(return_value=True)
        vp = VoicePipeline(
            mic=mock_mic,
            stt=mock_stt,
            tts_lock=tts_lock,
            audio_manager=mock_am,
            reprompt_cooldown_sec=2.0,
        )

        with patch(BROADCAST_PATH, new=AsyncMock()) as mock_broadcast:
            await vp._play_reprompt("retry_unclear.wav", "인식불가")
            await vp._play_reprompt("retry_unclear.wav", "인식불가")

        mock_am.play.assert_called_once()
        reprompts = [
            call for call in mock_broadcast.await_args_list
            if call.args[0]["type"] == "voice_reprompt"
        ]
        assert len(reprompts) == 1

    @pytest.mark.asyncio
    async def test_no_audio_skips_turn(self, mock_stt, tts_lock):
        """mic.listen이 None 반환 → STT/LLM 호출 없음."""
        mic = MagicMock()
        mic.listen = AsyncMock(return_value=None)
        mic.last_record_sec = 0.0
        mic.last_exit_reason = "ok"
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
        vp.start()

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

    @pytest.mark.asyncio
    async def test_demo_mode_greeting_plays_pre_recorded_voice(self, tmp_path, mock_mic, mock_stt, tts_lock):
        """DEMO_MODE=true면 LLM/Gemini TTS 없이 사전 음성 파일을 바로 재생."""
        voice_dir = tmp_path / "voices"
        voice_dir.mkdir()
        (voice_dir / "greeting.wav").write_bytes(b"RIFF" + b"\0" * 100)
        mock_stt.transcribe = AsyncMock(return_value="시아야 안녕")
        mock_am = MagicMock()
        mock_am.wait_until_idle = AsyncMock()
        mock_am.wait = AsyncMock(return_value=True)
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock, audio_manager=mock_am)
        vp.start()

        with patch("server.voice_pipeline.DEMO_MODE", True), \
             patch("server.demo_responses.DEMO_VOICE_DIR", voice_dir), \
             patch(BROADCAST_PATH, new=AsyncMock()) as mock_broadcast, \
             patch("ai_core.llm_client.call_async", new=AsyncMock()) as mock_llm, \
             patch("ai_core.tts.get_tts_cache") as mock_tts:
            await vp._run_one_turn()

        mock_llm.assert_not_called()
        mock_tts.assert_not_called()
        mock_am.play_path.assert_called_once()
        assert mock_am.play_path.call_args.args[0].endswith("greeting.wav")
        assert vp.voice_history == ["greeting.wav"]
        response = [
            call.args[0] for call in mock_broadcast.await_args_list
            if call.args[0]["type"] == "stt_response"
        ][0]
        assert response["audio_file"] == "greeting.wav"

    @pytest.mark.asyncio
    async def test_demo_mode_disabled_in_direction_stage(self, mock_mic, mock_stt, tts_lock):
        """방향단계(stage 2)에서는 DEMO_MODE여도 실제 LLM 경로를 사용한다."""
        mock_stt.transcribe = AsyncMock(return_value="시아야 안녕")
        mock_am = MagicMock()
        mock_am.wait_until_idle = AsyncMock()
        mock_am.wait = AsyncMock(return_value=True)
        mock_tts_cache = MagicMock()
        mock_tts_cache.get_or_create = AsyncMock(return_value="/tmp/x.mp3")
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock, audio_manager=mock_am)
        vp.start()
        vp.set_stage(2)  # 방향단계 → 데모 비활성

        with patch("server.voice_pipeline.DEMO_MODE", True), \
             patch(BROADCAST_PATH, new=AsyncMock()), \
             patch("ai_core.llm_client.call_async", new=AsyncMock(return_value="안녕! 반가워")) as mock_llm, \
             patch("ai_core.llm_client.SYSTEM_PROMPT", "프롬프트"), \
             patch("ai_core.tts.get_tts_cache", return_value=mock_tts_cache):
            await vp._run_one_turn()

        mock_llm.assert_awaited()        # 데모 우회 없이 LLM 호출
        assert vp.voice_history == []    # 데모 사전음성 기록 없음

    @pytest.mark.asyncio
    async def test_demo_mode_scene_traffic_light_only_once(self, tmp_path, mock_mic, mock_stt, tts_lock):
        """같은 시연 세션에서 신호등은 한 번만 안내하고 이후 all_clear로 넘어간다."""
        voice_dir = tmp_path / "voices"
        voice_dir.mkdir()
        for filename in ("traffic_light.wav", "all_clear.wav"):
            (voice_dir / filename).write_bytes(b"RIFF" + b"\0" * 100)
        scene = {
            "objects": [
                {"label": "traffic light", "bbox": {"x": 0.05, "y": 0, "w": 0.1, "h": 0.2}}
            ]
        }
        mock_stt.transcribe = AsyncMock(side_effect=["시아야 앞에 뭐 있어", "시아야 앞에 뭐 있어"])
        mock_am = MagicMock()
        mock_am.wait_until_idle = AsyncMock()
        mock_am.wait = AsyncMock(return_value=True)
        vp = VoicePipeline(
            mic=mock_mic,
            stt=mock_stt,
            tts_lock=tts_lock,
            audio_manager=mock_am,
            scene_provider=lambda: (scene, 0),
        )
        vp.start()

        with patch("server.voice_pipeline.DEMO_MODE", True), \
             patch("server.demo_responses.DEMO_VOICE_DIR", voice_dir), \
             patch(BROADCAST_PATH, new=AsyncMock()):
            await vp._run_one_turn()
            await vp._run_one_turn()

        assert vp.voice_history == ["traffic_light.wav", "all_clear.wav"]
        assert mock_am.play_path.call_args_list[0].args[0].endswith("traffic_light.wav")
        assert mock_am.play_path.call_args_list[1].args[0].endswith("all_clear.wav")

    def test_reset_clears_demo_voice_history(self, mock_mic, mock_stt, tts_lock):
        vp = VoicePipeline(mic=mock_mic, stt=mock_stt, tts_lock=tts_lock)
        vp._voice_history.extend(["traffic_light.wav"])
        vp.reset()
        assert vp.voice_history == []


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
        vp.start()

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
        vp.start()

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
        vp.start()

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
