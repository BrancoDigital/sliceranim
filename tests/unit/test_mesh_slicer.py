import struct

import numpy as np
import pytest

from sliceranim.core.mesh_slicer import (
    clean,
    cut_layer,
    has_open_edges,
    offset,
    read_stl,
    self_intersects,
    signed_area,
    slice_mesh,
    to_millimeters,
)
from sliceranim.core.errors import SlicerAnimError
from sliceranim.core.toolpaths import FEATURE_CODE


def box(x0, x1, y0, y1, z0, z1):
    """A closed box: 8 vertices, 12 triangles with outward normals."""
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=np.float64)
    t = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v, t


def walls(polygon, height):
    """Side walls only of a prism over `polygon` (no caps). The mesh is open at top and bottom."""
    n = len(polygon)
    bottom = [(x, y, 0.0) for x, y in polygon]
    top = [(x, y, height) for x, y in polygon]
    v = np.array(bottom + top, dtype=np.float64)
    t = []
    for i in range(n):
        j = (i + 1) % n
        t += [[i, j, n + j], [i, n + j, n + i]]
    return v, np.array(t)


def square(cx, cy, side):
    h = side / 2
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]


def test_cube_gives_two_loops_per_layer_at_the_right_offsets():
    v, t = box(0, 10, 0, 10, 5, 15)  # z starts at 5 to check the shift to the plate
    tp, open_edges = slice_mesh(v, t)
    assert not open_edges
    assert tp.layer_count == 50
    np.testing.assert_allclose(tp.layer_z[[0, -1]], [0.2, 10.0], atol=1e-5)
    first = tp.position[tp.layer == 0]
    inner = first[tp.feature[tp.layer == 0] == FEATURE_CODE["inner_wall"]]
    outer = first[tp.feature[tp.layer == 0] == FEATURE_CODE["outer_wall"]]
    np.testing.assert_allclose(inner[:, :2].min(axis=0), [0.675, 0.675], atol=1e-4)
    np.testing.assert_allclose(outer[:, :2].min(axis=0), [0.225, 0.225], atol=1e-4)
    np.testing.assert_allclose(outer[:, :2].max(axis=0), [9.775, 9.775], atol=1e-4)
    # Inner loop first, then outer loop. Each loop is closed: 4 corners + the first corner again.
    assert tp.run_start[:2].tolist() == [0, 5]
    assert tp.feature[:5].tolist() == [FEATURE_CODE["inner_wall"]] * 5
    np.testing.assert_allclose(tp.position[0], tp.position[4])


def test_print_time_comes_from_100_mm_per_second():
    v, t = box(0, 10, 0, 10, 0, 0.4)
    tp, _ = slice_mesh(v, t)
    loop_lengths = 4 * (10 - 2 * 0.675) + 4 * (10 - 2 * 0.225)
    assert tp.time[tp.layer_start[1] - 1] == pytest.approx(loop_lengths / 100.0, rel=1e-6)


def test_thin_wall_drops_the_inner_loop():
    v, t = box(0, 1.0, 0, 10, 0, 1)  # 1.0 mm is thinner than 3 strand widths (1.35 mm)
    tp, _ = slice_mesh(v, t)
    assert set(tp.feature.tolist()) == {FEATURE_CODE["outer_wall"]}


def test_hole_gets_its_loops_on_the_material_side():
    outer_v, outer_t = walls(square(0, 0, 20), 1.0)
    hole_v, hole_t = walls(square(0, 0, 6)[::-1], 1.0)
    v = np.vstack([outer_v, hole_v])
    t = np.vstack([outer_t, hole_t + len(outer_v)])
    tp, open_edges = slice_mesh(v, t)
    assert open_edges  # no caps
    layer0 = tp.position[tp.layer == 0][:, :2]
    radius = np.abs(layer0.astype(np.float64)).max(axis=1)  # distance from the center in the square metric
    # Hole loops sit outside the 3 mm hole edge, outer loops inside the 10 mm outer edge.
    assert sorted(set(np.round(radius, 3).tolist())) == [3.225, 3.675, 9.325, 9.775]


