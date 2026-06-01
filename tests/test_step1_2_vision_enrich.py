"""
Step 1-2 테스트: YOLO bbox 후처리 (enriched JSON)
실행: python tests/test_step1_2_vision_enrich.py
하드웨어 불필요 - mock 데이터 사용.
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-needed")

from ai_core.vision import enrich


def test_enrich():
    print("=" * 50)
    print("Step 1-2: enrich() 후처리 테스트")
    print("=" * 50)

    # Mock: 640x480 프레임에서 감지된 3개 객체
    mock_detections = [
        {"label": "person", "x": 10, "y": 50, "w": 180, "h": 350, "conf": 0.92},
        {"label": "chair", "x": 250, "y": 100, "w": 100, "h": 150, "conf": 0.87},
        {"label": "car", "x": 500, "y": 200, "w": 30, "h": 20, "conf": 0.65},
    ]
    frame_w, frame_h = 640, 480

    result = enrich(mock_detections, frame_w, frame_h, ultrasonic_cm=45)
    print(f"\n결과:\n{json.dumps(result, indent=2, ensure_ascii=False)}")

    # 검증
    objs = result["objects"]
    assert len(objs) == 3, f"객체 수 불일치: {len(objs)}"

    # person: x중심=(10+90)/640=0.156 → left, 면적=(180*350)/(640*480)=0.205 → near
    assert objs[0]["direction"] == "left", f"person 방향 오류: {objs[0]['direction']}"
    assert objs[0]["distance_est"] == "near", f"person 거리 오류: {objs[0]['distance_est']}"

    # chair: x중심=(250+50)/640=0.469 → center, 면적=(100*150)/(640*480)=0.049 → far
    assert objs[1]["direction"] == "center", f"chair 방향 오류: {objs[1]['direction']}"
    assert objs[1]["distance_est"] == "far", f"chair 거리 오류: {objs[1]['distance_est']}"

    # car: x중심=(500+15)/640=0.805 → right, 면적=(30*20)/(640*480)=0.002 → far
    assert objs[2]["direction"] == "right", f"car 방향 오류: {objs[2]['direction']}"
    assert objs[2]["distance_est"] == "far", f"car 거리 오류: {objs[2]['distance_est']}"

    # 초음파 매칭: center 객체 중 가장 큰 건 chair
    assert result["ultrasonic_cm"] == 45
    assert result["ultrasonic_target"] == "chair"

    print("\n[결과] Step 1-2 PASS - 방향/거리/초음파 매칭 모두 정상")


def test_relevance_gate():
    """Unit 6: min_relevant_area 미만의 작은/먼 객체는 제외."""
    mock_detections = [
        {"label": "person", "x": 10, "y": 50, "w": 180, "h": 350, "conf": 0.92},  # 면적 0.205
        {"label": "chair", "x": 250, "y": 100, "w": 100, "h": 150, "conf": 0.87},  # 면적 0.049
        {"label": "car", "x": 500, "y": 200, "w": 30, "h": 20, "conf": 0.65},      # 면적 0.002 (배경 오탐)
    ]
    frame_w, frame_h = 640, 480

    # 게이트 없음 → 3개 모두
    assert len(enrich(mock_detections, frame_w, frame_h)["objects"]) == 3

    # 0.02 게이트 → 작은 car(0.002) 제외, person/chair 유지
    gated = enrich(mock_detections, frame_w, frame_h, min_relevant_area=0.02)["objects"]
    labels = [o["label"] for o in gated]
    assert labels == ["person", "chair"], f"게이트 결과 오류: {labels}"

    # 강한 게이트 0.1 → person만
    strong = enrich(mock_detections, frame_w, frame_h, min_relevant_area=0.1)["objects"]
    assert [o["label"] for o in strong] == ["person"]

    print("[결과] Unit 6 관련성 게이트 PASS")


if __name__ == "__main__":
    test_enrich()
    test_relevance_gate()
