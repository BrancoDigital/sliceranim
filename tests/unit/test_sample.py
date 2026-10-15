"""Checks with the client sample. They skip when samples/sample.3mf or Bambu Studio is not present."""

import time
from pathlib import Path

import pytest

from sliceranim.core.bambu_cli import DEFAULT_PATHS, slice_project
from sliceranim.core.gcode_reader import read_gcode
from sliceranim.core.toolpaths import merge_points

SAMPLE_3MF = Path(__file__).resolve().parents[2] / "samples" / "sample.3mf"
pytestmark = pytest.mark.skipif(
    not SAMPLE_3MF.is_file() or not Path(DEFAULT_PATHS["darwin"]).is_file(),
    reason="needs samples/sample.3mf and Bambu Studio",
)


def test_sample_slices_reads_and_merges(tmp_path):
    start = time.perf_counter()
    gcode = slice_project(SAMPLE_3MF, tmp_path, DEFAULT_PATHS["darwin"])
    sliced = time.perf_counter()
    tp = read_gcode(gcode)
    read = time.perf_counter()
    merged = merge_points(tp, 2.0)
    done = time.perf_counter()
    print(
        f"\nslice {sliced - start:.2f} s, read {read - sliced:.2f} s, merge {done - read:.2f} s; "
        f"{tp.layer_count} layers, {tp.point_count} points before merging, {merged.point_count} after"
    )
    assert tp.layer_count == 764
    assert done - start < 10.0
