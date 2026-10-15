from sliceranim.core import errors


def test_messages_match_spec_section_12():
    assert str(errors.too_many_plates(3)) == "This file has 3 plates. Export one plate from your slicer and try again."
    assert errors.BAMBU_NOT_FOUND == "Bambu Studio not found. Set its path in preferences, or import a sliced file."
    assert str(errors.slicing_failed("Nothing to be sliced")) == "Slicing failed: Nothing to be sliced"
    assert errors.NO_LAYER_MARKERS == "No layer markers found. Supported slicers: Bambu Studio, OrcaSlicer."
    assert errors.NO_EXTRUSION == "No printed lines found in this file."
    assert errors.too_many_polygons(12_400_000) == (
        "This print makes about 12 million polygons. Lower Strand sides or raise Merge angle to make it faster."
    )
    assert errors.OPEN_MESH == "The mesh has holes, so some layers can be incomplete."
    assert str(errors.source_missing("/x/a.gcode")) == "Source file not found: /x/a.gcode. Open the file again."
    assert errors.NOT_A_PRINT_3MF == "This 3MF file has no G-code and is not a Bambu Studio project."
