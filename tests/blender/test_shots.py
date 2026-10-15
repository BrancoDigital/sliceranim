import json

import bpy
import numpy as np
from helpers import CUBE, keyframes, load, settings

from sliceranim.blender import shots
from sliceranim.core.errors import SlicerAnimError


def test_invalid_shot_list_is_reported_and_blocks_rebuild():
    load(CUBE)
    settings().shots[0].start_layer = 2
    assert [(p.row, p.rule) for p in shots.problems(bpy.context.scene)] == [(0, 1)]
    try:
        shots.rebuild(bpy.context.scene)
    except SlicerAnimError as error:
        assert str(error) == "The first shot must start at layer 1."
    else:
        raise AssertionError("rebuild did not refuse the bad shot list")


def test_rebuild_replaces_only_its_own_markers_and_cameras():
    load(CUBE)
    scene = bpy.context.scene
    scene.timeline_markers.new("My marker", frame=50)
    shots.rebuild(scene)
    shots.rebuild(scene)
    assert sorted(m.name for m in scene.timeline_markers) == ["My marker", "SA Shot 1", "SA Shot 2"]
    assert len([o for o in bpy.data.objects if o.type == "CAMERA"]) == 2
    assert all(m.camera is not None for m in scene.timeline_markers if m.name.startswith("SA Shot"))


def test_frame_rate_and_durations_set_the_frame_range():
    load(CUBE)
    settings().fps = "24"
    settings().shots[0].duration = 5.0
    shots.rebuild(bpy.context.scene)
    assert bpy.context.scene.frame_end == 24 * 9
    assert bpy.context.scene.render.fps == 24


def test_line_shots_use_linear_keys_and_other_shots_constant_keys():
    load(CUBE)
    obj = settings().toolpath_object
    from bpy_extras import anim_utils
    from sliceranim.blender import nodes

    data = obj.animation_data
    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find(
        nodes.input_path(obj, "Progress")
    )
    assert curve.keyframe_points[0].interpolation == "LINEAR"
    assert curve.keyframe_points[650].interpolation == "CONSTANT"


def test_my_camera_needs_a_camera_object():
    load(CUBE)
    s = settings()
    s.shots[0].camera = "CUSTOM"
    assert [p.message for p in shots.problems(bpy.context.scene)] == ["Choose a camera object for My camera."]
    mine = bpy.data.objects.new("Mine", bpy.data.cameras.new("Mine"))
    bpy.context.scene.collection.objects.link(mine)
    s.shots[0].custom_camera = mine
    shots.rebuild(bpy.context.scene)
    assert bpy.context.scene.timeline_markers["SA Shot 1"].camera == mine


def test_nozzle_keys_follow_the_line_shots():
    load(CUBE)
    s = settings()
    s.nozzle = True
    assert json.loads(s.line_frame_ranges) == [[1, 600]]
    assert keyframes(bpy.data.objects["SA Nozzle Tip"], "hide_render").tolist() == [[1.0, 0.0], [601.0, 1.0]]


def test_head_moves_during_the_line_shot():
    load(CUBE)
    head = keyframes(settings().head_object, "location", 0)
    assert np.ptp(head[:600, 1]) > 0


def test_needs_rebuild_tracks_changes_that_rebuild_reads():
    load(CUBE)
    scene = bpy.context.scene
    assert not shots.needs_rebuild(scene)
    settings().shots[0].duration = 10.0
    assert shots.needs_rebuild(scene)
    shots.rebuild(scene)
    settings().format_preset = "SQUARE"  # cameras depend on the aspect ratio
    assert shots.needs_rebuild(scene)
