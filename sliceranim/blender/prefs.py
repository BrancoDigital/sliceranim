"""Add-on preferences: the path of Bambu Studio."""

import bpy

ADDON_ID = __package__.rsplit(".", 1)[0]


class SLICERANIM_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    bambu_path: bpy.props.StringProperty(
        name="Bambu Studio",
        description="Bambu Studio program. Leave empty to use the standard install location",
        subtype="FILE_PATH",
    )

    def draw(self, context):
        self.layout.prop(self, "bambu_path")


def bambu_path(context) -> str:
    """The path set in preferences, or "" when the extension is not installed as an add-on (tests)."""
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences.bambu_path if addon else ""
