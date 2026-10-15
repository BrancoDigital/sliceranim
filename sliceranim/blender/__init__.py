"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import preview, prefs, props, ui

CLASSES = (prefs.SLICERANIM_AP_preferences, *preview.CLASSES, *ui.CLASSES)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(ui.menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(ui.menu_import)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
