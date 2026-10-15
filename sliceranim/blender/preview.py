"""Preview: play the video in the 3D view without a render (spec 11.4)."""

import json

import bpy

from ..core.errors import SlicerAnimError
from . import shots


def find_view3d(screen):
    return next((area for area in screen.areas if area.type == "VIEW_3D"), None)


def start(context) -> None:
    scene = context.scene
    settings = scene.sliceranim
    area = context.area if context.area and context.area.type == "VIEW_3D" else find_view3d(context.screen)
    if area is None:
        raise SlicerAnimError("Open a 3D view to preview.")
    if shots.needs_rebuild(scene):
        shots.rebuild(scene)
    space = area.spaces.active
    state = {
        "area": list(context.screen.areas).index(area),
        "perspective": space.region_3d.view_perspective,
        "shading": space.shading.type,
        "scene_lights": space.shading.use_scene_lights,
        "scene_world": space.shading.use_scene_world,
        "overlays": space.overlay.show_overlays,
        "sync": scene.sync_mode,
    }
    settings.preview_state = json.dumps(state)
    scene.sync_mode = "FRAME_DROP"
    space.shading.type = "MATERIAL"
    space.shading.use_scene_lights = True
    space.shading.use_scene_world = True
    space.overlay.show_overlays = False
    scene.frame_set(1)
    space.region_3d.view_perspective = "CAMERA"
    settings.preview_active = True
    if not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def stop(context) -> None:
    scene = context.scene
    settings = scene.sliceranim
    if context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=False)
    state = json.loads(settings.preview_state or "{}")
    areas = list(context.screen.areas)
    if state and state["area"] < len(areas) and areas[state["area"]].type == "VIEW_3D":
        space = areas[state["area"]].spaces.active
        space.region_3d.view_perspective = state["perspective"]
        space.shading.type = state["shading"]
        space.shading.use_scene_lights = state["scene_lights"]
        space.shading.use_scene_world = state["scene_world"]
        space.overlay.show_overlays = state.get("overlays", True)
    if state:
        scene.sync_mode = state["sync"]
    settings.preview_active = False
    settings.preview_state = ""


class SLICERANIM_OT_preview(bpy.types.Operator):
    """Play the video in the 3D view. Click again to stop"""

    bl_idname = "sliceranim.preview"
    bl_label = "Preview"

    @classmethod
    def poll(cls, context):
        return context.scene.sliceranim.toolpath_object is not None and context.screen is not None

    def execute(self, context):
        try:
            if context.scene.sliceranim.preview_active:
                stop(context)
            else:
                start(context)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (SLICERANIM_OT_preview,)
