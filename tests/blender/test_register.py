import bpy
from helpers import settings


def test_register_adds_the_scene_settings():
    assert settings().toolpath_object is None
    assert settings().fps == "30"
    assert settings().strand_sides == "6"
    assert settings().viewport_strand_sides == "4"
    assert abs(settings().ghost_opacity - 0.15) < 1e-6


def test_shot_items_have_the_spec_defaults():
    shot = settings().shots.add()
    assert (shot.duration, shot.style, shot.camera) == (4.0, "LINE", "TURNTABLE")
    assert shot.closeup_target == "LAYER" and not shot.closeup_dof
    assert shot.closeup_smoothing == 15
