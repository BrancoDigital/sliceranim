"""Materials, backdrop, lights, plate mat, and nozzle tip (spec section 10)."""

import json
import math

import bpy
import numpy as np
from mathutils import Vector

from ..core.camera_paths import START_AZIMUTH
from . import keys

MM = 0.001
COLLECTION = "Slicer Animator"
HIGHLIGHT_STRENGTH = 4.0
FINISHES = {
    # roughness, specular IOR level, sheen weight, transmission weight
    "MATTE": (0.6, 0.3, 0.0, 0.0),
    "GLOSSY": (0.15, 0.5, 0.0, 0.0),
    "SILK": (0.25, 0.7, 0.8, 0.0),
    "TRANSLUCENT": (0.2, 0.5, 0.0, 0.7),
}
# name: (azimuth from START_AZIMUTH, elevation, power factor). Power = factor x distance² (W, distance in m).
LIGHTS = {
    "SA Key Light": (math.radians(-40), math.radians(45), 60.0),
    "SA Fill Light": (math.radians(70), math.radians(20), 25.0),
    "SA Rim Light": (math.radians(180), math.radians(50), 50.0),
}
PLATE_SIZE_MM = 256.0
BAMBU_PLATE_CENTER_MM = (128.0, 128.0)
NOZZLE_HEIGHT_MM = 6.0
NOZZLE_LIFT_MM = 0.1  # strands are drawn centered on the nozzle height, so lift the tip by half a layer


def hex_to_linear(value: str) -> tuple[float, float, float]:
    """Turn "#RRGGBB" (sRGB) into linear RGB, the color space of Blender color properties."""
    value = value.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)


