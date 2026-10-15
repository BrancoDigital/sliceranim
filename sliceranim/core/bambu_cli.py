"""Headless slicing of a Bambu Studio project (spec section 6.3)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .errors import BAMBU_NOT_FOUND, SlicerAnimError, slicing_failed

DEFAULT_PATHS = {
    "darwin": "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    "win32": r"C:\Program Files\Bambu Studio\bambu-studio.exe",
}
TIMEOUT_SECONDS = 600


def find_bambu(preference_path: str = "", platform: str = sys.platform) -> Path:
    """Return the Bambu Studio program. The path in preferences comes first."""
    candidates = []
    if preference_path:
        candidates.append(preference_path)
    if platform in DEFAULT_PATHS:
        candidates.append(DEFAULT_PATHS[platform])
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    raise SlicerAnimError(BAMBU_NOT_FOUND)


def slice_command(bambu: Path, project: Path, out_dir: Path) -> list[str]:
    return [
        str(bambu),
        "--slice", "1",
        "--outputdir", str(out_dir),
        "--export-3mf", "sliced.gcode.3mf",
        str(project),
    ]


def slice_project(project, out_dir, bambu, *, run=subprocess.run) -> Path:
    """Slice plate 1 of `project` into `out_dir`. Return the path of plate_1.gcode.

    Bambu Studio writes result.json, plate_1.gcode, and sliced.gcode.3mf into out_dir.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("result.json", "plate_1.gcode"):
        (out_dir / stale).unlink(missing_ok=True)
    try:
        process = run(
            slice_command(Path(bambu), Path(project), out_dir),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, PermissionError) as error:
        raise SlicerAnimError(BAMBU_NOT_FOUND) from error
    except subprocess.TimeoutExpired as error:
        raise slicing_failed(f"Bambu Studio did not finish in {TIMEOUT_SECONDS} seconds.") from error
    result_path = out_dir / "result.json"
    if not result_path.is_file():
        raise slicing_failed(f"Bambu Studio stopped with exit code {process.returncode} and wrote no result.json.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("return_code", -1) != 0:
        raise slicing_failed(result.get("error_string") or "no error text in result.json")
    gcode = out_dir / "plate_1.gcode"
    if not gcode.is_file():
        raise slicing_failed("Bambu Studio wrote no plate_1.gcode.")
    return gcode
