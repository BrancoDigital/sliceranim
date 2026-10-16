import json
import subprocess

import pytest

from sliceranim.core.bambu_cli import (
    DEFAULT_PATHS,
    DEFAULT_PRESETS,
    find_bambu,
    flat_preset,
    model_slice_command,
    profiles_dir,
    slice_command,
    slice_model,
    slice_project,
    write_presets,
)
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


def make_profiles(root):
    """A small copy of the BBL system presets: one chain per kind."""
    files = {
        "machine/fdm_machine_common.json": {"name": "fdm_machine_common", "printable_height": "250", "from": "system"},
        "machine/Printer.json": {"name": "Printer", "inherits": "fdm_machine_common", "nozzle_diameter": ["0.4"]},
        "process/fdm_process_common.json": {"name": "fdm_process_common", "layer_height": "0.1", "wall_loops": "2"},
        "process/Standard.json": {"name": "Standard", "inherits": "fdm_process_common", "layer_height": "0.2"},
        "filament/PLA-PETG.json": {"name": "PLA/PETG", "filament_type": ["PLA"]},
    }
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    (root / "process" / "broken.json").write_text("{not json")
    return root


def test_flat_preset_resolves_the_inherits_chain(tmp_path):
    preset = flat_preset(make_profiles(tmp_path), "process", "Standard")
    assert (preset["layer_height"], preset["wall_loops"]) == ("0.2", "2")
    assert (preset["name"], preset["inherits"], preset["from"]) == ("Standard", "Standard", "User")


def test_flat_preset_finds_a_name_that_is_not_the_file_name(tmp_path):
    assert flat_preset(make_profiles(tmp_path), "filament", "PLA/PETG")["filament_type"] == ["PLA"]


def test_unknown_preset_names_the_preset(tmp_path):
    with pytest.raises(SlicerAnimError, match="Bambu Studio preset not found: Nope. Check the preset names"):
        flat_preset(make_profiles(tmp_path), "process", "Nope")


def test_write_presets_sets_the_layer_height(tmp_path):
    presets = {"machine": "Printer", "process": "Standard", "filament": "PLA/PETG"}
    files = write_presets(make_profiles(tmp_path / "BBL"), tmp_path / "out", presets, 0.28)
    assert [f.name for f in files] == ["machine.json", "process.json", "filament.json"]
    assert json.loads(files[1].read_text())["layer_height"] == "0.28"


def test_model_slice_command(tmp_path):
    out = tmp_path / "out"
    command = model_slice_command(tmp_path / "BambuStudio", tmp_path / "part.stl", out,
                                  [out / "machine.json", out / "process.json", out / "filament.json"])
    assert command[1:] == [
        "--slice", "1", "--outputdir", str(out),
        "--load-settings", f"{out / 'machine.json'};{out / 'process.json'}",
        "--load-filaments", str(out / "filament.json"),
        "--arrange", "1", "--orient", "0",
        str(tmp_path / "part.stl"),
    ]


def test_slice_model_returns_plate_1_gcode(tmp_path):
    fake = FakeBambu({"return_code": 0, "error_string": "Success."})
    presets = {"machine": "Printer", "process": "Standard", "filament": "PLA/PETG"}
    gcode = slice_model(tmp_path / "part.stl", tmp_path / "out", tmp_path / "BambuStudio", presets, 0.2,
                        profiles=make_profiles(tmp_path / "BBL"), run=fake)
    assert gcode == tmp_path / "out" / "plate_1.gcode"
    assert "--load-settings" in fake.calls[0]


def test_slice_model_failure_shows_error_string(tmp_path):
    fake = FakeBambu({"return_code": -100, "error_string": "Plate empty"}, gcode=None)
    presets = {"machine": "Printer", "process": "Standard", "filament": "PLA/PETG"}
    with pytest.raises(SlicerAnimError, match="Slicing failed: Plate empty"):
        slice_model(tmp_path / "part.stl", tmp_path / "out", tmp_path / "BambuStudio", presets, 0.2,
                    profiles=make_profiles(tmp_path / "BBL"), run=fake)


def test_profiles_dir_finds_the_macos_and_windows_layouts(tmp_path):
    mac = tmp_path / "BambuStudio.app" / "Contents"
    (mac / "Resources" / "profiles" / "BBL").mkdir(parents=True)
    assert profiles_dir(mac / "MacOS" / "BambuStudio") == mac / "Resources" / "profiles" / "BBL"
    win = tmp_path / "Bambu Studio"
    (win / "resources" / "profiles" / "BBL").mkdir(parents=True)
    assert profiles_dir(win / "bambu-studio.exe") == win / "resources" / "profiles" / "BBL"
    with pytest.raises(SlicerAnimError, match="presets not found"):
        profiles_dir(tmp_path / "elsewhere" / "BambuStudio")


def test_default_presets_are_the_p1s_standard_pla_set():
    assert DEFAULT_PRESETS == {
        "machine": "Bambu Lab P1S 0.4 nozzle",
        "process": "0.20mm Standard @BBL X1C",
        "filament": "Bambu PLA Basic @BBL X1C",
    }
