"""ToolpathSet: every extruded point of one print, in print order (spec section 5).

Units are millimeters and seconds. All indices count from 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

FEATURES = (
    "other",
    "outer_wall",
    "inner_wall",
    "overhang_wall",
    "sparse_infill",
    "solid_infill",
    "top_surface",
    "bottom_surface",
    "bridge",
    "gap_fill",
    "support",
    "support_interface",
    "brim_skirt",
    "prime_tower",
    "custom",
)
FEATURE_CODE = {name: code for code, name in enumerate(FEATURES)}

_SLICER_LABELS = {
    "outer wall": 1,
    "inner wall": 2,
    "floating vertical shell": 2,
    "overhang wall": 3,
    "sparse infill": 4,
    "internal solid infill": 5,
    "top surface": 6,
    "bottom surface": 7,
    "bridge": 8,
    "gap infill": 9,
    "support": 10,
    "support transition": 10,
    "support interface": 11,
    "brim": 12,
    "skirt": 12,
    "prime tower": 13,
    "custom": 14,
}


def feature_code(label: str) -> int:
    """Return the feature code for a slicer label such as "Outer wall". Unknown labels give 0."""
    return _SLICER_LABELS.get(label.strip().lower(), 0)


@dataclass
class ToolpathSet:
    position: np.ndarray  # float32 (N, 3), plate coordinates in mm
    layer: np.ndarray  # int32 (N,), from 0, no gaps
    feature: np.ndarray  # uint8 (N,)
    tool: np.ndarray  # uint8 (N,)
    width: np.ndarray  # float32 (N,), mm
    height: np.ndarray  # float32 (N,), mm
    time: np.ndarray  # float64 (N,), seconds from the first point
    object_id: np.ndarray  # int32 (N,)
    run_start: np.ndarray  # int32 (R,), index of the first point of each run
    layer_start: np.ndarray  # int32 (L,), index of the first point of each layer
    layer_z: np.ndarray  # float32 (L,), mm
    meta: dict = field(default_factory=dict)

    @property
    def point_count(self) -> int:
        return int(len(self.position))

    @property
    def layer_count(self) -> int:
        return int(len(self.layer_start))

    @property
    def total_time(self) -> float:
        return float(self.time[-1]) if self.point_count else 0.0

    def run_start_mask(self) -> np.ndarray:
        mask = np.zeros(self.point_count, dtype=bool)
        mask[self.run_start] = True
        return mask

    def validate(self) -> None:
        """Raise ValueError if the arrays break the rules of spec section 5."""
        n = self.point_count
        per_point = ("layer", "feature", "tool", "width", "height", "time", "object_id")
        if self.position.shape != (n, 3):
            raise ValueError("position must have shape (N, 3)")
        for name in per_point:
            if len(getattr(self, name)) != n:
                raise ValueError(f"{name} must have one value per point")
        if n == 0:
            return
        if self.run_start[0] != 0 or np.any(np.diff(self.run_start) <= 0):
            raise ValueError("run_start must start at 0 and increase")
        if np.any(np.diff(self.layer) < 0):
            raise ValueError("layer must not decrease in print order")
        if np.any(np.diff(self.time) < 0):
            raise ValueError("time must not decrease in print order")
        expected = np.searchsorted(self.layer, np.arange(self.layer_count))
        if not np.array_equal(expected, self.layer_start):
            raise ValueError("layer_start does not match layer")
        if not np.all(self.run_start_mask()[self.layer_start]):
            raise ValueError("each layer must start a new run")


def pack(
    *,
    position,
    layer,
    feature,
    tool,
    width,
    height,
    time,
    object_id,
    run_start,
    layer_z_by_number: dict[int, float] | None = None,
    meta: dict | None = None,
) -> ToolpathSet:
    """Make a ToolpathSet from per-point arrays.

    `layer` can have gaps (for example layers with no points). This function
    numbers the layers again from 0 without gaps.
    """
    position = np.asarray(position, dtype=np.float32).reshape(-1, 3)
    raw_layer = np.asarray(layer, dtype=np.int64)
    numbers, new_layer = np.unique(raw_layer, return_inverse=True)
    new_layer = new_layer.astype(np.int32)
    layer_start = np.searchsorted(new_layer, np.arange(len(numbers))).astype(np.int32)
    lookup = layer_z_by_number or {}
    layer_z = np.array(
        [lookup.get(int(number), position[start, 2]) for number, start in zip(numbers, layer_start)],
        dtype=np.float32,
    )
    tp = ToolpathSet(
        position=position,
        layer=new_layer,
        feature=np.asarray(feature, dtype=np.uint8),
        tool=np.asarray(tool, dtype=np.uint8),
        width=np.asarray(width, dtype=np.float32),
        height=np.asarray(height, dtype=np.float32),
        time=np.asarray(time, dtype=np.float64),
        object_id=np.asarray(object_id, dtype=np.int32),
        run_start=np.asarray(run_start, dtype=np.int32),
        layer_start=layer_start,
        layer_z=layer_z,
        meta=dict(meta or {}),
    )
    tp.validate()
    return tp


class ToolpathBuilder:
    """Collects points run by run. Call build() at the end."""

    def __init__(self):
        self._xyz: list[tuple[float, float, float]] = []
        self._attrs: list[tuple[int, int, int, float, float, float, int]] = []
        self._run_start: list[int] = []
        self._layer_z: dict[int, float] = {}
        self.in_run = False

    @property
    def point_count(self) -> int:
        return len(self._xyz)

    def set_layer_z(self, layer: int, z: float) -> None:
        self._layer_z.setdefault(layer, z)

    def end_run(self) -> None:
        self.in_run = False

    def add_point(self, x, y, z, *, time, layer, feature, tool, width, height, object_id) -> None:
        """Add one point. The first point after end_run() starts a new run."""
        if not self.in_run:
            self._run_start.append(len(self._xyz))
            self.in_run = True
        self._xyz.append((x, y, z))
        self._attrs.append((layer, feature, tool, width, height, time, object_id))

    def build(self, meta: dict | None = None) -> ToolpathSet:
        if self._attrs:
            layer, feature, tool, width, height, time, object_id = zip(*self._attrs)
        else:
            layer = feature = tool = width = height = time = object_id = ()
        return pack(
            position=np.array(self._xyz, dtype=np.float32).reshape(-1, 3),
            layer=layer,
            feature=feature,
            tool=tool,
            width=width,
            height=height,
            time=time,
            object_id=object_id,
            run_start=self._run_start,
            layer_z_by_number=self._layer_z,
            meta=meta,
        )


def subset(tp: ToolpathSet, keep: np.ndarray) -> ToolpathSet:
    """Keep the points where `keep` is True. Run and layer starts must be kept."""
    if not (np.all(keep[tp.run_start]) and np.all(keep[tp.layer_start])):
        raise ValueError("subset must keep the first point of every run and layer")
    new_index = np.cumsum(keep) - 1
    return ToolpathSet(
        position=tp.position[keep],
        layer=tp.layer[keep],
        feature=tp.feature[keep],
        tool=tp.tool[keep],
        width=tp.width[keep],
        height=tp.height[keep],
        time=tp.time[keep],
        object_id=tp.object_id[keep],
        run_start=new_index[tp.run_start].astype(np.int32),
        layer_start=new_index[tp.layer_start].astype(np.int32),
        layer_z=tp.layer_z.copy(),
        meta=dict(tp.meta),
    )


def merge_points(tp: ToolpathSet, angle_deg: float) -> ToolpathSet:
    """Remove a point when the path turns by less than angle_deg there (spec section 7).

    The first and last point of each run stay. A point also stays when the width
    or the height changes there. Each kept point keeps its own print time, so the
    total print time does not change. The angle is measured from the last kept
    point, so a gentle curve does not turn into one straight line.
    """
    result_meta = dict(tp.meta, merge_angle=angle_deg)
    if angle_deg <= 0 or tp.point_count == 0:
        out = subset(tp, np.ones(tp.point_count, dtype=bool))
        out.meta = result_meta
        return out
    cos_limit = math.cos(math.radians(angle_deg))
    pos = tp.position.astype(np.float64).tolist()
    width = tp.width.tolist()
    height = tp.height.tolist()
    keep = np.ones(tp.point_count, dtype=bool)
    starts = tp.run_start.tolist()
    ends = [s - 1 for s in starts[1:]] + [tp.point_count - 1]
    for start, end in zip(starts, ends):
        anchor = start
        for i in range(start + 1, end):
            if width[i] != width[anchor] or height[i] != height[anchor] or width[i] != width[i + 1] or height[i] != height[i + 1]:
                anchor = i
                continue
            ax, ay, az = pos[anchor]
            px, py, pz = pos[i]
            nx, ny, nz = pos[i + 1]
            ux, uy, uz = px - ax, py - ay, pz - az
            vx, vy, vz = nx - px, ny - py, nz - pz
            lu = math.sqrt(ux * ux + uy * uy + uz * uz)
            lv = math.sqrt(vx * vx + vy * vy + vz * vz)
            if lu == 0.0:
                keep[i] = False
                continue
            if lv == 0.0:
                anchor = i
                continue
            if (ux * vx + uy * vy + uz * vz) / (lu * lv) > cos_limit:
                keep[i] = False
            else:
                anchor = i
    out = subset(tp, keep)
    out.meta = result_meta
    return out


def shell_point_count(tp: ToolpathSet) -> int:
    """Number of points that the ghost can draw: outer walls, overhang walls, top surfaces."""
    codes = [FEATURE_CODE["outer_wall"], FEATURE_CODE["overhang_wall"], FEATURE_CODE["top_surface"]]
    return int(np.isin(tp.feature, codes).sum())


def estimate_polygons(tp: ToolpathSet, strand_sides: int, ghost: bool) -> int:
    """Estimate from spec section 7: points x strand sides, plus ghost points x 4."""
    estimate = tp.point_count * strand_sides
    if ghost:
        estimate += shell_point_count(tp) * 4
    return estimate
