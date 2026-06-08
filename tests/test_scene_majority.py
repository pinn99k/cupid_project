from server.main_server import clear_scene, get_scene, set_scene


def scene(direction=None):
    objects = []
    if direction:
        objects.append({
            "label": "person",
            "direction": direction,
            "distance_est": "mid",
            "bbox_ratio": 0.2,
        })
    return {"objects": objects, "ultrasonic_cm": None, "ultrasonic_target": None}


def test_get_scene_uses_recent_five_frame_majority():
    clear_scene()
    set_scene(scene("center"))
    set_scene(scene("center"))
    set_scene(scene(None))
    set_scene(scene("center"))
    set_scene(scene("right"))

    aggregated, _ = get_scene()
    assert aggregated["scene_history_frames"] == 5
    assert aggregated["objects"] == [
        {
            "label": "person",
            "direction": "center",
            "distance_est": "mid",
            "bbox_ratio": 0.2,
        }
    ]
    clear_scene()


def test_get_scene_keeps_stable_center_and_right():
    clear_scene()
    set_scene(scene("center"))
    set_scene(scene("right"))
    set_scene(scene("center"))
    set_scene(scene("right"))

    aggregated, _ = get_scene()
    directions = {obj["direction"] for obj in aggregated["objects"]}
    assert directions == {"center", "right"}
    clear_scene()
