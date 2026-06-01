"""tools/mock_device.py 코어 단위 테스트 — 포트 바인딩 없이."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.mock_device import MockDevice


class TestDistance:
    def test_default_and_payload_keys(self):
        d = MockDevice()
        payload = d.distance_payload()
        assert "cm" in payload and "ts" in payload
        assert payload["cm"] == 100.0

    def test_set_distance(self):
        d = MockDevice()
        d.set_distance(30)
        assert d.distance_payload()["cm"] == 30.0

    def test_ts_is_ms(self):
        d = MockDevice()
        ts = d.distance_payload()["ts"]
        assert ts > 1_000_000_000_000  # ms 단위 epoch


class TestFrame:
    def test_synthetic_frame_shape(self):
        d = MockDevice()
        frame = d.synthetic_frame()
        assert frame.shape == (480, 640, 3)

    def test_next_frame_without_video_is_synthetic(self):
        d = MockDevice()
        frame = d.next_frame()
        assert frame.shape == (480, 640, 3)

    def test_encode_jpeg_magic_bytes(self):
        d = MockDevice()
        jpeg = MockDevice.encode_jpeg(d.synthetic_frame())
        assert jpeg is not None
        assert jpeg[:2] == b"\xff\xd8"  # JPEG 매직 바이트
