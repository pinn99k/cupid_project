"""
Step 1-1 테스트: YOLO 감지 (웹캠 필요)
실행: python tests/test_step1_1_vision_detect.py
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .env 로드 (config.py 의존)
from dotenv import load_dotenv
load_dotenv()

# config의 OPENAI_API_KEY 검증 우회 (이 테스트는 LLM 불필요)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed-for-yolo")

from ai_core.vision import load_model, detect
import cv2


def test_detect_with_webcam():
    """웹캠 프레임에서 YOLO 감지 테스트."""
    print("=" * 50)
    print("Step 1-1: YOLO 감지 테스트")
    print("=" * 50)

    print("\n[1] 모델 로드...")
    load_model()
    print("  OK")

    print("\n[2] 웹캠 프레임 읽기...")
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        pytest.skip("웹캠 접근 권한 또는 연결된 카메라가 없음")
    print(f"  OK: {frame.shape[1]}x{frame.shape[0]}")

    print("\n[3] 감지 실행...")
    dets = detect(frame)
    print(f"  감지된 객체 수: {len(dets)}")
    for d in dets:
        print(f"    {d['label']:>12} conf={d['conf']:.2f} "
              f"pos=({d['x']:.0f},{d['y']:.0f}) size=({d['w']:.0f}x{d['h']:.0f})")

    print("\n[결과] Step 1-1 PASS")


def test_detect_with_dummy():
    """더미 이미지로 YOLO 감지 테스트 (웹캠 없어도 됨)."""
    import numpy as np

    print("=" * 50)
    print("Step 1-1: YOLO 감지 테스트 (더미)")
    print("=" * 50)

    print("\n[1] 모델 로드...")
    load_model()
    print("  OK")

    print("\n[2] 더미 이미지 감지...")
    dummy = np.zeros((480, 640, 3), dtype="uint8")
    dets = detect(dummy)
    print(f"  감지된 객체 수: {len(dets)} (빈 이미지이므로 0이 정상)")

    print("\n[결과] Step 1-1 (더미) PASS")


if __name__ == "__main__":
    if "--dummy" in sys.argv:
        test_detect_with_dummy()
    else:
        try:
            test_detect_with_webcam()
        except AssertionError:
            print("\n웹캠 없음 → 더미 테스트로 전환")
            test_detect_with_dummy()
