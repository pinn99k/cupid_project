"""시연용 키워드/장면 응답 선택 테스트."""

from server.demo_responses import find_response, find_scene_voice, get_position


def person(x, w=0.2, h=0.5, ratio=None):
    obj = {"label": "person", "bbox": {"x": x, "y": 0.1, "w": w, "h": h}}
    if ratio is not None:
        obj["bbox_ratio"] = ratio
    return obj


def test_keyword_responses():
    assert find_response("안녕 반가워", [], []) == "greeting.wav"
    assert find_response("너 누구야 소개해줘", [], []) == "intro.wav"
    assert find_response("같이 가자", [], []) == "lets_go.wav"
    assert find_response("다 왔어?", [], []) == "arrival.wav"
    assert find_response("이상한 말", [], []) == "fallback.wav"


def test_get_position_from_bbox_center_x():
    assert get_position({"x": 0.0, "w": 0.2}) == "left"
    assert get_position({"x": 0.4, "w": 0.2}) == "center"
    assert get_position({"x": 0.75, "w": 0.2}) == "right"


def test_scene_close_person_priority():
    objects = [
        {"label": "traffic light", "bbox": {"x": 0.1, "w": 0.1, "y": 0, "h": 0.2}},
        person(0.4, ratio=0.3),
    ]
    assert find_scene_voice(objects, []) == "person_center_close.wav"


def test_traffic_light_once_then_all_clear():
    objects = [{"label": "traffic light", "bbox": {"x": 0.0, "w": 0.1, "y": 0, "h": 0.2}}]
    assert find_scene_voice(objects, []) == "traffic_light.wav"
    assert find_scene_voice(objects, ["traffic_light.wav"]) == "all_clear.wav"


def test_far_person_after_traffic_seen():
    objects = [
        {"label": "traffic light", "bbox": {"x": 0.0, "w": 0.1, "y": 0, "h": 0.2}},
        person(0.75, ratio=0.1),
    ]
    assert find_scene_voice(objects, ["traffic_light.wav"]) == "person_right_far.wav"


def test_scene_aware_keyword_uses_scene():
    assert find_response("앞에 뭐 있어", [person(0.02, ratio=0.1)], []) == "person_left_far.wav"
