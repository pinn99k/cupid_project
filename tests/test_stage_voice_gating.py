"""단계별 음성 게이팅 — 수용(1)=음성 OFF / 방향(2)=음성 ON.

서버가 강제하는 불변식(ai_collab_handoff.md §2)을 못박는다.
가짜 pipeline으로 start/stop_listening 호출만 검증 (마이크/STT 비의존).
"""

import asyncio

import server.main_server as srv


class _FakePipeline:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop_listening(self):
        self.stopped += 1

    def reset(self):
        pass


def _send(event_msg):
    """handle_dashboard_message(async)를 동기 테스트에서 실행."""
    return asyncio.run(srv.handle_dashboard_message(event_msg))


def _with_fake():
    fake = _FakePipeline()
    srv.set_voice_pipeline(fake)
    return fake


def teardown_function(_):
    srv.set_voice_pipeline(None)


def test_stage1_voice_off():
    fake = _with_fake()
    _send({"event": "start_learning", "stage": 1})
    assert fake.stopped == 1 and fake.started == 0
    assert srv.app_state.current_stage == 1


def test_stage2_voice_on():
    fake = _with_fake()
    _send({"event": "start_learning", "stage": 2})
    assert fake.started == 1 and fake.stopped == 0
    assert srv.app_state.current_stage == 2


def test_default_stage_is_1_voice_off():
    # stage 미지정 → 1로 간주 → 음성 OFF
    fake = _with_fake()
    _send({"event": "start_learning"})
    assert fake.stopped == 1 and fake.started == 0
    assert srv.app_state.current_stage == 1


def test_stage3_if_sent_still_voice_on():
    # 대시보드는 stage3을 안 보내지만, 와도 서버가 죽지 않고 음성 ON 처리(>=2)
    fake = _with_fake()
    _send({"event": "start_learning", "stage": 3})
    assert fake.started == 1 and fake.stopped == 0
