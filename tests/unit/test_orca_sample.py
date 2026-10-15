"""Spec 15.5: one OrcaSlicer G-code file from the owner. The test skips until the file is in samples/."""

from pathlib import Path

import pytest

from sliceranim.core.gcode_reader import read_gcode
from sliceranim.core.toolpaths import FEATURE_CODE

ORCA = Path(__file__).resolve().parents[2] / "samples" / "orca_sample.gcode"


@pytest.mark.skipif(not ORCA.is_file(), reason="needs samples/orca_sample.gcode from the owner")
def test_orcaslicer_gcode_reads():
    tp = read_gcode(ORCA)
    tp.validate()
    assert tp.meta["slicer"] == "OrcaSlicer"
    assert tp.layer_count > 1
    assert FEATURE_CODE["outer_wall"] in set(tp.feature.tolist())
    assert tp.total_time > 0
