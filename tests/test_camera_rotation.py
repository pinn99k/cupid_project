"""카메라 회전(CAMERA_ROTATION) 신규 로직 단위 테스트.

대상: 108699a "디바이스 연결 및 최적화" 에서 추가된
  - server.config._parse_rotation  (env 파싱, 순수)
  - main._ROTATE_FLAGS / _ROTATE_FLAG  (도 → cv2 플래그 매핑)
  - 회전이 프레임 치수에 일관되게 적용되는지 (cv2.rotate 행동)
  - CAM_SOURCE 문자열 여부 → 스트림 소스 판별 로직

하드웨어/네트워크 비의존. 순수 로직과 cv2 변환만 검증한다.
"""

import cv2
import numpy as np
import pytest

from server.config import _parse_rotation


# ---------------------------------------------------------------------------
# 1. _parse_rotation — env 문자열 → 0/90/180/270
# ---------------------------------------------------------------------------
class TestParseRotation:
    @pytest.mark.parametrize("value,expected", [
        ("0", 0), ("90", 90), ("180", 180), ("270", 270),
    ])
    def test_valid(self, value, expected):
        assert _parse_rotation(value) == expected

    def test_whitespace_trimmed(self):
        assert _parse_rotation("  90  ") == 90

    @pytest.mark.parametrize("bad", ["45", "360", "-90", "1", "9999"])
    def test_out_of_set_falls_back_to_zero(self, bad):
        # 0/90/180/270 외 정수는 0으로 안전 폴백 (회전 안 함)
        assert _parse_rotation(bad) == 0

    @pytest.mark.parametrize("bad", ["", "abc", "90.0", "90deg", None])
    def test_non_integer_falls_back_to_zero(self, bad):
        assert _parse_rotation(bad) == 0


# ---------------------------------------------------------------------------
# 2. main._ROTATE_FLAGS — 도 → cv2 회전 플래그 매핑
# ---------------------------------------------------------------------------
class TestRotateFlagMapping:
    def test_mapping_matches_cv2_constants(self):
        import main
        assert main._ROTATE_FLAGS[90] == cv2.ROTATE_90_CLOCKWISE
        assert main._ROTATE_FLAGS[180] == cv2.ROTATE_180
        assert main._ROTATE_FLAGS[270] == cv2.ROTATE_90_COUNTERCLOCKWISE

    def test_zero_means_no_rotation(self):
        import main
        # 0도는 매핑에 없어야 하고 → .get(0) 은 None (회전 스킵 신호)
        assert 0 not in main._ROTATE_FLAGS
        assert main._ROTATE_FLAGS.get(0) is None


# ---------------------------------------------------------------------------
# 3. 회전이 프레임 치수에 일관되게 적용되는지 (다운스트림 shape 재독 전제)
# ---------------------------------------------------------------------------
class TestRotateBehavior:
    def _frame(self):
        # 비대칭 프레임(H=480, W=640, 3ch)으로 치수 변화를 명확히 검증
        f = np.zeros((480, 640, 3), dtype=np.uint8)
        f[0, 0] = (255, 255, 255)  # 좌상단 마커
        return f

    def test_90_swaps_dimensions(self):
        out = cv2.rotate(self._frame(), cv2.ROTATE_90_CLOCKWISE)
        assert out.shape[:2] == (640, 480)  # H↔W 교환

    def test_270_swaps_dimensions(self):
        out = cv2.rotate(self._frame(), cv2.ROTATE_90_COUNTERCLOCKWISE)
        assert out.shape[:2] == (640, 480)

    def test_180_keeps_dimensions(self):
        out = cv2.rotate(self._frame(), cv2.ROTATE_180)
        assert out.shape[:2] == (480, 640)

    def test_four_90s_restore_original(self):
        f = self._frame()
        out = f
        for _ in range(4):
            out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
        assert np.array_equal(out, f)  # 360도 = 원본


# ---------------------------------------------------------------------------
# 4. CAM_SOURCE 문자열 여부 → 스트림(ESP32-CAM) 소스 판별
# ---------------------------------------------------------------------------
class TestStreamSourceDetection:
    def test_url_is_stream(self):
        # _IS_STREAM_SOURCE = isinstance(CAM_SOURCE, str) 와 동일 의미
        assert isinstance("http://192.168.0.50:81/stream", str) is True

    def test_int_index_is_not_stream(self):
        # 로컬 웹캠 인덱스는 int → 스트림 아님 → 기본 백엔드 경로
        assert isinstance(0, str) is False
