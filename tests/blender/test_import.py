import tempfile
import zipfile
from pathlib import Path

import bpy
import numpy as np
from helpers import CUBE, box_object, keyframes, load, polygons_at, settings

from sliceranim.blender import importer, nodes
from sliceranim.core.errors import SlicerAnimError


def test_gcode_import_fills_the_source_summary():
    load(CUBE)
    s = settings()
    assert s.toolpath_object.name == "cube_3_layers Toolpaths"
    assert (s.layer_count, s.point_count) == (3, 42)
    assert s.slicer == "Bambu Studio 02.08.02.61"
    assert s.source_kind == "GCODE" and s.source_path == str(CUBE)
    np.testing.assert_allclose(s.file_color, (0.0129830, 0.2462013, 0.7835378), rtol=1e-4)  # #1E88E5
    assert abs(nodes.get_input(s.toolpath_object, "Profile Aspect") - 0.2 / 0.45) < 1e-6


def test_import_makes_the_short_print_shot_list_and_runs_rebuild():
    load(CUBE)
    scene = bpy.context.scene
    assert [(x.start_at_end, x.style, x.camera) for x in settings().shots] == [
        (False, "LINE", "TURNTABLE"),
        (True, "HOLD", "REVEAL"),
    ]
    assert (scene.frame_start, scene.frame_end) == (1, 720)
    assert [m.frame for m in scene.timeline_markers] == [1, 601]
    assert scene.render.engine == "BLENDER_EEVEE"


def test_the_build_grows_frame_by_frame():
    load(CUBE)
    assert polygons_at(720) == 30 * 4
    assert 0 < polygons_at(300) < 30 * 4
    obj = settings().toolpath_object
    progress = keyframes(obj, nodes.input_path(obj, "Progress"))
    assert len(progress) == 720 and progress[-1, 1] == 42
    assert np.all(np.diff(progress[:, 1]) >= 0)


def test_a_second_import_replaces_the_first():
    load(CUBE)
    load(CUBE)
    assert len([o for o in bpy.data.objects if o.name.endswith("Toolpaths")]) == 1


def test_sliced_3mf_loads_like_gcode():
    path = Path(tempfile.mkdtemp()) / "part.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", CUBE.read_text())
    load(path)
    assert settings().source_kind == "SLICED_3MF"
    assert settings().layer_count == 3


def test_mesh_object_goes_through_the_fallback_slicer():
    box = box_object(size=0.01)
    loaded = importer.read_mesh_object(bpy.context, box)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)
    s = settings()
    assert s.used_fallback and s.plate_centered_on_part
    assert (s.layer_count, s.source_kind) == (50, "MESH")
    assert box.hide_render
    assert len(settings().shots) == 4


def test_reload_reads_the_source_again_and_keeps_the_shots():
    load(CUBE)
    s = settings()
    s.shots[0].duration = 7.0
    s.merge_angle = 0.0
    loaded = importer.reload_source(bpy.context)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=True)
    assert s.shots[0].duration == 7.0
    assert s.built_merge_angle == 0.0


def test_reload_with_a_missing_source_raises_the_spec_error():
    copy = Path(tempfile.mkdtemp()) / "gone.gcode"
    copy.write_text(CUBE.read_text())
    load(copy)
    copy.unlink()
    try:
        importer.reload_source(bpy.context)
    except SlicerAnimError as error:
        assert str(error) == f"Source file not found: {copy}. Open the file again."
    else:
        raise AssertionError("no error")


def test_upper_case_file_extension_is_accepted():
    copy = Path(tempfile.mkdtemp()) / "PART.GCODE"
    copy.write_text(CUBE.read_text())
    load(copy)
    assert settings().layer_count == 3


def test_scaled_mesh_object_is_sliced_at_its_world_size():
    box = box_object(size=0.01)
    box.scale = (1.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    loaded = importer.read_mesh_object(bpy.context, box)
    assert loaded.tp.layer_count == 100  # 20 mm high at 0.2 mm per layer
