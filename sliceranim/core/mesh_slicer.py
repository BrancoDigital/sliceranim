"""Fallback slicer: cut a triangle mesh into 2 wall loops per outline (spec section 6.4).

Units are millimeters. The output sits on z = 0, like a part on the plate.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np

from .errors import NO_EXTRUSION, SlicerAnimError, part_too_large
from .toolpaths import FEATURE_CODE, ToolpathSet, pack

LAYER_HEIGHT = 0.2
WIDTH = 0.45
SPEED = 100.0  # mm/s
MITER_LIMIT = 4.0
MAX_PART_MM = 1000.0
_OUTER = FEATURE_CODE["outer_wall"]
_INNER = FEATURE_CODE["inner_wall"]


def read_stl(path) -> tuple[np.ndarray, np.ndarray]:
    """Read a binary or ASCII STL file. Return (vertices (V, 3), triangles (T, 3))."""
    data = Path(path).read_bytes()
    if len(data) >= 84:
        (count,) = struct.unpack_from("<I", data, 80)
        if len(data) == 84 + 50 * count:
            records = np.frombuffer(data, dtype=np.uint8, count=50 * count, offset=84).reshape(count, 50)
            corners = records[:, 12:48].copy().view("<f4").reshape(count * 3, 3)
            return corners.astype(np.float64), np.arange(count * 3).reshape(count, 3)
    text = data.decode("utf-8", errors="replace")
    corners = [[float(v) for v in line.split()[1:4]] for line in text.splitlines() if line.strip().startswith("vertex")]
    vertices = np.array(corners, dtype=np.float64).reshape(-1, 3)
    return vertices, np.arange(len(vertices)).reshape(-1, 3)


def write_stl(path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    """Write a binary STL file. Units are as given (mm for a slicer)."""
    corners = np.asarray(vertices, dtype=np.float64)[np.asarray(triangles)]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)
    records = np.zeros(len(corners), dtype=[("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
    records["normal"] = normals
    records["corners"] = corners
    with open(path, "wb") as file:
        file.write(b"sliceranim".ljust(80, b" "))
        file.write(struct.pack("<I", len(records)))
        file.write(records.tobytes())


def to_millimeters(vertices: np.ndarray, mm_per_unit: float) -> tuple[np.ndarray, bool]:
    """Scale Blender coordinates to mm. Return (vertices in mm, True when 1 unit was read as 1 mm).

    The Blender STL import puts 1 mm of the file at 1 unit (1 m). A part larger than MAX_PART_MM cannot
    be a print, so the plugin then reads 1 unit as 1 mm.
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    size = float(np.ptp(vertices, axis=0).max()) if len(vertices) else 0.0
    if size * mm_per_unit <= MAX_PART_MM:
        return vertices * mm_per_unit, False
    if size > MAX_PART_MM:
        raise part_too_large(size)
    return vertices, True


def weld(vertices: np.ndarray, triangles: np.ndarray, tolerance: float = 1e-5):
    """Merge vertices closer than `tolerance` and drop triangles with a repeated vertex."""
    keys = np.round(np.asarray(vertices, dtype=np.float64) / tolerance).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    welded = unique.astype(np.float64) * tolerance
    tris = inverse.reshape(-1)[np.asarray(triangles)]
    good = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    return welded, tris[good]


def has_open_edges(triangles: np.ndarray) -> bool:
    """True when an edge does not belong to exactly two triangles."""
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.any(counts != 2))


