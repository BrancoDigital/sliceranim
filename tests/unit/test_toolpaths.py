import math

import numpy as np
import pytest

from sliceranim.core.toolpaths import (
    FEATURE_CODE,
    ToolpathBuilder,
    estimate_polygons,
    feature_code,
    merge_points,
    pack,
)


def build(runs, layer_of_run=None, feature=1, width=0.45):
    """Make a ToolpathSet from a list of runs. Each run is a list of (x, y, z)."""
    b = ToolpathBuilder()
    t = 0.0
    for r, run in enumerate(runs):
        b.end_run()
        previous = None
        for x, y, z in run:
            if previous is not None:
                t += math.dist(previous, (x, y, z)) / 10.0
            b.add_point(x, y, z, time=t, layer=(layer_of_run or [0] * len(runs))[r], feature=feature,
                        tool=0, width=width, height=0.2, object_id=0)
            previous = (x, y, z)
    return b.build({"slicer": "test"})


def test_feature_labels_map_to_codes():
    assert feature_code("Outer wall") == FEATURE_CODE["outer_wall"]
    assert feature_code(" floating vertical shell ") == FEATURE_CODE["inner_wall"]
    assert feature_code("Support transition") == FEATURE_CODE["support"]
    assert feature_code("Skirt") == FEATURE_CODE["brim_skirt"]
    assert feature_code("Undefined") == FEATURE_CODE["other"]
    assert feature_code("Flush") == 0


def test_builder_tracks_runs_and_layers():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2)], [(0, 1, 0.2), (1, 1, 0.2), (2, 1, 0.2)], [(0, 0, 0.4), (1, 0, 0.4)]],
               layer_of_run=[0, 0, 1])
    assert tp.point_count == 7
    assert tp.run_start.tolist() == [0, 2, 5]
    assert tp.layer_start.tolist() == [0, 5]
    assert tp.layer_count == 2
    np.testing.assert_allclose(tp.layer_z, [0.2, 0.4])
    assert tp.position.dtype == np.float32
    assert tp.time.dtype == np.float64


def test_pack_numbers_layers_again_without_gaps():
    tp = pack(position=np.zeros((4, 3)), layer=[3, 3, 7, 7], feature=[1] * 4, tool=[0] * 4, width=[0.4] * 4,
              height=[0.2] * 4, time=[0, 1, 1, 2], object_id=[0] * 4, run_start=[0, 2],
              layer_z_by_number={3: 0.6, 7: 1.4})
    assert tp.layer.tolist() == [0, 0, 1, 1]
    np.testing.assert_allclose(tp.layer_z, [0.6, 1.4])


def test_validate_rejects_a_layer_that_starts_inside_a_run():
    with pytest.raises(ValueError, match="each layer must start a new run"):
        pack(position=np.zeros((3, 3)), layer=[0, 0, 1], feature=[1] * 3, tool=[0] * 3, width=[0.4] * 3,
             height=[0.2] * 3, time=[0, 1, 2], object_id=[0] * 3, run_start=[0])


def test_merge_removes_straight_points_and_keeps_corners():
    straight = [(float(x), 0.0, 0.2) for x in range(6)] + [(5.0, 5.0, 0.2)]
    tp = build([straight])
    merged = merge_points(tp, 2.0)
    np.testing.assert_allclose(merged.position, [[0, 0, 0.2], [5, 0, 0.2], [5, 5, 0.2]])
    assert merged.total_time == pytest.approx(tp.total_time)
    assert merged.meta["merge_angle"] == 2.0


def test_merge_keeps_run_ends_and_the_angle_zero_turns_it_off():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2), (2, 0, 0.2)], [(0, 1, 0.2), (1, 1, 0.2), (2, 1, 0.2)]])
    merged = merge_points(tp, 2.0)
    assert merged.point_count == 4
    assert merged.run_start.tolist() == [0, 2]
    assert merge_points(tp, 0.0).point_count == 6


def test_merge_does_not_flatten_a_gentle_curve():
    # A circle of radius 20 split into 1 degree steps. Each step turns by 1 degree only.
    angles = np.radians(np.arange(0, 361, 1.0))
    circle = [(20 * math.cos(a), 20 * math.sin(a), 0.2) for a in angles]
    merged = merge_points(build([circle]), 2.0)
    # Measured from the last kept point, the turn reaches 2 degrees after a few steps.
    assert 90 <= merged.point_count <= 200
    radius = np.hypot(merged.position[:, 0], merged.position[:, 1])
    np.testing.assert_allclose(radius, 20.0, atol=1e-3)


def test_merge_keeps_a_point_where_the_width_changes():
    b = ToolpathBuilder()
    for i, w in enumerate([0.4, 0.4, 0.5, 0.5]):
        b.add_point(float(i), 0.0, 0.2, time=float(i), layer=0, feature=1, tool=0, width=w, height=0.2, object_id=0)
    merged = merge_points(b.build(), 2.0)
    assert merged.width.tolist() == pytest.approx([0.4, 0.4, 0.5, 0.5])


def test_estimate_polygons_counts_the_ghost_shell():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2)]], feature=FEATURE_CODE["outer_wall"])
    assert estimate_polygons(tp, 6, ghost=False) == 12
    assert estimate_polygons(tp, 6, ghost=True) == 20
