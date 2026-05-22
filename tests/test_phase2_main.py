"""
Phase 2 테스트: main.py 웹캠 복구, 태스크 에러 콜백, 감지 루프.
실행: python tests/test_phase2_main.py
하드웨어 불필요 - cv2.VideoCapture mock 사용.
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")


def test_open_camera_success():
    """P0 #9: 웹캠 연결 성공 테스트."""
    print("=" * 50)
    print("Phase 2-1: _open_camera 성공")
    print("=" * 50)

    from main import _open_camera

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("main.cv2.VideoCapture", return_value=mock_cap):
        cap = asyncio.run(_open_camera())

    assert cap is not None, "웹캠 연결 성공 시 VideoCapture 반환"
    assert cap.isOpened(), "isOpened() == True"
    print("[PASS] Case 1: 첫 시도에 웹캠 연결 성공")
    print()


def test_open_camera_retry_then_success():
    """P0 #9: 웹캠 2회 실패 후 3회째 성공."""
    print("=" * 50)
    print("Phase 2-2: _open_camera 재시도 후 성공")
    print("=" * 50)

    from main import _open_camera

    fail_cap = MagicMock()
    fail_cap.isOpened.return_value = False

    success_cap = MagicMock()
    success_cap.isOpened.return_value = True

    # 2번 실패, 3번째 성공
    with patch("main.cv2.VideoCapture", side_effect=[fail_cap, fail_cap, success_cap]):
        with patch("main.WEBCAM_RETRY_DELAY", 0):  # 테스트 속도를 위해 딜레이 0
            cap = asyncio.run(_open_camera())

    assert cap is not None, "3번째 시도에서 성공해야 함"
    assert cap is success_cap, "성공한 캡처 객체 반환"
    assert fail_cap.release.call_count == 2, "실패한 캡처는 release 호출"
    print("[PASS] Case 1: 2회 실패 후 3회째 성공")
    print()


def test_open_camera_all_fail():
    """P0 #9: 웹캠 MAX_WEBCAM_RETRIES 모두 실패 → None."""
    print("=" * 50)
    print("Phase 2-3: _open_camera 전부 실패")
    print("=" * 50)

    from main import _open_camera, MAX_WEBCAM_RETRIES

    fail_cap = MagicMock()
    fail_cap.isOpened.return_value = False

    with patch("main.cv2.VideoCapture", return_value=fail_cap):
        with patch("main.WEBCAM_RETRY_DELAY", 0):
            cap = asyncio.run(_open_camera())

    assert cap is None, "전부 실패 시 None 반환"
    assert fail_cap.release.call_count == MAX_WEBCAM_RETRIES, \
        f"release {MAX_WEBCAM_RETRIES}회 호출"
    print(f"[PASS] Case 1: {MAX_WEBCAM_RETRIES}회 실패 → None")
    print()


def test_task_done_callback_logs_exception():
    """P1 #6: 태스크 에러 콜백이 예외를 로깅하는지 확인."""
    print("=" * 50)
    print("Phase 2-4: _task_done_callback 에러 로깅")
    print("=" * 50)

    from main import _task_done_callback

    # Case 1: 예외가 있는 태스크
    mock_task = MagicMock()
    mock_task.cancelled.return_value = False
    mock_task.exception.return_value = ValueError("test error")

    with patch("builtins.print") as mock_print:
        _task_done_callback(mock_task)
        printed = mock_print.call_args[0][0]
        assert "ValueError" in printed, f"예외 타입 포함: {printed}"
        assert "test error" in printed, f"예외 메시지 포함: {printed}"
    print("[PASS] Case 1: 예외 태스크 → 로그 출력")

    # Case 2: 취소된 태스크 → 아무것도 안 함
    mock_task2 = MagicMock()
    mock_task2.cancelled.return_value = True

    with patch("builtins.print") as mock_print:
        _task_done_callback(mock_task2)
        mock_print.assert_not_called()
    print("[PASS] Case 2: 취소된 태스크 → 로그 없음")

    # Case 3: 정상 완료 태스크 → 아무것도 안 함
    mock_task3 = MagicMock()
    mock_task3.cancelled.return_value = False
    mock_task3.exception.return_value = None

    with patch("builtins.print") as mock_print:
        _task_done_callback(mock_task3)
        mock_print.assert_not_called()
    print("[PASS] Case 3: 정상 태스크 → 로그 없음")
    print()


def test_detection_loop_no_camera():
    """P0 #9: 카메라 없을 때 detection_loop 가 graceful 종료."""
    print("=" * 50)
    print("Phase 2-5: detection_loop 카메라 없음 → 종료")
    print("=" * 50)

    from main import detection_loop

    with patch("main._open_camera", new_callable=AsyncMock, return_value=None):
        with patch("main.broadcast", new_callable=AsyncMock) as mock_broadcast:
            asyncio.run(detection_loop())

    # broadcast로 에러 전송 확인
    assert mock_broadcast.called, "broadcast 호출되어야 함"
    msg = mock_broadcast.call_args[0][0]
    assert msg["type"] == "error", f"에러 타입: {msg['type']}"
    assert "웹캠" in msg["message"], f"웹캠 관련 메시지: {msg['message']}"
    print("[PASS] Case 1: 카메라 없음 → error broadcast 후 종료")
    print()


