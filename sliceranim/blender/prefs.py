"""Add-on preferences: the path of Bambu Studio and the presets for slicing a mesh."""

import bpy

from ..core.bambu_cli import DEFAULT_PRESETS

ADDON_ID = __package__.rsplit(".", 1)[0]


class SLICERANIM_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    bambu_path: bpy.props.StringProperty(
        name="Bambu Studio",
        description="Bambu Studio program. Leave empty to use the standard install location",
        subtype="FILE_PATH",
    )
    machine_preset: bpy.props.StringProperty(
        name="Printer", description="Bambu Studio system preset for the printer", default=DEFAULT_PRESETS["machine"]
    )
    process_preset: bpy.props.StringProperty(
        name="Process", description="Bambu Studio system preset for the process", default=DEFAULT_PRESETS["process"]
    )
    filament_preset: bpy.props.StringProperty(
        name="Filament", description="Bambu Studio system preset for the filament", default=DEFAULT_PRESETS["filament"]
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "bambu_path")
        layout.label(text="Presets for slicing an STL file or a mesh object:")
        layout.prop(self, "machine_preset")
        layout.prop(self, "process_preset")
        layout.prop(self, "filament_preset")


def _preferences(context):
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def bambu_path(context) -> str:
    """The path set in preferences, or "" when the extension is not installed as an add-on (tests)."""
    preferences = _preferences(context)
    return preferences.bambu_path if preferences else ""


def presets(context) -> dict:
    """The machine, process, and filament presets from preferences, or the defaults (tests)."""
    preferences = _preferences(context)
    if preferences is None:
        return dict(DEFAULT_PRESETS)
    return {
        "machine": preferences.machine_preset or DEFAULT_PRESETS["machine"],
        "process": preferences.process_preset or DEFAULT_PRESETS["process"],
        "filament": preferences.filament_preset or DEFAULT_PRESETS["filament"],
    }