def signed_area(loop: np.ndarray) -> float:
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def point_in_polygon(point, loop: np.ndarray) -> bool:
    x, y = point
    x0, y0 = loop[:, 0], loop[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    crosses = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    return bool(np.count_nonzero(crosses & (x < x_at)) % 2)


def cut_layer(vertices: np.ndarray, triangles: np.ndarray, z: float) -> list[np.ndarray]:
    """Cut the mesh at height z. Return the closed outlines as (M, 2) arrays. Open chains are dropped."""
    vz = vertices[:, 2]
    if np.any(vz == z):
        z += 1e-7
    tz = vz[triangles]
    above = tz > z
    count = above.sum(axis=1)
    tris = triangles[(count == 1) | (count == 2)]
    above = above[(count == 1) | (count == 2)]
    if len(tris) == 0:
        return []
    corner_pairs = ((0, 1), (1, 2), (2, 0))
    keys_per_tri = []
    for a, b in corner_pairs:
        keys_per_tri.append(np.where(above[:, a] != above[:, b], np.minimum(tris[:, a], tris[:, b]) * len(vertices) + np.maximum(tris[:, a], tris[:, b]), -1))
    keys_per_tri = np.stack(keys_per_tri, axis=1)
    segments = np.sort(keys_per_tri, axis=1)[:, 1:]  # the two crossed edges; -1 sorts first
    point_of: dict[int, tuple[float, float]] = {}
    for key in np.unique(segments):
        i, j = divmod(int(key), len(vertices))
        vi, vj = vertices[i], vertices[j]
        t = (z - vi[2]) / (vj[2] - vi[2])
        point_of[int(key)] = (vi[0] + t * (vj[0] - vi[0]), vi[1] + t * (vj[1] - vi[1]))
    by_key: dict[int, list[int]] = {}
    for s, (k1, k2) in enumerate(segments.tolist()):
        by_key.setdefault(k1, []).append(s)
        by_key.setdefault(k2, []).append(s)
    used = np.zeros(len(segments), dtype=bool)
    loops = []
    for first in range(len(segments)):
        if used[first]:
            continue
        used[first] = True
        start_key, key = segments[first].tolist()
        chain = [start_key, key]
        closed = False
        while True:
            following = [s for s in by_key.get(key, []) if not used[s]]
            if not following:
                break
            s = following[0]
            used[s] = True
            k1, k2 = segments[s].tolist()
            key = k2 if k1 == key else k1
            if key == start_key:
                closed = True
                break
            chain.append(key)
        if closed and len(chain) >= 3:
            loops.append(np.array([point_of[k] for k in chain], dtype=np.float64))
    return loops


def orient(loops: list[np.ndarray]) -> list[np.ndarray]:
    """Turn outer outlines counterclockwise and holes clockwise, so the material is on the left."""
    out = []
    for i, loop in enumerate(loops):
        depth = sum(point_in_polygon(loop[0], other) for j, other in enumerate(loops) if j != i)
        is_hole = depth % 2 == 1
        area = signed_area(loop)
        if (area > 0) == is_hole:
            loop = loop[::-1]
        out.append(loop)
    return out


def clean(loop: np.ndarray, tolerance: float = 1e-6) -> np.ndarray:
    """Remove repeated points and points on a straight line between their neighbors.

    A triangulated mesh puts cut points in the middle of straight sides. Without
    this step, the offset of such a point near a corner folds back over the corner.
    """
    step = np.linalg.norm(loop - np.roll(loop, 1, axis=0), axis=1)
    loop = loop[step > tolerance]
    if len(loop) < 3:
        return loop
    before = loop - np.roll(loop, 1, axis=0)
    after = np.roll(loop, -1, axis=0) - loop
    cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
    dot = np.sum(before * after, axis=1)
    lengths = np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1)
    straight = (np.abs(cross) <= 1e-9 * lengths) & (dot > 0)
    return loop[~straight]


def offset(loop: np.ndarray, distance: float) -> np.ndarray:
    """Move each point of a loop to the left of the path by `distance` (miter join, limited)."""
    before = loop - np.roll(loop, 1, axis=0)
    after = np.roll(loop, -1, axis=0) - loop
    before /= np.linalg.norm(before, axis=1, keepdims=True)
    after /= np.linalg.norm(after, axis=1, keepdims=True)
    n_before = np.column_stack([-before[:, 1], before[:, 0]])
    n_after = np.column_stack([-after[:, 1], after[:, 0]])
    miter = n_before + n_after
    length = np.linalg.norm(miter, axis=1, keepdims=True)
    miter = np.where(length > 1e-9, miter / np.maximum(length, 1e-12), n_before)
    cos_half = np.sum(miter * n_before, axis=1, keepdims=True)
    scale = distance / np.maximum(cos_half, 1.0 / MITER_LIMIT)
    return loop + miter * scale


