"""Panel, operators, import menu entry, and drag and drop (spec 11.2 and 11.3)."""

import os

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty

from ..core.errors import OPEN_MESH, SlicerAnimError, too_many_polygons
from ..core.toolpaths import estimate_polygons
from . import importer, looks, nodes, output, preview, props, shots

_pending = {}  # a large print that waits for the user to confirm (spec section 7)


def ask_to_confirm() -> None:
    """Show the warning of spec section 12. The confirm operator builds the waiting print."""
    bpy.ops.sliceranim.confirm_large("INVOKE_DEFAULT")


def _finish_load(operator, context, loaded, *, keep_shots: bool) -> set:
    settings = context.scene.sliceranim
    tp = importer.prepare(context, loaded)
    polygons = estimate_polygons(tp, int(settings.strand_sides), settings.ghost)
    if polygons > importer.POLYGON_LIMIT and not operator.confirm_large:
        _pending.update(loaded=loaded, tp=tp, keep_shots=keep_shots, polygons=polygons)
        ask_to_confirm()
        return {"CANCELLED"}
    importer.build(context, loaded, tp, keep_shots=keep_shots)
    if loaded.open_edges:
        operator.report({"WARNING"}, OPEN_MESH)
    if loaded.note:
        operator.report({"INFO"}, loaded.note)
    return {"FINISHED"}


class _LoadBase:
    confirm_large: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def run(self, context, read, *, keep_shots=False):
        try:
            return _finish_load(self, context, read(), keep_shots=keep_shots)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}


class SLICERANIM_OT_load_file(_LoadBase, bpy.types.Operator):
    """Load G-code, a 3MF file, or an STL file as an animated print"""

    bl_idname = "sliceranim.load_file"
    bl_label = "Open File"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    filter_glob: StringProperty(default="*.gcode;*.3mf;*.stl", options={"HIDDEN"})

    def invoke(self, context, event):
        if self.directory and len(self.files):
            return self.execute(context)  # drag and drop gives the file directly
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not len(self.files):
            self.report({"ERROR"}, "Choose a file.")
            return {"CANCELLED"}
        path = os.path.join(self.directory, self.files[0].name)
        return self.run(context, lambda: importer.read_file(context, path))


class SLICERANIM_OT_use_selected(_LoadBase, bpy.types.Operator):
    """Slice the selected mesh object with Bambu Studio, or with the fallback slicer"""

    bl_idname = "sliceranim.use_selected"
    bl_label = "Use Selected Object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj != context.scene.sliceranim.toolpath_object

    def execute(self, context):
        return self.run(context, lambda: importer.read_mesh_object(context, context.active_object))


class SLICERANIM_OT_reload(_LoadBase, bpy.types.Operator):
    """Read the source again with the new Merge angle and Layer height"""

    bl_idname = "sliceranim.reload"
    bl_label = "Reload"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.sliceranim.toolpath_object is not None

    def execute(self, context):
        return self.run(context, lambda: importer.reload_source(context), keep_shots=True)


class SLICERANIM_OT_confirm_large(bpy.types.Operator):
    """Build a print with more than 10 million polygons"""

    bl_idname = "sliceranim.confirm_large"
    bl_label = "Large Print"
    bl_options = {"INTERNAL", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Large print", message=too_many_polygons(_pending["polygons"]), confirm_text="Build Anyway"
        )

    def execute(self, context):
        if not _pending:
            return {"CANCELLED"}
        importer.build(context, _pending["loaded"], _pending["tp"], keep_shots=_pending["keep_shots"])
        _pending.clear()
        return {"FINISHED"}


class SLICERANIM_OT_shot_add(bpy.types.Operator):
    """Add a shot after the active shot"""

    bl_idname = "sliceranim.shot_add"
    bl_label = "Add Shot"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sliceranim
        at_end, start = True, max(settings.layer_count, 1)
        if settings.active_shot + 1 < len(settings.shots):
            following = settings.shots[settings.active_shot + 1]
            at_end, start = following.start_at_end, following.start_layer
        item = settings.shots.add()  # this can move the items in memory, so read the next shot before it
        item.style = "HOLD"  # a Hold shot can share the start of the next shot (spec 8.3), so the list stays valid
        item.start_at_end = at_end
        item.start_layer = start
        target = min(settings.active_shot + 1, len(settings.shots) - 1)
        settings.shots.move(len(settings.shots) - 1, target)
        settings.active_shot = target
        return {"FINISHED"}


class SLICERANIM_OT_shot_remove(bpy.types.Operator):
    """Remove the active shot"""

    bl_idname = "sliceranim.shot_remove"
    bl_label = "Remove Shot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.sliceranim.shots) > 0

    def execute(self, context):
        settings = context.scene.sliceranim
        settings.shots.remove(settings.active_shot)
        settings.active_shot = max(0, min(settings.active_shot, len(settings.shots) - 1))
        return {"FINISHED"}


