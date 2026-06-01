"""server/config.py 디바이스 연동 설정 단위 테스트."""

from server.config import _parse_cam_source


class TestParseCamSource:
    def test_int_index(self):
        assert _parse_cam_source("0") == 0
        assert _parse_cam_source("1") == 1

    def test_http_url(self):
        assert _parse_cam_source("http://192.168.0.50/stream") == "http://192.168.0.50/stream"

    def test_https_url(self):
        assert _parse_cam_source("https://cam.local/stream") == "https://cam.local/stream"

    def test_whitespace_trimmed(self):
        assert _parse_cam_source("  2  ") == 2


class TestUltrasonicDefaults:
    def test_defaults_present(self):
        from server import config
        assert hasattr(config, "ULTRASONIC_URL")
        assert isinstance(config.ULTRASONIC_POLL_SEC, float)
        assert isinstance(config.ULTRASONIC_OFFSET_CM, float)
