"""Look inside 3MF files: sliced files and Bambu Studio projects (spec section 6.2)."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import NOT_A_PRINT_3MF, SlicerAnimError, too_many_plates
from .gcode_reader import parse_gcode
from .toolpaths import ToolpathSet

SLICED = "sliced"
PROJECT = "project"
_PLATE_GCODE = re.compile(r"^Metadata/plate_(\d+)\.gcode$")
_MODEL_SETTINGS = "Metadata/model_settings.config"


@dataclass(frozen=True)
class ThreeMFInfo:
    kind: str  # SLICED or PROJECT
    plate_count: int
    gcode_names: tuple[str, ...]  # zip members with G-code, in plate order


def inspect_3mf(path) -> ThreeMFInfo:
    """Find out what a 3MF file holds. Raise SlicerAnimError if it is not a print file."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise SlicerAnimError(NOT_A_PRINT_3MF) from error
    with archive:
        names = archive.namelist()
        gcode = sorted(
            (n for n in names if _PLATE_GCODE.match(n)),
            key=lambda n: int(_PLATE_GCODE.match(n).group(1)),
        )
        if gcode:
            return ThreeMFInfo(SLICED, len(gcode), tuple(gcode))
        if _MODEL_SETTINGS in names:
            text = archive.read(_MODEL_SETTINGS).decode("utf-8", errors="replace")
            plates = len(re.findall(r"<plate\b", text))
            return ThreeMFInfo(PROJECT, max(plates, 1), ())
    raise SlicerAnimError(NOT_A_PRINT_3MF)


def require_one_plate(info: ThreeMFInfo) -> None:
    if info.plate_count > 1:
        raise too_many_plates(info.plate_count)


def read_sliced_3mf(path, *, drop_custom: bool = True) -> ToolpathSet:
    """Read the G-code of a sliced 3MF file with one plate."""
    info = inspect_3mf(path)
    if info.kind != SLICED:
        raise SlicerAnimError(NOT_A_PRINT_3MF)
    require_one_plate(info)
    with zipfile.ZipFile(path) as archive, archive.open(info.gcode_names[0]) as raw:
        lines = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
        tp = parse_gcode(lines, drop_custom=drop_custom)
    tp.meta["source_path"] = str(Path(path))
    return tp
