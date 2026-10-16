import math

import bpy
import numpy as np
from mathutils import Vector
from test_looks import setup

from sliceranim.blender import cameras, importer
from sliceranim.core.timing import Shot, plan_frames


def plan_for(s, rows):
    """Fill the shot list from (start, duration, style, camera) rows and plan the frames at 10 fps."""
    s.shots.clear()
    for start, duration, style, camera in rows:
        item = s.shots.add()
        item.start_at_end = start is None
        item.start_layer = start or 1
        item.duration, item.style, item.camera = duration, style, camera
    shots = [Shot(start, duration, style, camera) for start, duration, style, camera in rows]
    tp = importer.toolpath_from_object(s.toolpath_object)
    return plan_frames(tp, shots, 10), tp


def test_one_camera_per_shot_with_keys_on_its_own_frames():
    s = setup()
    plan, tp = plan_for(s, [(1, 1.0, "LINE", "CLOSE_UP"), (2, 1.0, "LAYER", "TURNTABLE"), (None, 1.0, "HOLD", "REVEAL")])
    made = cameras.build(bpy.context.scene, plan, tp)
    assert [c.name for c in made] == ["SA Shot 1 Camera", "SA Shot 2 Camera", "SA Shot 3 Camera"]
    assert all(c.get(cameras.TAG) for c in made)
    assert not made[0].data.dof.use_dof  # depth of field is off by default
    bpy.context.scene.frame_set(15)
    orbit = made[1].matrix_world.translation
    center = np.array(s.part_center) * 0.001
    _, distance = cameras.framing(bpy.context.scene)
    assert abs(np.linalg.norm(np.array(orbit) - center) - distance * 0.001) < 1e-6


def test_cameras_look_at_their_target():
    s = setup()
    plan, tp = plan_for(s, [(1, 1.0, "LAYER", "HERO"), (None, 1.0, "HOLD", "REVEAL")])
    made = cameras.build(bpy.context.scene, plan, tp)
    bpy.context.scene.frame_set(1)
    camera = made[0]
    forward = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    to_center = Vector(s.part_center) * 0.001 - camera.matrix_world.translation
    assert forward.angle(to_center) < math.radians(0.01)


def test_rebuilding_cameras_removes_the_old_ones():
    s = setup()
    plan, tp = plan_for(s, [(1, 1.0, "LAYER", "HERO"), (None, 1.0, "HOLD", "REVEAL")])
    cameras.build(bpy.context.scene, plan, tp)
    cameras.build(bpy.context.scene, plan, tp)
    assert len([o for o in bpy.data.objects if o.type == "CAMERA"]) == 2


def test_my_camera_is_used_as_is():
    s = setup()
    data = bpy.data.cameras.new("Mine")
    mine = bpy.data.objects.new("Mine", data)
    bpy.context.scene.collection.objects.link(mine)
    plan, tp = plan_for(s, [(1, 1.0, "LAYER", "CUSTOM"), (None, 1.0, "HOLD", "REVEAL")])
    s.shots[0].custom_camera = mine
    made = cameras.build(bpy.context.scene, plan, tp)
    assert made[0] == mine
    assert mine.animation_data is None


def test_close_up_aims_at_the_current_layer_and_frames_all_of_it():
    s = setup()
    plan, tp = plan_for(s, [(1, 1.0, "LINE", "CLOSE_UP"), (None, 1.0, "HOLD", "REVEAL")])
    s.shots[0].closeup_dof = True
    made = cameras.build(bpy.context.scene, plan, tp)
    bpy.context.scene.frame_set(5)
    camera = made[0]
    layer_center = Vector((5.0, 5.0, 0.2)) * 0.001  # the fixture layers are 10 mm squares
    forward = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    to_center = layer_center - camera.matrix_world.translation
    assert forward.angle(to_center) < math.radians(0.5)
    expected = 0.001 * (math.hypot(9.55, 9.55) / 2) / math.sin(cameras.smaller_fov(bpy.context.scene) / 2) * 1.15
    assert abs(to_center.length - expected) < 0.002
    assert camera.data.dof.use_dof and abs(camera.data.dof.focus_distance - to_center.length) < 0.002


def corners_out_of_frame(scene, frames) -> list:
    """(frame, corner) pairs where a corner of the part's bounding box is outside the camera image."""
    from bpy_extras.object_utils import world_to_camera_view

    s = scene.sliceranim
    tp = importer.toolpath_from_object(s.toolpath_object)
    low, high = tp.position.min(axis=0) * 0.001, tp.position.max(axis=0) * 0.001
    corners = [Vector((x, y, z)) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
    bad = []
    for frame in frames:
        scene.frame_set(frame)
        camera = [m.camera for m in markers if m.frame <= frame][-1]
        for corner in corners:
            x, y, z = world_to_camera_view(scene, camera, corner)
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and z > 0):
                bad.append((frame, tuple(round(v, 3) for v in corner)))
    return bad


def test_shots_other_than_close_up_keep_the_whole_part_in_frame():
    """Owner check: some shots cut off the lower part of the print."""
    from helpers import box_object, no_bambu

    from sliceranim.blender import shots

    box = box_object(size=0.02)
    box.scale = (1.0, 1.0, 2.0)  # a tall part, 20 × 20 × 40 mm
    bpy.context.view_layer.update()
    with no_bambu():
        loaded = importer.read_mesh_object(bpy.context, box)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)
    scene = bpy.context.scene
    s = scene.sliceranim
    assert [x.camera for x in s.shots] == ["CLOSE_UP", "TURNTABLE", "RISING", "REVEAL"]
    first_wide = scene.timeline_markers["SA Shot 2"].frame
    assert corners_out_of_frame(scene, range(first_wide, scene.frame_end + 1, 5)) == []
    s.format_preset = "SQUARE"
    shots.rebuild(scene)
    assert corners_out_of_frame(scene, range(first_wide, scene.frame_end + 1, 5)) == []


def test_print_volume_framing_keeps_the_whole_p1s_volume_in_frame():
    """Owner idea: frame the full print volume of the printer instead of the part."""
    s = setup()
    s.framing = "VOLUME"
    bounds, distance = cameras.framing(bpy.context.scene)
    np.testing.assert_allclose(bounds.center, [128.0, 128.0, 125.0])
    assert distance > 1000.0
    backdrop = bpy.data.objects["SA Backdrop"]
    assert max(backdrop.dimensions) > 2 * 0.256  # the backdrop grows with the framing, so no horizon shows
    s.plate_centered_on_part = True
    bounds, _ = cameras.framing(bpy.context.scene)
    np.testing.assert_allclose(bounds.center, [5.0, 5.0, 125.0])


def test_every_shot_camera_stays_inside_the_backdrop():
    """A camera outside the backdrop sees the dark outer side of the backdrop wall (a black frame)."""
    from helpers import box_object, no_bambu

    box = box_object(size=0.02)
    box.scale = (1.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    with no_bambu():
        loaded = importer.read_mesh_object(bpy.context, box)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)
    scene = bpy.context.scene
    backdrop = bpy.data.objects["SA Backdrop"]
    radius = backdrop.dimensions.x / 2
    for frame in range(1, scene.frame_end + 1, 5):
        scene.frame_set(frame)
        for camera in (o for o in bpy.data.objects if o.get(cameras.TAG)):
            offset = camera.matrix_world.translation - backdrop.location
            assert offset.xy.length < radius and offset.z < radius, (frame, camera.name)
