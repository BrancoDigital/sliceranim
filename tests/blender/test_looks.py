import json

import bpy
import numpy as np
from helpers import settings
from test_strands import make_object

from sliceranim.blender import keys, looks, output


def setup():
    tp, obj = make_object()
    s = settings()
    s.toolpath_object = obj
    s.head_object = looks.put_object(bpy.context.scene, "SA Print Head", None)
    s.part_center = (5.0, 5.0, 0.3)
    s.part_radius = 7.1
    return s


def principled(name):
    material = bpy.data.materials[name]
    return next(n for n in material.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def test_hex_to_linear():
    np.testing.assert_allclose(looks.hex_to_linear("#808080"), [0.2158605] * 3, rtol=1e-5)
    np.testing.assert_allclose(looks.hex_to_linear("#FF6A1A"), [1.0, 0.1441285, 0.0103298], rtol=1e-4)


def test_default_look_makes_backdrop_and_three_lights_only():
    setup()
    looks.apply(bpy.context.scene)
    names = {o.name for o in bpy.data.collections["Slicer Animator"].objects}
    assert {"SA Backdrop", "SA Key Light", "SA Fill Light", "SA Rim Light"} <= names
    assert "SA Plate Mat" not in names and "SA Nozzle Tip" not in names


def test_finish_and_color_reach_the_filament_material():
    s = setup()
    s.use_file_color = False
    s.color = (1.0, 0.0, 0.0)
    s.finish = "TRANSLUCENT"
    bsdf = principled("SA Filament")
    assert tuple(bsdf.inputs["Base Color"].default_value)[:3] == (1.0, 0.0, 0.0)
    assert abs(bsdf.inputs["Transmission Weight"].default_value - 0.7) < 1e-6


def test_highlight_off_sets_the_emission_strength_to_zero():
    s = setup()
    s.highlight = False
    strength = bpy.data.materials["SA Filament"].node_tree.nodes["SA Highlight Strength"]
    assert strength.inputs[1].default_value == 0.0


def test_ghost_material_uses_opacity_and_dithered_blending():
    s = setup()
    s.ghost_opacity = 0.3
    assert abs(principled("SA Ghost").inputs["Alpha"].default_value - 0.3) < 1e-6
    assert bpy.data.materials["SA Ghost"].surface_render_method == "DITHERED"


def test_plate_mat_sits_on_the_bambu_plate_center_or_under_the_part():
    s = setup()
    s.plate_mat = True
    plate = bpy.data.objects["SA Plate Mat"]
    np.testing.assert_allclose(plate.location, (0.128, 0.128, 0.0))
    s.plate_centered_on_part = True
    looks.apply(bpy.context.scene)
    np.testing.assert_allclose(plate.location, (0.005, 0.005, 0.0))
    s.plate_mat = False
    assert "SA Plate Mat" not in bpy.data.objects


def test_nozzle_tip_follows_the_head_and_shows_in_line_shots_only():
    s = setup()
    s.line_frame_ranges = json.dumps([[1, 120], [481, 600]])
    s.nozzle = True
    nozzle = bpy.data.objects["SA Nozzle Tip"]
    assert nozzle.parent == s.head_object
    data = nozzle.animation_data
    from bpy_extras import anim_utils

    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find("hide_render")
    points = [tuple(k.co) for k in curve.keyframe_points]
    assert points == [(1.0, 0.0), (121.0, 1.0), (481.0, 0.0), (601.0, 1.0)]
    assert all(k.interpolation == "CONSTANT" for k in curve.keyframe_points)


def test_output_presets():
    s = setup()
    render = bpy.context.scene.render
    output.apply(bpy.context.scene)
    assert (render.resolution_x, render.resolution_y, render.fps) == (1920, 1080, 30)
    assert render.image_settings.media_type == "VIDEO"
    assert render.ffmpeg.codec == "H264"
    assert render.filepath == "//renders/cube_"
    s.format_preset = "UHD"
    s.fps = "60"
    s.file_type = "PNG"
    assert (render.resolution_x, render.resolution_y, render.fps) == (3840, 2160, 60)
    assert render.image_settings.file_format == "PNG"
    s.format_preset = "CUSTOM"
    s.custom_width, s.custom_height = 1080, 1920
    assert (render.resolution_x, render.resolution_y) == (1080, 1920)


def test_keys_write_replaces_old_keys():
    obj = bpy.data.objects.new("e", None)
    bpy.context.scene.collection.objects.link(obj)
    keys.write(obj, "location", [1, 2, 3], [0.0, 1.0, 2.0], keys.LINEAR, index=0)
    keys.write(obj, "location", [5, 6], [3.0, 4.0], keys.CONSTANT, index=0)
    bpy.context.scene.frame_set(6)
    assert obj.location.x == 4.0
    keys.remove(obj, {"location"})
    assert obj.animation_data.action is not None


def test_output_folder_is_made_next_to_a_saved_file():
    """Owner check: the panel showed //renders/ in red because the folder did not exist yet."""
    import tempfile
    from pathlib import Path

    from helpers import CUBE, load

    folder = Path(tempfile.mkdtemp(prefix="sliceranim_saved_"))
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "test.blend"))
    load(CUBE)
    assert (folder / "renders").is_dir()


def test_output_folder_is_not_made_for_an_unsaved_file():
    from helpers import CUBE, load

    load(CUBE)  # "//renders/" has no base folder yet. Nothing is made and nothing fails.
    assert settings().output_folder == "//renders/"


def test_output_folder_is_made_when_you_save_the_file_after_loading():
    import tempfile
    from pathlib import Path

    from helpers import CUBE, load

    load(CUBE)
    folder = Path(tempfile.mkdtemp(prefix="sliceranim_saved_"))
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "test.blend"))
    assert (folder / "renders").is_dir()
