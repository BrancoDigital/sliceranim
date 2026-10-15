"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import prefs, props

CLASSES = (prefs.SLICERANIM_AP_preferences,)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
