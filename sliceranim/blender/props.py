"""Scene settings of the plugin (spec 11.3). Everything here is saved in the .blend file."""

import math

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

STYLE_ITEMS = [
    ("LINE", "Line", "Frames follow print time. You see each line drawn"),
    ("LAYER", "Layer", "Whole layers appear, spread evenly over the shot"),
    ("HOLD", "Hold", "The build does not move"),
]
CAMERA_ITEMS = [
    ("TURNTABLE", "Turntable orbit", "Circle the part"),
    ("HERO", "Hero", "A fixed three-quarter view"),
    ("RISING", "Rising follow", "Move up with the current layer"),
    ("CLOSE_UP", "Close-up", "Frame the full layer that is printing"),
    ("REVEAL", "Final reveal", "Pull back, then spin around the finished part"),
    ("CUSTOM", "My camera", "Use a camera that you placed"),
]
FINISH_ITEMS = [
    ("MATTE", "Matte", ""),
    ("GLOSSY", "Glossy", ""),
    ("SILK", "Silk", ""),
    ("TRANSLUCENT", "Translucent", ""),
]
FORMAT_ITEMS = [
    ("FHD", "1920×1080", "16:9 1080p"),
    ("SQUARE", "1080×1080", "1:1"),
    ("UHD", "3840×2160", "16:9 4K"),
    ("CUSTOM", "Custom", "Your own size"),
]
FPS_ITEMS = [(v, v, "") for v in ("24", "25", "30", "60")]
FILE_ITEMS = [("MP4", "MP4 (H.264)", ""), ("PNG", "PNG frames", "")]
SIDES_ITEMS = [(v, v, "") for v in ("4", "6", "8")]
VIEWPORT_SIDES_ITEMS = [(v, v, "") for v in ("3", "4", "6", "8")]


def _looks(self, context):
    from . import looks

    looks.apply(context.scene)


def _strands(self, context):
    from . import nodes

    nodes.apply_settings(context.scene)


def _output(self, context):
    from . import output

    output.apply(context.scene)


def _end_changed(self, context):
    if self.start_at_end and self.style != "HOLD":
        self.style = "HOLD"  # spec 8.3 rule 4: only Hold shots start at End


def _is_camera(self, obj):
    return obj.type == "CAMERA"


class SLICERANIM_PG_shot(bpy.types.PropertyGroup):
    start_layer: IntProperty(name="Start layer", min=1, default=1)
    start_at_end: BoolProperty(name="End", description="Start after the last layer. The shot becomes a Hold shot",
                               update=_end_changed)
    duration: FloatProperty(name="Duration", description="Screen time in seconds", min=0.0, default=4.0, step=50)
    style: EnumProperty(name="Build style", items=STYLE_ITEMS, default="LINE")
    camera: EnumProperty(name="Camera", items=CAMERA_ITEMS, default="TURNTABLE")
    orbit_turns: FloatProperty(name="Turns", default=1.0, min=0.0, soft_max=4.0)
    orbit_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(25))
    orbit_clockwise: BoolProperty(name="Clockwise", default=False)
    hero_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(30))
    hero_side: FloatProperty(name="Side angle", subtype="ANGLE", default=math.radians(35))
    rising_distance: FloatProperty(
        name="Distance", description="Camera distance in mm. 0 uses the framing distance", default=0.0, min=0.0
    )
    rising_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(20))
    closeup_target: EnumProperty(
        name="Target",
        items=[("LAYER", "Current layer", "Aim at the center of the layer that is printing"),
               ("CURSOR", "3D cursor", "Aim at the point under the 3D cursor when you click Rebuild")],
        default="LAYER",
    )
    closeup_smoothing: IntProperty(name="Smoothing", description="Frames in the moving average", default=15, min=1)
    closeup_dof: BoolProperty(name="Depth of field", default=False)
    closeup_fstop: FloatProperty(name="F-stop", default=2.8, min=0.1)
    reveal_spin: FloatProperty(name="Spin amount", subtype="ANGLE", default=math.radians(90))
    reveal_pullback: FloatProperty(name="Pull-back share", subtype="PERCENTAGE", default=40.0, min=0.0, max=100.0)
    custom_camera: PointerProperty(name="Camera object", type=bpy.types.Object, poll=_is_camera)


