"""Read a source and build the toolpath object (spec sections 6, 7, and 11.2)."""

import bpy
import numpy as np

from ..core.toolpaths import ToolpathSet, pack

MM = 0.001
ATTRIBUTES = (
    # name, Blender type, ToolpathSet field, scale
    ("layer", "INT", "layer", None),
    ("feature", "INT", "feature", None),
    ("tool", "INT", "tool", None),
    ("width", "FLOAT", "width", MM),
    ("height", "FLOAT", "height", MM),
    ("time", "FLOAT", "time", None),
)


def toolpath_mesh(tp: ToolpathSet, name: str) -> bpy.types.Mesh:
    """One vertex per point (in meters), one edge per strand, and the point attributes."""
    n = tp.point_count
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(n)
    mesh.vertices.foreach_set("co", (tp.position.astype(np.float64) * MM).astype(np.float32).ravel())
    first = np.arange(n - 1, dtype=np.int32)[~tp.run_start_mask()[1:]]
    mesh.edges.add(len(first))
    mesh.edges.foreach_set("vertices", np.column_stack([first, first + 1]).ravel())
    mesh.attributes.new("order", "INT", "POINT").data.foreach_set("value", np.arange(n, dtype=np.int32))
    for attr, kind, field, scale in ATTRIBUTES:
        values = getattr(tp, field).astype(np.float64)
        if scale:
            values = values * scale
        dtype = np.int32 if kind == "INT" else np.float32
        mesh.attributes.new(attr, kind, "POINT").data.foreach_set("value", values.astype(dtype))
    mesh.update()
    return mesh


def _read_attribute(mesh, name: str, dtype) -> np.ndarray:
    values = np.empty(len(mesh.vertices), dtype=dtype)
    mesh.attributes[name].data.foreach_get("value", values)
    return values


def toolpath_from_object(obj) -> ToolpathSet:
    """Read the ToolpathSet back from the toolpath object. Rebuild needs no source file."""
    mesh = obj.data
    n = len(mesh.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edges)
    starts = np.ones(n, dtype=bool)
    starts[edges.reshape(-1, 2)[:, 1]] = False
    return pack(
        position=co.reshape(-1, 3).astype(np.float64) / MM,
        layer=_read_attribute(mesh, "layer", np.int32),
        feature=_read_attribute(mesh, "feature", np.int32),
        tool=_read_attribute(mesh, "tool", np.int32),
        width=_read_attribute(mesh, "width", np.float32) / MM,
        height=_read_attribute(mesh, "height", np.float32) / MM,
        time=_read_attribute(mesh, "time", np.float32),
        object_id=np.zeros(n),
        run_start=np.flatnonzero(starts),
    )
