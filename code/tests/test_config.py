"""server/config.py 단위 테스트."""

import os
import pytest


class TestConfigDefaults:
    """기본값 로딩 검증."""

    def test_llm_provider_default(self):
        from server.config import LLM_PROVIDER
        # .env에 설정이 있으면 그 값, 없으면 "groq"
        assert LLM_PROVIDER in ("groq", "gemini", "openai")

    def test_server_host_default(self):
        from server.config import SERVER_HOST
        assert isinstance(SERVER_HOST, str)
        assert len(SERVER_HOST) > 0

    def test_server_port_is_int(self):
        from server.config import SERVER_PORT
        assert isinstance(SERVER_PORT, int)
        assert 1 <= SERVER_PORT <= 65535

    def test_yolo_conf_threshold_range(self):
        from server.config import YOLO_CONF_THRESHOLD
        assert isinstance(YOLO_CONF_THRESHOLD, float)
        assert 0.0 < YOLO_CONF_THRESHOLD <= 1.0

    def test_danger_distance_positive(self):
        from server.config import DANGER_DISTANCE_CM
        assert isinstance(DANGER_DISTANCE_CM, float)
        assert DANGER_DISTANCE_CM > 0


class TestConfigRequire:
    """_require() fail-fast 검증."""

    def test_require_raises_on_missing(self):
        from server.config import _require
        # 존재하지 않는 환경변수
        with pytest.raises(RuntimeError, match="필수 환경변수"):
            _require("__NONEXISTENT_KEY_FOR_TEST__")

    def test_require_raises_on_empty(self, monkeypatch):
        from server.config import _require
        monkeypatch.setenv("__TEST_EMPTY_KEY__", "   ")
        with pytest.raises(RuntimeError):
            _require("__TEST_EMPTY_KEY__")

    def test_require_returns_value(self, monkeypatch):
        from server.config import _require
        monkeypatch.setenv("__TEST_KEY__", "hello")
        assert _require("__TEST_KEY__") == "hello"


class TestEnvValue:
    """환경변수 값 정규화 검증."""

    def test_strips_duplicate_key_prefix(self, monkeypatch):
        from server.config import _env_value

        monkeypatch.setenv("LLM_MODEL", "LLM_MODEL=gemini-2.5-flash")

        assert _env_value("LLM_MODEL", "fallback") == "gemini-2.5-flash"

    def test_returns_default_when_missing(self, monkeypatch):
        from server.config import _env_value

        monkeypatch.delenv("__MISSING_FOR_ENV_VALUE__", raising=False)

        assert _env_value("__MISSING_FOR_ENV_VALUE__", "fallback") == "fallback"
