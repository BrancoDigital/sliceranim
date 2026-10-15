"""Fast keyframe writing for Blender 5.2 layered actions."""

import bpy
import numpy as np
from bpy_extras import anim_utils

CONSTANT, LINEAR = 0, 1  # values of the Keyframe.interpolation enum


def _channelbag(id_data):
    data = id_data.animation_data
    if data is None or data.action is None or data.action_slot is None:
        return None
    return anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot)


def write(id_data, data_path: str, frames, values, interpolation, index: int = -1) -> None:
    """Replace all keys of one channel. `index` is -1 for a single value, or the array index.

    `interpolation` is CONSTANT, LINEAR, or an array with one of them per key.
    """
    id_data.keyframe_insert(data_path, index=index, frame=float(frames[0]))
    curve = _channelbag(id_data).fcurves.find(data_path, index=max(index, 0))
    curve.keyframe_points.clear()
    count = len(frames)
    curve.keyframe_points.add(count)
    co = np.column_stack([np.asarray(frames, dtype=np.float32), np.asarray(values, dtype=np.float32)])
    curve.keyframe_points.foreach_set("co", co.ravel())
    modes = np.broadcast_to(np.asarray(interpolation, dtype=np.int32), (count,))
    curve.keyframe_points.foreach_set("interpolation", np.ascontiguousarray(modes))
    curve.update()


def write_vector(id_data, data_path: str, frames, values, interpolation) -> None:
    values = np.asarray(values)
    for axis in range(values.shape[1]):
        write(id_data, data_path, frames, values[:, axis], interpolation, index=axis)


def remove(id_data, data_paths) -> None:
    """Delete the channels whose data path is in `data_paths`."""
    bag = _channelbag(id_data)
    if bag is None:
        return
    for curve in [c for c in bag.fcurves if c.data_path in data_paths]:
        bag.fcurves.remove(curve)
