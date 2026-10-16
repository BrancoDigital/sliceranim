"""Slicer Animator: animate how a 3D print grows, layer by layer.

This file does not import bpy, so the tests can import sliceranim.core without Blender.
"""

import tomllib
from pathlib import Path


def version() -> str:
    """The version in blender_manifest.toml, the one place where the version is set."""
    with open(Path(__file__).with_name("blender_manifest.toml"), "rb") as file:
        return tomllib.load(file)["version"]


def register():
    from .blender import register as register_blender

    register_blender()


def unregister():
    from .blender import unregister as unregister_blender

    unregister_blender()