def collection(scene) -> bpy.types.Collection:
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def put_object(scene, name: str, data) -> bpy.types.Object:
    """Return the object `name` with new `data`, made and linked if needed."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, data)
        collection(scene).objects.link(obj)
    elif data is not None and obj.data is not data:
        old = obj.data
        obj.data = data
        if old is not None and old.users == 0:
            _remove_data(old)
    return obj


def remove_object(name: str) -> None:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    data = obj.data
    bpy.data.objects.remove(obj)
    if data is not None and data.users == 0:
        _remove_data(data)


def _remove_data(data) -> None:
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Light):
        bpy.data.lights.remove(data)
    elif isinstance(data, bpy.types.Camera):
        bpy.data.cameras.remove(data)


def _principled(material) -> bpy.types.Node:
    return next(n for n in material.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _material(name: str) -> tuple[bpy.types.Material, bool]:
    material = bpy.data.materials.get(name)
    if material is not None:
        return material, False
    return bpy.data.materials.new(name), True


def filament_material() -> bpy.types.Material:
    material, new = _material("SA Filament")
    if new:
        tree = material.node_tree
        bsdf = _principled(material)
        heat = tree.nodes.new("ShaderNodeAttribute")
        heat.attribute_type = "GEOMETRY"
        heat.attribute_name = "heat"
        strength = tree.nodes.new("ShaderNodeMath")
        strength.name = "SA Highlight Strength"
        strength.operation = "MULTIPLY"
        tree.links.new(heat.outputs["Fac"], strength.inputs[0])
        tree.links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])
    return material


def ghost_material() -> bpy.types.Material:
    material, new = _material("SA Ghost")
    if new:
        material.surface_render_method = "DITHERED"
    return material


def plate_material() -> bpy.types.Material:
    material, new = _material("SA Textured PEI")
    if new:
        tree = material.node_tree
        bsdf = _principled(material)
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 400.0
        noise.inputs["Detail"].default_value = 4.0
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*hex_to_linear("#5A4A32"), 1.0)
        ramp.color_ramp.elements[1].color = (*hex_to_linear("#A88C5A"), 1.0)
        bump = tree.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.2
        tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Roughness"].default_value = 0.7
    return material


def brass_material() -> bpy.types.Material:
    material, new = _material("SA Brass")
    if new:
        bsdf = _principled(material)
        bsdf.inputs["Base Color"].default_value = (*hex_to_linear("#B5893B"), 1.0)
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.3
    return material


def backdrop_material() -> bpy.types.Material:
    material, _ = _material("SA Backdrop")
    return material


def update_materials(scene) -> None:
    settings = scene.sliceranim
    color = tuple(settings.file_color) if settings.use_file_color else tuple(settings.color)
    roughness, specular, sheen, transmission = FINISHES[settings.finish]
    material = filament_material()
    bsdf = _principled(material)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = specular
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Emission Color"].default_value = (*settings.highlight_color, 1.0)
    strength = material.node_tree.nodes["SA Highlight Strength"]
    strength.inputs[1].default_value = HIGHLIGHT_STRENGTH if settings.highlight else 0.0
    ghost = _principled(ghost_material())
    ghost_color = color if settings.ghost_use_filament_color else tuple(settings.ghost_color)
    ghost.inputs["Base Color"].default_value = (*ghost_color, 1.0)
    ghost.inputs["Alpha"].default_value = settings.ghost_opacity
    ghost.inputs["Roughness"].default_value = 0.3
    _principled(backdrop_material()).inputs["Base Color"].default_value = (*settings.backdrop_color, 1.0)
    _principled(backdrop_material()).inputs["Roughness"].default_value = 0.8


def _part(settings) -> tuple[Vector, float]:
    """Part center (m) and bounding sphere radius (m)."""
    return Vector(settings.part_center) * MM, max(settings.part_radius * MM, 0.005)


def backdrop_mesh(radius: float, segments: int = 64) -> bpy.types.Mesh:
    """A round studio backdrop: a floor that curves up into a wall all around. Units: m."""
    bend = 0.3 * radius
    profile = [(radius * 0.001, 0.0), (radius - bend, 0.0)]
    for k in range(1, 12):
        a = k / 12 * math.pi / 2
        profile.append((radius - bend + bend * math.sin(a), bend - bend * math.cos(a)))
    profile += [(radius, bend), (radius, radius)]
    angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = [(r * math.cos(t), r * math.sin(t), z) for (r, z) in profile for t in angles]
    faces = []
    for i in range(len(profile) - 1):
        for j in range(segments):
            a, b = i * segments + j, i * segments + (j + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    mesh = bpy.data.meshes.new("SA Backdrop")
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth()
    mesh.materials.append(backdrop_material())
    return mesh


def nozzle_mesh() -> bpy.types.Mesh:
    """A cone with its tip at the origin and 6 mm high. Units: m."""
    segments = 24
    tip, top, height = 0.2 * MM, 3.5 * MM, NOZZLE_HEIGHT_MM * MM
    angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = [(tip * math.cos(t), tip * math.sin(t), 0.0) for t in angles]
    verts += [(top * math.cos(t), top * math.sin(t), height) for t in angles]
    verts += [(0.0, 0.0, 0.0), (0.0, 0.0, height)]
    faces = [(j, (j + 1) % segments, segments + (j + 1) % segments, segments + j) for j in range(segments)]
    faces += [(2 * segments, (j + 1) % segments, j) for j in range(segments)]
    faces += [(2 * segments + 1, segments + j, segments + (j + 1) % segments) for j in range(segments)]
    mesh = bpy.data.meshes.new("SA Nozzle Tip")
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth()
    mesh.materials.append(brass_material())
    return mesh


def plate_mesh() -> bpy.types.Mesh:
    half = PLATE_SIZE_MM / 2 * MM
    mesh = bpy.data.meshes.new("SA Plate Mat")
    mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
    mesh.materials.append(plate_material())
    return mesh


def _aim(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _update_lights(scene, center: Vector, radius: float) -> None:
    distance = max(4 * radius, 0.05)
    for name, (azimuth, elevation, factor) in LIGHTS.items():
        light = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = 2 * radius
        light.energy = factor * distance**2
        obj = put_object(scene, name, light)
        a = START_AZIMUTH + azimuth
        obj.location = center + distance * Vector(
            (math.cos(elevation) * math.cos(a), math.cos(elevation) * math.sin(a), math.sin(elevation))
        )
        _aim(obj, center)


def write_nozzle_keys(scene) -> None:
    """Show the nozzle tip in Line shots only, with constant keys at the shot boundaries."""
    nozzle = bpy.data.objects.get("SA Nozzle Tip")
    if nozzle is None:
        return
    keys.remove(nozzle, {"hide_render", "hide_viewport"})
    ranges = json.loads(scene.sliceranim.line_frame_ranges or "[]")
    starts = {first for first, _ in ranges}
    hidden = {1: 1.0}
    for first, _ in ranges:
        hidden[first] = 0.0
    for _, last in ranges:
        if last + 1 not in starts:
            hidden[last + 1] = 1.0
    frames = sorted(hidden)
    values = [hidden[f] for f in frames]
    for path in ("hide_render", "hide_viewport"):
        keys.write(nozzle, path, frames, values, keys.CONSTANT)


def apply(scene) -> None:
    """Make the scene match the Look settings. Call this after any Look change."""
    settings = scene.sliceranim
    update_materials(scene)
    if settings.toolpath_object is None:
        return
    center, radius = _part(settings)
    floor = Vector((center.x, center.y, -0.2 * MM))
    if settings.backdrop:
        backdrop = put_object(scene, "SA Backdrop", backdrop_mesh(max(6 * radius, 0.05)))
        backdrop.location = floor
    else:
        remove_object("SA Backdrop")
    if settings.lights:
        _update_lights(scene, center, radius)
    else:
        for name in LIGHTS:
            remove_object(name)
    if settings.plate_mat:
        plate = put_object(scene, "SA Plate Mat", bpy.data.meshes.get("SA Plate Mat") or plate_mesh())
        if settings.plate_centered_on_part:
            plate.location = (center.x, center.y, 0.0)
        else:
            plate.location = (BAMBU_PLATE_CENTER_MM[0] * MM, BAMBU_PLATE_CENTER_MM[1] * MM, 0.0)
    else:
        remove_object("SA Plate Mat")
    if settings.nozzle and settings.head_object is not None:
        nozzle = put_object(scene, "SA Nozzle Tip", bpy.data.meshes.get("SA Nozzle Tip") or nozzle_mesh())
        nozzle.parent = settings.head_object
        nozzle.location = (0.0, 0.0, NOZZLE_LIFT_MM * MM)
        write_nozzle_keys(scene)
    else:
        remove_object("SA Nozzle Tip")
