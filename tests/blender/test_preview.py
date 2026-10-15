import bpy
from helpers import CUBE, load, settings

from sliceranim.blender import preview, shots


def view3d_space():
    return preview.find_view3d(bpy.context.screen).spaces.active


def test_preview_switches_the_view_and_exit_restores_it():
    load(CUBE)
    space = view3d_space()
    space.shading.type = "SOLID"
    space.region_3d.view_perspective = "PERSP"
    bpy.context.scene.sync_mode = "AUDIO_SYNC"
    assert bpy.ops.sliceranim.preview() == {"FINISHED"}
    assert settings().preview_active
    assert space.shading.type == "MATERIAL"
    assert space.shading.use_scene_lights and space.shading.use_scene_world
    assert space.region_3d.view_perspective == "CAMERA"
    assert bpy.context.scene.sync_mode == "FRAME_DROP"
    assert bpy.ops.sliceranim.preview() == {"FINISHED"}  # the same button is Exit Preview now
    assert not settings().preview_active
    assert space.shading.type == "SOLID"
    assert space.region_3d.view_perspective == "PERSP"
    assert bpy.context.scene.sync_mode == "AUDIO_SYNC"


def test_preview_runs_rebuild_first_when_the_shots_changed():
    load(CUBE)
    settings().shots[0].duration = 10.0
    assert shots.needs_rebuild(bpy.context.scene)
    bpy.ops.sliceranim.preview()
    assert not shots.needs_rebuild(bpy.context.scene)
    assert bpy.context.scene.frame_end == 14 * 30
    bpy.ops.sliceranim.preview()


def test_preview_is_off_without_a_toolpath_object():
    assert not bpy.ops.sliceranim.preview.poll()
