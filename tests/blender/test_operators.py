import math
import tempfile
import zipfile
from pathlib import Path

import bpy
from helpers import CUBE, box_object, settings

from sliceranim.blender import importer, ui


def run_load(path, **extra):
    path = Path(path)
    return bpy.ops.sliceranim.load_file(directory=str(path.parent), files=[{"name": path.name}], **extra)


def expect_error(call, text: str) -> None:
    """In background mode, an operator that reports an error raises RuntimeError."""
    try:
        call()
    except RuntimeError as error:
        assert text in str(error), str(error)
        return
    raise AssertionError("the operator did not report an error")


def test_open_file_operator_loads_gcode():
    assert run_load(CUBE) == {"FINISHED"}
    assert settings().layer_count == 3


def test_open_file_shows_the_two_plate_error():
    path = Path(tempfile.mkdtemp()) / "two.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "")
        archive.writestr("Metadata/plate_2.gcode", "")
    expect_error(lambda: run_load(path), "This file has 2 plates. Export one plate from your slicer and try again.")
    assert settings().toolpath_object is None


def test_large_print_waits_for_confirmation():
    limit, ask = importer.POLYGON_LIMIT, ui.ask_to_confirm
    asked = []
    importer.POLYGON_LIMIT = 10
    ui.ask_to_confirm = lambda: asked.append(True)  # the popup needs a person to click
    try:
        assert run_load(CUBE) == {"CANCELLED"}
        assert asked == [True]
        assert settings().toolpath_object is None
        assert ui._pending["polygons"] == 42 * 6
        assert bpy.ops.sliceranim.confirm_large() == {"FINISHED"}
        assert settings().layer_count == 3
    finally:
        importer.POLYGON_LIMIT, ui.ask_to_confirm = limit, ask
        ui._pending.clear()


def test_use_selected_object_operator():
    box_object()
    assert bpy.ops.sliceranim.use_selected() == {"FINISHED"}
    assert settings().used_fallback


def test_reload_operator_and_missing_source():
    copy = Path(tempfile.mkdtemp()) / "gone.gcode"
    copy.write_text(CUBE.read_text())
    run_load(copy)
    settings().merge_angle = math.radians(5)
    assert bpy.ops.sliceranim.reload() == {"FINISHED"}
    copy.unlink()
    expect_error(bpy.ops.sliceranim.reload, f"Source file not found: {copy}. Open the file again.")


def test_rebuild_button_is_off_while_the_shot_list_is_bad():
    run_load(CUBE)
    assert bpy.ops.sliceranim.rebuild.poll()
    settings().shots[0].duration = 0.0
    assert not bpy.ops.sliceranim.rebuild.poll()
    assert not bpy.ops.sliceranim.render.poll()


def test_shot_buttons_add_move_and_remove():
    run_load(CUBE)
    s = settings()
    s.active_shot = 0
    bpy.ops.sliceranim.shot_add()
    assert len(s.shots) == 3 and s.active_shot == 1 and s.shots[1].style == "HOLD"
    bpy.ops.sliceranim.shot_move(direction="UP")
    assert s.active_shot == 0 and s.shots[0].style == "HOLD"
    bpy.ops.sliceranim.shot_remove()
    assert len(s.shots) == 2 and s.shots[0].style == "LINE"


def test_import_menu_entry_exists():
    assert ui.menu_import in bpy.types.TOPBAR_MT_file_import._dyn_ui_initialize()
