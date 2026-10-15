import zipfile

import pytest

from sliceranim.core.errors import NOT_A_PRINT_3MF, SlicerAnimError
from sliceranim.core.threemf import PROJECT, SLICED, inspect_3mf, read_sliced_3mf, require_one_plate


def make_3mf(path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("3D/3dmodel.model", "<model/>")
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def test_sliced_3mf_with_one_plate(tmp_path, fixtures):
    gcode = (fixtures / "cube_3_layers.gcode").read_text()
    path = make_3mf(tmp_path / "part.gcode.3mf", {"Metadata/plate_1.gcode": gcode, "Metadata/plate_1.gcode.md5": "x"})
    info = inspect_3mf(path)
    assert info.kind == SLICED
    assert info.plate_count == 1
    assert info.gcode_names == ("Metadata/plate_1.gcode",)
    tp = read_sliced_3mf(path)
    assert tp.layer_count == 3
    assert tp.meta["source_path"].endswith("part.gcode.3mf")


def test_sliced_3mf_with_two_plates_is_refused(tmp_path):
    path = make_3mf(tmp_path / "two.gcode.3mf", {"Metadata/plate_2.gcode": "", "Metadata/plate_1.gcode": ""})
    info = inspect_3mf(path)
    assert info.plate_count == 2
    assert info.gcode_names == ("Metadata/plate_1.gcode", "Metadata/plate_2.gcode")
    with pytest.raises(SlicerAnimError, match="This file has 2 plates. Export one plate"):
        read_sliced_3mf(path)


def test_project_plate_count_comes_from_model_settings(tmp_path):
    config = "<config><object id='2'/><plate><metadata/></plate><plate></plate><plate/></config>"
    path = make_3mf(tmp_path / "project.3mf", {"Metadata/model_settings.config": config})
    info = inspect_3mf(path)
    assert info.kind == PROJECT
    assert info.plate_count == 3
    with pytest.raises(SlicerAnimError, match="This file has 3 plates"):
        require_one_plate(info)


def test_3mf_without_gcode_or_project_data_is_refused(tmp_path):
    path = make_3mf(tmp_path / "plain.3mf", {})
    with pytest.raises(SlicerAnimError, match=NOT_A_PRINT_3MF):
        inspect_3mf(path)


def test_a_file_that_is_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "broken.3mf"
    path.write_text("not a zip")
    with pytest.raises(SlicerAnimError, match=NOT_A_PRINT_3MF):
        inspect_3mf(path)
