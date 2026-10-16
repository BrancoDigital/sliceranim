"""Checks with the client sample. They skip when samples/sample.3mf or Bambu Studio is not present."""

import tempfile
import time
from pathlib import Path

import bpy
from helpers import SAMPLE_3MF, Skip, load, polygons_at, settings

from sliceranim.core.bambu_cli import DEFAULT_PATHS


def need_sample():
    if not SAMPLE_3MF.is_file():
        raise Skip("samples/sample.3mf is not present")
    if not Path(DEFAULT_PATHS["darwin"]).is_file():
        raise Skip("Bambu Studio is not installed")


def test_sample_loads_in_less_than_10_seconds():
    need_sample()
    start = time.perf_counter()
    load(SAMPLE_3MF)
    seconds = time.perf_counter() - start
    s = settings()
    print(f"    load: {seconds:.2f} s, {s.layer_count} layers, {s.point_count} points after merging")
    assert s.layer_count == 764
    assert bpy.context.scene.frame_end == 720
    assert seconds < 10.0


def test_sample_frame_evaluation_time():
    """Reports the time to evaluate a frame with viewport settings (spec 11.4). It does not fail."""
    need_sample()
    load(SAMPLE_3MF)
    for frame in (100, 400, 700):
        start = time.perf_counter()
        count = polygons_at(frame)
        print(f"    frame {frame}: {time.perf_counter() - start:.3f} s, {count} polygons")


def test_sample_render_smoke():
    """Spec 15.4: render three frames of the sample at 480x270."""
    need_sample()
    load(SAMPLE_3MF)
    s = settings()
    s.format_preset = "CUSTOM"
    s.custom_width, s.custom_height = 480, 270
    s.file_type = "PNG"
    scene = bpy.context.scene
    folder = Path(tempfile.mkdtemp(prefix="sliceranim_render_"))
    for frame in (60, 360, 680):
        scene.frame_set(frame)
        scene.render.filepath = str(folder / f"frame_{frame:04d}.png")
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(f"    frame {frame}: rendered in {time.perf_counter() - start:.2f} s")
        assert (folder / f"frame_{frame:04d}.png").is_file()
    print(f"    look at the frames in {folder}")


def test_sample_stl_from_the_blender_stl_import_slices_like_the_project():
    """Owner check: Use Selected Object on the imported sample.stl froze Blender and had no top layers."""
    stl = SAMPLE_3MF.with_name("sample.stl")
    if not stl.is_file():
        raise Skip("samples/sample.stl is not present")
    need_sample()
    bpy.ops.wm.stl_import(filepath=str(stl))
    start = time.perf_counter()
    assert bpy.ops.sliceranim.use_selected() == {"FINISHED"}
    seconds = time.perf_counter() - start
    s = settings()
    print(f"    use selected: {seconds:.2f} s, {s.layer_count} layers, {s.point_count} points after merging")
    assert (s.source_kind, s.layer_count, s.used_fallback) == ("MESH", 764, False)
    assert seconds < 20.0


def test_sample_stays_in_frame_outside_the_close_up_shot():
    """Owner check: the lower part of the sample was cut off in some shots."""
    from test_cameras import corners_out_of_frame

    need_sample()
    load(SAMPLE_3MF)
    scene = bpy.context.scene
    first_wide = scene.timeline_markers["SA Shot 2"].frame
    assert corners_out_of_frame(scene, range(first_wide, scene.frame_end + 1, 10)) == []
