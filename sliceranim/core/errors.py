"""Errors that the panel shows to the user. The text comes from section 12 of the spec."""


class SlicerAnimError(Exception):
    """An error with a message that the panel shows as is."""


BAMBU_NOT_FOUND = "Bambu Studio not found. Set its path in preferences, or import a sliced file."
NO_LAYER_MARKERS = "No layer markers found. Supported slicers: Bambu Studio, OrcaSlicer."
NO_EXTRUSION = "No printed lines found in this file."
OPEN_MESH = "The mesh has holes, so some layers can be incomplete."
NOT_A_PRINT_3MF = "This 3MF file has no G-code and is not a Bambu Studio project."


def too_many_plates(count: int) -> SlicerAnimError:
    return SlicerAnimError(f"This file has {count} plates. Export one plate from your slicer and try again.")


def slicing_failed(detail: str) -> SlicerAnimError:
    return SlicerAnimError(f"Slicing failed: {detail}")


def source_missing(path: str) -> SlicerAnimError:
    return SlicerAnimError(f"Source file not found: {path}. Open the file again.")


def too_many_polygons(polygons: int) -> str:
    millions = polygons / 1_000_000
    return (
        f"This print makes about {millions:.0f} million polygons. "
        "Lower Strand sides or raise Merge angle to make it faster."
    )
