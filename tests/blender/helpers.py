"""Shared helpers for the Blender tests."""

from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CUBE = FIXTURES / "cube_3_layers.gcode"
SAMPLE_3MF = ROOT / "samples" / "sample.3mf"


class Skip(Exception):
    """Raise to skip a test, for example when a client sample file is not present."""


def reset() -> None:
    """Start each test from an empty scene."""
    bpy.ops.wm.read_homefile(use_empty=True)


def settings():
    return bpy.context.scene.sliceranim


def evaluated_polygons(obj) -> int:
    """Polygon count of the evaluated object (3D view evaluation, so Viewport Strand Sides applies)."""
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def evaluated_bounds(obj) -> tuple[np.ndarray, np.ndarray]:
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
    finally:
        evaluated.to_mesh_clear()
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)


def load(path) -> None:
    """Load a file the way the Open File button does, without the polygon warning."""
    from sliceranim.blender import importer

    loaded = importer.read_file(bpy.context, str(path))
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)


def polygons_at(frame: int) -> int:
    bpy.context.scene.frame_set(frame)
    return evaluated_polygons(settings().toolpath_object)


def keyframes(id_data, data_path: str, index: int = 0) -> np.ndarray:
    """(frame, value) pairs of one channel."""
    from bpy_extras import anim_utils

    data = id_data.animation_data
    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find(data_path, index=index)
    co = np.empty(len(curve.keyframe_points) * 2, dtype=np.float32)
    curve.keyframe_points.foreach_get("co", co)
    return co.reshape(-1, 2)


def box_object(name: str = "Box", size: float = 0.01):
    """A closed box mesh object of `size` meters on z = 0. It becomes the active object."""
    s = size
    verts = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj
