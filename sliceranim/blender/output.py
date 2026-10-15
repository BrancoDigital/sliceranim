"""Render settings from the Output section (spec 11.1)."""

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
