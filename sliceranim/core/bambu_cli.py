"""Headless slicing with Bambu Studio: a project, or a mesh with system presets (spec section 6.3)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .errors import BAMBU_NOT_FOUND, SlicerAnimError, preset_not_found, slicing_failed

DEFAULT_PATHS = {
    "darwin": "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    "win32": r"C:\Program Files\Bambu Studio\bambu-studio.exe",
}
TIMEOUT_SECONDS = 600
DEFAULT_PRESETS = {
    "machine": "Bambu Lab P1S 0.4 nozzle",
    "process": "0.20mm Standard @BBL X1C",
    "filament": "Bambu PLA Basic @BBL X1C",
}


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
    return _run_slice(slice_command(Path(bambu), Path(project), out_dir), out_dir, run)


def profiles_dir(bambu: Path) -> Path:
    """The BBL system presets that ship with Bambu Studio (macOS and Windows layouts)."""
    bambu = Path(bambu)
    for candidate in (bambu.parent.parent / "Resources" / "profiles" / "BBL", bambu.parent / "resources" / "profiles" / "BBL"):
        if candidate.is_dir():
            return candidate
    raise SlicerAnimError(f"Bambu Studio presets not found next to {bambu}. Reinstall Bambu Studio.")


def _read_preset(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _find_preset(profiles: Path, kind: str, name: str) -> dict:
    data = _read_preset(profiles / kind / f"{name}.json")
    if isinstance(data, dict) and data.get("name") == name:
        return data
    for path in sorted((profiles / kind).glob("*.json")):  # a few names have "/", which a file name cannot have
        data = _read_preset(path)
        if isinstance(data, dict) and data.get("name") == name:
            return data
    raise preset_not_found(name)


def flat_preset(profiles: Path, kind: str, name: str) -> dict:
    """Resolve the inherits chain of a system preset into one preset that the command line accepts.

    Bambu Studio checks that the process fits the printer by the "inherits" name, so the flat preset
    names itself there. Without the flat preset, Bambu Studio slices nothing ("plate empty").
    """
    chain = [_find_preset(Path(profiles), kind, name)]
    while chain[-1].get("inherits"):
        chain.append(_find_preset(Path(profiles), kind, chain[-1]["inherits"]))
    preset = {}
    for data in reversed(chain):
        preset.update(data)
    preset.update({"name": name, "inherits": name, "from": "User"})
    return preset


def write_presets(profiles: Path, out_dir: Path, presets: dict, layer_height: float) -> list[Path]:
    """Write machine.json, process.json, and filament.json into out_dir. Return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for kind in ("machine", "process", "filament"):
        preset = flat_preset(profiles, kind, presets[kind])
        if kind == "process":
            preset["layer_height"] = f"{layer_height:g}"
        path = out_dir / f"{kind}.json"
        path.write_text(json.dumps(preset, indent=1), encoding="utf-8")
        files.append(path)
    return files


def model_slice_command(bambu: Path, model: Path, out_dir: Path, settings: list[Path]) -> list[str]:
    machine, process, filament = settings
    return [
        str(bambu),
        "--slice", "1",
        "--outputdir", str(out_dir),
        "--load-settings", f"{machine};{process}",
        "--load-filaments", str(filament),
        "--arrange", "1",
        "--orient", "0",
        str(model),
    ]


def slice_model(model, out_dir, bambu, presets: dict, layer_height: float, *, profiles=None,
                run=subprocess.run) -> Path:
    """Slice a mesh file (.stl) with system presets into `out_dir`. Return the path of plate_1.gcode.

    Bambu Studio places the part in the middle of the plate and keeps its orientation.
    """
    out_dir = Path(out_dir)
    profiles = Path(profiles) if profiles is not None else profiles_dir(Path(bambu))
    settings = write_presets(profiles, out_dir, presets, layer_height)
    return _run_slice(model_slice_command(Path(bambu), Path(model), out_dir, settings), out_dir, run)


def _run_slice(command: list[str], out_dir: Path, run) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("result.json", "plate_1.gcode"):
        (out_dir / stale).unlink(missing_ok=True)
    try:
        process = run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
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
