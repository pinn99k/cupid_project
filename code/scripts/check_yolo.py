"""
YOLO 모델 다운로드 및 기본 동작 확인 스크립트.
실행: python scripts/check_yolo.py
"""

import sys
from pathlib import Path


def check_yolo():
    print("[YOLO 확인] ultralytics import 중...")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  FAIL: ultralytics가 설치되지 않았습니다. pip install ultralytics")
        sys.exit(1)
    print("  OK: ultralytics import 성공")

    model_path = "yolov8n.pt"
    print(f"[YOLO 확인] 모델 로드 중: {model_path}")
    try:
        model = YOLO(model_path)  # 없으면 자동 다운로드
        print("  OK: 모델 로드 성공")
    except Exception as e:
        print(f"  FAIL: 모델 로드 실패 — {e}")
        sys.exit(1)

    print("[YOLO 확인] 더미 이미지로 추론 테스트 중...")
    try:
        import numpy as np
        dummy = np.zeros((480, 640, 3), dtype="uint8")
        results = model(dummy, verbose=False)
        print(f"  OK: 추론 성공 (감지된 객체 수: {len(results[0].boxes)})")
    except Exception as e:
        print(f"  FAIL: 추론 실패 — {e}")
        sys.exit(1)

    print("\n[결과] YOLO 모델 확인 완료. Phase 1 진행 가능.")


if __name__ == "__main__":
    check_yolo()
