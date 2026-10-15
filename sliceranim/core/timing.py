"""Turn the shot list into per-frame values (spec section 8).

Progress is the count of printed points. Progress = k + f (0 <= f < 1) means
points 0 to k-1 are printed and the strand into point k is a fraction f long.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .toolpaths import ToolpathSet

LINE, LAYER, HOLD = "LINE", "LAYER", "HOLD"
TURNTABLE, HERO, RISING, CLOSE_UP, REVEAL, CUSTOM = "TURNTABLE", "HERO", "RISING", "CLOSE_UP", "REVEAL", "CUSTOM"
SHORT_PRINT_LAYERS = 20


@dataclass
class Shot:
    start_layer: int | None  # layer number as the panel shows it (from 1), or None for End
    duration: float  # seconds
    style: str  # LINE, LAYER, or HOLD
    camera: str  # TURNTABLE, HERO, RISING, CLOSE_UP, REVEAL, or CUSTOM


@dataclass(frozen=True)
class ShotProblem:
    row: int  # shot index from 0, or -1 for the whole list
    rule: int  # rule number from spec 8.3, or 0 for a value out of range
    message: str


@dataclass
class FramePlan:
    progress: np.ndarray  # float64 (F,)
    current_layer: np.ndarray  # float64 (F,), layer index from 0
    head: np.ndarray  # float64 (F, 3), mm
    shot_index: np.ndarray  # int32 (F,)
    shot_first_frame: list[int] = field(default_factory=list)  # scene frame of each shot start, from 1
    shot_frame_count: list[int] = field(default_factory=list)

    @property
    def frame_count(self) -> int:
        return int(len(self.progress))


def default_shots(layer_count: int) -> list[Shot]:
    """The shot list that the importer makes (spec 8.4)."""
    if layer_count < SHORT_PRINT_LAYERS:
        return [Shot(1, 20.0, LINE, TURNTABLE), Shot(None, 4.0, HOLD, REVEAL)]
    return [
        Shot(1, 4.0, LINE, CLOSE_UP),
        Shot(6, 12.0, LAYER, TURNTABLE),
        Shot(layer_count - 4, 4.0, LINE, RISING),
        Shot(None, 4.0, HOLD, REVEAL),
    ]


def _start_index(shot: Shot, layer_count: int) -> int:
    """Layer index where the shot starts. layer_count stands for End."""
    return layer_count if shot.start_layer is None else shot.start_layer - 1


def validate_shots(shots: list[Shot], layer_count: int) -> list[ShotProblem]:
    """Check the rules of spec 8.3. Return one problem per failed rule and row."""
    if not shots:
        return [ShotProblem(-1, 0, "Add at least one shot.")]
    problems = []
    for row, shot in enumerate(shots):
        if shot.start_layer is not None and not 1 <= shot.start_layer <= layer_count:
            problems.append(ShotProblem(row, 0, f"Start layer must be 1 to {layer_count}, or End."))
        if row == 0 and shot.start_layer != 1:
            problems.append(ShotProblem(row, 1, "The first shot must start at layer 1."))
        if shot.start_layer is None and shot.style != HOLD:
            problems.append(ShotProblem(row, 4, "Only a Hold shot can start at End."))
        if not shot.duration > 0:
            problems.append(ShotProblem(row, 5, "Duration must be more than 0 seconds."))
        if row + 1 < len(shots):
            here = _start_index(shot, layer_count)
            there = _start_index(shots[row + 1], layer_count)
            if there < here:
                problems.append(ShotProblem(row + 1, 2, "Start layers must not go down from one shot to the next."))
            elif there == here and shot.style != HOLD:
                problems.append(ShotProblem(row, 3, "Only a Hold shot can have the same start layer as the next shot."))
    return problems


def shot_frame_counts(shots: list[Shot], fps: int) -> list[int]:
    return [max(1, int(round(shot.duration * fps))) for shot in shots]


def progress_at_time(tp: ToolpathSet, t) -> np.ndarray:
    """Progress at print time t (seconds)."""
    t = np.atleast_1d(np.asarray(t, dtype=np.float64))
    time = tp.time
    n = tp.point_count
    j = np.searchsorted(time, t, side="right")
    progress = j.astype(np.float64)
    inside = (j > 0) & (j < n)
    jj = j[inside]
    span = time[jj] - time[jj - 1]
    progress[inside] += np.where(span > 0, (t[inside] - time[jj - 1]) / np.where(span > 0, span, 1.0), 0.0)
    return progress


def state_at(tp: ToolpathSet, progress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Current layer and print head position (mm) for each Progress value.

    The current layer is the layer of the newest point. The head sits at the tip of the growing strand.
    """
    n = tp.point_count
    progress = np.asarray(progress, dtype=np.float64)
    k = np.floor(progress).astype(np.int64)
    f = progress - k
    newest = np.clip(np.where(f > 0, k, k - 1), 0, n - 1)
    current_layer = tp.layer[newest].astype(np.float64)
    position = tp.position.astype(np.float64)
    head = position[newest].copy()
    starts = tp.run_start_mask()
    growing = (f > 0) & (k >= 1) & (k < n)
    growing[growing] &= ~starts[k[growing]]
    kk = k[growing]
    head[growing] = position[kk - 1] + f[growing, None] * (position[kk] - position[kk - 1])
    return current_layer, head


def plan_frames(tp: ToolpathSet, shots: list[Shot], fps: int) -> FramePlan:
    """Compute Progress, current layer, and print head for every frame. The shots must be valid."""
    layers = tp.layer_count
    progress_of_layer = np.append(tp.layer_start, tp.point_count).astype(np.float64)
    time_of_layer = np.append(tp.time[tp.layer_start], tp.total_time)
    counts = shot_frame_counts(shots, fps)
    parts, index_parts, first_frames = [], [], []
    frame = 1
    for row, (shot, count) in enumerate(zip(shots, counts)):
        last = row == len(shots) - 1
        a = _start_index(shot, layers)
        b = layers if last else _start_index(shots[row + 1], layers)
        i = np.arange(count, dtype=np.float64)
        s = (i + 1) / count if last else i / count
        if shot.style == HOLD:
            p = np.full(count, progress_of_layer[a])
        elif shot.style == LAYER:
            done = np.floor(s * (b - a) + 1e-9).astype(np.int64)
            p = progress_of_layer[a + done]
        else:
            t0, t1 = time_of_layer[a], time_of_layer[b]
            if t1 > t0:
                p = progress_at_time(tp, t0 + s * (t1 - t0))
            else:
                p = progress_of_layer[a] + s * (progress_of_layer[b] - progress_of_layer[a])
            p = np.clip(p, progress_of_layer[a], progress_of_layer[b])
        parts.append(p)
        index_parts.append(np.full(count, row, dtype=np.int32))
        first_frames.append(frame)
        frame += count
    progress = np.concatenate(parts)
    current_layer, head = state_at(tp, progress)
    return FramePlan(
        progress=progress,
        current_layer=current_layer,
        head=head,
        shot_index=np.concatenate(index_parts),
        shot_first_frame=first_frames,
        shot_frame_count=counts,
    )