def test_detection_loop_frame_fail_recovery():
    """P0 #9: 프레임 읽기 연속 실패 시 웹캠 재연결 시도."""
    print("=" * 50)
    print("Phase 2-6: 프레임 실패 → 웹캠 재연결")
    print("=" * 50)

    from main import detection_loop

    # 초기 캡처 — isOpened True, read()는 항상 (False, None)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)

    call_count = 0

    async def mock_open_camera():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_cap  # 최초 연결 성공
        return None           # 재연결 실패 → 루프 종료

    mock_open = AsyncMock(side_effect=mock_open_camera)

    with patch("main._open_camera", mock_open):
        with patch("main.broadcast", new_callable=AsyncMock):
            with patch("main.MAX_FRAME_FAILS", 3):  # 3회 실패로 줄임
                asyncio.run(detection_loop())

    assert call_count == 2, f"_open_camera 2회 호출 (초기 + 재연결): {call_count}"
    assert mock_cap.release.called, "실패한 캡처 release 호출"
    print("[PASS] Case 1: 프레임 연속 실패 → 재연결 시도 → 실패 시 종료")
    print()


def test_detect_runs_in_thread():
    """P1: detect()가 asyncio.to_thread로 호출되는지 확인."""
    print("=" * 50)
    print("Phase 2-7: detect()가 to_thread로 실행")
    print("=" * 50)

    import main as main_mod
    import inspect

    # detection_loop 소스에서 asyncio.to_thread(detect 가 있는지 확인
    source = inspect.getsource(main_mod.detection_loop)
    assert "asyncio.to_thread(detect" in source or "to_thread(detect" in source, \
        "detect()가 asyncio.to_thread로 감싸져야 함"
    print("[PASS] Case 1: detection_loop 소스에 asyncio.to_thread(detect) 존재")

    # create_task에 add_done_callback이 있는지 확인
    assert "add_done_callback" in source, \
        "create_task에 add_done_callback 등록해야 함"
    print("[PASS] Case 2: create_task에 add_done_callback 등록됨")
    print()


def test_unused_imports_removed():
    """P1: current_stage, learning_active 미사용 import 제거 확인."""
    print("=" * 50)
    print("Phase 2-8: 미사용 import 제거 확인")
    print("=" * 50)

    import main as main_mod
    import inspect

    source = inspect.getsource(main_mod)
    # "from server.main_server import app, current_stage, learning_active" 가 없어야 함
    assert "current_stage" not in source.split("from server.main_server")[1].split("\n")[0] \
        if "from server.main_server" in source else True, \
        "current_stage import가 남아있으면 안 됨"

    # app만 import하는지 확인
    lines = source.split("\n")
    for line in lines:
        if "from server.main_server import" in line:
            assert "current_stage" not in line, f"current_stage가 import에 남아있음: {line}"
            assert "learning_active" not in line, f"learning_active가 import에 남아있음: {line}"
            assert "app" in line, f"app은 import해야 함: {line}"
            break
    print("[PASS] Case 1: top-level import에 current_stage, learning_active 없음")
    print()


def test_shutdown_event_exists():
    """P1: shutdown 이벤트 핸들러 존재 확인."""
    print("=" * 50)
    print("Phase 2-9: shutdown 이벤트 핸들러")
    print("=" * 50)

    import main as main_mod
    import inspect

    source = inspect.getsource(main_mod)
    assert 'on_event("shutdown")' in source or "on_event('shutdown')" in source, \
        "shutdown 이벤트 핸들러가 있어야 함"
    print("[PASS] Case 1: @app.on_event('shutdown') 핸들러 존재")

    # shutdown 함수가 _detection_task를 cancel하는지
    shutdown_source = inspect.getsource(main_mod.shutdown)
    assert "_detection_task" in shutdown_source, "shutdown에서 _detection_task 정리"
    assert "cancel" in shutdown_source, "shutdown에서 task.cancel() 호출"
    print("[PASS] Case 2: shutdown에서 detection_task cancel 처리")
    print()


if __name__ == "__main__":
    test_open_camera_success()
    test_open_camera_retry_then_success()
    test_open_camera_all_fail()
    test_task_done_callback_logs_exception()
    test_detection_loop_no_camera()
    test_detection_loop_frame_fail_recovery()
    test_detect_runs_in_thread()
    test_unused_imports_removed()
    test_shutdown_event_exists()
    print("=" * 50)
    print("[결과] Phase 2 main.py PASS - 모든 테스트 통과")
    print("=" * 50)