class SLICERANIM_OT_shot_move(bpy.types.Operator):
    """Move the active shot up or down"""

    bl_idname = "sliceranim.shot_move"
    bl_label = "Move Shot"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        settings = context.scene.sliceranim
        target = settings.active_shot + (-1 if self.direction == "UP" else 1)
        if 0 <= target < len(settings.shots):
            settings.shots.move(settings.active_shot, target)
            settings.active_shot = target
        return {"FINISHED"}


def reset_to_defaults(scene) -> None:
    """Set the Look and Output settings and the shot list back to their defaults, then run Rebuild."""
    settings = scene.sliceranim
    for name in props.USER_SETTINGS:
        settings.property_unset(name)
    nodes.apply_settings(scene)
    looks.apply(scene)
    output.apply(scene)
    shots.fill_default_shots(settings, settings.layer_count)
    shots.rebuild(scene)


class SLICERANIM_OT_reset_defaults(bpy.types.Operator):
    """Set the look, the shot list, and the output settings back to their defaults"""

    bl_idname = "sliceranim.reset_defaults"
    bl_label = "Reset to Defaults"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.sliceranim.toolpath_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Reset to Defaults",
            message="Reset sets the look, the shot list, and the output settings back to their defaults. "
            "The loaded print stays.",
            confirm_text="Reset",
        )

    def execute(self, context):
        if context.scene.sliceranim.preview_active:
            preview.stop(context)
        try:
            reset_to_defaults(context.scene)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class SLICERANIM_OT_rebuild(bpy.types.Operator):
    """Write the keyframes, markers, and cameras for the shot list"""

    bl_idname = "sliceranim.rebuild"
    bl_label = "Rebuild"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return not shots.problems(context.scene)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Rebuild",
            message="Rebuild replaces the shot markers and keyframes that it made before. Manual changes to them will be lost.",
            confirm_text="Rebuild",
        )

    def execute(self, context):
        try:
            shots.rebuild(context.scene)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class SLICERANIM_OT_render(bpy.types.Operator):
    """Render the video to the output folder"""

    bl_idname = "sliceranim.render"
    bl_label = "Render"

    @classmethod
    def poll(cls, context):
        return not shots.problems(context.scene)

    def execute(self, context):
        scene = context.scene
        if scene.sliceranim.preview_active:
            preview.stop(context)
        try:
            if shots.needs_rebuild(scene):
                shots.rebuild(scene)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        output.apply(scene)
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        return {"FINISHED"}


