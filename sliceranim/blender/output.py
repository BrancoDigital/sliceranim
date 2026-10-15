"""Render settings from the Output section (spec 11.1)."""

import os

import bpy
from bpy.app.handlers import persistent

PRESETS = {"FHD": (1920, 1080), "SQUARE": (1080, 1080), "UHD": (3840, 2160)}


def resolution(settings) -> tuple[int, int]:
    if settings.format_preset == "CUSTOM":
        return settings.custom_width, settings.custom_height
    return PRESETS[settings.format_preset]


def apply(scene) -> None:
    settings = scene.sliceranim
    render = scene.render
    render.resolution_x, render.resolution_y = resolution(settings)
    render.resolution_percentage = 100
    render.fps = int(settings.fps)
    render.fps_base = 1.0
    name = settings.toolpath_object.name if settings.toolpath_object else "slicer_anim"
    folder = settings.output_folder or "//renders/"
    if not folder.endswith(("/", "\\")):
        folder += "/"
    make_folder(folder)
    if settings.file_type == "MP4":
        render.image_settings.media_type = "VIDEO"
        render.image_settings.file_format = "FFMPEG"
        render.ffmpeg.format = "MPEG4"
        render.ffmpeg.codec = "H264"
        render.ffmpeg.constant_rate_factor = "HIGH"
    else:
        render.image_settings.media_type = "IMAGE"
        render.image_settings.file_format = "PNG"
    render.filepath = f"{folder}{name}_"


def make_folder(folder: str) -> None:
    """Make the output folder, so that the panel does not show the path in red.

    A relative path ("//renders/") needs a saved .blend file. Until then, nothing is made.
    """
    if folder.startswith("//") and not bpy.data.filepath:
        return
    try:
        os.makedirs(bpy.path.abspath(folder), exist_ok=True)
    except OSError:
        pass  # the render reports a folder that it cannot write


@persistent
def on_save(*_args) -> None:
    """Make the output folder when you save the .blend file for the first time after a load."""
    for scene in bpy.data.scenes:
        if scene.sliceranim.toolpath_object is not None:
            make_folder(scene.sliceranim.output_folder or "//renders/")
