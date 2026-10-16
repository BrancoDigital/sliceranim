"""Rebuild: write keyframes, markers, and cameras from the shot list (spec 8.5)."""

import hashlib
import json

import bpy
import numpy as np

from ..core.errors import SlicerAnimError
from ..core.timing import CUSTOM, HOLD, LINE, Shot, ShotProblem, default_shots, plan_frames, validate_shots
from . import cameras, keys, looks, nodes, output

MM = 0.001
MARKER_PREFIX = "SA Shot "


def shots_from_settings(settings) -> list[Shot]:
    return [
        Shot(None if s.start_at_end else s.start_layer, s.duration, s.style, s.camera)
        for s in settings.shots
    ]


def fill_default_shots(settings, layer_count: int) -> None:
    settings.shots.clear()
    for shot in default_shots(layer_count):
        item = settings.shots.add()
        item.start_at_end = shot.start_layer is None
        item.start_layer = shot.start_layer or layer_count
        item.duration = shot.duration
        item.style = shot.style
        item.camera = shot.camera
    settings.active_shot = 0


def problems(scene) -> list[ShotProblem]:
    settings = scene.sliceranim
    if settings.toolpath_object is None:
        return [ShotProblem(-1, 0, "Load a file first.")]
    found = validate_shots(shots_from_settings(settings), settings.layer_count)
    for row, shot in enumerate(settings.shots):
        if shot.camera == CUSTOM and shot.custom_camera is None:
            found.append(ShotProblem(row, 0, "Choose a camera object for My camera."))
    return found


def signature(scene) -> str:
    """A fingerprint of everything that Rebuild reads. Preview compares it to see if Rebuild must run."""
    settings = scene.sliceranim
    data = {
        "shots": [{k: _plain(getattr(s, k)) for k in s.bl_rna.properties.keys() if k not in ("rna_type", "name")}
                  for s in settings.shots],
        "fps": settings.fps,
        "size": output.resolution(settings),
        "points": settings.point_count,
        "merge": round(settings.built_merge_angle, 6),
        "radius": round(settings.part_radius, 6),
        "cursor": [round(v, 6) for v in scene.cursor.location],
        "object": settings.toolpath_object.name if settings.toolpath_object else "",
    }
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _plain(value):
    if isinstance(value, bpy.types.ID):
        return value.name
    if hasattr(value, "__len__") and not isinstance(value, str):
        return [round(v, 6) for v in value]
    return round(value, 6) if isinstance(value, float) else value


def needs_rebuild(scene) -> bool:
    return scene.sliceranim.rebuild_signature != signature(scene)


def clear(scene) -> None:
    """Delete the markers, keyframes, and cameras that the last Rebuild made."""
    settings = scene.sliceranim
    for marker in [m for m in scene.timeline_markers if m.name.startswith(MARKER_PREFIX)]:
        scene.timeline_markers.remove(marker)
    obj = settings.toolpath_object
    if obj is not None:
        keys.remove(obj, {nodes.input_path(obj, "Progress"), nodes.input_path(obj, "Current Layer")})
    if settings.head_object is not None:
        keys.remove(settings.head_object, {"location"})
    cameras.remove_shot_cameras()


def rebuild(scene):
    """Write everything in spec 8.5. Raise SlicerAnimError when the shot list is not valid."""
    from . import importer

    found = problems(scene)
    if found:
        raise SlicerAnimError(found[0].message)
    settings = scene.sliceranim
    output.apply(scene)
    obj = settings.toolpath_object
    tp = importer.toolpath_from_object(obj)
    shot_list = shots_from_settings(settings)
    plan = plan_frames(tp, shot_list, int(settings.fps))
    clear(scene)
    frames = np.arange(1, plan.frame_count + 1)
    is_line = np.array([shot_list[i].style == LINE for i in plan.shot_index])
    keys.write(obj, nodes.input_path(obj, "Progress"), frames, plan.progress,
               np.where(is_line, keys.LINEAR, keys.CONSTANT))
    keys.write(obj, nodes.input_path(obj, "Current Layer"), frames, plan.current_layer, keys.CONSTANT)
    keys.write_vector(settings.head_object, "location", frames, plan.head * MM, keys.LINEAR)
    shot_cameras = cameras.build(scene, plan, tp)
    for row, camera in enumerate(shot_cameras):
        marker = scene.timeline_markers.new(f"{MARKER_PREFIX}{row + 1}", frame=plan.shot_first_frame[row])
        marker.camera = camera
    scene.frame_start = 1
    scene.frame_end = plan.frame_count
    scene.camera = shot_cameras[0]
    settings.nozzle_frame_ranges = json.dumps([
        [first, first + count - 1]
        for first, count, shot in zip(plan.shot_first_frame, plan.shot_frame_count, shot_list)
        if shot.style != HOLD
    ])
    looks.write_nozzle_keys(scene)
    settings.rebuild_signature = signature(scene)
    scene.frame_set(scene.frame_current)
    return plan
