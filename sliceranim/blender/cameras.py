"""One camera object per shot (spec section 9)."""

import bpy
import numpy as np
from mathutils import Euler, Vector

from ..core import camera_paths as paths
from ..core.timing import CLOSE_UP, CUSTOM, HERO, REVEAL, RISING, TURNTABLE
from . import keys, looks
from .output import resolution

MM = 0.001
LENS_MM = 50.0
SENSOR_MM = 36.0
TAG = "sliceranim_shot_camera"


def remove_shot_cameras() -> None:
    for obj in [o for o in bpy.data.objects if o.get(TAG)]:
        looks.remove_object(obj.name)


def smaller_fov(scene) -> float:
    """The smaller of the horizontal and vertical field of view for the output size (radians)."""
    width, height = resolution(scene.sliceranim)
    return min(paths.field_of_view(LENS_MM, SENSOR_MM, width, height))


def framing(scene) -> tuple[paths.Bounds, float]:
    """Part bounds (mm) and the framing distance (mm) for the output aspect ratio."""
    settings = scene.sliceranim
    bounds = paths.Bounds(center=np.array(settings.part_center, dtype=np.float64), radius=settings.part_radius)
    return bounds, paths.framing_distance(bounds.radius, smaller_fov(scene))


def path_for_shot(scene, shot, head: np.ndarray, layer: np.ndarray, layer_info, previous) -> paths.CameraPath:
    """Camera path of one shot.

    `head` (mm) and `layer` (layer index) have one value per frame of the shot.
    `layer_info` is (centers, radii) per layer from paths.layer_bounds().
    """
    bounds, distance = framing(scene)
    count = len(head)
    if shot.camera == TURNTABLE:
        return paths.turntable(bounds, distance, count, turns=shot.orbit_turns,
                               height_angle=shot.orbit_height, clockwise=shot.orbit_clockwise)
    if shot.camera == HERO:
        return paths.hero(bounds, distance, count, height_angle=shot.hero_height, side_angle=shot.hero_side)
    if shot.camera == RISING:
        return paths.rising_follow(bounds, shot.rising_distance or distance, head[:, 2], height_angle=shot.rising_height)
    if shot.camera == CLOSE_UP:
        centers, radii = layer_info
        index = layer.astype(np.int64)
        if shot.closeup_target == "CURSOR":
            targets = np.tile(np.array(scene.cursor.location) / MM, (count, 1))
        else:
            targets = centers[index]
        return paths.close_up(targets, radii[index], smaller_fov(scene), smoothing=shot.closeup_smoothing)
    if shot.camera == REVEAL:
        return paths.final_reveal(bounds, distance, count, previous, spin=shot.reveal_spin,
                                  pullback_share=shot.reveal_pullback / 100.0)
    raise ValueError(shot.camera)


def eulers(location: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Rotation of a camera at `location` that looks at `target`, one Euler per frame, without flips."""
    out = np.zeros((len(location), 3))
    previous = Euler()
    for i, (here, there) in enumerate(zip(location, target)):
        previous = (Vector(there) - Vector(here)).to_track_quat("-Z", "Y").to_euler("XYZ", previous)
        out[i] = previous
    return out


def _custom_pose(scene, obj) -> tuple[np.ndarray, np.ndarray]:
    _, distance = framing(scene)
    matrix = obj.matrix_world
    location = np.array(matrix.translation) / MM
    forward = np.array(matrix.to_quaternion() @ Vector((0, 0, -1)))
    return location, location + forward * distance


def build(scene, plan, tp) -> list:
    """Make one camera per shot with keyframes for its frames. Return the camera objects in shot order."""
    remove_shot_cameras()
    settings = scene.sliceranim
    layer_info = paths.layer_bounds(tp.position, tp.layer_start)
    result = []
    previous = None
    for row, shot in enumerate(settings.shots):
        first = plan.shot_first_frame[row]
        count = plan.shot_frame_count[row]
        if shot.camera == CUSTOM:
            result.append(shot.custom_camera)
            previous = _custom_pose(scene, shot.custom_camera)
            continue
        span = slice(first - 1, first - 1 + count)
        path = path_for_shot(scene, shot, plan.head[span], plan.current_layer[span], layer_info, previous)
        data = bpy.data.cameras.new(f"SA Shot {row + 1}")
        data.lens = LENS_MM
        data.sensor_width = SENSOR_MM
        data.clip_start = 0.001
        data.clip_end = 1000.0
        if shot.camera == CLOSE_UP and shot.closeup_dof:
            data.dof.use_dof = True
            data.dof.aperture_fstop = shot.closeup_fstop
            data.dof.focus_distance = float(np.linalg.norm(path.location - path.target, axis=1).mean()) * MM
        obj = looks.put_object(scene, f"SA Shot {row + 1} Camera", data)
        obj[TAG] = True
        frames = np.arange(first, first + count)
        keys.write_vector(obj, "location", frames, path.location * MM, keys.LINEAR)
        keys.write_vector(obj, "rotation_euler", frames, eulers(path.location, path.target), keys.LINEAR)
        previous = (path.location[-1], path.target[-1])
        result.append(obj)
    return result
