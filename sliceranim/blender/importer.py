"""Read a source and build the toolpath object (spec sections 6, 7, and 11.2)."""

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np

from ..core import bambu_cli, threemf
from ..core.camera_paths import part_bounds
from ..core.errors import SlicerAnimError, source_missing
from ..core.gcode_reader import read_gcode
from ..core.mesh_slicer import read_stl, slice_mesh
from ..core.timing import validate_shots
from ..core.toolpaths import ToolpathSet, merge_points, pack
from . import looks, nodes, output, prefs, shots

MM = 0.001
POLYGON_LIMIT = 10_000_000
HEAD = "SA Print Head"
ATTRIBUTES = (
    # name, Blender type, ToolpathSet field, scale
    ("layer", "INT", "layer", None),
    ("feature", "INT", "feature", None),
    ("tool", "INT", "tool", None),
    ("width", "FLOAT", "width", MM),
    ("height", "FLOAT", "height", MM),
    ("time", "FLOAT", "time", None),
)


@dataclass
class Loaded:
    tp: ToolpathSet
    kind: str  # GCODE, SLICED_3MF, PROJECT, STL, or MESH
    source_path: str  # the file that Reload reads
    label: str  # file or object name for the panel and the object name
    open_edges: bool = False
    source_mesh: object = None


def slice_dir(project: Path) -> Path:
    """`<blend directory>/slices/<project name>/` when the .blend file is saved, else a temporary directory."""
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent / "slices" / project.stem
    return Path(tempfile.mkdtemp(prefix="sliceranim_"))


def read_file(context, filepath: str) -> Loaded:
    path = Path(bpy.path.abspath(filepath))
    if not path.is_file():
        raise source_missing(str(path))
    name = path.name.lower()
    if name.endswith(".gcode"):
        return Loaded(read_gcode(path), "GCODE", str(path), path.name)
    if name.endswith(".3mf"):
        info = threemf.inspect_3mf(path)
        threemf.require_one_plate(info)
        if info.kind == threemf.SLICED:
            return Loaded(threemf.read_sliced_3mf(path), "SLICED_3MF", str(path), path.name)
        bambu = bambu_cli.find_bambu(prefs.bambu_path(context))
        gcode = bambu_cli.slice_project(path, slice_dir(path), bambu)
        return Loaded(read_gcode(gcode), "PROJECT", str(gcode), path.name)
    if name.endswith(".stl"):
        vertices, triangles = read_stl(path)
        tp, open_edges = slice_mesh(vertices, triangles)
        return Loaded(tp, "STL", str(path), path.name, open_edges)
    raise SlicerAnimError(f"Unsupported file type: {path.suffix}. Use .gcode, .gcode.3mf, .3mf, or .stl.")


def read_mesh_object(context, obj) -> Loaded:
    """Run the fallback slicer on a mesh object. Blender units become mm through the scene unit scale."""
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
        triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles)
    finally:
        evaluated.to_mesh_clear()
    matrix = np.array(obj.matrix_world)
    world = co.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]
    scale = context.scene.unit_settings.scale_length / MM
    tp, open_edges = slice_mesh(world * scale, triangles.reshape(-1, 3))
    return Loaded(tp, "MESH", "", obj.name, open_edges, obj)


def reload_source(context) -> Loaded:
    """Read the source of the current toolpath object again (spec section 7, Reload)."""
    settings = context.scene.sliceranim
    if settings.source_kind == "MESH":
        if settings.source_mesh is None:
            raise source_missing(settings.source_label)
        return read_mesh_object(context, settings.source_mesh)
    path = Path(settings.source_path)
    if not path.is_file():
        raise source_missing(str(path))
    if settings.source_kind == "SLICED_3MF":
        tp = threemf.read_sliced_3mf(path)
    elif settings.source_kind == "STL":
        tp, open_edges = slice_mesh(*read_stl(path))
        return Loaded(tp, "STL", str(path), settings.source_label, open_edges)
    else:
        tp = read_gcode(path)
    return Loaded(tp, settings.source_kind, str(path), settings.source_label)


def prepare(context, loaded: Loaded) -> ToolpathSet:
    """Merge points with the Merge angle from the panel."""
    return merge_points(loaded.tp, math.degrees(context.scene.sliceranim.merge_angle))


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


def _file_color(tp: ToolpathSet) -> tuple[float, float, float]:
    colors = tp.meta.get("filament_colors") or []
    tool = int(tp.tool[0]) if tp.point_count else 0
    if not colors:
        return looks.hex_to_linear("#808080")
    try:
        return looks.hex_to_linear(colors[tool if tool < len(colors) else 0][:7])
    except ValueError:
        return looks.hex_to_linear("#808080")


def _remove_toolpath_object(settings) -> None:
    obj = settings.toolpath_object
    if obj is None:
        return
    settings.toolpath_object = None
    looks.remove_object(obj.name)


def build(context, loaded: Loaded, tp: ToolpathSet, *, keep_shots: bool) -> bpy.types.Object:
    """Build the toolpath object and everything around it, then run Rebuild."""
    scene = context.scene
    settings = scene.sliceranim
    _remove_toolpath_object(settings)
    name = f"{Path(loaded.label).name.split('.')[0]} Toolpaths".strip()
    obj = looks.put_object(scene, name, toolpath_mesh(tp, name))
    nodes.ensure_modifier(obj, looks.filament_material(), looks.ghost_material())
    nodes.set_input(obj, "Profile Aspect", float(np.median(tp.height) / np.median(tp.width)))
    head = looks.put_object(scene, HEAD, None)
    head.empty_display_size = 0.002
    bounds = part_bounds(tp.position)
    settings.toolpath_object = obj
    settings.head_object = head
    settings.source_kind = loaded.kind
    settings.source_path = loaded.source_path
    settings.source_label = loaded.label
    settings.source_mesh = loaded.source_mesh
    settings.slicer = " ".join(v for v in (tp.meta.get("slicer", ""), tp.meta.get("slicer_version", "")) if v)
    settings.layer_count = tp.layer_count
    settings.point_count = tp.point_count
    settings.print_time = tp.total_time
    settings.used_fallback = bool(tp.meta.get("fallback"))
    settings.plate_centered_on_part = bool(tp.meta.get("fallback"))
    settings.built_merge_angle = math.radians(tp.meta.get("merge_angle", 0.0))
    settings.part_center = bounds.center.tolist()
    settings.part_radius = bounds.radius
    settings.file_color = _file_color(tp)
    current = shots.shots_from_settings(settings)
    if not keep_shots or not current or validate_shots(current, tp.layer_count):
        shots.fill_default_shots(settings, tp.layer_count)
    if not settings.engine_set:
        scene.render.engine = "BLENDER_EEVEE"
        settings.engine_set = True
    if loaded.source_mesh is not None:
        loaded.source_mesh.hide_set(True)
        loaded.source_mesh.hide_render = True
    nodes.apply_settings(scene)
    looks.apply(scene)
    output.apply(scene)
    shots.rebuild(scene)
    return obj
