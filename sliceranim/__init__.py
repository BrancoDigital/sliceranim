"""Slicer Animator: animate how a 3D print grows, layer by layer.

This file does not import bpy, so the tests can import sliceranim.core without Blender.
"""


def register():
    from .blender import register as register_blender

    register_blender()


def unregister():
    from .blender import unregister as unregister_blender

    unregister_blender()
