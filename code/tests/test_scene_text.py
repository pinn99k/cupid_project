"""ai_core/scene_text.py 단위 테스트 — 순수 함수, 의존성 없음."""

from ai_core.scene_text import scene_to_korean, label_kr


class TestLabelKr:
    def test_known(self):
        assert label_kr("person") == "사람"
        assert label_kr("chair") == "의자"

    def test_unknown_passthrough(self):
        assert label_kr("zebra") == "zebra"


class TestSceneToKorean:
    def test_empty_scene(self):
        result = scene_to_korean({"objects": []})
        assert "없음" in result

    def test_single_object(self):
        enriched = {
            "objects": [
                {"label": "person", "direction": "left", "distance_est": "near"}
            ]
        }
        result = scene_to_korean(enriched)
        assert "왼쪽 가까이 사람" in result

    def test_multiple_objects(self):
        enriched = {
            "objects": [
                {"label": "person", "direction": "center", "distance_est": "near"},
                {"label": "chair", "direction": "right", "distance_est": "far"},
            ]
        }
        result = scene_to_korean(enriched)
        assert "앞 가까이 사람" in result
        assert "오른쪽 멀리 의자" in result

    def test_ultrasonic_included(self):
        enriched = {
            "objects": [{"label": "person", "direction": "center", "distance_est": "near"}],
            "ultrasonic_cm": 30,
            "ultrasonic_target": "person",
        }
        result = scene_to_korean(enriched)
        assert "30cm" in result
        assert "사람" in result

    def test_ultrasonic_absent(self):
        enriched = {
            "objects": [{"label": "chair", "direction": "left", "distance_est": "mid"}],
            "ultrasonic_cm": None,
            "ultrasonic_target": None,
        }
        result = scene_to_korean(enriched)
        assert "cm" not in result

    def test_unknown_label_passthrough(self):
        enriched = {"objects": [{"label": "zebra", "direction": "left", "distance_est": "near"}]}
        result = scene_to_korean(enriched)
        assert "zebra" in result
