"""The Geometry Nodes setup that draws the strands (spec section 7)."""

import bpy

GROUP_NAME = "Slicer Animator Strands"
MODIFIER_NAME = "Slicer Animator"
SHELL_FEATURES = (1, 3, 6)  # outer_wall, overhang_wall, top_surface
GHOST_RENDER_SIDES = 4
INPUTS = (
    ("Progress", "NodeSocketFloat", 0.0),
    ("Current Layer", "NodeSocketFloat", 0.0),
    ("Strand Sides", "NodeSocketInt", 6),
    ("Viewport Strand Sides", "NodeSocketInt", 4),
    ("Ghost", "NodeSocketBool", False),
    ("Highlight Layers", "NodeSocketFloat", 3.0),
    ("Profile Aspect", "NodeSocketFloat", 0.45),
)


class _Builder:
    def __init__(self, tree):
        self.tree = tree

    def node(self, idname, **props):
        n = self.tree.nodes.new(idname)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def link(self, out_socket, in_socket):
        self.tree.links.new(out_socket, in_socket)

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def compare(self, op, a, b, data_type="FLOAT"):
        n = self.node("FunctionNodeCompare", data_type=data_type, operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def boolean(self, op, a, b=None):
        n = self.node("FunctionNodeBooleanMath", operation=op)
        self.link(a, n.inputs[0])
        if b is not None:
            self.link(b, n.inputs[1])
        return n.outputs[0]

    def attr(self, name, data_type):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=data_type)
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    def switch(self, input_type, cond, false, true):
        n = self.node("GeometryNodeSwitch", input_type=input_type)
        self.link(cond, n.inputs[0])
        for i, v in ((1, false), (2, true)):
            if v is None:
                continue
            if isinstance(v, (int, float, bool)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]


def _sweep(b, curve_geo, sides, aspect, material):
    """Sweep an oval profile with `sides` points along curves made from mesh edges."""
    to_curve = b.node("GeometryNodeMeshToCurve")
    b.link(curve_geo, to_curve.inputs["Mesh"])
    normal = b.node("GeometryNodeSetCurveNormal")
    normal.inputs["Mode"].default_value = "Z Up"
    b.link(to_curve.outputs[0], normal.inputs["Curve"])
    circle = b.node("GeometryNodeCurvePrimitiveCircle", mode="RADIUS")
    b.link(sides, circle.inputs["Resolution"])
    circle.inputs["Radius"].default_value = 1.0
    squash = b.node("ShaderNodeCombineXYZ")
    squash.inputs[0].default_value = 1.0
    squash.inputs[2].default_value = 1.0
    b.link(aspect, squash.inputs[1])
    xform = b.node("GeometryNodeTransform")
    b.link(circle.outputs["Curve"], xform.inputs["Geometry"])
    b.link(squash.outputs[0], xform.inputs["Scale"])
    sweep = b.node("GeometryNodeCurveToMesh")
    b.link(normal.outputs[0], sweep.inputs["Curve"])
    b.link(xform.outputs[0], sweep.inputs["Profile Curve"])
    b.link(b.math("MULTIPLY", b.attr("width", "FLOAT"), 0.5), sweep.inputs["Scale"])
    smooth = b.node("GeometryNodeSetShadeSmooth")
    b.link(sweep.outputs[0], smooth.inputs[0])
    setmat = b.node("GeometryNodeSetMaterial")
    setmat.inputs["Material"].default_value = material
    b.link(smooth.outputs[0], setmat.inputs["Geometry"])
    return setmat.outputs[0]


