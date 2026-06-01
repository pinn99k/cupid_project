"""펌웨어 ↔ 서버 계약 검증 (pytest).

펌웨어가 mock_device.py 와 바이트 호환되는 /distance·/stream 을 내는지 검사.
대상은 환경변수로 전환:

  SIA_DEVICE_HOST   기본 127.0.0.1
  SIA_PORT_CONTROL  기본 80   (/distance, /health)
  SIA_PORT_STREAM   기본 81   (/stream)

기본값은 "실칩"이 아니라 **mock 또는 실칩 어느 쪽이든** 가리킬 수 있다.
대상이 응답하지 않으면 테스트는 skip(하드웨어/서버 미기동) 처리한다 — pytest 가
디바이스 부재로 실패하지 않게 한다.

mock 으로 검증하는 예:
  python tools/mock_device.py --port 9000        # 한 포트에 둘 다
  SIA_PORT_CONTROL=9000 SIA_PORT_STREAM=9000 \
    pytest firmware/tests/test_contract.py -v

실칩으로 검증하는 예:
  SIA_DEVICE_HOST=192.168.0.50 pytest firmware/tests/test_contract.py -v
"""

import os
import urllib.request

import pytest

HOST = os.getenv("SIA_DEVICE_HOST", "127.0.0.1")
PORT_CONTROL = os.getenv("SIA_PORT_CONTROL", "80")
PORT_STREAM = os.getenv("SIA_PORT_STREAM", "81")

DISTANCE_URL = f"http://{HOST}:{PORT_CONTROL}/distance"
STREAM_URL = f"http://{HOST}:{PORT_STREAM}/stream"

# 서버측 신뢰 범위 (ai_core/calibration.py 와 일치). 무반사 센티넬(-1.0)은 예외 허용.
MIN_CM, MAX_CM = 2.0, 400.0
NO_ECHO = -1.0


def _get(url, timeout=2.0):
    return urllib.request.urlopen(url, timeout=timeout)


def _require_device():
    """대상이 살아있지 않으면 skip."""
    try:
        _get(DISTANCE_URL).read()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"디바이스/mock 미응답 ({DISTANCE_URL}): {exc}")


def test_distance_json_schema():
    """/distance → {"cm": number, "ts": int}."""
    _require_device()
    import json

    with _get(DISTANCE_URL) as resp:
        assert resp.status == 200
        ctype = resp.headers.get("Content-Type", "")
        assert "application/json" in ctype, ctype
        payload = json.loads(resp.read())

    assert set(payload) >= {"cm", "ts"}, f"키 누락: {payload}"
    assert isinstance(payload["cm"], (int, float)), payload["cm"]
    assert isinstance(payload["ts"], int), payload["ts"]


def test_distance_value_range():
    """cm 은 신뢰범위(2~400) 안이거나 무반사 센티넬(-1.0)."""
    _require_device()
    import json

    with _get(DISTANCE_URL) as resp:
        cm = json.loads(resp.read())["cm"]

    ok = cm == NO_ECHO or (MIN_CM <= cm <= MAX_CM)
    assert ok, f"cm 비정상: {cm} (허용: {NO_ECHO} 또는 {MIN_CM}~{MAX_CM})"


def test_stream_content_type():
    """/stream → multipart/x-mixed-replace, boundary=frame."""
    try:
        resp = _get(STREAM_URL, timeout=2.0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"스트림 미응답 ({STREAM_URL}): {exc}")

    try:
        ctype = resp.headers.get("Content-Type", "")
        assert "multipart/x-mixed-replace" in ctype, ctype
        assert "boundary=frame" in ctype.replace(" ", ""), ctype
        # 첫 청크에 JPEG 파트 헤더가 등장하는지(최소 1프레임)
        chunk = resp.read(512)
        assert b"image/jpeg" in chunk, chunk[:80]
    finally:
        resp.close()
