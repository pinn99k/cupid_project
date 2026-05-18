"""
Step 1-3 테스트: 위험 판단 (Stage 3 전용)
실행: python tests/test_step1_3_danger.py
하드웨어 불필요 - mock 데이터 사용.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")

from ai_core.danger import judge


def test_danger():
    print("=" * 50)
    print("Step 1-3: danger.judge() 테스트")
    print("=" * 50)

    # Case 1: Stage 1에서는 항상 None
    result = judge(
        {"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"},
        current_stage=1
    )
    assert result is None, f"Stage 1에서 None이어야 함: {result}"
    print("[PASS] Case 1: Stage 1 → None")

    # Case 2: Stage 2에서도 항상 None
    result = judge(
        {"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"},
        current_stage=2
    )
    assert result is None, f"Stage 2에서 None이어야 함: {result}"
    print("[PASS] Case 2: Stage 2 → None")

    # Case 3: Stage 3 + 초음파 20cm → emergency
    result = judge(
        {"objects": [], "ultrasonic_cm": 20, "ultrasonic_target": "chair"},
        current_stage=3
    )
    assert result is not None, "Stage 3 + 20cm에서 emergency여야 함"
    assert result["level"] == "emergency"
    assert result["audio_file"] == "warn_emergency.mp3"
    print(f"[PASS] Case 3: Stage 3 + 20cm → {result['level']}")

    # Case 4: Stage 3 + YOLO near person → warning
    result = judge(
        {
            "objects": [{
                "label": "person", "direction": "left",
                "distance_est": "near", "bbox_ratio": 0.3, "confidence": 0.9
            }],
            "ultrasonic_cm": None, "ultrasonic_target": None
        },
        current_stage=3
    )
    assert result is not None, "near person에서 warning이어야 함"
    assert result["level"] == "warning"
    assert result["object"] == "person"
    print(f"[PASS] Case 4: Stage 3 + near person → {result['level']}")

    # Case 5: Stage 3 + 안전 (far chair) → None
    result = judge(
        {
            "objects": [{
                "label": "chair", "direction": "center",
                "distance_est": "far", "bbox_ratio": 0.03, "confidence": 0.8
            }],
            "ultrasonic_cm": 200, "ultrasonic_target": "chair"
        },
        current_stage=3
    )
    assert result is None, f"안전 상태에서 None이어야 함: {result}"
    print("[PASS] Case 5: Stage 3 + safe → None")

    print(f"\n[결과] Step 1-3 PASS - 5개 케이스 모두 통과")


if __name__ == "__main__":
    test_danger()
