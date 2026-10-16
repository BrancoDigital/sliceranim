import math

import numpy as np
import pytest

from sliceranim.core.camera_paths import (
    START_AZIMUTH,
    Bounds,
    close_up,
    field_of_view,
    final_reveal,
    framing_distance,
    hero,
    layer_bounds,
    moving_average,
    part_bounds,
    rising_follow,
    sphere_in_view,
    turntable,
    volume_bounds,
)

BOUNDS = Bounds(center=np.array([0.0, 0.0, 50.0]), radius=50.0)


def test_part_bounds_uses_the_bounding_box():
    b = part_bounds(np.array([[0, 0, 0], [30, 40, 0]], dtype=np.float32))
    np.testing.assert_allclose(b.center, [15, 20, 0])
    assert b.radius == pytest.approx(25.0)


def test_field_of_view_for_16_9_and_square():
    h, v = field_of_view(50, 36, 1920, 1080)
    assert math.degrees(h) == pytest.approx(39.598, abs=1e-3)
    assert math.degrees(v) == pytest.approx(22.895, abs=1e-3)
    h, v = field_of_view(50, 36, 1080, 1080)
    assert h == pytest.approx(v)


def test_framing_distance_formula():
    assert framing_distance(10.0, math.radians(60)) == pytest.approx(10 / 0.5 * 1.15)


def test_turntable_makes_one_turn_without_repeating_the_first_frame():
    path = turntable(BOUNDS, 300.0, 4)
    offsets = path.location - BOUNDS.center
    np.testing.assert_allclose(np.linalg.norm(offsets, axis=1), 300.0)
    azimuth = np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0]))
    np.testing.assert_allclose(np.diff(azimuth), math.pi / 2)  # counterclockwise, a quarter turn per frame
    np.testing.assert_allclose(path.target, np.tile(BOUNDS.center, (4, 1)))
    elevation = np.degrees(np.arcsin(offsets[:, 2] / 300.0))
    np.testing.assert_allclose(elevation, 25.0)


def test_clockwise_turntable_turns_the_other_way():
    offsets = turntable(BOUNDS, 300.0, 4, clockwise=True).location - BOUNDS.center
    assert np.diff(np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0])))[0] < 0


def test_hero_is_static_at_a_three_quarter_view():
    path = hero(BOUNDS, 300.0, 3)
    assert np.ptp(path.location, axis=0).max() == 0
    offset = path.location[0] - BOUNDS.center
    assert math.degrees(math.atan2(offset[1], offset[0])) == pytest.approx(-55.0)


def test_rising_follow_aims_at_the_head_height():
    head_z = np.array([1.0, 2.0, 3.0])
    path = rising_follow(BOUNDS, 300.0, head_z)
    np.testing.assert_allclose(path.target[:, 2], head_z)
    np.testing.assert_allclose(np.diff(path.location[:, 2]), 1.0)


def test_moving_average_is_centered_and_shrinks_at_the_ends():
    points = np.array([[0, 0, 0], [3, 0, 0], [6, 0, 0], [9, 0, 0]], dtype=np.float64)
    np.testing.assert_allclose(moving_average(points, 3)[:, 0], [1.5, 3, 6, 7.5])


def test_layer_bounds_per_layer():
    position = np.array([[0, 0, 0.2], [10, 20, 0.2], [2, 2, 0.4], [4, 2, 0.4]], dtype=np.float32)
    centers, radii = layer_bounds(position, np.array([0, 2]))
    np.testing.assert_allclose(centers, [[5, 10, 0.2], [3, 2, 0.4]])
    np.testing.assert_allclose(radii, [math.hypot(10, 20) / 2, 1.0])  # a tiny layer gets at least 1 mm


def test_close_up_frames_the_whole_layer():
    targets = np.tile([5.0, 5.0, 0.2], (4, 1))
    path = close_up(targets, np.full(4, 10.0), math.radians(60))
    np.testing.assert_allclose(np.linalg.norm(path.location - path.target, axis=1), framing_distance(10.0, math.radians(60)))
    np.testing.assert_allclose(path.target, targets)


def test_close_up_smooths_jumps_between_layers():
    targets = np.array([[0, 0, 0], [10, 0, 0], [0, 0, 0], [10, 0, 0]], dtype=np.float64)
    radii = np.array([10.0, 30.0, 10.0, 30.0])
    path = close_up(targets, radii, math.radians(60), smoothing=15)
    assert np.ptp(path.target[:, 0]) < 10.0
    distance = np.linalg.norm(path.location - path.target, axis=1)
    assert np.ptp(distance) < framing_distance(20.0, math.radians(60))


def test_final_reveal_pulls_back_then_spins_90_degrees():
    previous = (np.array([0.0, -40.0, 60.0]), np.array([0.0, 0.0, 60.0]))
    path = final_reveal(BOUNDS, 300.0, 10, previous)
    np.testing.assert_allclose(path.location[0], previous[0])  # starts at the previous framing
    np.testing.assert_allclose(path.target[0], previous[1])
    offsets = path.location[4:] - BOUNDS.center  # 40% of 10 frames = 4 pull-back frames
    np.testing.assert_allclose(np.linalg.norm(offsets, axis=1), 300.0)
    azimuth = np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0]))
    assert math.degrees(azimuth[-1] - azimuth[0]) == pytest.approx(90.0)
    np.testing.assert_allclose(path.target[4:], np.tile(BOUNDS.center, (6, 1)))


def test_final_reveal_as_first_shot_starts_at_the_framing_distance():
    path = final_reveal(BOUNDS, 300.0, 5, None)
    np.testing.assert_allclose(np.linalg.norm(path.location - BOUNDS.center, axis=1), 300.0)
    offset = path.location[0] - BOUNDS.center
    assert math.atan2(offset[1], offset[0]) == pytest.approx(START_AZIMUTH)


def test_sphere_in_view():
    location = np.array([[0.0, -300.0, 0.0], [0.0, -60.0, 0.0]])
    target = np.zeros((2, 3))
    assert sphere_in_view(location, target, np.zeros(3), 50.0, math.radians(40)).tolist() == [True, False]


def test_rising_follow_keeps_the_whole_part_in_view():
    """Owner check: the rising follow shot cut off the lower part of a tall print."""
    tall = Bounds(center=np.array([128.0, 128.0, 76.5]), radius=153.0)
    head_z = np.linspace(0.2, 153.0, 50)
    fov = math.radians(22.9)  # vertical field of view at 1920×1080
    path = rising_follow(tall, None, head_z, fov=fov)
    np.testing.assert_allclose(path.target[:, 2], head_z)
    assert sphere_in_view(path.location, path.target, tall.center, tall.radius, fov).all()
    distance = np.linalg.norm(path.location - path.target, axis=1)
    assert np.ptp(distance) < 1e-6  # one distance for the whole shot, so the camera does not move in and out
    assert distance[0] >= framing_distance(tall.radius, fov)


def test_volume_bounds_hold_the_p1s_print_volume():
    bounds = volume_bounds((128.0, 128.0))
    np.testing.assert_allclose(bounds.center, [128.0, 128.0, 125.0])
    assert bounds.radius == pytest.approx(math.sqrt(256**2 + 256**2 + 250**2) / 2)
