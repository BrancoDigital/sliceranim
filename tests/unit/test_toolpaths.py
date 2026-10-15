import math

import numpy as np
import pytest

from sliceranim.core.toolpaths import FEATURE_CODE, ToolpathBuilder, feature_code, pack


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