def test_cut_layer_returns_one_closed_outline_for_a_box():
    v, t = box(0, 10, 0, 10, 0, 10)
    loops = cut_layer(v, t, 5.0)
    assert len(loops) == 1
    assert abs(signed_area(loops[0])) == pytest.approx(100.0)


def test_cut_exactly_at_a_vertex_height_still_works():
    v, t = box(0, 10, 0, 10, 0, 10)
    assert len(cut_layer(v, t, 10.0 - 1e-12)) <= 1
    assert len(cut_layer(v, t, 0.0)) == 1


def test_clean_removes_repeated_and_straight_points():
    loop = np.array([(0, 0), (0, 0), (5, 0), (10, 0), (10, 10), (0, 10)], dtype=np.float64)
    np.testing.assert_allclose(clean(loop), [(0, 0), (10, 0), (10, 10), (0, 10)])


def test_offset_moves_a_counterclockwise_square_inward():
    sq = np.array(square(0, 0, 10), dtype=np.float64)
    moved = offset(sq, 1.0)
    np.testing.assert_allclose(np.abs(moved), 4.0)


def test_self_intersects_finds_a_bow_tie():
    bow_tie = np.array([(0, 0), (2, 2), (2, 0), (0, 2)], dtype=np.float64)
    assert self_intersects(bow_tie)
    assert not self_intersects(np.array(square(0, 0, 2), dtype=np.float64))


def test_has_open_edges():
    v, t = box(0, 1, 0, 1, 0, 1)
    assert not has_open_edges(t)
    assert has_open_edges(t[:-1])


def test_read_binary_and_ascii_stl(tmp_path):
    v, t = box(0, 10, 0, 10, 0, 10)
    binary = tmp_path / "cube.stl"
    with open(binary, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(t)))
        for tri in t:
            f.write(struct.pack("<3f", 0, 0, 0))
            for corner in tri:
                f.write(struct.pack("<3f", *v[corner]))
            f.write(b"\0\0")
    ascii_path = tmp_path / "cube_ascii.stl"
    lines = ["solid cube"]
    for tri in t:
        lines += ["facet normal 0 0 0", "outer loop"] + [f"vertex {x} {y} {z}" for x, y, z in v[tri]] + ["endloop", "endfacet"]
    ascii_path.write_text("\n".join(lines + ["endsolid cube"]))
    for path in (binary, ascii_path):
        vertices, triangles = read_stl(path)
        assert triangles.shape == (12, 3)
        np.testing.assert_allclose(vertices[triangles[0]], v[t[0]])
        tp, open_edges = slice_mesh(vertices, triangles)
        assert not open_edges
        assert tp.layer_count == 50


def test_to_millimeters_uses_the_scene_unit_scale():
    v, _ = box(0, 0.02, 0, 0.02, 0, 0.01)  # 20 mm × 20 mm × 10 mm in meters
    mm, units_as_mm = to_millimeters(v, 1000.0)
    np.testing.assert_allclose(mm.max(axis=0), [20.0, 20.0, 10.0])
    assert not units_as_mm


def test_to_millimeters_reads_1_unit_as_1_mm_for_a_part_too_large_to_print():
    v, _ = box(0, 191.8, 0, 191.8, 0, 153.1)  # the Blender STL import puts 1 mm at 1 unit
    mm, units_as_mm = to_millimeters(v, 1000.0)
    np.testing.assert_allclose(mm.max(axis=0), [191.8, 191.8, 153.1])
    assert units_as_mm


def test_to_millimeters_refuses_a_part_too_large_even_at_1_mm_per_unit():
    v, _ = box(0, 1500, 0, 10, 0, 10)
    with pytest.raises(SlicerAnimError, match="1500 mm across"):
        to_millimeters(v, 1000.0)
