"""Camera location and aim point for every frame of a shot (spec section 9).

Units are mm and radians. Azimuth 0 points along +X. The front of the plate is -Y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MARGIN = 1.15
START_AZIMUTH = -math.pi / 2 + math.radians(35)  # three-quarter view from the front right
P1S_VOLUME_MM = (256.0, 256.0, 250.0)  # print volume of the Bambu Lab P1S (printable area and height of its preset)


@dataclass(frozen=True)
class Bounds:
    center: np.ndarray  # (3,)
    radius: float  # radius of the bounding sphere of the bounding box


@dataclass
class CameraPath:
    location: np.ndarray  # (F, 3)
    target: np.ndarray  # (F, 3)


def part_bounds(position: np.ndarray) -> Bounds:
    low = position.min(axis=0).astype(np.float64)
    high = position.max(axis=0).astype(np.float64)
    return Bounds(center=(low + high) / 2, radius=max(float(np.linalg.norm(high - low)) / 2, 1e-3))


def volume_bounds(center_xy, size=P1S_VOLUME_MM) -> Bounds:
    """Bounds of the print volume, standing on z = 0 with its middle at `center_xy` (mm)."""
    center = np.array([center_xy[0], center_xy[1], size[2] / 2], dtype=np.float64)
    return Bounds(center=center, radius=float(np.linalg.norm(size)) / 2)


def field_of_view(lens_mm: float, sensor_mm: float, width_px: int, height_px: int) -> tuple[float, float]:
    """Horizontal and vertical field of view of a Blender camera with sensor fit Auto."""
    half_long = math.atan(sensor_mm / 2 / lens_mm)
    if width_px >= height_px:
        horizontal = 2 * half_long
        vertical = 2 * math.atan(math.tan(half_long) * height_px / width_px)
    else:
        vertical = 2 * half_long
        horizontal = 2 * math.atan(math.tan(half_long) * width_px / height_px)
    return horizontal, vertical


def framing_distance(radius: float, fov: float, margin: float = MARGIN) -> float:
    """Distance at which the bounding sphere fits the smaller field of view, times the margin."""
    return radius / math.sin(fov / 2) * margin


def orbit_point(center, distance, azimuth, elevation) -> np.ndarray:
    """Points at `distance` from center. Azimuth and elevation can be arrays."""
    azimuth = np.asarray(azimuth, dtype=np.float64)
    elevation = np.asarray(elevation, dtype=np.float64)
    direction = np.stack(
        [np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth), np.sin(elevation)], axis=-1
    )
    return np.asarray(center, dtype=np.float64) + np.asarray(distance, dtype=np.float64)[..., None] * direction


def _fixed(center, count) -> np.ndarray:
    return np.tile(np.asarray(center, dtype=np.float64), (count, 1))


def turntable(bounds: Bounds, distance: float, frames: int, *, turns=1.0, height_angle=math.radians(25), clockwise=False) -> CameraPath:
    s = np.arange(frames) / frames
    azimuth = START_AZIMUTH + (-1 if clockwise else 1) * 2 * math.pi * turns * s
    location = orbit_point(bounds.center, np.full(frames, distance), azimuth, np.full(frames, height_angle))
    return CameraPath(location, _fixed(bounds.center, frames))


def hero(bounds: Bounds, distance: float, frames: int, *, height_angle=math.radians(30), side_angle=math.radians(35)) -> CameraPath:
    azimuth = -math.pi / 2 + side_angle
    location = orbit_point(bounds.center, np.full(frames, distance), np.full(frames, azimuth), np.full(frames, height_angle))
    return CameraPath(location, _fixed(bounds.center, frames))


def sphere_in_view(location, target, center, radius: float, fov: float) -> np.ndarray:
    """True for each frame where the whole sphere is inside a view cone of angle `fov` around the aim line."""
    location = np.atleast_2d(np.asarray(location, dtype=np.float64))
    aim = np.atleast_2d(np.asarray(target, dtype=np.float64)) - location
    to_center = np.asarray(center, dtype=np.float64) - location
    distance = np.linalg.norm(to_center, axis=1)
    cosine = np.einsum("ij,ij->i", aim, to_center) / np.maximum(np.linalg.norm(aim, axis=1) * distance, 1e-12)
    off_axis = np.arccos(np.clip(cosine, -1.0, 1.0))
    half_size = np.arcsin(np.clip(radius / np.maximum(distance, 1e-12), 0.0, 1.0))
    return (distance > radius) & (off_axis + half_size <= fov / 2 + 1e-9)


def fit_distance(bounds: Bounds, target: np.ndarray, azimuth: float, elevation: float, fov: float,
                 margin: float = MARGIN) -> float:
    """The smallest distance from `target` (F, 3) at which the bounding sphere, grown by the margin,
    stays in view on every frame. It equals framing_distance() when the target is the center."""
    target = np.asarray(target, dtype=np.float64)
    radius = bounds.radius * margin
    direction = orbit_point(np.zeros(3), np.array(1.0), np.array(azimuth), np.array(elevation))

    def fits(distance: float) -> bool:
        return bool(sphere_in_view(target + distance * direction, target, bounds.center, radius, fov).all())

    low = framing_distance(bounds.radius, fov, margin)
    if fits(low):
        return low
    high = 2 * low
    while not fits(high):
        high *= 2
    for _ in range(40):
        middle = (low + high) / 2
        low, high = (low, middle) if fits(middle) else (middle, high)
    return high


def rising_follow(bounds: Bounds, distance: float | None, head_z: np.ndarray, *, fov: float | None = None,
                  height_angle=math.radians(20)) -> CameraPath:
    """Move up with the print head and aim at its height. Without a set distance, the camera stays far
    enough away that the whole part is in view on every frame (spec section 9)."""
    frames = len(head_z)
    target = _fixed(bounds.center, frames)
    target[:, 2] = head_z
    if distance is None:
        distance = fit_distance(bounds, target, START_AZIMUTH, height_angle, fov)
    location = orbit_point(target, np.full(frames, distance), np.full(frames, START_AZIMUTH), np.full(frames, height_angle))
    return CameraPath(location, target)


def moving_average(points: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average. Near the ends, the window gets smaller."""
    points = np.asarray(points, dtype=np.float64)
    if window <= 1 or len(points) < 2:
        return points.copy()
    half = window // 2
    padded = np.vstack([np.zeros((1, points.shape[1])), np.cumsum(points, axis=0)])
    index = np.arange(len(points))
    low = np.clip(index - half, 0, len(points))
    high = np.clip(index + half + 1, 0, len(points))
    return (padded[high] - padded[low]) / (high - low)[:, None]