def _segments_cross(p, q, a, b) -> np.ndarray:
    def cross(o, u, v):
        return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])

    d1 = cross(p, q, a)
    d2 = cross(p, q, b)
    d3 = cross(a, b, p)
    d4 = cross(a, b, q)
    return (d1 * d2 < 0) & (d3 * d4 < 0)


def self_intersects(loop: np.ndarray) -> bool:
    """True when two edges of the closed loop cross each other."""
    n = len(loop)
    if n < 4:
        return False
    p = loop
    q = np.roll(loop, -1, axis=0)
    xmin = np.minimum(p[:, 0], q[:, 0])
    xmax = np.maximum(p[:, 0], q[:, 0])
    order = np.argsort(xmin, kind="stable")
    sorted_xmin = xmin[order]
    for position, i in enumerate(order):
        stop = np.searchsorted(sorted_xmin, xmax[i], side="right")
        others = order[position + 1 : stop]
        others = others[(others != (i + 1) % n) & (others != (i - 1) % n)]
        if others.size and np.any(_segments_cross(p[i], q[i], p[others], q[others])):
            return True
    return False


def inner_loop_is_valid(inner: np.ndarray, outline: np.ndarray) -> bool:
    """Spec 6.4 step 4: drop the inner loop if it crosses itself or its area falls to 0 or below."""
    sign = 1.0 if signed_area(outline) > 0 else -1.0
    if sign * signed_area(inner) <= 1e-9:
        return False
    return not self_intersects(inner)


def slice_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    layer_height: float = LAYER_HEIGHT,
    width: float = WIDTH,
    speed: float = SPEED,
) -> tuple[ToolpathSet, bool]:
    """Slice a mesh in mm. Return the toolpaths and True when the mesh has open edges."""
    verts, tris = weld(vertices, triangles)
    if len(tris) == 0:
        raise SlicerAnimError(NO_EXTRUSION)
    open_edges = has_open_edges(tris)
    verts = verts.copy()
    verts[:, 2] -= verts[:, 2].min()
    top = verts[:, 2].max()
    layer_count = int(math.ceil(top / layer_height - 0.5))
    xyz, layer, feature, time, run_start, layer_z = [], [], [], [], [], {}
    clock = 0.0

    def add_run(loop: np.ndarray, z: float, k: int, code: int):
        nonlocal clock
        closed = np.vstack([loop, loop[:1]])
        run_start.append(len(xyz))
        steps = np.r_[0.0, np.linalg.norm(np.diff(closed, axis=0), axis=1)]
        times = clock + np.cumsum(steps) / speed
        clock = float(times[-1])
        for (x, y), t in zip(closed, times):
            xyz.append((x, y, z))
            layer.append(k)
            feature.append(code)
            time.append(t)

    for k in range(layer_count):
        z_top = (k + 1) * layer_height
        outlines = [clean(loop) for loop in cut_layer(verts, tris, (k + 0.5) * layer_height)]
        outlines = orient([loop for loop in outlines if len(loop) >= 3])
        for outline in outlines:
            inner = offset(outline, 1.5 * width)
            if inner_loop_is_valid(inner, outline):
                add_run(inner, z_top, k, _INNER)
            add_run(offset(outline, 0.5 * width), z_top, k, _OUTER)
        layer_z[k] = z_top
    if not xyz:
        raise SlicerAnimError(NO_EXTRUSION)
    n = len(xyz)
    tp = pack(
        position=xyz,
        layer=layer,
        feature=feature,
        tool=np.zeros(n),
        width=np.full(n, width),
        height=np.full(n, layer_height),
        time=time,
        object_id=np.zeros(n),
        run_start=run_start,
        layer_z_by_number=layer_z,
        meta={"slicer": "Fallback slicer", "slicer_version": "", "filament_colors": [], "filament_type": "", "fallback": True},
    )
    return tp, open_edges
