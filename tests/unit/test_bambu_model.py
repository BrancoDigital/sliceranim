"""Slice a mesh with the real Bambu Studio and its system presets. Skips when Bambu Studio is not installed."""

from pathlib import Path

import numpy as np
import pytest

from sliceranim.core.bambu_cli import DEFAULT_PATHS, DEFAULT_PRESETS, slice_model
from sliceranim.core.gcode_reader import read_gcode
from sliceranim.core.mesh_slicer import write_stl
from sliceranim.core.toolpaths import FEATURE_CODE

pytestmark = pytest.mark.skipif(not Path(DEFAULT_PATHS["darwin"]).is_file(), reason="needs Bambu Studio")


def box_stl(path: Path) -> Path:
    v = np.array([[0, 0, 0], [20, 0, 0], [20, 20, 0], [0, 20, 0],
                  [0, 0, 10], [20, 0, 10], [20, 20, 10], [0, 20, 10]], dtype=np.float64)
    t = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    write_stl(path, v, t)
    return path


def test_a_box_slices_with_walls_infill_and_top_surface(tmp_path):
    gcode = slice_model(box_stl(tmp_path / "box.stl"), tmp_path / "out", DEFAULT_PATHS["darwin"], DEFAULT_PRESETS, 0.2)
    tp = read_gcode(gcode)
    assert tp.layer_count == 50
    found = set(np.unique(tp.feature).tolist())
    assert {FEATURE_CODE["outer_wall"], FEATURE_CODE["sparse_infill"], FEATURE_CODE["top_surface"]} <= found


def test_layer_height_sets_the_layer_count(tmp_path):
    gcode = slice_model(box_stl(tmp_path / "box.stl"), tmp_path / "out", DEFAULT_PATHS["darwin"], DEFAULT_PRESETS, 0.25)
    assert read_gcode(gcode).layer_count == 40
