import numpy as np
import pytest

from sliceranim.core.timing import (
    CLOSE_UP,
    HOLD,
    LAYER,
    LINE,
    REVEAL,
    RISING,
    TURNTABLE,
    Shot,
    default_shots,
    plan_frames,
    progress_at_time,
    state_at,
    validate_shots,
)
from sliceranim.core.toolpaths import ToolpathBuilder


def ladder(layers=10, points_per_layer=5, seconds_per_strand=1.0):
    """One straight run per layer along X. Each strand takes `seconds_per_strand`."""
    b = ToolpathBuilder()
    t = 0.0
    for k in range(layers):
        b.end_run()
        for i in range(points_per_layer):
            if i:
                t += seconds_per_strand
            b.add_point(float(i), 0.0, 0.2 * (k + 1), time=t, layer=k, feature=1, tool=0, width=0.45,
                        height=0.2, object_id=0)
    return b.build()


def test_default_shot_list_for_the_sample_layer_count():
    shots = default_shots(764)
    assert [(s.start_layer, s.duration, s.style, s.camera) for s in shots] == [
        (1, 4.0, LINE, CLOSE_UP),
        (6, 12.0, LAYER, TURNTABLE),
        (760, 4.0, LINE, RISING),
        (None, 4.0, HOLD, REVEAL),
    ]
    assert validate_shots(shots, 764) == []


@pytest.mark.parametrize("layers", [1, 5, 10, 11, 19])
def test_short_prints_get_the_two_shot_list_and_it_is_valid(layers):
    shots = default_shots(layers)
    assert [(s.start_layer, s.duration, s.style, s.camera) for s in shots] == [
        (1, 20.0, LINE, TURNTABLE),
        (None, 4.0, HOLD, REVEAL),
    ]
    assert validate_shots(shots, layers) == []


def test_twenty_layers_get_the_four_shot_list_and_it_is_valid():
    assert len(default_shots(20)) == 4
    assert validate_shots(default_shots(20), 20) == []


def test_each_rule_reports_its_row():
    rules = lambda shots: [(p.row, p.rule) for p in validate_shots(shots, 100)]
    assert rules([Shot(2, 1, LINE, "HERO")]) == [(0, 1)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(50, 1, LINE, "HERO"), Shot(40, 1, LINE, "HERO")]) == [(2, 2)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(1, 1, LINE, "HERO")]) == [(0, 3)]
    assert rules([Shot(1, 1, HOLD, "HERO"), Shot(1, 1, LINE, "HERO")]) == []
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(None, 1, LINE, "HERO")]) == [(1, 4)]
    assert rules([Shot(1, 0, LINE, "HERO")]) == [(0, 5)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(101, 1, LINE, "HERO")]) == [(1, 0)]
    assert rules([]) == [(-1, 0)]


def test_progress_at_time_follows_the_point_times():
    tp = ladder(layers=1, points_per_layer=3)  # times 0, 1, 2
    np.testing.assert_allclose(progress_at_time(tp, [0.0, 0.5, 1.0, 1.25, 2.0, 9.0]), [1, 1.5, 2, 2.25, 3, 3])


def test_state_at_gives_the_tip_of_the_growing_strand():
    tp = ladder(layers=2, points_per_layer=3)
    layer, head = state_at(tp, np.array([1.5, 3.0, 3.5, 6.0]))
    np.testing.assert_allclose(head[0], [0.5, 0, 0.2])  # half way from point 0 to point 1
    np.testing.assert_allclose(head[1], [2, 0, 0.2])  # point 2 is the newest
    np.testing.assert_allclose(head[2], [0, 0, 0.4])  # point 3 starts a run: no strand grows into it
    np.testing.assert_allclose(layer, [0, 0, 1, 1])


def test_frames_add_up_to_the_sum_of_durations():
    tp = ladder(layers=30)
    plan = plan_frames(tp, default_shots(30), fps=30)
    assert plan.frame_count == 24 * 30
    assert plan.shot_first_frame == [1, 121, 481, 601]
    assert plan.shot_frame_count == [120, 360, 120, 120]


def test_line_shot_runs_print_time_linearly_and_stops_before_the_next_shot():
    tp = ladder(layers=10, points_per_layer=5)  # 4 s per layer, 40 s in all
    plan = plan_frames(tp, [Shot(1, 2.0, LINE, "HERO"), Shot(3, 1.0, HOLD, "HERO")], fps=4)
    # Shot 1 covers layers 1 and 2: print time 0 to 8 s over 8 frames, 1 s per frame.
    # At 4 s, point 5 starts layer 2 at the same time as point 4 ends layer 1, so both count.
    np.testing.assert_allclose(plan.progress[:8], [1, 2, 3, 4, 6, 7, 8, 9])
    # Hold at layer 3 shows layers 1 and 2 complete: 10 points.
    np.testing.assert_allclose(plan.progress[8:], 10)


def test_layer_shot_shows_complete_layers_only():
    tp = ladder(layers=10, points_per_layer=5)
    plan = plan_frames(tp, [Shot(1, 1.0, LAYER, "HERO"), Shot(None, 1.0, HOLD, "HERO")], fps=5)
    # 10 layers over 5 frames: 0, 2, 4, 6, 8 layers complete.
    np.testing.assert_allclose(plan.progress[:5], [0, 10, 20, 30, 40])
    np.testing.assert_allclose(plan.progress[5:], 50)


def test_the_last_shot_ends_with_the_whole_print():
    tp = ladder(layers=10)
    for style in (LINE, LAYER):
        plan = plan_frames(tp, [Shot(1, 1.0, style, "HERO")], fps=10)
        assert plan.progress[-1] == tp.point_count


def test_a_line_shot_with_no_print_time_moves_by_point_count():
    tp = ladder(layers=4, points_per_layer=3, seconds_per_strand=0.0)
    plan = plan_frames(tp, [Shot(1, 1.0, LINE, "HERO")], fps=4)
    np.testing.assert_allclose(plan.progress, [3, 6, 9, 12])


def test_hold_mid_print_stays_at_its_start_layer():
    tp = ladder(layers=10, points_per_layer=5)
    shots = [Shot(1, 1.0, LINE, "HERO"), Shot(4, 1.0, HOLD, "HERO"), Shot(4, 1.0, LINE, "HERO")]
    plan = plan_frames(tp, shots, fps=2)
    np.testing.assert_allclose(plan.progress[2:4], 15)  # layers 1 to 3 complete
    assert plan.progress[-1] == tp.point_count
    np.testing.assert_allclose(plan.current_layer[2:4], 2)  # newest point is in layer index 2


def test_a_very_short_shot_still_gets_one_frame():
    tp = ladder(layers=10)
    plan = plan_frames(tp, [Shot(1, 0.01, LINE, "HERO"), Shot(None, 1.0, HOLD, "HERO")], fps=30)
    assert plan.shot_frame_count == [1, 30]
