"""
실사용 시나리오 통합 테스트 (판단 레이어, 헤드리스).
'사람이 계속 머무름 / 접근 / 다중 / 떠났다 복귀' 등 연속 데이터 스트림을
danger.judge + scene_text + calibration 조합에 대해 검증.

※ 라이브 E2E(마이크/웹캠/오디오)는 하드웨어 필요 → manual_test_guide.md 참고.
"""

from ai_core.danger import judge
from ai_core.scene_text import scene_to_korean
from ai_core.calibration import process, median_filter

STAGE_EXP = 3  # 체험 단계


def obj(label="person", direction="center", distance="near", ratio=0.3, conf=0.9):
    return {
        "label": label, "direction": direction, "distance_est": distance,
        "bbox_ratio": ratio, "confidence": conf,
    }


def scene(objects, uc=None, target=None):
    return {"objects": objects, "ultrasonic_cm": uc, "ultrasonic_target": target}


# ===========================================================================
# 1. 사람이 계속 그 자리에 있음 (연속 동일 프레임)
# ===========================================================================
class TestPersonStays:
    def test_near_person_flags_danger_every_frame(self):
        """근접 사람이 10프레임 연속 → judge는 매 프레임 danger 반환.
        (= 루프단에서 쿨다운으로 중복 억제해야 함을 문서화)"""
        results = [judge(scene([obj()]), STAGE_EXP) for _ in range(10)]
        assert all(r is not None for r in results)
        assert all(r["object"] == "person" for r in results)

    def test_far_person_never_flags(self):
        """멀리 있는 사람이 계속 있어도 위험 아님."""
        results = [judge(scene([obj(distance="far", ratio=0.03)]), STAGE_EXP) for _ in range(10)]
        assert all(r is None for r in results)


# ===========================================================================
# 2. 사람이 점점 다가옴 (far → mid → near)
# ===========================================================================
class TestApproaching:
    def test_danger_only_when_near(self):
        far = judge(scene([obj(distance="far", ratio=0.03)]), STAGE_EXP)
        mid = judge(scene([obj(distance="mid", ratio=0.1)]), STAGE_EXP)
        near = judge(scene([obj(distance="near", ratio=0.3)]), STAGE_EXP)
        assert far is None
        assert mid is None          # near만 위험 후보
        assert near is not None and near["level"] == "warning"


# ===========================================================================
# 3. 여러 사람 — 가장 위험한 것 선택
# ===========================================================================
class TestMultiple:
    def test_picks_center_near(self):
        d = judge(scene([
            obj(direction="left", distance="near"),
            obj(direction="center", distance="near"),
        ]), STAGE_EXP)
        assert d is not None
        assert d["direction"] == "center"  # center 가중치 최고

    def test_mixed_labels(self):
        d = judge(scene([
            obj(label="chair", direction="right", distance="near"),
            obj(label="person", direction="center", distance="near"),
        ]), STAGE_EXP)
        assert d["object"] == "person"     # center near person이 최고점
        assert d["audio_file"] == "warn_person.wav"


# ===========================================================================
# 4. 초음파 긴급 — YOLO보다 우선
# ===========================================================================
class TestUltrasonicEmergency:
    def test_ultrasonic_overrides(self):
        d = judge(scene([obj(distance="far", ratio=0.02)], uc=20, target="person"), STAGE_EXP)
        assert d is not None
        assert d["level"] == "emergency"
        assert d["audio_file"] == "warn_emergency.wav"

    def test_above_threshold_no_emergency(self):
        d = judge(scene([obj(distance="far", ratio=0.02)], uc=200, target="person"), STAGE_EXP)
        assert d is None  # 200cm는 안전 + YOLO도 far


# ===========================================================================
# 5. 떠났다가 다시 나타남
# ===========================================================================
class TestLeaveReturn:
    def test_sequence(self):
        seq = [
            judge(scene([obj()]), STAGE_EXP),          # 있음 → 위험
            judge(scene([]), STAGE_EXP),               # 떠남 → None
            judge(scene([obj()]), STAGE_EXP),          # 복귀 → 위험
        ]
        assert seq[0] is not None
        assert seq[1] is None
        assert seq[2] is not None


# ===========================================================================
# 6. 장면 묘사 — 연속 동일 장면은 안정적(중복 억제 가능), 변하면 달라짐
# ===========================================================================
class TestSceneTextStream:
    def test_stable_under_sustained(self):
        s = scene([obj(label="person", direction="left", distance="near")])
        texts = {scene_to_korean(s) for _ in range(5)}
        assert len(texts) == 1  # 동일 장면 → 동일 텍스트 (fingerprint 중복 억제 가능)

    def test_changes_when_scene_changes(self):
        t1 = scene_to_korean(scene([obj(direction="left")]))
        t2 = scene_to_korean(scene([obj(direction="right")]))
        assert t1 != t2


# ===========================================================================
# 7. 초음파 연속 노이즈 스트림 — 보정/필터 안정성
# ===========================================================================
class TestUltrasonicStream:
    def test_noisy_stream_median_stable(self):
        # 30cm 근처 측정에 스파이크 섞임 → 중앙값은 ~30 유지
        readings = [30, 31, 500, 29, 30]   # 500 = 반사 오류
        assert process(readings, offset=0) == 30

    def test_offset_applied_in_stream(self):
        # 센서가 2cm 낮게 읽음 → offset +2 보정
        assert process([28, 29, 28], offset=2) == 30

    def test_all_invalid_stream(self):
        assert median_filter([-1, 0, 999, 1000]) is None
