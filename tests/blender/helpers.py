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