def layer_bounds(position: np.ndarray, layer_start: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Center (L, 3) and bounding sphere radius (L,) of each layer's bounding box. The radius is at least 1 mm."""
    position = np.asarray(position, dtype=np.float64)
    low = np.minimum.reduceat(position, layer_start, axis=0)
    high = np.maximum.reduceat(position, layer_start, axis=0)
    return (low + high) / 2, np.maximum(np.linalg.norm(high - low, axis=1) / 2, 1.0)


def close_up(targets: np.ndarray, radii: np.ndarray, fov: float, *, smoothing=15, height_angle=math.radians(30), side_angle=math.radians(35)) -> CameraPath:
    """Frame the full layer that is printing.

    `targets` (mm) and `radii` (mm) are per frame: the center and radius of the current layer,
    or a fixed point. The camera stays at the framing distance of the radius. Both values are
    smoothed, so the camera does not jump when a new layer has another size.
    """
    target = moving_average(targets, smoothing)
    radius = moving_average(np.asarray(radii, dtype=np.float64)[:, None], smoothing)[:, 0]
    frames = len(target)
    distance = radius / math.sin(fov / 2) * MARGIN
    azimuth = -math.pi / 2 + side_angle
    location = orbit_point(target, distance, np.full(frames, azimuth), np.full(frames, height_angle))
    return CameraPath(location, target)


def _smoothstep(u: np.ndarray) -> np.ndarray:
    return u * u * (3 - 2 * u)


def final_reveal(
    bounds: Bounds,
    distance: float,
    frames: int,
    previous: tuple[np.ndarray, np.ndarray] | None,
    *,
    spin=math.radians(90),
    pullback_share=0.4,
) -> CameraPath:
    """Pull back from the previous framing, then spin around the part (spec section 9).

    `previous` is the (location, target) of the previous shot's last frame, or None.
    """
    pull = min(frames, int(round(frames * pullback_share)))
    if previous is None:
        azimuth, elevation = START_AZIMUTH, math.radians(30)
    else:
        offset = np.asarray(previous[0], dtype=np.float64) - bounds.center
        azimuth = math.atan2(offset[1], offset[0])
        horizontal = math.hypot(offset[0], offset[1])
        elevation = min(max(math.atan2(offset[2], horizontal), math.radians(5)), math.radians(60))
    pose = orbit_point(bounds.center, np.array(distance), np.array(azimuth), np.array(elevation))
    location = np.zeros((frames, 3))
    target = _fixed(bounds.center, frames)
    if pull:
        u = _smoothstep(np.arange(pull) / pull)[:, None]
        if previous is None:
            location[:pull] = pose
        else:
            location[:pull] = previous[0] + u * (pose - previous[0])
            target[:pull] = previous[1] + u * (bounds.center - previous[1])
    rest = frames - pull
    if rest:
        v = np.arange(rest) / max(rest - 1, 1)
        location[pull:] = orbit_point(bounds.center, np.full(rest, distance), azimuth + spin * v, np.full(rest, elevation))
    return CameraPath(location, target)