class SLICERANIM_UL_shots(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        bad_rows = {p.row for p in shots.problems(context.scene)}
        row = layout.row(align=True)
        row.alert = index in bad_rows
        start = "End" if item.start_at_end else str(item.start_layer)
        row.label(text=f"{index + 1}. {start}")
        row.label(text=f"{item.duration:g} s")
        row.label(text=bpy.types.UILayout.enum_item_name(item, "style", item.style))
        row.label(text=bpy.types.UILayout.enum_item_name(item, "camera", item.camera))


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer Anim"


class SLICERANIM_PT_source(_Panel, bpy.types.Panel):
    bl_label = "Source"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.operator(SLICERANIM_OT_load_file.bl_idname, icon="FILEBROWSER")
        layout.operator(SLICERANIM_OT_use_selected.bl_idname, icon="MESH_DATA")
        layout.prop(settings, "layer_height", text="Layer height (STL, mesh)")
        if settings.toolpath_object is None:
            return
        layer_height_changed = (settings.source_kind in ("STL", "MESH")
                                and abs(settings.layer_height - settings.built_layer_height) > 1e-6)
        if abs(settings.merge_angle - settings.built_merge_angle) > 1e-6 or layer_height_changed:
            row = layout.row()
            row.alert = True
            row.operator(SLICERANIM_OT_reload.bl_idname, icon="FILE_REFRESH")
        box = layout.box()
        box.label(text=settings.source_label, icon="FILE")
        box.label(text=f"Slicer: {settings.slicer or 'unknown'}")
        hours, rest = divmod(int(settings.print_time), 3600)
        box.label(text=f"{settings.layer_count} layers, {hours} h {rest // 60} min")
        box.label(text=f"{settings.point_count:,} points")
        if settings.used_fallback:
            box.label(text="Fallback slicer: 2 walls, no infill.", icon="INFO")
            box.label(text="Install Bambu Studio for a full slice.")
        layout.operator(SLICERANIM_OT_reset_defaults.bl_idname, icon="LOOP_BACK")


class SLICERANIM_PT_look(_Panel, bpy.types.Panel):
    bl_label = "Look"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.use_property_split = True
        layout.prop(settings, "use_file_color")
        if not settings.use_file_color:
            layout.prop(settings, "color")
        layout.prop(settings, "finish")
        layout.prop(settings, "highlight")
        if settings.highlight:
            layout.prop(settings, "highlight_color")
            layout.prop(settings, "highlight_layers")
        layout.prop(settings, "ghost")
        if settings.ghost:
            layout.prop(settings, "ghost_use_filament_color")
            if not settings.ghost_use_filament_color:
                layout.prop(settings, "ghost_color")
            layout.prop(settings, "ghost_opacity")
        layout.prop(settings, "strand_sides")
        layout.prop(settings, "viewport_strand_sides")
        layout.prop(settings, "merge_angle")
        layout.prop(settings, "backdrop")
        if settings.backdrop:
            layout.prop(settings, "backdrop_color")
        layout.prop(settings, "lights")
        if settings.lights:
            layout.prop(settings, "light_color")
            layout.prop(settings, "light_intensity")
        layout.prop(settings, "plate_mat")
        layout.prop(settings, "nozzle")
        if settings.nozzle:
            layout.prop(settings, "nozzle_size")


class SLICERANIM_PT_shots(_Panel, bpy.types.Panel):
    bl_label = "Shots"

    def draw(self, context):
        scene = context.scene
        settings = scene.sliceranim
        layout = self.layout
        row = layout.row()
        row.template_list("SLICERANIM_UL_shots", "", settings, "shots", settings, "active_shot", rows=4)
        column = row.column(align=True)
        column.operator(SLICERANIM_OT_shot_add.bl_idname, icon="ADD", text="")
        column.operator(SLICERANIM_OT_shot_remove.bl_idname, icon="REMOVE", text="")
        column.operator(SLICERANIM_OT_shot_move.bl_idname, icon="TRIA_UP", text="").direction = "UP"
        column.operator(SLICERANIM_OT_shot_move.bl_idname, icon="TRIA_DOWN", text="").direction = "DOWN"
        for problem in shots.problems(scene):
            where = f"Shot {problem.row + 1}: " if problem.row >= 0 else ""
            layout.label(text=where + problem.message, icon="ERROR")
        if not settings.shots or not 0 <= settings.active_shot < len(settings.shots):
            return
        shot = settings.shots[settings.active_shot]
        layout.use_property_split = True
        layout.prop(shot, "start_at_end")
        if not shot.start_at_end:
            layout.prop(shot, "start_layer")
        layout.prop(shot, "duration")
        layout.prop(shot, "style")
        layout.prop(shot, "camera")
        fields = {
            "TURNTABLE": ("orbit_turns", "orbit_height", "orbit_clockwise"),
            "HERO": ("hero_height", "hero_side"),
            "RISING": ("rising_distance", "rising_height"),
            "CLOSE_UP": ("closeup_target", "closeup_smoothing", "closeup_dof", "closeup_fstop"),
            "REVEAL": ("reveal_spin", "reveal_pullback"),
            "CUSTOM": ("custom_camera",),
        }[shot.camera]
        for name in fields:
            layout.prop(shot, name)


class SLICERANIM_PT_output(_Panel, bpy.types.Panel):
    bl_label = "Output"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.use_property_split = True
        layout.prop(settings, "format_preset")
        if settings.format_preset == "CUSTOM":
            layout.prop(settings, "custom_width")
            layout.prop(settings, "custom_height")
        layout.prop(settings, "fps")
        layout.prop(settings, "file_type")
        layout.prop(settings, "output_folder")
        layout.use_property_split = False
        row = layout.row(align=True)
        row.operator(SLICERANIM_OT_rebuild.bl_idname, icon="FILE_REFRESH")
        label = "Exit Preview" if settings.preview_active else "Preview"
        row.operator(preview.SLICERANIM_OT_preview.bl_idname, text=label, icon="PLAY")
        layout.operator(SLICERANIM_OT_render.bl_idname, icon="RENDER_ANIMATION")


class SLICERANIM_FH_toolpaths(bpy.types.FileHandler):
    bl_idname = "SLICERANIM_FH_toolpaths"
    bl_label = "Print Toolpaths"
    bl_import_operator = "sliceranim.load_file"
    bl_file_extensions = ".gcode;.3mf"

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"


def menu_import(self, context):
    self.layout.operator(SLICERANIM_OT_load_file.bl_idname, text="Print Toolpaths (.gcode, .3mf, .stl)")


CLASSES = (
    SLICERANIM_OT_load_file,
    SLICERANIM_OT_use_selected,
    SLICERANIM_OT_reload,
    SLICERANIM_OT_confirm_large,
    SLICERANIM_OT_shot_add,
    SLICERANIM_OT_shot_remove,
    SLICERANIM_OT_shot_move,
    SLICERANIM_OT_reset_defaults,
    SLICERANIM_OT_rebuild,
    SLICERANIM_OT_render,
    SLICERANIM_UL_shots,
    SLICERANIM_PT_source,
    SLICERANIM_PT_look,
    SLICERANIM_PT_shots,
    SLICERANIM_PT_output,
    SLICERANIM_FH_toolpaths,
)