class SLICERANIM_PG_settings(bpy.types.PropertyGroup):
    # Source
    toolpath_object: PointerProperty(type=bpy.types.Object)
    head_object: PointerProperty(type=bpy.types.Object)
    source_kind: EnumProperty(
        items=[("NONE", "None", ""), ("GCODE", "G-code", ""), ("SLICED_3MF", "Sliced 3MF", ""),
               ("PROJECT", "Bambu project", ""), ("STL", "STL", ""), ("MESH", "Mesh object", "")],
        default="NONE",
    )
    source_path: StringProperty(description="File that Reload reads", subtype="FILE_PATH")
    source_label: StringProperty(description="File or object name shown in the panel")
    source_mesh: PointerProperty(type=bpy.types.Object, description="Mesh that the fallback slicer read")
    slicer: StringProperty()
    layer_count: IntProperty()
    point_count: IntProperty()
    print_time: FloatProperty()
    used_fallback: BoolProperty()
    built_merge_angle: FloatProperty(subtype="ANGLE", default=-1.0)
    part_center: FloatVectorProperty(size=3, description="Part center in mm")
    part_radius: FloatProperty(description="Bounding sphere radius in mm")
    camera_reach: FloatProperty(description="Distance in mm of the farthest shot camera from the framed center, from the last Rebuild")
    plate_centered_on_part: BoolProperty()
    file_color: FloatVectorProperty(subtype="COLOR", size=3, default=(0.216, 0.216, 0.216), min=0.0, max=1.0)  # #808080
    engine_set: BoolProperty(description="The first import already set the render engine")
    layer_height: FloatProperty(
        name="Layer height", description="Layer height in mm when the plugin slices an STL file or a mesh object",
        default=0.2, min=0.04, max=1.0, soft_min=0.08, soft_max=0.28, step=1, precision=2)
    built_layer_height: FloatProperty(default=-1.0)
    # Look
    use_file_color: BoolProperty(name="Color from file", default=True, update=_looks)
    color: FloatVectorProperty(name="Color", subtype="COLOR", size=3, default=(0.216, 0.216, 0.216), min=0.0, max=1.0, update=_looks)
    finish: EnumProperty(name="Finish", items=FINISH_ITEMS, default="MATTE", update=_looks)
    highlight: BoolProperty(name="Active-layer highlight", default=True, update=_looks)
    highlight_color: FloatVectorProperty(name="Highlight color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                         default=(1.0, 0.1441, 0.0103), update=_looks)  # #FF6A1A in linear color
    highlight_layers: IntProperty(name="Highlight layers", default=3, min=1, update=_strands)
    ghost: BoolProperty(name="Ghost", description="Show the part that is not printed yet as a clear shell", default=False, update=_strands)
    ghost_use_filament_color: BoolProperty(name="Filament color", default=True, update=_looks)
    ghost_color: FloatVectorProperty(name="Ghost color", subtype="COLOR", size=3, default=(1.0, 1.0, 1.0), min=0.0, max=1.0, update=_looks)
    ghost_opacity: FloatProperty(name="Opacity", subtype="FACTOR", default=0.15, min=0.0, max=1.0, update=_looks)
    strand_sides: EnumProperty(name="Strand sides", items=SIDES_ITEMS, default="6", update=_strands)
    viewport_strand_sides: EnumProperty(name="Viewport strand sides", items=VIEWPORT_SIDES_ITEMS, default="4", update=_strands)
    merge_angle: FloatProperty(name="Merge angle", subtype="ANGLE", default=math.radians(2.0), min=0.0, max=math.radians(30))
    backdrop: BoolProperty(name="Studio backdrop", default=True, update=_looks)
    backdrop_color: FloatVectorProperty(name="Backdrop color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                        default=(0.693, 0.693, 0.693), update=_looks)  # #D9D9D9 in linear color
    lights: BoolProperty(name="Lights", default=True, update=_looks)
    light_color: FloatVectorProperty(name="Light color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                     default=(1.0, 1.0, 1.0), update=_looks)
    light_intensity: FloatProperty(name="Light intensity", description="Multiplies the power of the three lights",
                                   default=1.0, min=0.0, soft_max=3.0, update=_looks)
    plate_mat: BoolProperty(name="Plate mat", default=False, update=_looks)
    nozzle: BoolProperty(name="Nozzle tip", default=False, update=_looks)
    nozzle_size: FloatProperty(name="Nozzle size", description="Height of the nozzle tip in mm",
                               default=6.0, min=1.0, soft_max=40.0, update=_looks)
    # Shots
    framing: EnumProperty(
        name="Framing",
        items=[("PART", "Part", "Frame the whole part in every shot except Close-up"),
               ("VOLUME", "Print volume", "Frame the whole print volume of a Bambu Lab P1S (256 × 256 × 250 mm)")],
        default="PART", update=_looks)
    shots: CollectionProperty(type=SLICERANIM_PG_shot)
    active_shot: IntProperty()
    nozzle_frame_ranges: StringProperty(
        description="JSON list of [first, last] frames of the Line and Layer shots, from the last Rebuild")
    rebuild_signature: StringProperty()
    # Output
    format_preset: EnumProperty(name="Format", items=FORMAT_ITEMS, default="FHD", update=_output)
    custom_width: IntProperty(name="Width", default=1920, min=16, update=_output)
    custom_height: IntProperty(name="Height", default=1080, min=16, update=_output)
    fps: EnumProperty(name="Frame rate", items=FPS_ITEMS, default="30", update=_output)
    file_type: EnumProperty(name="File type", items=FILE_ITEMS, default="MP4", update=_output)
    output_folder: StringProperty(name="Output folder", subtype="DIR_PATH", default="//renders/", update=_output)
    # Preview
    preview_active: BoolProperty()
    preview_state: StringProperty()


# The settings in the Look and Output sections. Reset to Defaults sets them back to their defaults.
USER_SETTINGS = (
    "use_file_color", "color", "finish", "highlight", "highlight_color", "highlight_layers",
    "ghost", "ghost_use_filament_color", "ghost_color", "ghost_opacity",
    "strand_sides", "viewport_strand_sides", "merge_angle", "backdrop", "backdrop_color",
    "lights", "light_color", "light_intensity", "plate_mat", "nozzle", "nozzle_size",
    "framing", "format_preset", "custom_width", "custom_height", "fps", "file_type", "output_folder",
)

CLASSES = (SLICERANIM_PG_shot, SLICERANIM_PG_settings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sliceranim = PointerProperty(type=SLICERANIM_PG_settings)


def unregister():
    del bpy.types.Scene.sliceranim
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