def build_strand_group(filament_material, ghost_material):
    old = bpy.data.node_groups.get(GROUP_NAME)
    if old is not None:
        bpy.data.node_groups.remove(old)
    tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name, socket_type, default in INPUTS:
        s = tree.interface.new_socket(name, in_out="INPUT", socket_type=socket_type)
        s.default_value = default
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    b = _Builder(tree)
    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")
    geo = gi.outputs["Geometry"]

    k = b.math("FLOOR", gi.outputs["Progress"])
    frac = b.math("SUBTRACT", gi.outputs["Progress"], k)
    order = b.attr("order", "INT")

    # Steps 1 and 2: keep points 0..k, and slide point k toward its previous point.
    delete = b.node("GeometryNodeDeleteGeometry", domain="POINT")
    b.link(geo, delete.inputs["Geometry"])
    b.link(b.compare("GREATER_THAN", order, k), delete.inputs["Selection"])
    neighbors = b.node("GeometryNodeInputMeshVertexNeighbors")
    is_last = b.boolean("AND", b.compare("EQUAL", order, k),
                        b.compare("GREATER_THAN", neighbors.outputs["Vertex Count"], 0.5))
    index = b.node("GeometryNodeInputIndex")
    position = b.node("GeometryNodeInputPosition")
    prev = b.node("GeometryNodeSampleIndex", data_type="FLOAT_VECTOR", domain="POINT")
    b.link(delete.outputs[0], prev.inputs["Geometry"])
    b.link(position.outputs[0], prev.inputs["Value"])
    b.link(b.math("SUBTRACT", index.outputs[0], 1.0), prev.inputs["Index"])
    lerp = b.node("ShaderNodeMix", data_type="VECTOR")
    b.link(frac, lerp.inputs["Factor"])
    b.link(prev.outputs[0], lerp.inputs[4])
    b.link(position.outputs[0], lerp.inputs[5])
    setpos = b.node("GeometryNodeSetPosition")
    b.link(delete.outputs[0], setpos.inputs["Geometry"])
    b.link(is_last, setpos.inputs["Selection"])
    b.link(lerp.outputs[1], setpos.inputs["Position"])

    # Step 6: heat for the active-layer highlight.
    behind = b.math("SUBTRACT", gi.outputs["Current Layer"], b.attr("layer", "INT"))
    heat = b.math("SUBTRACT", 1.0, b.math("DIVIDE", behind, gi.outputs["Highlight Layers"]), clamp=True)
    store = b.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    store.inputs["Name"].default_value = "heat"
    b.link(setpos.outputs[0], store.inputs["Geometry"])
    b.link(heat, store.inputs["Value"])

    is_viewport = b.node("GeometryNodeIsViewport").outputs[0]
    sides = b.switch("INT", is_viewport, gi.outputs["Strand Sides"], gi.outputs["Viewport Strand Sides"])
    printed = _sweep(b, store.outputs[0], sides, gi.outputs["Profile Aspect"], filament_material)

    # Step 8: the ghost shell of the part that is not printed yet.
    feature = b.attr("feature", "INT")
    shell = b.compare("EQUAL", feature, SHELL_FEATURES[0], "INT")
    for code in SHELL_FEATURES[1:]:
        shell = b.boolean("OR", shell, b.compare("EQUAL", feature, code, "INT"))
    keep = b.boolean("AND", b.compare("GREATER_THAN", order, k), shell)
    ghost_delete = b.node("GeometryNodeDeleteGeometry", domain="POINT")
    b.link(geo, ghost_delete.inputs["Geometry"])
    b.link(b.boolean("NOT", keep), ghost_delete.inputs["Selection"])
    ghost_sides = b.switch("INT", is_viewport, GHOST_RENDER_SIDES, gi.outputs["Viewport Strand Sides"])
    ghost = _sweep(b, ghost_delete.outputs[0], ghost_sides, gi.outputs["Profile Aspect"], ghost_material)
    ghost_on = b.switch("GEOMETRY", gi.outputs["Ghost"], None, ghost)

    join = b.node("GeometryNodeJoinGeometry")
    b.link(printed, join.inputs[0])
    b.link(ghost_on, join.inputs[0])
    b.link(join.outputs[0], go.inputs["Geometry"])
    return tree

def ensure_modifier(obj, filament_material, ghost_material):
    """Give `obj` the strand modifier with a fresh node group."""
    group = build_strand_group(filament_material, ghost_material)
    modifier = obj.modifiers.get(MODIFIER_NAME) or obj.modifiers.new(MODIFIER_NAME, "NODES")
    modifier.node_group = group
    return modifier


def _identifier(obj, name: str) -> str:
    group = obj.modifiers[MODIFIER_NAME].node_group
    for item in group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(name)


def _input(obj, name: str):
    return getattr(obj.modifiers[MODIFIER_NAME].properties.inputs, _identifier(obj, name))


def set_input(obj, name: str, value) -> None:
    """Set a modifier input. Blender 5.2 does not redraw on its own after this, so tag the object."""
    _input(obj, name).value = value
    obj.update_tag()


def get_input(obj, name: str):
    return _input(obj, name).value


def input_path(obj, name: str) -> str:
    """Data path for keyframes, for example modifiers["Slicer Animator"].properties.inputs.Socket_2.value."""
    return _input(obj, name).path_from_id("value")


def apply_settings(scene) -> None:
    """Copy the strand settings from the panel to the modifier."""
    settings = scene.sliceranim
    obj = settings.toolpath_object
    if obj is None or MODIFIER_NAME not in obj.modifiers:
        return
    set_input(obj, "Strand Sides", int(settings.strand_sides))
    set_input(obj, "Viewport Strand Sides", int(settings.viewport_strand_sides))
    set_input(obj, "Ghost", settings.ghost)
    set_input(obj, "Highlight Layers", float(settings.highlight_layers))
