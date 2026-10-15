import bpy
import numpy as np
from helpers import CUBE, evaluated_bounds, evaluated_polygons

from sliceranim.blender import importer, nodes
from sliceranim.core.gcode_reader import read_gcode


def make_object():
    tp = read_gcode(CUBE)
    obj = bpy.data.objects.new("cube", importer.toolpath_mesh(tp, "cube"))
    bpy.context.scene.collection.objects.link(obj)
    nodes.ensure_modifier(obj, bpy.data.materials.new("filament"), bpy.data.materials.new("ghost"))
    nodes.set_input(obj, "Profile Aspect", 0.2 / 0.45)
    return tp, obj


def test_mesh_has_one_vertex_per_point_and_one_edge_per_strand():
    tp, obj = make_object()
    assert len(obj.data.vertices) == tp.point_count == 42
    assert len(obj.data.edges) == 30
    for name in ("order", "layer", "feature", "tool", "width", "height", "time"):
        assert name in obj.data.attributes, name
    np.testing.assert_allclose(obj.data.vertices[1].co, (9.325e-3, 0.675e-3, 0.2e-3), atol=1e-7)


def test_toolpaths_read_back_from_the_object_match_the_source():
    tp, obj = make_object()
    back = importer.toolpath_from_object(obj)
    np.testing.assert_allclose(back.position, tp.position, atol=1e-4)
    assert back.run_start.tolist() == tp.run_start.tolist()
    assert back.layer_start.tolist() == tp.layer_start.tolist()
    np.testing.assert_allclose(back.time, tp.time, rtol=1e-6)
    np.testing.assert_allclose(back.width, tp.width, rtol=1e-5)


def test_progress_controls_how_many_strands_are_drawn():
    _, obj = make_object()
    sides = nodes.get_input(obj, "Viewport Strand Sides")
    assert sides == 4
    for progress, strands in ((0.0, 0), (2.5, 2), (5.0, 4), (42.0, 30)):
        nodes.set_input(obj, "Progress", progress)
        assert evaluated_polygons(obj) == strands * sides, progress


def test_ghost_adds_the_unprinted_outer_walls_only():
    _, obj = make_object()
    nodes.set_input(obj, "Progress", 0.0)
    nodes.set_input(obj, "Ghost", True)
    assert evaluated_polygons(obj) == 12 * 4  # 4 outer wall strands per layer, 3 layers
    nodes.set_input(obj, "Progress", 42.0)
    assert evaluated_polygons(obj) == 30 * 4


def test_strands_are_flat_ovals_of_strand_width_and_height():
    _, obj = make_object()
    nodes.set_input(obj, "Progress", 42.0)
    low, high = evaluated_bounds(obj)
    np.testing.assert_allclose(high[2], 0.6e-3 + 0.1e-3, atol=1e-6)  # top layer z + half the height
    np.testing.assert_allclose(low[:2], [0.0, 0.0], atol=1e-6)  # outer wall at 0.225 mm, minus half of 0.45 mm


def test_input_paths_can_be_keyframed():
    _, obj = make_object()
    path = nodes.input_path(obj, "Progress")
    assert path.startswith('modifiers["Slicer Animator"].properties.inputs.')
    assert obj.keyframe_insert(path, frame=1)
