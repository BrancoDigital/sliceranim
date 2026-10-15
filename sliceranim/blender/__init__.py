"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import output, preview, prefs, props, ui

CLASSES = (prefs.SLICERANIM_AP_preferences, *preview.CLASSES, *ui.CLASSES)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(ui.menu_import)
    bpy.app.handlers.save_post.append(output.on_save)


def unregister():
    if output.on_save in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(output.on_save)
    bpy.types.TOPBAR_MT_file_import.remove(ui.menu_import)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
