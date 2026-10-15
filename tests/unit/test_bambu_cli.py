import json
import subprocess

import pytest

from sliceranim.core.bambu_cli import DEFAULT_PATHS, find_bambu, slice_command, slice_project
from sliceranim.core.errors import BAMBU_NOT_FOUND, SlicerAnimError


class FakeBambu:
    """Stands in for subprocess.run. It writes the files that Bambu Studio writes."""

    def __init__(self, result: dict | None, gcode: str | None = "; CHANGE_LAYER\n", returncode: int = 0):
        self.result = result
        self.gcode = gcode
        self.returncode = returncode
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        out_dir = command[command.index("--outputdir") + 1]
        from pathlib import Path

        if self.result is not None:
            (Path(out_dir) / "result.json").write_text(json.dumps(self.result))
        if self.gcode is not None:
            (Path(out_dir) / "plate_1.gcode").write_text(self.gcode)
        return subprocess.CompletedProcess(command, self.returncode, "", "")


def test_slice_command_matches_the_spec(tmp_path):
    command = slice_command(tmp_path / "BambuStudio", tmp_path / "p.3mf", tmp_path / "out")
    assert command[1:] == ["--slice", "1", "--outputdir", str(tmp_path / "out"),
                           "--export-3mf", "sliced.gcode.3mf", str(tmp_path / "p.3mf")]


def test_successful_slice_returns_plate_1_gcode(tmp_path):
    fake = FakeBambu({"return_code": 0, "error_string": "Success."})
    gcode = slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)
    assert gcode == tmp_path / "out" / "plate_1.gcode"
    assert len(fake.calls) == 1


def test_failed_slice_shows_error_string(tmp_path):
    fake = FakeBambu({"return_code": -50, "error_string": "Nothing to be sliced"}, gcode=None)
    with pytest.raises(SlicerAnimError, match="Slicing failed: Nothing to be sliced"):
        slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)


def test_missing_result_json_is_a_slicing_failure(tmp_path):
    fake = FakeBambu(None, gcode=None, returncode=139)
    with pytest.raises(SlicerAnimError, match="exit code 139"):
        slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)


def test_stale_output_from_an_earlier_run_is_not_used(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "plate_1.gcode").write_text("old")
    fake = FakeBambu({"return_code": 0}, gcode=None)
    with pytest.raises(SlicerAnimError, match="wrote no plate_1.gcode"):
        slice_project(tmp_path / "p.3mf", out, tmp_path / "BambuStudio", run=fake)


def test_find_bambu_prefers_the_preference_path(tmp_path):
    program = tmp_path / "MyBambu"
    program.write_text("")
    assert find_bambu(str(program), platform="darwin") == program


def test_find_bambu_raises_when_nothing_exists(tmp_path):
    with pytest.raises(SlicerAnimError, match=BAMBU_NOT_FOUND):
        find_bambu(str(tmp_path / "missing"), platform="linux")


def test_default_paths_match_the_spec():
    assert DEFAULT_PATHS["darwin"] == "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
