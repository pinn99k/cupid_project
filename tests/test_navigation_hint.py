from ai_core.navigation_hint import get_navigation_hint


def person(direction):
    return {"label": "person", "direction": direction, "distance_est": "mid", "bbox_ratio": 0.2}


def test_person_center_guides_right():
    hint = get_navigation_hint([person("center")])
    assert hint["obstacle_summary"] == "앞에 사람"
    assert hint["direction_hint"] == "오른쪽으로 조금 이동해보자."


def test_person_left_guides_right():
    hint = get_navigation_hint([person("left")])
    assert hint["obstacle_summary"] == "왼쪽에 사람"
    assert hint["direction_hint"] == "오른쪽으로 이동해보자."


def test_person_right_guides_left():
    hint = get_navigation_hint([person("right")])
    assert hint["obstacle_summary"] == "오른쪽에 사람"
    assert hint["direction_hint"] == "왼쪽으로 이동해보자."


def test_person_center_and_right_guides_left():
    hint = get_navigation_hint([person("center"), person("right")])
    assert hint["obstacle_summary"] == "앞과 오른쪽에 사람"
    assert hint["direction_hint"] == "왼쪽으로 이동해보자."


def test_person_center_and_left_guides_right():
    hint = get_navigation_hint([person("center"), person("left")])
    assert hint["obstacle_summary"] == "앞과 왼쪽에 사람"
    assert hint["direction_hint"] == "오른쪽으로 이동해보자."


def test_no_object_guides_forward():
    hint = get_navigation_hint([])
    assert hint["obstacle_summary"] == "앞에 특별한 장애물은 보이지 않음"
    assert hint["direction_hint"] == "정면으로 천천히 걸어가보자."
