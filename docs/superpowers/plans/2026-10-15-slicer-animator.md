# Slicer Animator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build version 1 of the Slicer Animator Blender extension: real G-code (or a fallback slice of a mesh) becomes a toolpath object that grows layer by layer, driven by a shot list, with Preview in the 3D view and an MP4 render.

**Architecture:** Pure-Python `sliceranim/core/` (numpy, no `bpy`) reads every input into one ToolpathSet and computes per-frame timing and camera paths; pytest tests it. `sliceranim/blender/` turns that into one mesh with point attributes, a Geometry Nodes strand setup driven by one keyframed Progress value, one camera per shot, and the panel. Headless Blender tests check the scene.

**Tech Stack:** Blender 5.2 LTS (5.2.2, Python 3.13, numpy 2.3.4 inside Blender), Geometry Nodes, Eevee, pytest 9.1.1 in a local virtual environment, Bambu Studio 2.08 command line.

**Spec:** `docs/superpowers/specs/2026-10-15-slicer-animator-design.md` (approved on 2026-10-15). Read it before you start.

**How this plan was checked:** On 2026-10-15, every file in this plan was written in a scratch copy of the repository (outside git) and the tasks were replayed in order. After each Step 1 the tests failed as this plan says, and after each Step 3 they passed with the counts in this plan. The final state had 80 unit tests and 53 Blender tests passing, the zip built, and the zip installed and loaded a file in a clean Blender profile.

## Global Constraints

- Blender: 5.2.0 or later (`blender_version_min = "5.2.0"`). Target: Blender 5.2 LTS on macOS. Test machine: Apple M1, 8 GB.
- Python in Blender is 3.13. The virtual environment for unit tests uses `python3.13` with `numpy==2.3.4` and `pytest==9.1.1`.
- No dependencies outside Blender. Blender ships with numpy.
- No `bpy` import anywhere in `sliceranim/core/` or in `sliceranim/__init__.py` at module level.
- Extension id `sliceranim`, name `Slicer Animator`, license `SPDX:GPL-3.0-or-later`.
- Units: the core works in mm and seconds. Blender objects are in meters (factor 0.001).
- All stored indices count from 0. The panel shows layer numbers from 1.
- Error texts are exactly the ones in spec section 12 (they live in `sliceranim/core/errors.py`).
- Client files stay in `samples/` and never go into git. Tests that need them skip when they are missing. Do not save a `.blend`, a render, or a slice inside the repository (git ignores `*.blend`, `slices/`, `renders/`, and `samples/`).
- Blender path for commands: `/Applications/Blender.app/Contents/MacOS/Blender`.
- Use relative imports inside `sliceranim/`. Blender loads the extension as `bl_ext.user_default.sliceranim`.

## Details this plan adds to the spec

The spec leaves these points open. The plan decides them as follows. They do not change approved behavior.

1. The toolpath mesh has one more point attribute, `time` (float, seconds), so Rebuild works from the `.blend` file alone.
2. The Geometry Nodes group has two more inputs: `Highlight Layers` (the highlight setting of spec 10) and `Profile Aspect` (median height / median width, because Curve to Mesh scales the profile evenly).
3. A 3MF file with no G-code and no Bambu project data stops with: "This 3MF file has no G-code and is not a Bambu Studio project."
4. Headless slicing writes to `slices/<project name>/` inside the spec's `slices/` folder.
5. The toolpath object is named `<file name> Toolpaths`. Plugin objects go into a collection named `Slicer Animator`, with names that start with `SA `.
6. The close-up camera uses the Hero angles (30° height, 35° side).
7. Light power is 60, 25, and 50 × distance² W for key, fill, and rim (distance in m, 4 × part radius).

## File Structure

```
Makefile, pyproject.toml, README.md      development commands, pytest configuration, how to run the tests
sliceranim/                              the extension (the build zips this folder)
  blender_manifest.toml
  __init__.py                            register() and unregister(); imports bpy only inside them
  core/                                  no bpy
    errors.py                            spec section 12 messages
    toolpaths.py                         ToolpathSet, builder, pack, merging, polygon estimate
    gcode_reader.py                      G-code to ToolpathSet, arcs
    threemf.py                           3MF detection, plate count, sliced 3MF reading
    bambu_cli.py                         headless slicing
    mesh_slicer.py                       STL reading and the 2-loop fallback slicer
    timing.py                            shot list rules and per-frame values
    camera_paths.py                      camera location and aim point per frame
  blender/                               imports bpy
    __init__.py                          class registration
    props.py, prefs.py                   scene settings, add-on preferences
    importer.py                          read sources, build the toolpath object, read it back
    nodes.py                             Geometry Nodes strand group and modifier inputs
    keys.py                              fast keyframe writing
    looks.py                             materials, backdrop, lights, plate mat, nozzle tip
    output.py                            render settings
    cameras.py                           one camera object per shot
    shots.py                             Rebuild
    preview.py                           Preview and Exit Preview
    ui.py                                panel, operators, import menu, drag and drop
tests/
  fixtures/cube_3_layers.gcode           hand-made, committed
  unit/                                  pytest, no Blender
  blender/                               headless Blender tests (run_all.py runs them)
```

## Review Focus

These inputs follow from the spec but are easy to miss. Each has a test in the task that owns the code.

1. G-code saved with Windows line endings (`\r\n`) must read the same as Unix line endings. Test: `test_windows_line_endings_are_read` in Task 4.
2. A layer marker with no printed lines (a layer of only travel or only custom G-code) must not leave an empty layer, because `layer_start` must have one entry per layer with points. Test: `test_a_layer_without_printed_lines_does_not_leave_a_gap` in Task 4.
3. A shot shorter than one frame (for example 0.01 s) must still get one frame, so the frame plan stays valid. Test: `test_a_very_short_shot_still_gets_one_frame` in Task 8.
4. A file name with an upper-case extension (`PART.GCODE`) must load. Test: `test_upper_case_file_extension_is_accepted` in Task 14.
5. A scaled mesh object for Use Selected Object must be sliced at its world size, not its mesh size. Test: `test_scaled_mesh_object_is_sliced_at_its_world_size` in Task 14.

---

## Part A: Core (pure Python, pytest)

Tasks 1 to 9 do not need Blender. Run every test command from the repository root.

### Task 1: Project setup and error messages

Set up the development tools and the user-facing error messages of spec section 12. Every later task uses `make test`.

**Files:**
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `README.md`
- Create: `sliceranim/__init__.py`
- Create: `sliceranim/core/__init__.py`
- Create: `sliceranim/core/errors.py`
- Modify: `.gitignore`
- Test: `tests/unit/conftest.py`
- Test: `tests/unit/test_errors.py`

**Interfaces:**
- Consumes: Nothing.
- Produces:
  - `sliceranim.core.errors.SlicerAnimError(Exception)`: an error with a message that the panel shows as is.
  - Constants `BAMBU_NOT_FOUND`, `NO_LAYER_MARKERS`, `NO_EXTRUSION`, `OPEN_MESH`, `NOT_A_PRINT_3MF` (str).
  - Functions `too_many_plates(count) -> SlicerAnimError`, `slicing_failed(detail) -> SlicerAnimError`, `source_missing(path) -> SlicerAnimError`, `too_many_polygons(polygons) -> str`.
  - `make venv`, `make test`, `make test-blender`, `make build`.

- [ ] **Step 1: Add the development folders to `.gitignore`**

Append these lines to the end of `.gitignore`:

```gitignore
# Development
.venv/
.pytest_cache/
dist/
```

- [ ] **Step 2: Add the test configuration, the Makefile, and the README**

Create `pyproject.toml`:

```toml
# Test configuration only. The extension itself is built from sliceranim/blender_manifest.toml.
[tool.pytest.ini_options]
testpaths = ["tests/unit"]
pythonpath = ["."]
```

Create `Makefile`:

```makefile
BLENDER ?= /Applications/Blender.app/Contents/MacOS/Blender
PYTHON ?= .venv/bin/python

.PHONY: venv test test-blender build

venv:
	python3.13 -m venv .venv
	.venv/bin/pip install numpy==2.3.4 pytest==9.1.1

test:
	$(PYTHON) -m pytest

test-blender:
	$(BLENDER) -b --factory-startup --python-exit-code 1 -P tests/blender/run_all.py

build:
	mkdir -p dist
	$(BLENDER) --command extension build --source-dir sliceranim --output-dir dist
```

Create `README.md`:

```markdown
# Slicer Animator

Slicer Animator is a Blender 5.2 extension. It makes videos of a 3D print that grows layer by layer, from real G-code. The design is in `docs/superpowers/specs/2026-10-15-slicer-animator-design.md`.

## Development

You need Python 3.13 and Blender 5.2 in `/Applications/Blender.app`.

1. Make the virtual environment: `make venv`
2. Run the unit tests, which do not need Blender: `make test`
3. Run the Blender tests in headless Blender: `make test-blender`
4. Build the installable zip file into `dist/`: `make build`

Client files go in `samples/`. Git ignores this folder. Do not commit client files. The tests that need `samples/sample.3mf` skip when the file is not there.
```


- [ ] **Step 3: Make the virtual environment**

Run: `make venv`

Expected: pip ends with `Successfully installed ... numpy-2.3.4 ... pytest-9.1.1`.

- [ ] **Step 4: Write the failing tests**

Create `tests/unit/conftest.py`:

```python
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fixtures() -> Path:
    return ROOT / "tests" / "fixtures"
```

Create `tests/unit/test_errors.py`:

```python
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
```

- [ ] **Step 5: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim'`.

- [ ] **Step 6: Write the implementation**

Create `sliceranim/__init__.py`:

```python
"""Slicer Animator: animate how a 3D print grows, layer by layer.

This file does not import bpy, so the tests can import sliceranim.core without Blender.
"""


def register():
    from .blender import register as register_blender

    register_blender()


def unregister():
    from .blender import unregister as unregister_blender

    unregister_blender()
```

Create `sliceranim/core/__init__.py`:

```python
"""Code that runs without Blender. Nothing in this package imports bpy."""
```

Create `sliceranim/core/errors.py`:

```python
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
```

- [ ] **Step 7: Run the tests and see them pass**

Run: `make test`

Expected: `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add .gitignore pyproject.toml Makefile README.md tests/unit/conftest.py tests/unit/test_errors.py sliceranim/__init__.py sliceranim/core/__init__.py sliceranim/core/errors.py
git commit -m "Add project setup and spec error messages"
```

### Task 2: ToolpathSet data format

Make the ToolpathSet of spec section 5 and the builder that the readers use. `pack()` numbers the layers again from 0 without gaps, so every later step can trust `layer_start`.

**Files:**
- Create: `sliceranim/core/toolpaths.py`
- Test: `tests/unit/test_toolpaths.py`

**Interfaces:**
- Consumes: Nothing from earlier tasks.
- Produces:
  - `FEATURES` (tuple of 15 names), `FEATURE_CODE: dict[str, int]`, `feature_code(label: str) -> int`.
  - `ToolpathSet` dataclass with arrays `position, layer, feature, tool, width, height, time, object_id, run_start, layer_start, layer_z` and `meta: dict`; properties `point_count`, `layer_count`, `total_time`; methods `run_start_mask() -> np.ndarray[bool]`, `validate()`.
  - `pack(*, position, layer, feature, tool, width, height, time, object_id, run_start, layer_z_by_number=None, meta=None) -> ToolpathSet`.
  - `ToolpathBuilder` with `in_run: bool`, `point_count`, `set_layer_z(layer, z)`, `end_run()`, `add_point(x, y, z, *, time, layer, feature, tool, width, height, object_id)`, `build(meta=None) -> ToolpathSet`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_toolpaths.py`:

```python
import math

import numpy as np
import pytest

from sliceranim.core.toolpaths import FEATURE_CODE, ToolpathBuilder, feature_code, pack


def build(runs, layer_of_run=None, feature=1, width=0.45):
    """Make a ToolpathSet from a list of runs. Each run is a list of (x, y, z)."""
    b = ToolpathBuilder()
    t = 0.0
    for r, run in enumerate(runs):
        b.end_run()
        previous = None
        for x, y, z in run:
            if previous is not None:
                t += math.dist(previous, (x, y, z)) / 10.0
            b.add_point(x, y, z, time=t, layer=(layer_of_run or [0] * len(runs))[r], feature=feature,
                        tool=0, width=width, height=0.2, object_id=0)
            previous = (x, y, z)
    return b.build({"slicer": "test"})


def test_feature_labels_map_to_codes():
    assert feature_code("Outer wall") == FEATURE_CODE["outer_wall"]
    assert feature_code(" floating vertical shell ") == FEATURE_CODE["inner_wall"]
    assert feature_code("Support transition") == FEATURE_CODE["support"]
    assert feature_code("Skirt") == FEATURE_CODE["brim_skirt"]
    assert feature_code("Undefined") == FEATURE_CODE["other"]
    assert feature_code("Flush") == 0


def test_builder_tracks_runs_and_layers():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2)], [(0, 1, 0.2), (1, 1, 0.2), (2, 1, 0.2)], [(0, 0, 0.4), (1, 0, 0.4)]],
               layer_of_run=[0, 0, 1])
    assert tp.point_count == 7
    assert tp.run_start.tolist() == [0, 2, 5]
    assert tp.layer_start.tolist() == [0, 5]
    assert tp.layer_count == 2
    np.testing.assert_allclose(tp.layer_z, [0.2, 0.4])
    assert tp.position.dtype == np.float32
    assert tp.time.dtype == np.float64


def test_pack_numbers_layers_again_without_gaps():
    tp = pack(position=np.zeros((4, 3)), layer=[3, 3, 7, 7], feature=[1] * 4, tool=[0] * 4, width=[0.4] * 4,
              height=[0.2] * 4, time=[0, 1, 1, 2], object_id=[0] * 4, run_start=[0, 2],
              layer_z_by_number={3: 0.6, 7: 1.4})
    assert tp.layer.tolist() == [0, 0, 1, 1]
    np.testing.assert_allclose(tp.layer_z, [0.6, 1.4])


def test_validate_rejects_a_layer_that_starts_inside_a_run():
    with pytest.raises(ValueError, match="each layer must start a new run"):
        pack(position=np.zeros((3, 3)), layer=[0, 0, 1], feature=[1] * 3, tool=[0] * 3, width=[0.4] * 3,
             height=[0.2] * 3, time=[0, 1, 2], object_id=[0] * 3, run_start=[0])
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.toolpaths'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/toolpaths.py`:

```python
"""ToolpathSet: every extruded point of one print, in print order (spec section 5).

Units are millimeters and seconds. All indices count from 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FEATURES = (
    "other",
    "outer_wall",
    "inner_wall",
    "overhang_wall",
    "sparse_infill",
    "solid_infill",
    "top_surface",
    "bottom_surface",
    "bridge",
    "gap_fill",
    "support",
    "support_interface",
    "brim_skirt",
    "prime_tower",
    "custom",
)
FEATURE_CODE = {name: code for code, name in enumerate(FEATURES)}

_SLICER_LABELS = {
    "outer wall": 1,
    "inner wall": 2,
    "floating vertical shell": 2,
    "overhang wall": 3,
    "sparse infill": 4,
    "internal solid infill": 5,
    "top surface": 6,
    "bottom surface": 7,
    "bridge": 8,
    "gap infill": 9,
    "support": 10,
    "support transition": 10,
    "support interface": 11,
    "brim": 12,
    "skirt": 12,
    "prime tower": 13,
    "custom": 14,
}


def feature_code(label: str) -> int:
    """Return the feature code for a slicer label such as "Outer wall". Unknown labels give 0."""
    return _SLICER_LABELS.get(label.strip().lower(), 0)


@dataclass
class ToolpathSet:
    position: np.ndarray  # float32 (N, 3), plate coordinates in mm
    layer: np.ndarray  # int32 (N,), from 0, no gaps
    feature: np.ndarray  # uint8 (N,)
    tool: np.ndarray  # uint8 (N,)
    width: np.ndarray  # float32 (N,), mm
    height: np.ndarray  # float32 (N,), mm
    time: np.ndarray  # float64 (N,), seconds from the first point
    object_id: np.ndarray  # int32 (N,)
    run_start: np.ndarray  # int32 (R,), index of the first point of each run
    layer_start: np.ndarray  # int32 (L,), index of the first point of each layer
    layer_z: np.ndarray  # float32 (L,), mm
    meta: dict = field(default_factory=dict)

    @property
    def point_count(self) -> int:
        return int(len(self.position))

    @property
    def layer_count(self) -> int:
        return int(len(self.layer_start))

    @property
    def total_time(self) -> float:
        return float(self.time[-1]) if self.point_count else 0.0

    def run_start_mask(self) -> np.ndarray:
        mask = np.zeros(self.point_count, dtype=bool)
        mask[self.run_start] = True
        return mask

    def validate(self) -> None:
        """Raise ValueError if the arrays break the rules of spec section 5."""
        n = self.point_count
        per_point = ("layer", "feature", "tool", "width", "height", "time", "object_id")
        if self.position.shape != (n, 3):
            raise ValueError("position must have shape (N, 3)")
        for name in per_point:
            if len(getattr(self, name)) != n:
                raise ValueError(f"{name} must have one value per point")
        if n == 0:
            return
        if self.run_start[0] != 0 or np.any(np.diff(self.run_start) <= 0):
            raise ValueError("run_start must start at 0 and increase")
        if np.any(np.diff(self.layer) < 0):
            raise ValueError("layer must not decrease in print order")
        if np.any(np.diff(self.time) < 0):
            raise ValueError("time must not decrease in print order")
        expected = np.searchsorted(self.layer, np.arange(self.layer_count))
        if not np.array_equal(expected, self.layer_start):
            raise ValueError("layer_start does not match layer")
        if not np.all(self.run_start_mask()[self.layer_start]):
            raise ValueError("each layer must start a new run")


def pack(
    *,
    position,
    layer,
    feature,
    tool,
    width,
    height,
    time,
    object_id,
    run_start,
    layer_z_by_number: dict[int, float] | None = None,
    meta: dict | None = None,
) -> ToolpathSet:
    """Make a ToolpathSet from per-point arrays.

    `layer` can have gaps (for example layers with no points). This function
    numbers the layers again from 0 without gaps.
    """
    position = np.asarray(position, dtype=np.float32).reshape(-1, 3)
    raw_layer = np.asarray(layer, dtype=np.int64)
    numbers, new_layer = np.unique(raw_layer, return_inverse=True)
    new_layer = new_layer.astype(np.int32)
    layer_start = np.searchsorted(new_layer, np.arange(len(numbers))).astype(np.int32)
    lookup = layer_z_by_number or {}
    layer_z = np.array(
        [lookup.get(int(number), position[start, 2]) for number, start in zip(numbers, layer_start)],
        dtype=np.float32,
    )
    tp = ToolpathSet(
        position=position,
        layer=new_layer,
        feature=np.asarray(feature, dtype=np.uint8),
        tool=np.asarray(tool, dtype=np.uint8),
        width=np.asarray(width, dtype=np.float32),
        height=np.asarray(height, dtype=np.float32),
        time=np.asarray(time, dtype=np.float64),
        object_id=np.asarray(object_id, dtype=np.int32),
        run_start=np.asarray(run_start, dtype=np.int32),
        layer_start=layer_start,
        layer_z=layer_z,
        meta=dict(meta or {}),
    )
    tp.validate()
    return tp


class ToolpathBuilder:
    """Collects points run by run. Call build() at the end."""

    def __init__(self):
        self._xyz: list[tuple[float, float, float]] = []
        self._attrs: list[tuple[int, int, int, float, float, float, int]] = []
        self._run_start: list[int] = []
        self._layer_z: dict[int, float] = {}
        self.in_run = False

    @property
    def point_count(self) -> int:
        return len(self._xyz)

    def set_layer_z(self, layer: int, z: float) -> None:
        self._layer_z.setdefault(layer, z)

    def end_run(self) -> None:
        self.in_run = False

    def add_point(self, x, y, z, *, time, layer, feature, tool, width, height, object_id) -> None:
        """Add one point. The first point after end_run() starts a new run."""
        if not self.in_run:
            self._run_start.append(len(self._xyz))
            self.in_run = True
        self._xyz.append((x, y, z))
        self._attrs.append((layer, feature, tool, width, height, time, object_id))

    def build(self, meta: dict | None = None) -> ToolpathSet:
        if self._attrs:
            layer, feature, tool, width, height, time, object_id = zip(*self._attrs)
        else:
            layer = feature = tool = width = height = time = object_id = ()
        return pack(
            position=np.array(self._xyz, dtype=np.float32).reshape(-1, 3),
            layer=layer,
            feature=feature,
            tool=tool,
            width=width,
            height=height,
            time=time,
            object_id=object_id,
            run_start=self._run_start,
            layer_z_by_number=self._layer_z,
            meta=meta,
        )
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_toolpaths.py sliceranim/core/toolpaths.py
git commit -m "Add the ToolpathSet data format"
```

### Task 3: Merge angle and polygon estimate

Add point merging (spec section 7, Merge angle) and the polygon estimate for the 10 million warning. The angle is measured from the last kept point, so a gentle curve does not become one straight line.

**Files:**
- Modify: `sliceranim/core/toolpaths.py`
- Modify: `tests/unit/test_toolpaths.py`

**Interfaces:**
- Consumes: `ToolpathSet`, `ToolpathBuilder`, `FEATURE_CODE` from Task 2.
- Produces:
  - `subset(tp, keep: np.ndarray[bool]) -> ToolpathSet`.
  - `merge_points(tp, angle_deg: float) -> ToolpathSet`. Sets `meta["merge_angle"]`. 0 turns merging off.
  - `shell_point_count(tp) -> int` and `estimate_polygons(tp, strand_sides: int, ghost: bool) -> int`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_toolpaths.py`, replace the import line

```python
from sliceranim.core.toolpaths import FEATURE_CODE, ToolpathBuilder, feature_code, pack
```

with

```python
from sliceranim.core.toolpaths import (
    FEATURE_CODE,
    ToolpathBuilder,
    estimate_polygons,
    feature_code,
    merge_points,
    pack,
)
```

Then append the tests below to the end of the file.

Append to the end of `tests/unit/test_toolpaths.py`:

```python
def test_merge_removes_straight_points_and_keeps_corners():
    straight = [(float(x), 0.0, 0.2) for x in range(6)] + [(5.0, 5.0, 0.2)]
    tp = build([straight])
    merged = merge_points(tp, 2.0)
    np.testing.assert_allclose(merged.position, [[0, 0, 0.2], [5, 0, 0.2], [5, 5, 0.2]])
    assert merged.total_time == pytest.approx(tp.total_time)
    assert merged.meta["merge_angle"] == 2.0


def test_merge_keeps_run_ends_and_the_angle_zero_turns_it_off():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2), (2, 0, 0.2)], [(0, 1, 0.2), (1, 1, 0.2), (2, 1, 0.2)]])
    merged = merge_points(tp, 2.0)
    assert merged.point_count == 4
    assert merged.run_start.tolist() == [0, 2]
    assert merge_points(tp, 0.0).point_count == 6


def test_merge_does_not_flatten_a_gentle_curve():
    # A circle of radius 20 split into 1 degree steps. Each step turns by 1 degree only.
    angles = np.radians(np.arange(0, 361, 1.0))
    circle = [(20 * math.cos(a), 20 * math.sin(a), 0.2) for a in angles]
    merged = merge_points(build([circle]), 2.0)
    # Measured from the last kept point, the turn reaches 2 degrees after a few steps.
    assert 90 <= merged.point_count <= 200
    radius = np.hypot(merged.position[:, 0], merged.position[:, 1])
    np.testing.assert_allclose(radius, 20.0, atol=1e-3)


def test_merge_keeps_a_point_where_the_width_changes():
    b = ToolpathBuilder()
    for i, w in enumerate([0.4, 0.4, 0.5, 0.5]):
        b.add_point(float(i), 0.0, 0.2, time=float(i), layer=0, feature=1, tool=0, width=w, height=0.2, object_id=0)
    merged = merge_points(b.build(), 2.0)
    assert merged.width.tolist() == pytest.approx([0.4, 0.4, 0.5, 0.5])


def test_estimate_polygons_counts_the_ghost_shell():
    tp = build([[(0, 0, 0.2), (1, 0, 0.2)]], feature=FEATURE_CODE["outer_wall"])
    assert estimate_polygons(tp, 6, ghost=False) == 12
    assert estimate_polygons(tp, 6, ghost=True) == 20
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ImportError: cannot import name 'estimate_polygons' from 'sliceranim.core.toolpaths'`.

- [ ] **Step 3: Write the implementation**

In `sliceranim/core/toolpaths.py`, add `import math` after `from __future__ import annotations`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field
```

Then append the code below to the end of the file.

Append to the end of `sliceranim/core/toolpaths.py`:

```python
def subset(tp: ToolpathSet, keep: np.ndarray) -> ToolpathSet:
    """Keep the points where `keep` is True. Run and layer starts must be kept."""
    if not (np.all(keep[tp.run_start]) and np.all(keep[tp.layer_start])):
        raise ValueError("subset must keep the first point of every run and layer")
    new_index = np.cumsum(keep) - 1
    return ToolpathSet(
        position=tp.position[keep],
        layer=tp.layer[keep],
        feature=tp.feature[keep],
        tool=tp.tool[keep],
        width=tp.width[keep],
        height=tp.height[keep],
        time=tp.time[keep],
        object_id=tp.object_id[keep],
        run_start=new_index[tp.run_start].astype(np.int32),
        layer_start=new_index[tp.layer_start].astype(np.int32),
        layer_z=tp.layer_z.copy(),
        meta=dict(tp.meta),
    )


def merge_points(tp: ToolpathSet, angle_deg: float) -> ToolpathSet:
    """Remove a point when the path turns by less than angle_deg there (spec section 7).

    The first and last point of each run stay. A point also stays when the width
    or the height changes there. Each kept point keeps its own print time, so the
    total print time does not change. The angle is measured from the last kept
    point, so a gentle curve does not turn into one straight line.
    """
    result_meta = dict(tp.meta, merge_angle=angle_deg)
    if angle_deg <= 0 or tp.point_count == 0:
        out = subset(tp, np.ones(tp.point_count, dtype=bool))
        out.meta = result_meta
        return out
    cos_limit = math.cos(math.radians(angle_deg))
    pos = tp.position.astype(np.float64).tolist()
    width = tp.width.tolist()
    height = tp.height.tolist()
    keep = np.ones(tp.point_count, dtype=bool)
    starts = tp.run_start.tolist()
    ends = [s - 1 for s in starts[1:]] + [tp.point_count - 1]
    for start, end in zip(starts, ends):
        anchor = start
        for i in range(start + 1, end):
            if width[i] != width[anchor] or height[i] != height[anchor] or width[i] != width[i + 1] or height[i] != height[i + 1]:
                anchor = i
                continue
            ax, ay, az = pos[anchor]
            px, py, pz = pos[i]
            nx, ny, nz = pos[i + 1]
            ux, uy, uz = px - ax, py - ay, pz - az
            vx, vy, vz = nx - px, ny - py, nz - pz
            lu = math.sqrt(ux * ux + uy * uy + uz * uz)
            lv = math.sqrt(vx * vx + vy * vy + vz * vz)
            if lu == 0.0:
                keep[i] = False
                continue
            if lv == 0.0:
                anchor = i
                continue
            if (ux * vx + uy * vy + uz * vz) / (lu * lv) > cos_limit:
                keep[i] = False
            else:
                anchor = i
    out = subset(tp, keep)
    out.meta = result_meta
    return out


def shell_point_count(tp: ToolpathSet) -> int:
    """Number of points that the ghost can draw: outer walls, overhang walls, top surfaces."""
    codes = [FEATURE_CODE["outer_wall"], FEATURE_CODE["overhang_wall"], FEATURE_CODE["top_surface"]]
    return int(np.isin(tp.feature, codes).sum())


def estimate_polygons(tp: ToolpathSet, strand_sides: int, ghost: bool) -> int:
    """Estimate from spec section 7: points x strand sides, plus ghost points x 4."""
    estimate = tp.point_count * strand_sides
    if ghost:
        estimate += shell_point_count(tp) * 4
    return estimate
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_toolpaths.py sliceranim/core/toolpaths.py
git commit -m "Add point merging and the polygon estimate"
```

### Task 4: G-code reader

Read Bambu Studio and OrcaSlicer G-code (spec 6.1). The fixture is a 10 mm square part with 3 layers in the Bambu Studio comment format. It is made by hand and holds no client data.

**Files:**
- Create: `sliceranim/core/gcode_reader.py`
- Test: `tests/fixtures/cube_3_layers.gcode`
- Test: `tests/unit/test_gcode_reader.py`

**Interfaces:**
- Consumes: `ToolpathBuilder`, `feature_code`, `FEATURE_CODE` (Task 2), the errors (Task 1).
- Produces:
  - `read_gcode(path, *, drop_custom=True) -> ToolpathSet`. Sets `meta["source_path"]`.
  - `parse_gcode(lines: Iterable[str], *, drop_custom=True) -> ToolpathSet`. Meta keys: `slicer` ("Bambu Studio" or "OrcaSlicer"), `slicer_version`, `filament_colors` (list of "#RRGGBB"), `filament_type`.
  - `arc_points(start, end, i, j, clockwise, step=0.5) -> list[tuple[float, float, float]]`.
  - `tests/fixtures/cube_3_layers.gcode`: 3 layers, 14 points and 10 strands per layer, filament color `#1E88E5`.

Facts from the real sample (sliced on 2026-10-15): the file has 414,248 lines, 24,006 arc moves (`G2`/`G3` with `I` and `J`), relative extrusion (`M83`), and the commands `T255` and `T1000`, which are machine commands and not filaments. A full-circle helix such as `G3 Z60.2 I-1.032 J.644 P1 F30000` has no `X`/`Y` and no `E`, so it is a travel move. Wipe moves have negative `E`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fixtures/cube_3_layers.gcode`:

```gcode
; HEADER_BLOCK_START
; BambuStudio 02.08.02.61
; total layer number: 3
; HEADER_BLOCK_END
G90
M83 ; use relative distances for extrusion
G1 X0 Y0 Z5 F30000
G1 X-5 Y-5 E8 F600 ; purge before the first layer is ignored
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; LAYER_HEIGHT: 0.2
G1 E-.8 F1800
; layer num/total_layer_count: 1/3
; OBJECT_ID: 7
G1 X0.675 Y0.675 Z0.2 F30000
G1 E.8 F1800
; FEATURE: Inner wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.325 Y0.675 E.3
G1 X9.325 Y9.325 E.3
G1 X0.675 Y9.325 E.3
G1 X0.675 Y0.675 E.3
; WIPE_START
G1 X9.325 Y0.675 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X0.225 Y0.225 Z0.2 F30000
G1 E.8 F1800
; FEATURE: Outer wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.775 Y0.225 E.3
G1 X9.775 Y9.775 E.3
G1 X0.225 Y9.775 E.3
G1 X0.225 Y0.225 E.3
; WIPE_START
G1 X9.775 Y0.225 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X2 Y2 F30000
G1 E.8 F1800
; FEATURE: Sparse infill
; LINE_WIDTH: 0.45
G1 F6000
G1 X8 Y8 E.2
G1 X8 Y2 F30000
G1 X2 Y8 E.2
; CHANGE_LAYER
; Z_HEIGHT: 0.4
; LAYER_HEIGHT: 0.2
G1 E-.8 F1800
; layer num/total_layer_count: 2/3
; OBJECT_ID: 7
G1 X0.675 Y0.675 Z0.4 F30000
G1 E.8 F1800
; FEATURE: Inner wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.325 Y0.675 E.3
G1 X9.325 Y9.325 E.3
G1 X0.675 Y9.325 E.3
G1 X0.675 Y0.675 E.3
; WIPE_START
G1 X9.325 Y0.675 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X0.225 Y0.225 Z0.4 F30000
G1 E.8 F1800
; FEATURE: Outer wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.775 Y0.225 E.3
G1 X9.775 Y9.775 E.3
G1 X0.225 Y9.775 E.3
G1 X0.225 Y0.225 E.3
; WIPE_START
G1 X9.775 Y0.225 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X2 Y2 F30000
G1 E.8 F1800
; FEATURE: Sparse infill
; LINE_WIDTH: 0.45
G1 F6000
G1 X8 Y8 E.2
G1 X8 Y2 F30000
G1 X2 Y8 E.2
; CHANGE_LAYER
; Z_HEIGHT: 0.6
; LAYER_HEIGHT: 0.2
G1 E-.8 F1800
; layer num/total_layer_count: 3/3
; OBJECT_ID: 7
G1 X0.675 Y0.675 Z0.6 F30000
G1 E.8 F1800
; FEATURE: Inner wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.325 Y0.675 E.3
G1 X9.325 Y9.325 E.3
G1 X0.675 Y9.325 E.3
G1 X0.675 Y0.675 E.3
; WIPE_START
G1 X9.325 Y0.675 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X0.225 Y0.225 Z0.6 F30000
G1 E.8 F1800
; FEATURE: Outer wall
; LINE_WIDTH: 0.45
G1 F3000
G1 X9.775 Y0.225 E.3
G1 X9.775 Y9.775 E.3
G1 X0.225 Y9.775 E.3
G1 X0.225 Y0.225 E.3
; WIPE_START
G1 X9.775 Y0.225 E-.4
; WIPE_END
G1 E-.04 F1800
G1 X2 Y2 F30000
G1 E.8 F1800
; FEATURE: Sparse infill
; LINE_WIDTH: 0.45
G1 F6000
G1 X8 Y8 E.2
G1 X8 Y2 F30000
G1 X2 Y8 E.2
; filament_colour = #1E88E5;#161616
; filament_type = PLA;PLA
```

Create `tests/unit/test_gcode_reader.py`:

```python
import math

import numpy as np
import pytest

from sliceranim.core.errors import NO_EXTRUSION, NO_LAYER_MARKERS, SlicerAnimError
from sliceranim.core.gcode_reader import arc_points, parse_gcode, read_gcode
from sliceranim.core.toolpaths import FEATURE_CODE


def gcode(text: str):
    return parse_gcode(text.strip().splitlines())


HEADER = """
; HEADER_BLOCK_START
; BambuStudio 02.08.02.61
; HEADER_BLOCK_END
G90
M83
"""


def test_one_line_makes_a_run_with_start_and_end_point():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; LAYER_HEIGHT: 0.2
G1 X10 Y10 Z0.2 F30000
; FEATURE: Outer wall
; LINE_WIDTH: 0.42
G1 F600
G1 X20 Y10 E0.5
""")
    assert tp.point_count == 2
    np.testing.assert_allclose(tp.position, [[10, 10, 0.2], [20, 10, 0.2]], atol=1e-6)
    assert tp.run_start.tolist() == [0]
    assert tp.feature.tolist() == [FEATURE_CODE["outer_wall"]] * 2
    np.testing.assert_allclose(tp.width, 0.42)
    np.testing.assert_allclose(tp.height, 0.2)
    # 10 mm at 600 mm/min = 10 mm/s takes 1 s.
    np.testing.assert_allclose(tp.time, [0.0, 1.0])
    assert tp.meta["slicer"] == "Bambu Studio"
    assert tp.meta["slicer_version"] == "02.08.02.61"


def test_travel_retract_wipe_feature_and_layer_end_the_run():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
; FEATURE: Inner wall
G1 X10 Y0 E1
G1 X10 Y10 E1
G1 X12 Y12 F30000
G1 X12 Y20 E1 F600
G1 E-0.8
G1 E0.8
G1 X20 Y20 E1
; WIPE_START
G1 X25 Y20 E-0.3
; WIPE_END
G1 X30 Y20 E1
; FEATURE: Outer wall
G1 X40 Y20 E1
; CHANGE_LAYER
; Z_HEIGHT: 0.4
G1 X50 Y20 Z0.4 E1
""")
    # Runs: (0,0)->(10,0)->(10,10), (12,12)->(12,20), (12,20)->(20,20),
    # (25,20)->(30,20), (30,20)->(40,20), and in layer 1 (40,20)->(50,20).
    assert tp.run_start.tolist() == [0, 3, 5, 7, 9, 11]
    assert tp.point_count == 13
    assert tp.layer.tolist() == [0] * 11 + [1] * 2
    assert tp.layer_start.tolist() == [0, 11]
    np.testing.assert_allclose(tp.layer_z, [0.2, 0.4])


def test_moves_before_the_first_layer_marker_are_ignored():
    tp = gcode(HEADER + """
G1 X0 Y0 Z0.2 F600
G1 X100 Y0 E5
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; FEATURE: Outer wall
G1 X100 Y10 E1
""")
    assert tp.point_count == 2
    np.testing.assert_allclose(tp.position[0], [100, 0, 0.2])


def test_custom_feature_is_dropped_by_default_and_kept_on_request():
    text = HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
; FEATURE: Custom
G1 X10 Y0 E1
; FEATURE: Outer wall
G1 X10 Y10 E1
"""
    assert gcode(text).point_count == 2
    kept = parse_gcode(text.strip().splitlines(), drop_custom=False)
    assert kept.point_count == 4


def test_absolute_extrusion_and_g92_reset():
    tp = gcode("""
G90
M82
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
G92 E0
G1 X10 Y0 E1.0
G1 X20 Y0 E1.0
G1 X30 Y0 E2.0
""")
    # The second move has E equal to the last E, so it extrudes nothing and ends the run.
    assert tp.run_start.tolist() == [0, 2]
    assert tp.point_count == 4


def test_relative_xyz_positions():
    tp = gcode("""
G91
M83
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X5 Y5 Z0.2 F600
G1 X10 E1
""")
    np.testing.assert_allclose(tp.position, [[5, 5, 0.2], [15, 5, 0.2]], atol=1e-6)


def test_arc_is_split_into_segments_of_half_a_millimeter_or_less():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X10 Y0 Z0.2 F600
G3 X-10 Y0 I-10 J0 E2
""")
    # Half circle, radius 10: length 31.4 mm, so 63 segments and 64 points.
    assert tp.point_count == 64
    xy = tp.position[:, :2].astype(np.float64)
    np.testing.assert_allclose(np.hypot(xy[:, 0], xy[:, 1]), 10.0, atol=1e-4)
    assert np.all(xy[:, 1] >= -1e-6)  # counterclockwise from (10,0) goes through +Y
    steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    assert steps.max() <= 0.5 + 1e-6
    assert tp.total_time == pytest.approx(math.pi * 10 / 10, rel=1e-3)


def test_full_circle_arc_when_end_equals_start():
    points = arc_points((10, 0, 0), (10, 0, 0), -10, 0, clockwise=True)
    assert len(points) == math.ceil(2 * math.pi * 10 / 0.5)
    assert points[0][1] < 0  # clockwise from (10,0) goes through -Y
    assert points[-1] == (10, 0, 0)


def test_tool_change_and_bambu_machine_tool_codes():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
T1
T1000
T255
G1 X10 Y0 E1
""")
    assert tp.tool.tolist() == [1, 1]


def test_filament_settings_and_object_id():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; OBJECT_ID: 3364
G1 X0 Y0 Z0.2 F600
G1 X10 Y0 E1
; filament_colour = #161616;#FF0000
; filament_type = PLA;PETG
""")
    assert tp.object_id.tolist() == [3364, 3364]
    assert tp.meta["filament_colors"] == ["#161616", "#FF0000"]
    assert tp.meta["filament_type"] == "PLA"


def test_orcaslicer_header_is_detected():
    tp = gcode("""
; generated by OrcaSlicer 2.3.2 on 2026-10-15 at 10:00:00
M83
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
G1 X10 Y0 E1
""")
    assert tp.meta["slicer"] == "OrcaSlicer"
    assert tp.meta["slicer_version"] == "2.3.2"


def test_no_layer_marker_raises():
    with pytest.raises(SlicerAnimError, match=NO_LAYER_MARKERS):
        gcode("G1 X0 Y0 F600\nG1 X10 Y0 E1\n")


def test_no_extrusion_raises():
    with pytest.raises(SlicerAnimError, match=NO_EXTRUSION):
        gcode("; CHANGE_LAYER\nG1 X0 Y0 F600\nG1 X10 Y0\n")


def test_zero_feed_rate_adds_no_time_and_does_not_crash():
    tp = gcode("""
M83
; CHANGE_LAYER
G1 X0 Y0 Z0.2
G1 X10 Y0 E1
""")
    assert tp.time.tolist() == [0.0, 0.0]


def test_read_gcode_from_fixture_file(fixtures):
    tp = read_gcode(fixtures / "cube_3_layers.gcode")
    assert tp.layer_count == 3
    assert tp.meta["source_path"].endswith("cube_3_layers.gcode")
    tp.validate()


def test_windows_line_endings_are_read():
    text = (HEADER + "; CHANGE_LAYER\n; Z_HEIGHT: 0.2\nG1 X0 Y0 Z0.2 F600\nG1 X10 Y0 E1\n").replace("\n", "\r\n")
    tp = parse_gcode(text.splitlines(keepends=True))
    assert tp.point_count == 2


def test_a_layer_without_printed_lines_does_not_leave_a_gap():
    tp = gcode(HEADER + """
; CHANGE_LAYER
; Z_HEIGHT: 0.2
G1 X0 Y0 Z0.2 F600
G1 X10 Y0 E1
; CHANGE_LAYER
; Z_HEIGHT: 0.4
G1 X0 Y0 Z0.4
; CHANGE_LAYER
; Z_HEIGHT: 0.6
G1 X0 Y0 Z0.6
G1 X10 Y0 E1
""")
    assert tp.layer_count == 2
    assert tp.layer.tolist() == [0, 0, 1, 1]
    np.testing.assert_allclose(tp.layer_z, [0.2, 0.6])
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.gcode_reader'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/gcode_reader.py`:

```python
"""Read Bambu Studio and OrcaSlicer G-code into a ToolpathSet (spec section 6.1)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

from .errors import NO_EXTRUSION, NO_LAYER_MARKERS, SlicerAnimError
from .toolpaths import FEATURE_CODE, ToolpathBuilder, ToolpathSet, feature_code

ARC_STEP_MM = 0.5
_CUSTOM = FEATURE_CODE["custom"]
_SLICER = re.compile(r"^;\s*(?:generated by\s+)?(BambuStudio|OrcaSlicer)\s+v?([0-9][0-9.]*)", re.IGNORECASE)


def read_gcode(path, *, drop_custom: bool = True) -> ToolpathSet:
    """Read a .gcode file."""
    with open(path, "r", encoding="utf-8", errors="replace") as lines:
        tp = parse_gcode(lines, drop_custom=drop_custom)
    tp.meta["source_path"] = str(Path(path))
    return tp


def parse_gcode(lines: Iterable[str], *, drop_custom: bool = True) -> ToolpathSet:
    """Read G-code from any iterable of lines."""
    return _Reader(drop_custom).read(lines)


def arc_points(start, end, i, j, clockwise: bool, step: float = ARC_STEP_MM) -> list[tuple[float, float, float]]:
    """Points along a G2/G3 arc, after the start point. Each segment is `step` mm or less.

    The end point equal to the start point means a full circle. Z changes linearly (helix).
    """
    x0, y0, z0 = start
    x1, y1, z1 = end
    cx, cy = x0 + i, y0 + j
    radius = math.hypot(i, j)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = a1 - a0
    if clockwise:
        while sweep >= -1e-9:
            sweep -= 2 * math.pi
        while sweep < -2 * math.pi:
            sweep += 2 * math.pi
    else:
        while sweep <= 1e-9:
            sweep += 2 * math.pi
        while sweep > 2 * math.pi:
            sweep -= 2 * math.pi
    count = max(1, math.ceil(abs(sweep) * radius / step))
    points = []
    for k in range(1, count):
        a = a0 + sweep * k / count
        points.append((cx + radius * math.cos(a), cy + radius * math.sin(a), z0 + (z1 - z0) * k / count))
    points.append((x1, y1, z1))
    return points


def _params(words: list[str]) -> dict[str, float]:
    out = {}
    for word in words[1:]:
        letter = word[0].upper()
        try:
            out[letter] = float(word[1:])
        except ValueError:
            pass
    return out


class _Reader:
    def __init__(self, drop_custom: bool):
        self.drop_custom = drop_custom
        self.builder = ToolpathBuilder()
        self.x = self.y = self.z = 0.0
        self.e_abs = 0.0
        self.xyz_relative = False
        self.e_relative = False
        self.feed = 0.0  # mm per minute
        self.time = 0.0
        self.layer = -1
        self.feature = 0
        self.width = 0.4
        self.height = 0.2
        self.tool = 0
        self.object_id = 0
        self.in_wipe = False
        self.meta: dict = {"slicer": "", "slicer_version": "", "filament_colors": [], "filament_type": ""}

    def read(self, lines: Iterable[str]) -> ToolpathSet:
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line[0] == ";":
                self._comment(line)
                continue
            code = line.split(";", 1)[0].split()
            if not code:
                continue
            command = code[0].upper()
            if command in ("G0", "G1", "G2", "G3"):
                self._move(command, _params(code))
            elif command == "G90":
                self.xyz_relative = False
            elif command == "G91":
                self.xyz_relative = True
            elif command == "M82":
                self.e_relative = False
            elif command == "M83":
                self.e_relative = True
            elif command == "G92":
                params = _params(code)
                if "E" in params:
                    self.e_abs = params["E"]
            elif command[0] == "T" and command[1:].isdigit():
                number = int(command[1:])
                if number < 16:  # T255 and T1000 are Bambu machine commands, not filaments
                    self.tool = number
        if self.layer < 0:
            raise SlicerAnimError(NO_LAYER_MARKERS)
        if self.builder.point_count == 0:
            raise SlicerAnimError(NO_EXTRUSION)
        return self.builder.build(self.meta)

    def _comment(self, line: str) -> None:
        body = line[1:].strip()
        if body == "CHANGE_LAYER":
            self.layer += 1
            self.builder.end_run()
        elif body.startswith("Z_HEIGHT:"):
            if self.layer >= 0:
                self.builder.set_layer_z(self.layer, float(body[9:]))
        elif body.startswith("LAYER_HEIGHT:"):
            self.height = float(body[13:])
        elif body.startswith("FEATURE:"):
            self.feature = feature_code(body[8:])
            self.builder.end_run()
        elif body.startswith("LINE_WIDTH:"):
            self.width = float(body[11:])
        elif body == "WIPE_START":
            self.in_wipe = True
            self.builder.end_run()
        elif body == "WIPE_END":
            self.in_wipe = False
        elif body.startswith("OBJECT_ID:"):
            self.object_id = int(float(body[10:]))
        elif body.startswith("filament_colour ="):
            self.meta["filament_colors"] = [c.strip() for c in body.split("=", 1)[1].split(";") if c.strip()]
        elif body.startswith("filament_type ="):
            types = [t.strip() for t in body.split("=", 1)[1].split(";") if t.strip()]
            self.meta["filament_type"] = types[0] if types else ""
        elif not self.meta["slicer"]:
            match = _SLICER.match(line)
            if match:
                self.meta["slicer"] = "OrcaSlicer" if match.group(1).lower() == "orcaslicer" else "Bambu Studio"
                self.meta["slicer_version"] = match.group(2)

    def _target(self, params: dict[str, float]) -> tuple[float, float, float]:
        if self.xyz_relative:
            return (self.x + params.get("X", 0.0), self.y + params.get("Y", 0.0), self.z + params.get("Z", 0.0))
        return (params.get("X", self.x), params.get("Y", self.y), params.get("Z", self.z))

    def _extruded(self, params: dict[str, float]) -> float:
        if "E" not in params:
            return 0.0
        if self.e_relative:
            return params["E"]
        amount = params["E"] - self.e_abs
        self.e_abs = params["E"]
        return amount

    def _move(self, command: str, params: dict[str, float]) -> None:
        if "F" in params:
            self.feed = params["F"]
        start = (self.x, self.y, self.z)
        end = self._target(params)
        extruded = self._extruded(params)
        is_arc = command in ("G2", "G3") and ("I" in params or "J" in params)
        if is_arc:
            path = arc_points(start, end, params.get("I", 0.0), params.get("J", 0.0), command == "G2")
            moves_xy = math.hypot(params.get("I", 0.0), params.get("J", 0.0)) > 0
        else:
            path = [end]
            moves_xy = end[0] != start[0] or end[1] != start[1]
        self.x, self.y, self.z = end
        if end == start and extruded == 0 and not is_arc:
            return  # a feed-rate-only line such as "G1 F3000"
        is_extrusion = extruded > 0 and moves_xy and self.layer >= 0 and not self.in_wipe
        if not is_extrusion or (self.drop_custom and self.feature == _CUSTOM):
            self.builder.end_run()
            return
        attrs = dict(
            layer=self.layer,
            feature=self.feature,
            tool=self.tool,
            width=self.width,
            height=self.height,
            object_id=self.object_id,
        )
        if not self.builder.in_run:
            self.builder.add_point(*start, time=self.time, **attrs)
        speed = self.feed / 60.0
        previous = start
        for point in path:
            if speed > 0:
                self.time += math.dist(previous, point) / speed
            self.builder.add_point(*point, time=self.time, **attrs)
            previous = point
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `27 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/cube_3_layers.gcode tests/unit/test_gcode_reader.py sliceranim/core/gcode_reader.py
git commit -m "Add the G-code reader"
```

### Task 5: 3MF files

Look inside 3MF files (spec 6.2). The tests make small zip files in a temporary folder, so no 3MF file goes into git.

**Files:**
- Create: `sliceranim/core/threemf.py`
- Test: `tests/unit/test_threemf.py`

**Interfaces:**
- Consumes: `parse_gcode` (Task 4), the errors (Task 1).
- Produces:
  - `SLICED = "sliced"`, `PROJECT = "project"`, `ThreeMFInfo(kind, plate_count, gcode_names)`.
  - `inspect_3mf(path) -> ThreeMFInfo`, `require_one_plate(info)`, `read_sliced_3mf(path, *, drop_custom=True) -> ToolpathSet`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_threemf.py`:

```python
import zipfile

import pytest

from sliceranim.core.errors import NOT_A_PRINT_3MF, SlicerAnimError
from sliceranim.core.threemf import PROJECT, SLICED, inspect_3mf, read_sliced_3mf, require_one_plate


def make_3mf(path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("3D/3dmodel.model", "<model/>")
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def test_sliced_3mf_with_one_plate(tmp_path, fixtures):
    gcode = (fixtures / "cube_3_layers.gcode").read_text()
    path = make_3mf(tmp_path / "part.gcode.3mf", {"Metadata/plate_1.gcode": gcode, "Metadata/plate_1.gcode.md5": "x"})
    info = inspect_3mf(path)
    assert info.kind == SLICED
    assert info.plate_count == 1
    assert info.gcode_names == ("Metadata/plate_1.gcode",)
    tp = read_sliced_3mf(path)
    assert tp.layer_count == 3
    assert tp.meta["source_path"].endswith("part.gcode.3mf")


def test_sliced_3mf_with_two_plates_is_refused(tmp_path):
    path = make_3mf(tmp_path / "two.gcode.3mf", {"Metadata/plate_2.gcode": "", "Metadata/plate_1.gcode": ""})
    info = inspect_3mf(path)
    assert info.plate_count == 2
    assert info.gcode_names == ("Metadata/plate_1.gcode", "Metadata/plate_2.gcode")
    with pytest.raises(SlicerAnimError, match="This file has 2 plates. Export one plate"):
        read_sliced_3mf(path)


def test_project_plate_count_comes_from_model_settings(tmp_path):
    config = "<config><object id='2'/><plate><metadata/></plate><plate></plate><plate/></config>"
    path = make_3mf(tmp_path / "project.3mf", {"Metadata/model_settings.config": config})
    info = inspect_3mf(path)
    assert info.kind == PROJECT
    assert info.plate_count == 3
    with pytest.raises(SlicerAnimError, match="This file has 3 plates"):
        require_one_plate(info)


def test_3mf_without_gcode_or_project_data_is_refused(tmp_path):
    path = make_3mf(tmp_path / "plain.3mf", {})
    with pytest.raises(SlicerAnimError, match=NOT_A_PRINT_3MF):
        inspect_3mf(path)


def test_a_file_that_is_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "broken.3mf"
    path.write_text("not a zip")
    with pytest.raises(SlicerAnimError, match=NOT_A_PRINT_3MF):
        inspect_3mf(path)
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.threemf'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/threemf.py`:

```python
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
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `32 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_threemf.py sliceranim/core/threemf.py
git commit -m "Add 3MF inspection and sliced 3MF reading"
```

### Task 6: Headless slicing with Bambu Studio

Run Bambu Studio from the command line (spec 6.3). The unit tests use a fake `subprocess.run`. One more test slices the real sample when `samples/sample.3mf` and Bambu Studio are present, and prints the numbers for the spec.

**Files:**
- Create: `sliceranim/core/bambu_cli.py`
- Test: `tests/unit/test_bambu_cli.py`
- Test: `tests/unit/test_sample.py`

**Interfaces:**
- Consumes: The errors (Task 1). The sample test also uses `read_gcode` (Task 4) and `merge_points` (Task 3).
- Produces:
  - `DEFAULT_PATHS: dict[str, str]`, `find_bambu(preference_path="", platform=sys.platform) -> Path`.
  - `slice_command(bambu, project, out_dir) -> list[str]`, `slice_project(project, out_dir, bambu, *, run=subprocess.run) -> Path` (the path of `plate_1.gcode`).

Facts checked on 2026-10-15 with Bambu Studio 2.08.02.61: the command writes `result.json`, `plate_1.gcode`, and `sliced.gcode.3mf` directly into the output directory. `result.json` holds `return_code` (0 on success) and `error_string` ("Success.").

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_bambu_cli.py`:

```python
import json
import subprocess

import pytest

from sliceranim.core.bambu_cli import DEFAULT_PATHS, find_bambu, slice_command, slice_project
from sliceranim.core.errors import BAMBU_NOT_FOUND, SlicerAnimError


class FakeBambu:
    """Stands in for subprocess.run. It writes the files that Bambu Studio writes."""

    def __init__(self, result: dict | None, gcode: str | None = "; CHANGE_LAYER\n", returncode: int = 0):
        self.result = result
        self.gcode = gcode
        self.returncode = returncode
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        out_dir = command[command.index("--outputdir") + 1]
        from pathlib import Path

        if self.result is not None:
            (Path(out_dir) / "result.json").write_text(json.dumps(self.result))
        if self.gcode is not None:
            (Path(out_dir) / "plate_1.gcode").write_text(self.gcode)
        return subprocess.CompletedProcess(command, self.returncode, "", "")


def test_slice_command_matches_the_spec(tmp_path):
    command = slice_command(tmp_path / "BambuStudio", tmp_path / "p.3mf", tmp_path / "out")
    assert command[1:] == ["--slice", "1", "--outputdir", str(tmp_path / "out"),
                           "--export-3mf", "sliced.gcode.3mf", str(tmp_path / "p.3mf")]


def test_successful_slice_returns_plate_1_gcode(tmp_path):
    fake = FakeBambu({"return_code": 0, "error_string": "Success."})
    gcode = slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)
    assert gcode == tmp_path / "out" / "plate_1.gcode"
    assert len(fake.calls) == 1


def test_failed_slice_shows_error_string(tmp_path):
    fake = FakeBambu({"return_code": -50, "error_string": "Nothing to be sliced"}, gcode=None)
    with pytest.raises(SlicerAnimError, match="Slicing failed: Nothing to be sliced"):
        slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)


def test_missing_result_json_is_a_slicing_failure(tmp_path):
    fake = FakeBambu(None, gcode=None, returncode=139)
    with pytest.raises(SlicerAnimError, match="exit code 139"):
        slice_project(tmp_path / "p.3mf", tmp_path / "out", tmp_path / "BambuStudio", run=fake)


def test_stale_output_from_an_earlier_run_is_not_used(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "plate_1.gcode").write_text("old")
    fake = FakeBambu({"return_code": 0}, gcode=None)
    with pytest.raises(SlicerAnimError, match="wrote no plate_1.gcode"):
        slice_project(tmp_path / "p.3mf", out, tmp_path / "BambuStudio", run=fake)


def test_find_bambu_prefers_the_preference_path(tmp_path):
    program = tmp_path / "MyBambu"
    program.write_text("")
    assert find_bambu(str(program), platform="darwin") == program


def test_find_bambu_raises_when_nothing_exists(tmp_path):
    with pytest.raises(SlicerAnimError, match=BAMBU_NOT_FOUND):
        find_bambu(str(tmp_path / "missing"), platform="linux")


def test_default_paths_match_the_spec():
    assert DEFAULT_PATHS["darwin"] == "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
```

Create `tests/unit/test_sample.py`:

```python
"""Checks with the client sample. They skip when samples/sample.3mf or Bambu Studio is not present."""

import time
from pathlib import Path

import pytest

from sliceranim.core.bambu_cli import DEFAULT_PATHS, slice_project
from sliceranim.core.gcode_reader import read_gcode
from sliceranim.core.toolpaths import merge_points

SAMPLE_3MF = Path(__file__).resolve().parents[2] / "samples" / "sample.3mf"
pytestmark = pytest.mark.skipif(
    not SAMPLE_3MF.is_file() or not Path(DEFAULT_PATHS["darwin"]).is_file(),
    reason="needs samples/sample.3mf and Bambu Studio",
)


def test_sample_slices_reads_and_merges(tmp_path):
    start = time.perf_counter()
    gcode = slice_project(SAMPLE_3MF, tmp_path, DEFAULT_PATHS["darwin"])
    sliced = time.perf_counter()
    tp = read_gcode(gcode)
    read = time.perf_counter()
    merged = merge_points(tp, 2.0)
    done = time.perf_counter()
    print(
        f"\nslice {sliced - start:.2f} s, read {read - sliced:.2f} s, merge {done - read:.2f} s; "
        f"{tp.layer_count} layers, {tp.point_count} points before merging, {merged.point_count} after"
    )
    assert tp.layer_count == 764
    assert done - start < 10.0
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.bambu_cli'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/bambu_cli.py`:

```python
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
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `41 passed`. Without the sample or Bambu Studio, expect `40 passed, 1 skipped`.

- [ ] **Step 5: Print the sample numbers**

Run: `.venv/bin/python -m pytest -s tests/unit/test_sample.py`

Expected: one line like `slice 2.89 s, read 1.07 s, merge 0.22 s; 764 layers, 378247 points before merging, 306701 after`. The point counts must match exactly. The times can differ.

- [ ] **Step 6: Correct the point counts in the spec**

Approved spec section 6.3 says that the first reader test measures the counts and corrects them. In `docs/superpowers/specs/2026-10-15-slicer-animator-design.md`, replace this paragraph:

```
Tested on 2026-10-15 with Bambu Studio 2.08.02.61: `samples/sample.3mf` sliced in 2.4 seconds to 764 layers, 4 h 11 min of print time, and 386k strand points. The arc and merge settings of this count were not recorded. Section 16 gives a different count for the same part. The first G-code reader test measures the count again with the rules of sections 6.1 and 7, and corrects both numbers.
```

with:

```
Tested on 2026-10-15 with Bambu Studio 2.08.02.61: `samples/sample.3mf` sliced in 2.4 seconds to 764 layers and 4 h 11 min of print time. The G-code reader makes 378,247 strand points from it, with arcs split at 0.5 mm. Merging at 2° leaves 306,701 points.
```

Then replace the table row

```
| Read G-code | 0.55 s for 313k points (arc and merge settings not recorded, see section 6.3) |
```

with:

```
| Read G-code | 0.55 s for 313k points (throwaway probe reader) |
| Read G-code with the plugin reader | 1.1 s for 378,247 points. Merging at 2° takes 0.2 s and leaves 306,701 points. |
```

If your times from Step 5 differ by more than 50%, write your times.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_bambu_cli.py tests/unit/test_sample.py sliceranim/core/bambu_cli.py docs/superpowers/specs/2026-10-15-slicer-animator-design.md
git commit -m "Add headless slicing with Bambu Studio and correct the sample point counts"
```

### Task 7: Fallback slicer

Cut a mesh into 2 wall loops per outline (spec 6.4). The outer loop moves inward by w/2 and the inner loop by 1.5 × w, toward the material. Straight-line points from triangulated sides are removed before the offset, because an offset of such a point near a corner folds back over the corner.

**Files:**
- Create: `sliceranim/core/mesh_slicer.py`
- Test: `tests/unit/test_mesh_slicer.py`

**Interfaces:**
- Consumes: `pack`, `FEATURE_CODE` (Task 2), the errors (Task 1).
- Produces:
  - `read_stl(path) -> (vertices (V,3), triangles (T,3))` for binary and ASCII STL.
  - `slice_mesh(vertices, triangles, *, layer_height=0.2, width=0.45, speed=100.0) -> (ToolpathSet, open_edges: bool)`. Units mm. The part is moved to z = 0. Meta: `slicer="Fallback slicer"`, `fallback=True`.
  - Helpers used by tests: `weld`, `has_open_edges`, `signed_area`, `cut_layer`, `orient`, `clean`, `offset`, `self_intersects`, `inner_loop_is_valid`.

Measured on the sample STL (3,340 triangles) on 2026-10-15: 765 layers and 161,373 points in 1.8 s. The mesh is closed.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_mesh_slicer.py`:

```python
import struct

import numpy as np
import pytest

from sliceranim.core.mesh_slicer import (
    clean,
    cut_layer,
    has_open_edges,
    offset,
    read_stl,
    self_intersects,
    signed_area,
    slice_mesh,
)
from sliceranim.core.toolpaths import FEATURE_CODE


def box(x0, x1, y0, y1, z0, z1):
    """A closed box: 8 vertices, 12 triangles with outward normals."""
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=np.float64)
    t = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v, t


def walls(polygon, height):
    """Side walls only of a prism over `polygon` (no caps). The mesh is open at top and bottom."""
    n = len(polygon)
    bottom = [(x, y, 0.0) for x, y in polygon]
    top = [(x, y, height) for x, y in polygon]
    v = np.array(bottom + top, dtype=np.float64)
    t = []
    for i in range(n):
        j = (i + 1) % n
        t += [[i, j, n + j], [i, n + j, n + i]]
    return v, np.array(t)


def square(cx, cy, side):
    h = side / 2
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]


def test_cube_gives_two_loops_per_layer_at_the_right_offsets():
    v, t = box(0, 10, 0, 10, 5, 15)  # z starts at 5 to check the shift to the plate
    tp, open_edges = slice_mesh(v, t)
    assert not open_edges
    assert tp.layer_count == 50
    np.testing.assert_allclose(tp.layer_z[[0, -1]], [0.2, 10.0], atol=1e-5)
    first = tp.position[tp.layer == 0]
    inner = first[tp.feature[tp.layer == 0] == FEATURE_CODE["inner_wall"]]
    outer = first[tp.feature[tp.layer == 0] == FEATURE_CODE["outer_wall"]]
    np.testing.assert_allclose(inner[:, :2].min(axis=0), [0.675, 0.675], atol=1e-4)
    np.testing.assert_allclose(outer[:, :2].min(axis=0), [0.225, 0.225], atol=1e-4)
    np.testing.assert_allclose(outer[:, :2].max(axis=0), [9.775, 9.775], atol=1e-4)
    # Inner loop first, then outer loop. Each loop is closed: 4 corners + the first corner again.
    assert tp.run_start[:2].tolist() == [0, 5]
    assert tp.feature[:5].tolist() == [FEATURE_CODE["inner_wall"]] * 5
    np.testing.assert_allclose(tp.position[0], tp.position[4])


def test_print_time_comes_from_100_mm_per_second():
    v, t = box(0, 10, 0, 10, 0, 0.4)
    tp, _ = slice_mesh(v, t)
    loop_lengths = 4 * (10 - 2 * 0.675) + 4 * (10 - 2 * 0.225)
    assert tp.time[tp.layer_start[1] - 1] == pytest.approx(loop_lengths / 100.0, rel=1e-6)


def test_thin_wall_drops_the_inner_loop():
    v, t = box(0, 1.0, 0, 10, 0, 1)  # 1.0 mm is thinner than 3 strand widths (1.35 mm)
    tp, _ = slice_mesh(v, t)
    assert set(tp.feature.tolist()) == {FEATURE_CODE["outer_wall"]}


def test_hole_gets_its_loops_on_the_material_side():
    outer_v, outer_t = walls(square(0, 0, 20), 1.0)
    hole_v, hole_t = walls(square(0, 0, 6)[::-1], 1.0)
    v = np.vstack([outer_v, hole_v])
    t = np.vstack([outer_t, hole_t + len(outer_v)])
    tp, open_edges = slice_mesh(v, t)
    assert open_edges  # no caps
    layer0 = tp.position[tp.layer == 0][:, :2]
    radius = np.abs(layer0.astype(np.float64)).max(axis=1)  # distance from the center in the square metric
    # Hole loops sit outside the 3 mm hole edge, outer loops inside the 10 mm outer edge.
    assert sorted(set(np.round(radius, 3).tolist())) == [3.225, 3.675, 9.325, 9.775]


def test_cut_layer_returns_one_closed_outline_for_a_box():
    v, t = box(0, 10, 0, 10, 0, 10)
    loops = cut_layer(v, t, 5.0)
    assert len(loops) == 1
    assert abs(signed_area(loops[0])) == pytest.approx(100.0)


def test_cut_exactly_at_a_vertex_height_still_works():
    v, t = box(0, 10, 0, 10, 0, 10)
    assert len(cut_layer(v, t, 10.0 - 1e-12)) <= 1
    assert len(cut_layer(v, t, 0.0)) == 1


def test_clean_removes_repeated_and_straight_points():
    loop = np.array([(0, 0), (0, 0), (5, 0), (10, 0), (10, 10), (0, 10)], dtype=np.float64)
    np.testing.assert_allclose(clean(loop), [(0, 0), (10, 0), (10, 10), (0, 10)])


def test_offset_moves_a_counterclockwise_square_inward():
    sq = np.array(square(0, 0, 10), dtype=np.float64)
    moved = offset(sq, 1.0)
    np.testing.assert_allclose(np.abs(moved), 4.0)


def test_self_intersects_finds_a_bow_tie():
    bow_tie = np.array([(0, 0), (2, 2), (2, 0), (0, 2)], dtype=np.float64)
    assert self_intersects(bow_tie)
    assert not self_intersects(np.array(square(0, 0, 2), dtype=np.float64))


def test_has_open_edges():
    v, t = box(0, 1, 0, 1, 0, 1)
    assert not has_open_edges(t)
    assert has_open_edges(t[:-1])


def test_read_binary_and_ascii_stl(tmp_path):
    v, t = box(0, 10, 0, 10, 0, 10)
    binary = tmp_path / "cube.stl"
    with open(binary, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(t)))
        for tri in t:
            f.write(struct.pack("<3f", 0, 0, 0))
            for corner in tri:
                f.write(struct.pack("<3f", *v[corner]))
            f.write(b"\0\0")
    ascii_path = tmp_path / "cube_ascii.stl"
    lines = ["solid cube"]
    for tri in t:
        lines += ["facet normal 0 0 0", "outer loop"] + [f"vertex {x} {y} {z}" for x, y, z in v[tri]] + ["endloop", "endfacet"]
    ascii_path.write_text("\n".join(lines + ["endsolid cube"]))
    for path in (binary, ascii_path):
        vertices, triangles = read_stl(path)
        assert triangles.shape == (12, 3)
        np.testing.assert_allclose(vertices[triangles[0]], v[t[0]])
        tp, open_edges = slice_mesh(vertices, triangles)
        assert not open_edges
        assert tp.layer_count == 50
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.mesh_slicer'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/mesh_slicer.py`:

```python
"""Fallback slicer: cut a triangle mesh into 2 wall loops per outline (spec section 6.4).

Units are millimeters. The output sits on z = 0, like a part on the plate.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np

from .errors import NO_EXTRUSION, SlicerAnimError
from .toolpaths import FEATURE_CODE, ToolpathSet, pack

LAYER_HEIGHT = 0.2
WIDTH = 0.45
SPEED = 100.0  # mm/s
MITER_LIMIT = 4.0
_OUTER = FEATURE_CODE["outer_wall"]
_INNER = FEATURE_CODE["inner_wall"]


def read_stl(path) -> tuple[np.ndarray, np.ndarray]:
    """Read a binary or ASCII STL file. Return (vertices (V, 3), triangles (T, 3))."""
    data = Path(path).read_bytes()
    if len(data) >= 84:
        (count,) = struct.unpack_from("<I", data, 80)
        if len(data) == 84 + 50 * count:
            records = np.frombuffer(data, dtype=np.uint8, count=50 * count, offset=84).reshape(count, 50)
            corners = records[:, 12:48].copy().view("<f4").reshape(count * 3, 3)
            return corners.astype(np.float64), np.arange(count * 3).reshape(count, 3)
    text = data.decode("utf-8", errors="replace")
    corners = [[float(v) for v in line.split()[1:4]] for line in text.splitlines() if line.strip().startswith("vertex")]
    vertices = np.array(corners, dtype=np.float64).reshape(-1, 3)
    return vertices, np.arange(len(vertices)).reshape(-1, 3)


def weld(vertices: np.ndarray, triangles: np.ndarray, tolerance: float = 1e-5):
    """Merge vertices closer than `tolerance` and drop triangles with a repeated vertex."""
    keys = np.round(np.asarray(vertices, dtype=np.float64) / tolerance).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    welded = unique.astype(np.float64) * tolerance
    tris = inverse.reshape(-1)[np.asarray(triangles)]
    good = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    return welded, tris[good]


def has_open_edges(triangles: np.ndarray) -> bool:
    """True when an edge does not belong to exactly two triangles."""
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.any(counts != 2))


def signed_area(loop: np.ndarray) -> float:
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def point_in_polygon(point, loop: np.ndarray) -> bool:
    x, y = point
    x0, y0 = loop[:, 0], loop[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    crosses = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    return bool(np.count_nonzero(crosses & (x < x_at)) % 2)


def cut_layer(vertices: np.ndarray, triangles: np.ndarray, z: float) -> list[np.ndarray]:
    """Cut the mesh at height z. Return the closed outlines as (M, 2) arrays. Open chains are dropped."""
    vz = vertices[:, 2]
    if np.any(vz == z):
        z += 1e-7
    tz = vz[triangles]
    above = tz > z
    count = above.sum(axis=1)
    tris = triangles[(count == 1) | (count == 2)]
    above = above[(count == 1) | (count == 2)]
    if len(tris) == 0:
        return []
    corner_pairs = ((0, 1), (1, 2), (2, 0))
    keys_per_tri = []
    for a, b in corner_pairs:
        keys_per_tri.append(np.where(above[:, a] != above[:, b], np.minimum(tris[:, a], tris[:, b]) * len(vertices) + np.maximum(tris[:, a], tris[:, b]), -1))
    keys_per_tri = np.stack(keys_per_tri, axis=1)
    segments = np.sort(keys_per_tri, axis=1)[:, 1:]  # the two crossed edges; -1 sorts first
    point_of: dict[int, tuple[float, float]] = {}
    for key in np.unique(segments):
        i, j = divmod(int(key), len(vertices))
        vi, vj = vertices[i], vertices[j]
        t = (z - vi[2]) / (vj[2] - vi[2])
        point_of[int(key)] = (vi[0] + t * (vj[0] - vi[0]), vi[1] + t * (vj[1] - vi[1]))
    by_key: dict[int, list[int]] = {}
    for s, (k1, k2) in enumerate(segments.tolist()):
        by_key.setdefault(k1, []).append(s)
        by_key.setdefault(k2, []).append(s)
    used = np.zeros(len(segments), dtype=bool)
    loops = []
    for first in range(len(segments)):
        if used[first]:
            continue
        used[first] = True
        start_key, key = segments[first].tolist()
        chain = [start_key, key]
        closed = False
        while True:
            following = [s for s in by_key.get(key, []) if not used[s]]
            if not following:
                break
            s = following[0]
            used[s] = True
            k1, k2 = segments[s].tolist()
            key = k2 if k1 == key else k1
            if key == start_key:
                closed = True
                break
            chain.append(key)
        if closed and len(chain) >= 3:
            loops.append(np.array([point_of[k] for k in chain], dtype=np.float64))
    return loops


def orient(loops: list[np.ndarray]) -> list[np.ndarray]:
    """Turn outer outlines counterclockwise and holes clockwise, so the material is on the left."""
    out = []
    for i, loop in enumerate(loops):
        depth = sum(point_in_polygon(loop[0], other) for j, other in enumerate(loops) if j != i)
        is_hole = depth % 2 == 1
        area = signed_area(loop)
        if (area > 0) == is_hole:
            loop = loop[::-1]
        out.append(loop)
    return out


def clean(loop: np.ndarray, tolerance: float = 1e-6) -> np.ndarray:
    """Remove repeated points and points on a straight line between their neighbors.

    A triangulated mesh puts cut points in the middle of straight sides. Without
    this step, the offset of such a point near a corner folds back over the corner.
    """
    step = np.linalg.norm(loop - np.roll(loop, 1, axis=0), axis=1)
    loop = loop[step > tolerance]
    if len(loop) < 3:
        return loop
    before = loop - np.roll(loop, 1, axis=0)
    after = np.roll(loop, -1, axis=0) - loop
    cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
    dot = np.sum(before * after, axis=1)
    lengths = np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1)
    straight = (np.abs(cross) <= 1e-9 * lengths) & (dot > 0)
    return loop[~straight]


def offset(loop: np.ndarray, distance: float) -> np.ndarray:
    """Move each point of a loop to the left of the path by `distance` (miter join, limited)."""
    before = loop - np.roll(loop, 1, axis=0)
    after = np.roll(loop, -1, axis=0) - loop
    before /= np.linalg.norm(before, axis=1, keepdims=True)
    after /= np.linalg.norm(after, axis=1, keepdims=True)
    n_before = np.column_stack([-before[:, 1], before[:, 0]])
    n_after = np.column_stack([-after[:, 1], after[:, 0]])
    miter = n_before + n_after
    length = np.linalg.norm(miter, axis=1, keepdims=True)
    miter = np.where(length > 1e-9, miter / np.maximum(length, 1e-12), n_before)
    cos_half = np.sum(miter * n_before, axis=1, keepdims=True)
    scale = distance / np.maximum(cos_half, 1.0 / MITER_LIMIT)
    return loop + miter * scale


def _segments_cross(p, q, a, b) -> np.ndarray:
    def cross(o, u, v):
        return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])

    d1 = cross(p, q, a)
    d2 = cross(p, q, b)
    d3 = cross(a, b, p)
    d4 = cross(a, b, q)
    return (d1 * d2 < 0) & (d3 * d4 < 0)


def self_intersects(loop: np.ndarray) -> bool:
    """True when two edges of the closed loop cross each other."""
    n = len(loop)
    if n < 4:
        return False
    p = loop
    q = np.roll(loop, -1, axis=0)
    xmin = np.minimum(p[:, 0], q[:, 0])
    xmax = np.maximum(p[:, 0], q[:, 0])
    order = np.argsort(xmin, kind="stable")
    sorted_xmin = xmin[order]
    for position, i in enumerate(order):
        stop = np.searchsorted(sorted_xmin, xmax[i], side="right")
        others = order[position + 1 : stop]
        others = others[(others != (i + 1) % n) & (others != (i - 1) % n)]
        if others.size and np.any(_segments_cross(p[i], q[i], p[others], q[others])):
            return True
    return False


def inner_loop_is_valid(inner: np.ndarray, outline: np.ndarray) -> bool:
    """Spec 6.4 step 4: drop the inner loop if it crosses itself or its area falls to 0 or below."""
    sign = 1.0 if signed_area(outline) > 0 else -1.0
    if sign * signed_area(inner) <= 1e-9:
        return False
    return not self_intersects(inner)


def slice_mesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    layer_height: float = LAYER_HEIGHT,
    width: float = WIDTH,
    speed: float = SPEED,
) -> tuple[ToolpathSet, bool]:
    """Slice a mesh in mm. Return the toolpaths and True when the mesh has open edges."""
    verts, tris = weld(vertices, triangles)
    if len(tris) == 0:
        raise SlicerAnimError(NO_EXTRUSION)
    open_edges = has_open_edges(tris)
    verts = verts.copy()
    verts[:, 2] -= verts[:, 2].min()
    top = verts[:, 2].max()
    layer_count = int(math.ceil(top / layer_height - 0.5))
    xyz, layer, feature, time, run_start, layer_z = [], [], [], [], [], {}
    clock = 0.0

    def add_run(loop: np.ndarray, z: float, k: int, code: int):
        nonlocal clock
        closed = np.vstack([loop, loop[:1]])
        run_start.append(len(xyz))
        steps = np.r_[0.0, np.linalg.norm(np.diff(closed, axis=0), axis=1)]
        times = clock + np.cumsum(steps) / speed
        clock = float(times[-1])
        for (x, y), t in zip(closed, times):
            xyz.append((x, y, z))
            layer.append(k)
            feature.append(code)
            time.append(t)

    for k in range(layer_count):
        z_top = (k + 1) * layer_height
        outlines = [clean(loop) for loop in cut_layer(verts, tris, (k + 0.5) * layer_height)]
        outlines = orient([loop for loop in outlines if len(loop) >= 3])
        for outline in outlines:
            inner = offset(outline, 1.5 * width)
            if inner_loop_is_valid(inner, outline):
                add_run(inner, z_top, k, _INNER)
            add_run(offset(outline, 0.5 * width), z_top, k, _OUTER)
        layer_z[k] = z_top
    if not xyz:
        raise SlicerAnimError(NO_EXTRUSION)
    n = len(xyz)
    tp = pack(
        position=xyz,
        layer=layer,
        feature=feature,
        tool=np.zeros(n),
        width=np.full(n, width),
        height=np.full(n, layer_height),
        time=time,
        object_id=np.zeros(n),
        run_start=run_start,
        layer_z_by_number=layer_z,
        meta={"slicer": "Fallback slicer", "slicer_version": "", "filament_colors": [], "filament_type": "", "fallback": True},
    )
    return tp, open_edges
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `52 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_mesh_slicer.py sliceranim/core/mesh_slicer.py
git commit -m "Add the fallback slicer with 2 wall loops"
```

### Task 8: Timing and the shot list

Turn the shot list into one Progress value, one current layer, and one print head position per frame (spec section 8). Progress = k + f means points 0 to k − 1 are printed and the strand into point k is a fraction f long.

**Files:**
- Create: `sliceranim/core/timing.py`
- Test: `tests/unit/test_timing.py`

**Interfaces:**
- Consumes: `ToolpathSet`, `ToolpathBuilder` (Task 2).
- Produces:
  - Constants `LINE, LAYER, HOLD`, `TURNTABLE, HERO, RISING, CLOSE_UP, REVEAL, CUSTOM`, `SHORT_PRINT_LAYERS = 20`.
  - `Shot(start_layer: int | None, duration: float, style: str, camera: str)`; `None` means End. Layer numbers count from 1, as in the panel.
  - `ShotProblem(row, rule, message)`; `default_shots(layer_count) -> list[Shot]`; `validate_shots(shots, layer_count) -> list[ShotProblem]`; `shot_frame_counts(shots, fps) -> list[int]`.
  - `FramePlan(progress, current_layer, head, shot_index, shot_first_frame, shot_frame_count)` with `frame_count`. Frames count from 1. `head` is in mm.
  - `progress_at_time(tp, t) -> np.ndarray`, `state_at(tp, progress) -> (current_layer, head)`, `plan_frames(tp, shots, fps) -> FramePlan`.

Frame rule: in a shot of F frames, frame i uses s = i / F, so the next shot starts where this one stops. The last shot uses s = (i + 1) / F, so the video ends with the whole print.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_timing.py`:

```python
import numpy as np
import pytest

from sliceranim.core.timing import (
    CLOSE_UP,
    HOLD,
    LAYER,
    LINE,
    REVEAL,
    RISING,
    TURNTABLE,
    Shot,
    default_shots,
    plan_frames,
    progress_at_time,
    state_at,
    validate_shots,
)
from sliceranim.core.toolpaths import ToolpathBuilder


def ladder(layers=10, points_per_layer=5, seconds_per_strand=1.0):
    """One straight run per layer along X. Each strand takes `seconds_per_strand`."""
    b = ToolpathBuilder()
    t = 0.0
    for k in range(layers):
        b.end_run()
        for i in range(points_per_layer):
            if i:
                t += seconds_per_strand
            b.add_point(float(i), 0.0, 0.2 * (k + 1), time=t, layer=k, feature=1, tool=0, width=0.45,
                        height=0.2, object_id=0)
    return b.build()


def test_default_shot_list_for_the_sample_layer_count():
    shots = default_shots(764)
    assert [(s.start_layer, s.duration, s.style, s.camera) for s in shots] == [
        (1, 4.0, LINE, CLOSE_UP),
        (6, 12.0, LAYER, TURNTABLE),
        (760, 4.0, LINE, RISING),
        (None, 4.0, HOLD, REVEAL),
    ]
    assert validate_shots(shots, 764) == []


@pytest.mark.parametrize("layers", [1, 5, 10, 11, 19])
def test_short_prints_get_the_two_shot_list_and_it_is_valid(layers):
    shots = default_shots(layers)
    assert [(s.start_layer, s.duration, s.style, s.camera) for s in shots] == [
        (1, 20.0, LINE, TURNTABLE),
        (None, 4.0, HOLD, REVEAL),
    ]
    assert validate_shots(shots, layers) == []


def test_twenty_layers_get_the_four_shot_list_and_it_is_valid():
    assert len(default_shots(20)) == 4
    assert validate_shots(default_shots(20), 20) == []


def test_each_rule_reports_its_row():
    rules = lambda shots: [(p.row, p.rule) for p in validate_shots(shots, 100)]
    assert rules([Shot(2, 1, LINE, "HERO")]) == [(0, 1)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(50, 1, LINE, "HERO"), Shot(40, 1, LINE, "HERO")]) == [(2, 2)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(1, 1, LINE, "HERO")]) == [(0, 3)]
    assert rules([Shot(1, 1, HOLD, "HERO"), Shot(1, 1, LINE, "HERO")]) == []
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(None, 1, LINE, "HERO")]) == [(1, 4)]
    assert rules([Shot(1, 0, LINE, "HERO")]) == [(0, 5)]
    assert rules([Shot(1, 1, LINE, "HERO"), Shot(101, 1, LINE, "HERO")]) == [(1, 0)]
    assert rules([]) == [(-1, 0)]


def test_progress_at_time_follows_the_point_times():
    tp = ladder(layers=1, points_per_layer=3)  # times 0, 1, 2
    np.testing.assert_allclose(progress_at_time(tp, [0.0, 0.5, 1.0, 1.25, 2.0, 9.0]), [1, 1.5, 2, 2.25, 3, 3])


def test_state_at_gives_the_tip_of_the_growing_strand():
    tp = ladder(layers=2, points_per_layer=3)
    layer, head = state_at(tp, np.array([1.5, 3.0, 3.5, 6.0]))
    np.testing.assert_allclose(head[0], [0.5, 0, 0.2])  # half way from point 0 to point 1
    np.testing.assert_allclose(head[1], [2, 0, 0.2])  # point 2 is the newest
    np.testing.assert_allclose(head[2], [0, 0, 0.4])  # point 3 starts a run: no strand grows into it
    np.testing.assert_allclose(layer, [0, 0, 1, 1])


def test_frames_add_up_to_the_sum_of_durations():
    tp = ladder(layers=30)
    plan = plan_frames(tp, default_shots(30), fps=30)
    assert plan.frame_count == 24 * 30
    assert plan.shot_first_frame == [1, 121, 481, 601]
    assert plan.shot_frame_count == [120, 360, 120, 120]


def test_line_shot_runs_print_time_linearly_and_stops_before_the_next_shot():
    tp = ladder(layers=10, points_per_layer=5)  # 4 s per layer, 40 s in all
    plan = plan_frames(tp, [Shot(1, 2.0, LINE, "HERO"), Shot(3, 1.0, HOLD, "HERO")], fps=4)
    # Shot 1 covers layers 1 and 2: print time 0 to 8 s over 8 frames, 1 s per frame.
    # At 4 s, point 5 starts layer 2 at the same time as point 4 ends layer 1, so both count.
    np.testing.assert_allclose(plan.progress[:8], [1, 2, 3, 4, 6, 7, 8, 9])
    # Hold at layer 3 shows layers 1 and 2 complete: 10 points.
    np.testing.assert_allclose(plan.progress[8:], 10)


def test_layer_shot_shows_complete_layers_only():
    tp = ladder(layers=10, points_per_layer=5)
    plan = plan_frames(tp, [Shot(1, 1.0, LAYER, "HERO"), Shot(None, 1.0, HOLD, "HERO")], fps=5)
    # 10 layers over 5 frames: 0, 2, 4, 6, 8 layers complete.
    np.testing.assert_allclose(plan.progress[:5], [0, 10, 20, 30, 40])
    np.testing.assert_allclose(plan.progress[5:], 50)


def test_the_last_shot_ends_with_the_whole_print():
    tp = ladder(layers=10)
    for style in (LINE, LAYER):
        plan = plan_frames(tp, [Shot(1, 1.0, style, "HERO")], fps=10)
        assert plan.progress[-1] == tp.point_count


def test_a_line_shot_with_no_print_time_moves_by_point_count():
    tp = ladder(layers=4, points_per_layer=3, seconds_per_strand=0.0)
    plan = plan_frames(tp, [Shot(1, 1.0, LINE, "HERO")], fps=4)
    np.testing.assert_allclose(plan.progress, [3, 6, 9, 12])


def test_hold_mid_print_stays_at_its_start_layer():
    tp = ladder(layers=10, points_per_layer=5)
    shots = [Shot(1, 1.0, LINE, "HERO"), Shot(4, 1.0, HOLD, "HERO"), Shot(4, 1.0, LINE, "HERO")]
    plan = plan_frames(tp, shots, fps=2)
    np.testing.assert_allclose(plan.progress[2:4], 15)  # layers 1 to 3 complete
    assert plan.progress[-1] == tp.point_count
    np.testing.assert_allclose(plan.current_layer[2:4], 2)  # newest point is in layer index 2


def test_a_very_short_shot_still_gets_one_frame():
    tp = ladder(layers=10)
    plan = plan_frames(tp, [Shot(1, 0.01, LINE, "HERO"), Shot(None, 1.0, HOLD, "HERO")], fps=30)
    assert plan.shot_frame_count == [1, 30]
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.timing'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/timing.py`:

```python
"""Turn the shot list into per-frame values (spec section 8).

Progress is the count of printed points. Progress = k + f (0 <= f < 1) means
points 0 to k-1 are printed and the strand into point k is a fraction f long.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .toolpaths import ToolpathSet

LINE, LAYER, HOLD = "LINE", "LAYER", "HOLD"
TURNTABLE, HERO, RISING, CLOSE_UP, REVEAL, CUSTOM = "TURNTABLE", "HERO", "RISING", "CLOSE_UP", "REVEAL", "CUSTOM"
SHORT_PRINT_LAYERS = 20


@dataclass
class Shot:
    start_layer: int | None  # layer number as the panel shows it (from 1), or None for End
    duration: float  # seconds
    style: str  # LINE, LAYER, or HOLD
    camera: str  # TURNTABLE, HERO, RISING, CLOSE_UP, REVEAL, or CUSTOM


@dataclass(frozen=True)
class ShotProblem:
    row: int  # shot index from 0, or -1 for the whole list
    rule: int  # rule number from spec 8.3, or 0 for a value out of range
    message: str


@dataclass
class FramePlan:
    progress: np.ndarray  # float64 (F,)
    current_layer: np.ndarray  # float64 (F,), layer index from 0
    head: np.ndarray  # float64 (F, 3), mm
    shot_index: np.ndarray  # int32 (F,)
    shot_first_frame: list[int] = field(default_factory=list)  # scene frame of each shot start, from 1
    shot_frame_count: list[int] = field(default_factory=list)

    @property
    def frame_count(self) -> int:
        return int(len(self.progress))


def default_shots(layer_count: int) -> list[Shot]:
    """The shot list that the importer makes (spec 8.4)."""
    if layer_count < SHORT_PRINT_LAYERS:
        return [Shot(1, 20.0, LINE, TURNTABLE), Shot(None, 4.0, HOLD, REVEAL)]
    return [
        Shot(1, 4.0, LINE, CLOSE_UP),
        Shot(6, 12.0, LAYER, TURNTABLE),
        Shot(layer_count - 4, 4.0, LINE, RISING),
        Shot(None, 4.0, HOLD, REVEAL),
    ]


def _start_index(shot: Shot, layer_count: int) -> int:
    """Layer index where the shot starts. layer_count stands for End."""
    return layer_count if shot.start_layer is None else shot.start_layer - 1


def validate_shots(shots: list[Shot], layer_count: int) -> list[ShotProblem]:
    """Check the rules of spec 8.3. Return one problem per failed rule and row."""
    if not shots:
        return [ShotProblem(-1, 0, "Add at least one shot.")]
    problems = []
    for row, shot in enumerate(shots):
        if shot.start_layer is not None and not 1 <= shot.start_layer <= layer_count:
            problems.append(ShotProblem(row, 0, f"Start layer must be 1 to {layer_count}, or End."))
        if row == 0 and shot.start_layer != 1:
            problems.append(ShotProblem(row, 1, "The first shot must start at layer 1."))
        if shot.start_layer is None and shot.style != HOLD:
            problems.append(ShotProblem(row, 4, "Only a Hold shot can start at End."))
        if not shot.duration > 0:
            problems.append(ShotProblem(row, 5, "Duration must be more than 0 seconds."))
        if row + 1 < len(shots):
            here = _start_index(shot, layer_count)
            there = _start_index(shots[row + 1], layer_count)
            if there < here:
                problems.append(ShotProblem(row + 1, 2, "Start layers must not go down from one shot to the next."))
            elif there == here and shot.style != HOLD:
                problems.append(ShotProblem(row, 3, "Only a Hold shot can have the same start layer as the next shot."))
    return problems


def shot_frame_counts(shots: list[Shot], fps: int) -> list[int]:
    return [max(1, int(round(shot.duration * fps))) for shot in shots]


def progress_at_time(tp: ToolpathSet, t) -> np.ndarray:
    """Progress at print time t (seconds)."""
    t = np.atleast_1d(np.asarray(t, dtype=np.float64))
    time = tp.time
    n = tp.point_count
    j = np.searchsorted(time, t, side="right")
    progress = j.astype(np.float64)
    inside = (j > 0) & (j < n)
    jj = j[inside]
    span = time[jj] - time[jj - 1]
    progress[inside] += np.where(span > 0, (t[inside] - time[jj - 1]) / np.where(span > 0, span, 1.0), 0.0)
    return progress


def state_at(tp: ToolpathSet, progress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Current layer and print head position (mm) for each Progress value.

    The current layer is the layer of the newest point. The head sits at the tip of the growing strand.
    """
    n = tp.point_count
    progress = np.asarray(progress, dtype=np.float64)
    k = np.floor(progress).astype(np.int64)
    f = progress - k
    newest = np.clip(np.where(f > 0, k, k - 1), 0, n - 1)
    current_layer = tp.layer[newest].astype(np.float64)
    position = tp.position.astype(np.float64)
    head = position[newest].copy()
    starts = tp.run_start_mask()
    growing = (f > 0) & (k >= 1) & (k < n)
    growing[growing] &= ~starts[k[growing]]
    kk = k[growing]
    head[growing] = position[kk - 1] + f[growing, None] * (position[kk] - position[kk - 1])
    return current_layer, head


def plan_frames(tp: ToolpathSet, shots: list[Shot], fps: int) -> FramePlan:
    """Compute Progress, current layer, and print head for every frame. The shots must be valid."""
    layers = tp.layer_count
    progress_of_layer = np.append(tp.layer_start, tp.point_count).astype(np.float64)
    time_of_layer = np.append(tp.time[tp.layer_start], tp.total_time)
    counts = shot_frame_counts(shots, fps)
    parts, index_parts, first_frames = [], [], []
    frame = 1
    for row, (shot, count) in enumerate(zip(shots, counts)):
        last = row == len(shots) - 1
        a = _start_index(shot, layers)
        b = layers if last else _start_index(shots[row + 1], layers)
        i = np.arange(count, dtype=np.float64)
        s = (i + 1) / count if last else i / count
        if shot.style == HOLD:
            p = np.full(count, progress_of_layer[a])
        elif shot.style == LAYER:
            done = np.floor(s * (b - a) + 1e-9).astype(np.int64)
            p = progress_of_layer[a + done]
        else:
            t0, t1 = time_of_layer[a], time_of_layer[b]
            if t1 > t0:
                p = progress_at_time(tp, t0 + s * (t1 - t0))
            else:
                p = progress_of_layer[a] + s * (progress_of_layer[b] - progress_of_layer[a])
            p = np.clip(p, progress_of_layer[a], progress_of_layer[b])
        parts.append(p)
        index_parts.append(np.full(count, row, dtype=np.int32))
        first_frames.append(frame)
        frame += count
    progress = np.concatenate(parts)
    current_layer, head = state_at(tp, progress)
    return FramePlan(
        progress=progress,
        current_layer=current_layer,
        head=head,
        shot_index=np.concatenate(index_parts),
        shot_first_frame=first_frames,
        shot_frame_count=counts,
    )
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `69 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_timing.py sliceranim/core/timing.py
git commit -m "Add timing and shot list rules"
```

### Task 9: Camera paths

Compute the camera location and aim point for every frame of each preset (spec section 9). This is pure math, so it lives in `core/` and runs in pytest. The Blender part in Task 13 only turns these arrays into keyframes.

**Files:**
- Create: `sliceranim/core/camera_paths.py`
- Test: `tests/unit/test_camera_paths.py`

**Interfaces:**
- Consumes: Nothing from earlier tasks.
- Produces:
  - `MARGIN = 1.15`, `START_AZIMUTH` (three-quarter view, −55°), `Bounds(center, radius)`, `CameraPath(location, target)`.
  - `part_bounds(position) -> Bounds`, `field_of_view(lens_mm, sensor_mm, width_px, height_px) -> (h, v)`, `framing_distance(radius, fov, margin=1.15) -> float`, `orbit_point(center, distance, azimuth, elevation)`.
  - `turntable(bounds, distance, frames, *, turns=1.0, height_angle=25°, clockwise=False)`, `hero(bounds, distance, frames, *, height_angle=30°, side_angle=35°)`, `rising_follow(bounds, distance, head_z, *, height_angle=20°)`, `moving_average(points, window)`, `close_up(targets, *, distance=30.0, smoothing=15, height_angle=30°, side_angle=35°)`, `final_reveal(bounds, distance, frames, previous, *, spin=90°, pullback_share=0.4)`. All return `CameraPath` in mm.

The spec gives no height or side angle for the close-up. This plan uses the Hero angles (30° and 35°).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_camera_paths.py`:

```python
import math

import numpy as np
import pytest

from sliceranim.core.camera_paths import (
    START_AZIMUTH,
    Bounds,
    close_up,
    field_of_view,
    final_reveal,
    framing_distance,
    hero,
    moving_average,
    part_bounds,
    rising_follow,
    turntable,
)

BOUNDS = Bounds(center=np.array([0.0, 0.0, 50.0]), radius=50.0)


def test_part_bounds_uses_the_bounding_box():
    b = part_bounds(np.array([[0, 0, 0], [30, 40, 0]], dtype=np.float32))
    np.testing.assert_allclose(b.center, [15, 20, 0])
    assert b.radius == pytest.approx(25.0)


def test_field_of_view_for_16_9_and_square():
    h, v = field_of_view(50, 36, 1920, 1080)
    assert math.degrees(h) == pytest.approx(39.598, abs=1e-3)
    assert math.degrees(v) == pytest.approx(22.895, abs=1e-3)
    h, v = field_of_view(50, 36, 1080, 1080)
    assert h == pytest.approx(v)


def test_framing_distance_formula():
    assert framing_distance(10.0, math.radians(60)) == pytest.approx(10 / 0.5 * 1.15)


def test_turntable_makes_one_turn_without_repeating_the_first_frame():
    path = turntable(BOUNDS, 300.0, 4)
    offsets = path.location - BOUNDS.center
    np.testing.assert_allclose(np.linalg.norm(offsets, axis=1), 300.0)
    azimuth = np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0]))
    np.testing.assert_allclose(np.diff(azimuth), math.pi / 2)  # counterclockwise, a quarter turn per frame
    np.testing.assert_allclose(path.target, np.tile(BOUNDS.center, (4, 1)))
    elevation = np.degrees(np.arcsin(offsets[:, 2] / 300.0))
    np.testing.assert_allclose(elevation, 25.0)


def test_clockwise_turntable_turns_the_other_way():
    offsets = turntable(BOUNDS, 300.0, 4, clockwise=True).location - BOUNDS.center
    assert np.diff(np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0])))[0] < 0


def test_hero_is_static_at_a_three_quarter_view():
    path = hero(BOUNDS, 300.0, 3)
    assert np.ptp(path.location, axis=0).max() == 0
    offset = path.location[0] - BOUNDS.center
    assert math.degrees(math.atan2(offset[1], offset[0])) == pytest.approx(-55.0)


def test_rising_follow_aims_at_the_head_height():
    head_z = np.array([1.0, 2.0, 3.0])
    path = rising_follow(BOUNDS, 300.0, head_z)
    np.testing.assert_allclose(path.target[:, 2], head_z)
    np.testing.assert_allclose(np.diff(path.location[:, 2]), 1.0)


def test_moving_average_is_centered_and_shrinks_at_the_ends():
    points = np.array([[0, 0, 0], [3, 0, 0], [6, 0, 0], [9, 0, 0]], dtype=np.float64)
    np.testing.assert_allclose(moving_average(points, 3)[:, 0], [1.5, 3, 6, 7.5])


def test_close_up_keeps_30_mm_from_the_smoothed_target():
    targets = np.array([[0, 0, 0], [10, 0, 0], [0, 0, 0], [10, 0, 0]], dtype=np.float64)
    path = close_up(targets, smoothing=15)
    np.testing.assert_allclose(np.linalg.norm(path.location - path.target, axis=1), 30.0)
    assert np.ptp(path.target[:, 0]) < 10.0


def test_final_reveal_pulls_back_then_spins_90_degrees():
    previous = (np.array([0.0, -40.0, 60.0]), np.array([0.0, 0.0, 60.0]))
    path = final_reveal(BOUNDS, 300.0, 10, previous)
    np.testing.assert_allclose(path.location[0], previous[0])  # starts at the previous framing
    np.testing.assert_allclose(path.target[0], previous[1])
    offsets = path.location[4:] - BOUNDS.center  # 40% of 10 frames = 4 pull-back frames
    np.testing.assert_allclose(np.linalg.norm(offsets, axis=1), 300.0)
    azimuth = np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0]))
    assert math.degrees(azimuth[-1] - azimuth[0]) == pytest.approx(90.0)
    np.testing.assert_allclose(path.target[4:], np.tile(BOUNDS.center, (6, 1)))


def test_final_reveal_as_first_shot_starts_at_the_framing_distance():
    path = final_reveal(BOUNDS, 300.0, 5, None)
    np.testing.assert_allclose(np.linalg.norm(path.location - BOUNDS.center, axis=1), 300.0)
    offset = path.location[0] - BOUNDS.center
    assert math.atan2(offset[1], offset[0]) == pytest.approx(START_AZIMUTH)
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.core.camera_paths'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/core/camera_paths.py`:

```python
"""Camera location and aim point for every frame of a shot (spec section 9).

Units are mm and radians. Azimuth 0 points along +X. The front of the plate is -Y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MARGIN = 1.15
START_AZIMUTH = -math.pi / 2 + math.radians(35)  # three-quarter view from the front right


@dataclass(frozen=True)
class Bounds:
    center: np.ndarray  # (3,)
    radius: float  # radius of the bounding sphere of the bounding box


@dataclass
class CameraPath:
    location: np.ndarray  # (F, 3)
    target: np.ndarray  # (F, 3)


def part_bounds(position: np.ndarray) -> Bounds:
    low = position.min(axis=0).astype(np.float64)
    high = position.max(axis=0).astype(np.float64)
    return Bounds(center=(low + high) / 2, radius=max(float(np.linalg.norm(high - low)) / 2, 1e-3))


def field_of_view(lens_mm: float, sensor_mm: float, width_px: int, height_px: int) -> tuple[float, float]:
    """Horizontal and vertical field of view of a Blender camera with sensor fit Auto."""
    half_long = math.atan(sensor_mm / 2 / lens_mm)
    if width_px >= height_px:
        horizontal = 2 * half_long
        vertical = 2 * math.atan(math.tan(half_long) * height_px / width_px)
    else:
        vertical = 2 * half_long
        horizontal = 2 * math.atan(math.tan(half_long) * width_px / height_px)
    return horizontal, vertical


def framing_distance(radius: float, fov: float, margin: float = MARGIN) -> float:
    """Distance at which the bounding sphere fits the smaller field of view, times the margin."""
    return radius / math.sin(fov / 2) * margin


def orbit_point(center, distance, azimuth, elevation) -> np.ndarray:
    """Points at `distance` from center. Azimuth and elevation can be arrays."""
    azimuth = np.asarray(azimuth, dtype=np.float64)
    elevation = np.asarray(elevation, dtype=np.float64)
    direction = np.stack(
        [np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth), np.sin(elevation)], axis=-1
    )
    return np.asarray(center, dtype=np.float64) + np.asarray(distance, dtype=np.float64)[..., None] * direction


def _fixed(center, count) -> np.ndarray:
    return np.tile(np.asarray(center, dtype=np.float64), (count, 1))


def turntable(bounds: Bounds, distance: float, frames: int, *, turns=1.0, height_angle=math.radians(25), clockwise=False) -> CameraPath:
    s = np.arange(frames) / frames
    azimuth = START_AZIMUTH + (-1 if clockwise else 1) * 2 * math.pi * turns * s
    location = orbit_point(bounds.center, np.full(frames, distance), azimuth, np.full(frames, height_angle))
    return CameraPath(location, _fixed(bounds.center, frames))


def hero(bounds: Bounds, distance: float, frames: int, *, height_angle=math.radians(30), side_angle=math.radians(35)) -> CameraPath:
    azimuth = -math.pi / 2 + side_angle
    location = orbit_point(bounds.center, np.full(frames, distance), np.full(frames, azimuth), np.full(frames, height_angle))
    return CameraPath(location, _fixed(bounds.center, frames))


def rising_follow(bounds: Bounds, distance: float, head_z: np.ndarray, *, height_angle=math.radians(20)) -> CameraPath:
    frames = len(head_z)
    target = _fixed(bounds.center, frames)
    target[:, 2] = head_z
    location = orbit_point(target, np.full(frames, distance), np.full(frames, START_AZIMUTH), np.full(frames, height_angle))
    return CameraPath(location, target)


def moving_average(points: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average. Near the ends, the window gets smaller."""
    points = np.asarray(points, dtype=np.float64)
    if window <= 1 or len(points) < 2:
        return points.copy()
    half = window // 2
    padded = np.vstack([np.zeros((1, points.shape[1])), np.cumsum(points, axis=0)])
    index = np.arange(len(points))
    low = np.clip(index - half, 0, len(points))
    high = np.clip(index + half + 1, 0, len(points))
    return (padded[high] - padded[low]) / (high - low)[:, None]


def close_up(targets: np.ndarray, *, distance=30.0, smoothing=15, height_angle=math.radians(30), side_angle=math.radians(35)) -> CameraPath:
    """Follow `targets` (the print head, or a fixed point repeated) at a short distance."""
    target = moving_average(targets, smoothing)
    frames = len(target)
    azimuth = -math.pi / 2 + side_angle
    location = orbit_point(target, np.full(frames, distance), np.full(frames, azimuth), np.full(frames, height_angle))
    return CameraPath(location, target)


def _smoothstep(u: np.ndarray) -> np.ndarray:
    return u * u * (3 - 2 * u)


def final_reveal(
    bounds: Bounds,
    distance: float,
    frames: int,
    previous: tuple[np.ndarray, np.ndarray] | None,
    *,
    spin=math.radians(90),
    pullback_share=0.4,
) -> CameraPath:
    """Pull back from the previous framing, then spin around the part (spec section 9).

    `previous` is the (location, target) of the previous shot's last frame, or None.
    """
    pull = min(frames, int(round(frames * pullback_share)))
    if previous is None:
        azimuth, elevation = START_AZIMUTH, math.radians(30)
    else:
        offset = np.asarray(previous[0], dtype=np.float64) - bounds.center
        azimuth = math.atan2(offset[1], offset[0])
        horizontal = math.hypot(offset[0], offset[1])
        elevation = min(max(math.atan2(offset[2], horizontal), math.radians(5)), math.radians(60))
    pose = orbit_point(bounds.center, np.array(distance), np.array(azimuth), np.array(elevation))
    location = np.zeros((frames, 3))
    target = _fixed(bounds.center, frames)
    if pull:
        u = _smoothstep(np.arange(pull) / pull)[:, None]
        if previous is None:
            location[:pull] = pose
        else:
            location[:pull] = previous[0] + u * (pose - previous[0])
            target[:pull] = previous[1] + u * (bounds.center - previous[1])
    rest = frames - pull
    if rest:
        v = np.arange(rest) / max(rest - 1, 1)
        location[pull:] = orbit_point(bounds.center, np.full(rest, distance), azimuth + spin * v, np.full(rest, elevation))
    return CameraPath(location, target)
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test`

Expected: `80 passed`. Without the sample or Bambu Studio, expect `79 passed, 1 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_camera_paths.py sliceranim/core/camera_paths.py
git commit -m "Add camera path math for the six presets"
```

## Part B: Blender extension (headless Blender tests)

Tasks 10 to 17 need Blender 5.2. `make test-blender` runs all Blender tests. To run some of them, add a filter: `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P tests/blender/run_all.py -- test_strands`.

### Task 10: Extension skeleton, settings, and Blender test runner

Make the Blender extension load: the manifest, the scene settings of spec 11.3, and the add-on preferences. Add the headless test runner that all later Blender tasks use. Blender has its own Python, so the Blender tests do not use pytest.

**Files:**
- Create: `sliceranim/blender_manifest.toml`
- Create: `sliceranim/blender/__init__.py`
- Create: `sliceranim/blender/prefs.py`
- Create: `sliceranim/blender/props.py`
- Test: `tests/blender/run_all.py`
- Test: `tests/blender/helpers.py`
- Test: `tests/blender/test_register.py`

**Interfaces:**
- Consumes: Nothing from Part A at run time. `sliceranim/__init__.py` from Task 1 calls `sliceranim.blender.register()`.
- Produces:
  - `bpy.types.Scene.sliceranim` (`SLICERANIM_PG_settings`) and `SLICERANIM_PG_shot`. Field names are in `props.py` below. Update callbacks call `looks.apply`, `nodes.apply_settings`, and `output.apply`, which later tasks add.
  - `prefs.bambu_path(context) -> str` ("" when the extension is not installed as an add-on, for example in tests).
  - `tests/blender/run_all.py` (runs every `test_*` function in `tests/blender/test_*.py`) and `helpers.py` with `reset()`, `settings()`, `Skip`, `ROOT`, `FIXTURES`, `CUBE`, `SAMPLE_3MF`.

Colors in Blender color properties are linear. `#FF6A1A` is (1.0, 0.1441, 0.0103), `#D9D9D9` is 0.693, and `#808080` is 0.216.

- [ ] **Step 1: Write the failing tests**

Create `tests/blender/run_all.py`:

```python
"""Run the Blender tests headless.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P tests/blender/run_all.py
    ... -P tests/blender/run_all.py -- test_import        (only tests whose name contains "test_import")
"""

import importlib.util
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

import helpers  # noqa: E402
import sliceranim  # noqa: E402


def main() -> None:
    selected = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    sliceranim.register()
    passed = failed = skipped = 0
    for file in sorted(HERE.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(file.stem, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in sorted(n for n in dir(module) if n.startswith("test_")):
            label = f"{file.stem}::{name}"
            if selected and not any(s in label for s in selected):
                continue
            helpers.reset()
            start = time.perf_counter()
            try:
                getattr(module, name)()
            except helpers.Skip as reason:
                skipped += 1
                print(f"SKIP {label}: {reason}")
                continue
            except Exception:
                failed += 1
                print(f"FAIL {label}")
                traceback.print_exc()
                continue
            passed += 1
            print(f"PASS {label} ({time.perf_counter() - start:.2f} s)")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        sys.exit(1)


main()
```

Create `tests/blender/helpers.py`:

```python
"""Shared helpers for the Blender tests."""

from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CUBE = FIXTURES / "cube_3_layers.gcode"
SAMPLE_3MF = ROOT / "samples" / "sample.3mf"


class Skip(Exception):
    """Raise to skip a test, for example when a client sample file is not present."""


def reset() -> None:
    """Start each test from an empty scene."""
    bpy.ops.wm.read_homefile(use_empty=True)


def settings():
    return bpy.context.scene.sliceranim
```

Create `tests/blender/test_register.py`:

```python
import bpy
from helpers import settings


def test_register_adds_the_scene_settings():
    assert settings().toolpath_object is None
    assert settings().fps == "30"
    assert settings().strand_sides == "6"
    assert settings().viewport_strand_sides == "4"
    assert abs(settings().ghost_opacity - 0.15) < 1e-6


def test_shot_items_have_the_spec_defaults():
    shot = settings().shots.add()
    assert (shot.duration, shot.style, shot.camera) == (4.0, "LINE", "TURNTABLE")
    assert abs(shot.closeup_distance - 30.0) < 1e-6
    assert shot.closeup_smoothing == 15
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ModuleNotFoundError: No module named 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender_manifest.toml`:

```toml
schema_version = "1.0.0"

id = "sliceranim"
version = "0.1.0"
name = "Slicer Animator"
tagline = "Animate a 3D print growing layer by layer from real G-code"
maintainer = "Luis Branco <luis@brancooo.com>"
type = "add-on"

blender_version_min = "5.2.0"

license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 Luis Branco"]
tags = ["Animation", "Import-Export"]

[permissions]
files = "Read print files and write sliced files and renders"

[build]
paths_exclude_pattern = ["__pycache__/", "*.pyc"]
```

Create `sliceranim/blender/__init__.py`:

```python
"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import prefs, props

CLASSES = (prefs.SLICERANIM_AP_preferences,)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
```

Create `sliceranim/blender/prefs.py`:

```python
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
```

Create `sliceranim/blender/props.py`:

```python
"""Scene settings of the plugin (spec 11.3). Everything here is saved in the .blend file."""

import math

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

STYLE_ITEMS = [
    ("LINE", "Line", "Frames follow print time. You see each line drawn"),
    ("LAYER", "Layer", "Whole layers appear, spread evenly over the shot"),
    ("HOLD", "Hold", "The build does not move"),
]
CAMERA_ITEMS = [
    ("TURNTABLE", "Turntable orbit", "Circle the part"),
    ("HERO", "Hero", "A fixed three-quarter view"),
    ("RISING", "Rising follow", "Move up with the current layer"),
    ("CLOSE_UP", "Close-up", "Follow the print head from close by"),
    ("REVEAL", "Final reveal", "Pull back, then spin around the finished part"),
    ("CUSTOM", "My camera", "Use a camera that you placed"),
]
FINISH_ITEMS = [
    ("MATTE", "Matte", ""),
    ("GLOSSY", "Glossy", ""),
    ("SILK", "Silk", ""),
    ("TRANSLUCENT", "Translucent", ""),
]
FORMAT_ITEMS = [
    ("FHD", "1920×1080", "16:9 1080p"),
    ("SQUARE", "1080×1080", "1:1"),
    ("UHD", "3840×2160", "16:9 4K"),
    ("CUSTOM", "Custom", "Your own size"),
]
FPS_ITEMS = [(v, v, "") for v in ("24", "25", "30", "60")]
FILE_ITEMS = [("MP4", "MP4 (H.264)", ""), ("PNG", "PNG frames", "")]
SIDES_ITEMS = [(v, v, "") for v in ("4", "6", "8")]
VIEWPORT_SIDES_ITEMS = [(v, v, "") for v in ("3", "4", "6", "8")]


def _looks(self, context):
    from . import looks

    looks.apply(context.scene)


def _strands(self, context):
    from . import nodes

    nodes.apply_settings(context.scene)


def _output(self, context):
    from . import output

    output.apply(context.scene)


def _is_camera(self, obj):
    return obj.type == "CAMERA"


class SLICERANIM_PG_shot(bpy.types.PropertyGroup):
    start_layer: IntProperty(name="Start layer", min=1, default=1)
    start_at_end: BoolProperty(name="End", description="Start after the last layer")
    duration: FloatProperty(name="Duration", description="Screen time in seconds", min=0.0, default=4.0, step=50)
    style: EnumProperty(name="Build style", items=STYLE_ITEMS, default="LINE")
    camera: EnumProperty(name="Camera", items=CAMERA_ITEMS, default="TURNTABLE")
    orbit_turns: FloatProperty(name="Turns", default=1.0, min=0.0, soft_max=4.0)
    orbit_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(25))
    orbit_clockwise: BoolProperty(name="Clockwise", default=False)
    hero_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(30))
    hero_side: FloatProperty(name="Side angle", subtype="ANGLE", default=math.radians(35))
    rising_distance: FloatProperty(
        name="Distance", description="Camera distance in mm. 0 uses the framing distance", default=0.0, min=0.0
    )
    rising_height: FloatProperty(name="Height angle", subtype="ANGLE", default=math.radians(20))
    closeup_target: EnumProperty(
        name="Target",
        items=[("HEAD", "Print head", ""), ("CURSOR", "3D cursor", "The point under the 3D cursor when you click Rebuild")],
        default="HEAD",
    )
    closeup_distance: FloatProperty(name="Distance", description="Camera distance in mm", default=30.0, min=1.0)
    closeup_smoothing: IntProperty(name="Smoothing", description="Frames in the moving average", default=15, min=1)
    closeup_dof: BoolProperty(name="Depth of field", default=True)
    closeup_fstop: FloatProperty(name="F-stop", default=2.8, min=0.1)
    reveal_spin: FloatProperty(name="Spin amount", subtype="ANGLE", default=math.radians(90))
    reveal_pullback: FloatProperty(name="Pull-back share", subtype="PERCENTAGE", default=40.0, min=0.0, max=100.0)
    custom_camera: PointerProperty(name="Camera object", type=bpy.types.Object, poll=_is_camera)


class SLICERANIM_PG_settings(bpy.types.PropertyGroup):
    # Source
    toolpath_object: PointerProperty(type=bpy.types.Object)
    head_object: PointerProperty(type=bpy.types.Object)
    source_kind: EnumProperty(
        items=[("NONE", "None", ""), ("GCODE", "G-code", ""), ("SLICED_3MF", "Sliced 3MF", ""),
               ("PROJECT", "Bambu project", ""), ("STL", "STL", ""), ("MESH", "Mesh object", "")],
        default="NONE",
    )
    source_path: StringProperty(description="File that Reload reads", subtype="FILE_PATH")
    source_label: StringProperty(description="File or object name shown in the panel")
    source_mesh: PointerProperty(type=bpy.types.Object, description="Mesh that the fallback slicer read")
    slicer: StringProperty()
    layer_count: IntProperty()
    point_count: IntProperty()
    print_time: FloatProperty()
    used_fallback: BoolProperty()
    built_merge_angle: FloatProperty(subtype="ANGLE", default=-1.0)
    part_center: FloatVectorProperty(size=3, description="Part center in mm")
    part_radius: FloatProperty(description="Bounding sphere radius in mm")
    plate_centered_on_part: BoolProperty()
    file_color: FloatVectorProperty(subtype="COLOR", size=3, default=(0.216, 0.216, 0.216), min=0.0, max=1.0)  # #808080
    engine_set: BoolProperty(description="The first import already set the render engine")
    # Look
    use_file_color: BoolProperty(name="Color from file", default=True, update=_looks)
    color: FloatVectorProperty(name="Color", subtype="COLOR", size=3, default=(0.216, 0.216, 0.216), min=0.0, max=1.0, update=_looks)
    finish: EnumProperty(name="Finish", items=FINISH_ITEMS, default="MATTE", update=_looks)
    highlight: BoolProperty(name="Active-layer highlight", default=True, update=_looks)
    highlight_color: FloatVectorProperty(name="Highlight color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                         default=(1.0, 0.1441, 0.0103), update=_looks)  # #FF6A1A in linear color
    highlight_layers: IntProperty(name="Highlight layers", default=3, min=1, update=_strands)
    ghost: BoolProperty(name="Ghost", description="Show the part that is not printed yet as a clear shell", default=False, update=_strands)
    ghost_use_filament_color: BoolProperty(name="Filament color", default=True, update=_looks)
    ghost_color: FloatVectorProperty(name="Ghost color", subtype="COLOR", size=3, default=(1.0, 1.0, 1.0), min=0.0, max=1.0, update=_looks)
    ghost_opacity: FloatProperty(name="Opacity", subtype="FACTOR", default=0.15, min=0.0, max=1.0, update=_looks)
    strand_sides: EnumProperty(name="Strand sides", items=SIDES_ITEMS, default="6", update=_strands)
    viewport_strand_sides: EnumProperty(name="Viewport strand sides", items=VIEWPORT_SIDES_ITEMS, default="4", update=_strands)
    merge_angle: FloatProperty(name="Merge angle", subtype="ANGLE", default=math.radians(2.0), min=0.0, max=math.radians(30))
    backdrop: BoolProperty(name="Studio backdrop", default=True, update=_looks)
    backdrop_color: FloatVectorProperty(name="Backdrop color", subtype="COLOR", size=3, min=0.0, max=1.0,
                                        default=(0.693, 0.693, 0.693), update=_looks)  # #D9D9D9 in linear color
    lights: BoolProperty(name="Lights", default=True, update=_looks)
    plate_mat: BoolProperty(name="Plate mat", default=False, update=_looks)
    nozzle: BoolProperty(name="Nozzle tip", default=False, update=_looks)
    # Shots
    shots: CollectionProperty(type=SLICERANIM_PG_shot)
    active_shot: IntProperty()
    line_frame_ranges: StringProperty(description="JSON list of [first, last] frames of Line shots, from the last Rebuild")
    rebuild_signature: StringProperty()
    # Output
    format_preset: EnumProperty(name="Format", items=FORMAT_ITEMS, default="FHD", update=_output)
    custom_width: IntProperty(name="Width", default=1920, min=16, update=_output)
    custom_height: IntProperty(name="Height", default=1080, min=16, update=_output)
    fps: EnumProperty(name="Frame rate", items=FPS_ITEMS, default="30", update=_output)
    file_type: EnumProperty(name="File type", items=FILE_ITEMS, default="MP4", update=_output)
    output_folder: StringProperty(name="Output folder", subtype="DIR_PATH", default="//renders/", update=_output)
    # Preview
    preview_active: BoolProperty()
    preview_state: StringProperty()


CLASSES = (SLICERANIM_PG_shot, SLICERANIM_PG_settings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sliceranim = PointerProperty(type=SLICERANIM_PG_settings)


def unregister():
    del bpy.types.Scene.sliceranim
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `2 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Validate the manifest**

Run: `/Applications/Blender.app/Contents/MacOS/Blender --command extension validate sliceranim`

Expected: `Success parsing TOML in ".../sliceranim"`.

- [ ] **Step 6: Commit**

```bash
git add tests/blender/run_all.py tests/blender/helpers.py tests/blender/test_register.py sliceranim/blender_manifest.toml sliceranim/blender/__init__.py sliceranim/blender/prefs.py sliceranim/blender/props.py
git commit -m "Add the extension skeleton, scene settings, and Blender test runner"
```

### Task 11: Toolpath mesh and strand Geometry Nodes

Build the toolpath mesh and the Geometry Nodes group of spec section 7, including the ghost (step 8) and the Viewport Strand Sides switch. `toolpath_from_object()` reads the ToolpathSet back from the mesh, so Rebuild never needs the source file.

**Files:**
- Create: `sliceranim/blender/nodes.py`
- Create: `sliceranim/blender/importer.py`
- Modify: `tests/blender/helpers.py`
- Test: `tests/blender/test_strands.py`

**Interfaces:**
- Consumes: `read_gcode` (Task 4) in the tests; `ToolpathSet`, `pack` (Task 2).
- Produces:
  - `nodes.GROUP_NAME`, `nodes.MODIFIER_NAME = "Slicer Animator"`, `nodes.SHELL_FEATURES = (1, 3, 6)`.
  - `nodes.build_strand_group(filament_material, ghost_material)`, `nodes.ensure_modifier(obj, filament_material, ghost_material)`.
  - `nodes.set_input(obj, name, value)` (also tags the object for redraw), `nodes.get_input(obj, name)`, `nodes.input_path(obj, name) -> str`, `nodes.apply_settings(scene)`.
  - Group inputs: Progress, Current Layer, Strand Sides, Viewport Strand Sides, Ghost, Highlight Layers, Profile Aspect.
  - `importer.MM = 0.001`, `importer.toolpath_mesh(tp, name) -> bpy.types.Mesh`, `importer.toolpath_from_object(obj) -> ToolpathSet`.
  - Test helpers `evaluated_polygons(obj) -> int`, `evaluated_bounds(obj) -> (low, high)`.

Facts checked in Blender 5.2.2 on 2026-10-15:

1. Curve to Mesh has a float `Scale` input only. A per-strand oval is not possible, so the profile is squashed by one `Profile Aspect` for the whole object: median height / median width.
2. With the normal mode `Z Up`, the profile's Y axis becomes the vertical axis. The test `test_strands_are_flat_ovals_of_strand_width_and_height` checks this.
3. Compare, Switch, and Mix nodes show only the sockets of their data type, so the socket index depends on `data_type`. Set the type first, then link.
4. After `mod.properties.inputs.<id>.value = x`, Blender does not update the object in background mode. `set_input` calls `obj.update_tag()`.
5. Background evaluation uses viewport settings, so `Is Viewport` is true in the tests and 4 sides apply.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/blender/helpers.py`:

```python
def evaluated_polygons(obj) -> int:
    """Polygon count of the evaluated object (3D view evaluation, so Viewport Strand Sides applies)."""
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def evaluated_bounds(obj) -> tuple[np.ndarray, np.ndarray]:
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
    finally:
        evaluated.to_mesh_clear()
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)
```

Create `tests/blender/test_strands.py`:

```python
import bpy
import numpy as np
from helpers import CUBE, evaluated_bounds, evaluated_polygons

from sliceranim.blender import importer, nodes
from sliceranim.core.gcode_reader import read_gcode


def make_object():
    tp = read_gcode(CUBE)
    obj = bpy.data.objects.new("cube", importer.toolpath_mesh(tp, "cube"))
    bpy.context.scene.collection.objects.link(obj)
    nodes.ensure_modifier(obj, bpy.data.materials.new("filament"), bpy.data.materials.new("ghost"))
    nodes.set_input(obj, "Profile Aspect", 0.2 / 0.45)
    return tp, obj


def test_mesh_has_one_vertex_per_point_and_one_edge_per_strand():
    tp, obj = make_object()
    assert len(obj.data.vertices) == tp.point_count == 42
    assert len(obj.data.edges) == 30
    for name in ("order", "layer", "feature", "tool", "width", "height", "time"):
        assert name in obj.data.attributes, name
    np.testing.assert_allclose(obj.data.vertices[1].co, (9.325e-3, 0.675e-3, 0.2e-3), atol=1e-7)


def test_toolpaths_read_back_from_the_object_match_the_source():
    tp, obj = make_object()
    back = importer.toolpath_from_object(obj)
    np.testing.assert_allclose(back.position, tp.position, atol=1e-4)
    assert back.run_start.tolist() == tp.run_start.tolist()
    assert back.layer_start.tolist() == tp.layer_start.tolist()
    np.testing.assert_allclose(back.time, tp.time, rtol=1e-6)
    np.testing.assert_allclose(back.width, tp.width, rtol=1e-5)


def test_progress_controls_how_many_strands_are_drawn():
    _, obj = make_object()
    sides = nodes.get_input(obj, "Viewport Strand Sides")
    assert sides == 4
    for progress, strands in ((0.0, 0), (2.5, 2), (5.0, 4), (42.0, 30)):
        nodes.set_input(obj, "Progress", progress)
        assert evaluated_polygons(obj) == strands * sides, progress


def test_ghost_adds_the_unprinted_outer_walls_only():
    _, obj = make_object()
    nodes.set_input(obj, "Progress", 0.0)
    nodes.set_input(obj, "Ghost", True)
    assert evaluated_polygons(obj) == 12 * 4  # 4 outer wall strands per layer, 3 layers
    nodes.set_input(obj, "Progress", 42.0)
    assert evaluated_polygons(obj) == 30 * 4


def test_strands_are_flat_ovals_of_strand_width_and_height():
    _, obj = make_object()
    nodes.set_input(obj, "Progress", 42.0)
    low, high = evaluated_bounds(obj)
    np.testing.assert_allclose(high[2], 0.6e-3 + 0.1e-3, atol=1e-6)  # top layer z + half the height
    np.testing.assert_allclose(low[:2], [0.0, 0.0], atol=1e-6)  # outer wall at 0.225 mm, minus half of 0.45 mm


def test_input_paths_can_be_keyframed():
    _, obj = make_object()
    path = nodes.input_path(obj, "Progress")
    assert path.startswith('modifiers["Slicer Animator"].properties.inputs.')
    assert obj.keyframe_insert(path, frame=1)
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'importer' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/nodes.py`:

```python
"""The Geometry Nodes setup that draws the strands (spec section 7)."""

import bpy

GROUP_NAME = "Slicer Animator Strands"
MODIFIER_NAME = "Slicer Animator"
SHELL_FEATURES = (1, 3, 6)  # outer_wall, overhang_wall, top_surface
GHOST_RENDER_SIDES = 4
INPUTS = (
    ("Progress", "NodeSocketFloat", 0.0),
    ("Current Layer", "NodeSocketFloat", 0.0),
    ("Strand Sides", "NodeSocketInt", 6),
    ("Viewport Strand Sides", "NodeSocketInt", 4),
    ("Ghost", "NodeSocketBool", False),
    ("Highlight Layers", "NodeSocketFloat", 3.0),
    ("Profile Aspect", "NodeSocketFloat", 0.45),
)


class _Builder:
    def __init__(self, tree):
        self.tree = tree

    def node(self, idname, **props):
        n = self.tree.nodes.new(idname)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def link(self, out_socket, in_socket):
        self.tree.links.new(out_socket, in_socket)

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def compare(self, op, a, b, data_type="FLOAT"):
        n = self.node("FunctionNodeCompare", data_type=data_type, operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def boolean(self, op, a, b=None):
        n = self.node("FunctionNodeBooleanMath", operation=op)
        self.link(a, n.inputs[0])
        if b is not None:
            self.link(b, n.inputs[1])
        return n.outputs[0]

    def attr(self, name, data_type):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=data_type)
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    def switch(self, input_type, cond, false, true):
        n = self.node("GeometryNodeSwitch", input_type=input_type)
        self.link(cond, n.inputs[0])
        for i, v in ((1, false), (2, true)):
            if v is None:
                continue
            if isinstance(v, (int, float, bool)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]


def _sweep(b, curve_geo, sides, aspect, material):
    """Sweep an oval profile with `sides` points along curves made from mesh edges."""
    to_curve = b.node("GeometryNodeMeshToCurve")
    b.link(curve_geo, to_curve.inputs["Mesh"])
    normal = b.node("GeometryNodeSetCurveNormal")
    normal.inputs["Mode"].default_value = "Z Up"
    b.link(to_curve.outputs[0], normal.inputs["Curve"])
    circle = b.node("GeometryNodeCurvePrimitiveCircle", mode="RADIUS")
    b.link(sides, circle.inputs["Resolution"])
    circle.inputs["Radius"].default_value = 1.0
    squash = b.node("ShaderNodeCombineXYZ")
    squash.inputs[0].default_value = 1.0
    squash.inputs[2].default_value = 1.0
    b.link(aspect, squash.inputs[1])
    xform = b.node("GeometryNodeTransform")
    b.link(circle.outputs["Curve"], xform.inputs["Geometry"])
    b.link(squash.outputs[0], xform.inputs["Scale"])
    sweep = b.node("GeometryNodeCurveToMesh")
    b.link(normal.outputs[0], sweep.inputs["Curve"])
    b.link(xform.outputs[0], sweep.inputs["Profile Curve"])
    b.link(b.math("MULTIPLY", b.attr("width", "FLOAT"), 0.5), sweep.inputs["Scale"])
    smooth = b.node("GeometryNodeSetShadeSmooth")
    b.link(sweep.outputs[0], smooth.inputs[0])
    setmat = b.node("GeometryNodeSetMaterial")
    setmat.inputs["Material"].default_value = material
    b.link(smooth.outputs[0], setmat.inputs["Geometry"])
    return setmat.outputs[0]


def build_strand_group(filament_material, ghost_material):
    old = bpy.data.node_groups.get(GROUP_NAME)
    if old is not None:
        bpy.data.node_groups.remove(old)
    tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name, socket_type, default in INPUTS:
        s = tree.interface.new_socket(name, in_out="INPUT", socket_type=socket_type)
        s.default_value = default
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    b = _Builder(tree)
    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")
    geo = gi.outputs["Geometry"]

    k = b.math("FLOOR", gi.outputs["Progress"])
    frac = b.math("SUBTRACT", gi.outputs["Progress"], k)
    order = b.attr("order", "INT")

    # Steps 1 and 2: keep points 0..k, and slide point k toward its previous point.
    delete = b.node("GeometryNodeDeleteGeometry", domain="POINT")
    b.link(geo, delete.inputs["Geometry"])
    b.link(b.compare("GREATER_THAN", order, k), delete.inputs["Selection"])
    neighbors = b.node("GeometryNodeInputMeshVertexNeighbors")
    is_last = b.boolean("AND", b.compare("EQUAL", order, k),
                        b.compare("GREATER_THAN", neighbors.outputs["Vertex Count"], 0.5))
    index = b.node("GeometryNodeInputIndex")
    position = b.node("GeometryNodeInputPosition")
    prev = b.node("GeometryNodeSampleIndex", data_type="FLOAT_VECTOR", domain="POINT")
    b.link(delete.outputs[0], prev.inputs["Geometry"])
    b.link(position.outputs[0], prev.inputs["Value"])
    b.link(b.math("SUBTRACT", index.outputs[0], 1.0), prev.inputs["Index"])
    lerp = b.node("ShaderNodeMix", data_type="VECTOR")
    b.link(frac, lerp.inputs["Factor"])
    b.link(prev.outputs[0], lerp.inputs[4])
    b.link(position.outputs[0], lerp.inputs[5])
    setpos = b.node("GeometryNodeSetPosition")
    b.link(delete.outputs[0], setpos.inputs["Geometry"])
    b.link(is_last, setpos.inputs["Selection"])
    b.link(lerp.outputs[1], setpos.inputs["Position"])

    # Step 6: heat for the active-layer highlight.
    behind = b.math("SUBTRACT", gi.outputs["Current Layer"], b.attr("layer", "INT"))
    heat = b.math("SUBTRACT", 1.0, b.math("DIVIDE", behind, gi.outputs["Highlight Layers"]), clamp=True)
    store = b.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    store.inputs["Name"].default_value = "heat"
    b.link(setpos.outputs[0], store.inputs["Geometry"])
    b.link(heat, store.inputs["Value"])

    is_viewport = b.node("GeometryNodeIsViewport").outputs[0]
    sides = b.switch("INT", is_viewport, gi.outputs["Strand Sides"], gi.outputs["Viewport Strand Sides"])
    printed = _sweep(b, store.outputs[0], sides, gi.outputs["Profile Aspect"], filament_material)

    # Step 8: the ghost shell of the part that is not printed yet.
    feature = b.attr("feature", "INT")
    shell = b.compare("EQUAL", feature, SHELL_FEATURES[0], "INT")
    for code in SHELL_FEATURES[1:]:
        shell = b.boolean("OR", shell, b.compare("EQUAL", feature, code, "INT"))
    keep = b.boolean("AND", b.compare("GREATER_THAN", order, k), shell)
    ghost_delete = b.node("GeometryNodeDeleteGeometry", domain="POINT")
    b.link(geo, ghost_delete.inputs["Geometry"])
    b.link(b.boolean("NOT", keep), ghost_delete.inputs["Selection"])
    ghost_sides = b.switch("INT", is_viewport, GHOST_RENDER_SIDES, gi.outputs["Viewport Strand Sides"])
    ghost = _sweep(b, ghost_delete.outputs[0], ghost_sides, gi.outputs["Profile Aspect"], ghost_material)
    ghost_on = b.switch("GEOMETRY", gi.outputs["Ghost"], None, ghost)

    join = b.node("GeometryNodeJoinGeometry")
    b.link(printed, join.inputs[0])
    b.link(ghost_on, join.inputs[0])
    b.link(join.outputs[0], go.inputs["Geometry"])
    return tree

def ensure_modifier(obj, filament_material, ghost_material):
    """Give `obj` the strand modifier with a fresh node group."""
    group = build_strand_group(filament_material, ghost_material)
    modifier = obj.modifiers.get(MODIFIER_NAME) or obj.modifiers.new(MODIFIER_NAME, "NODES")
    modifier.node_group = group
    return modifier


def _identifier(obj, name: str) -> str:
    group = obj.modifiers[MODIFIER_NAME].node_group
    for item in group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(name)


def _input(obj, name: str):
    return getattr(obj.modifiers[MODIFIER_NAME].properties.inputs, _identifier(obj, name))


def set_input(obj, name: str, value) -> None:
    """Set a modifier input. Blender 5.2 does not redraw on its own after this, so tag the object."""
    _input(obj, name).value = value
    obj.update_tag()


def get_input(obj, name: str):
    return _input(obj, name).value


def input_path(obj, name: str) -> str:
    """Data path for keyframes, for example modifiers["Slicer Animator"].properties.inputs.Socket_2.value."""
    return _input(obj, name).path_from_id("value")


def apply_settings(scene) -> None:
    """Copy the strand settings from the panel to the modifier."""
    settings = scene.sliceranim
    obj = settings.toolpath_object
    if obj is None or MODIFIER_NAME not in obj.modifiers:
        return
    set_input(obj, "Strand Sides", int(settings.strand_sides))
    set_input(obj, "Viewport Strand Sides", int(settings.viewport_strand_sides))
    set_input(obj, "Ghost", settings.ghost)
    set_input(obj, "Highlight Layers", float(settings.highlight_layers))
```

Create `sliceranim/blender/importer.py`:

```python
"""Read a source and build the toolpath object (spec sections 6, 7, and 11.2)."""

import bpy
import numpy as np

from ..core.toolpaths import ToolpathSet, pack

MM = 0.001
ATTRIBUTES = (
    # name, Blender type, ToolpathSet field, scale
    ("layer", "INT", "layer", None),
    ("feature", "INT", "feature", None),
    ("tool", "INT", "tool", None),
    ("width", "FLOAT", "width", MM),
    ("height", "FLOAT", "height", MM),
    ("time", "FLOAT", "time", None),
)


def toolpath_mesh(tp: ToolpathSet, name: str) -> bpy.types.Mesh:
    """One vertex per point (in meters), one edge per strand, and the point attributes."""
    n = tp.point_count
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(n)
    mesh.vertices.foreach_set("co", (tp.position.astype(np.float64) * MM).astype(np.float32).ravel())
    first = np.arange(n - 1, dtype=np.int32)[~tp.run_start_mask()[1:]]
    mesh.edges.add(len(first))
    mesh.edges.foreach_set("vertices", np.column_stack([first, first + 1]).ravel())
    mesh.attributes.new("order", "INT", "POINT").data.foreach_set("value", np.arange(n, dtype=np.int32))
    for attr, kind, field, scale in ATTRIBUTES:
        values = getattr(tp, field).astype(np.float64)
        if scale:
            values = values * scale
        dtype = np.int32 if kind == "INT" else np.float32
        mesh.attributes.new(attr, kind, "POINT").data.foreach_set("value", values.astype(dtype))
    mesh.update()
    return mesh


def _read_attribute(mesh, name: str, dtype) -> np.ndarray:
    values = np.empty(len(mesh.vertices), dtype=dtype)
    mesh.attributes[name].data.foreach_get("value", values)
    return values


def toolpath_from_object(obj) -> ToolpathSet:
    """Read the ToolpathSet back from the toolpath object. Rebuild needs no source file."""
    mesh = obj.data
    n = len(mesh.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edges)
    starts = np.ones(n, dtype=bool)
    starts[edges.reshape(-1, 2)[:, 1]] = False
    return pack(
        position=co.reshape(-1, 3).astype(np.float64) / MM,
        layer=_read_attribute(mesh, "layer", np.int32),
        feature=_read_attribute(mesh, "feature", np.int32),
        tool=_read_attribute(mesh, "tool", np.int32),
        width=_read_attribute(mesh, "width", np.float32) / MM,
        height=_read_attribute(mesh, "height", np.float32) / MM,
        time=_read_attribute(mesh, "time", np.float32),
        object_id=np.zeros(n),
        run_start=np.flatnonzero(starts),
    )
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `8 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/helpers.py tests/blender/test_strands.py sliceranim/blender/nodes.py sliceranim/blender/importer.py
git commit -m "Add the toolpath mesh and the strand Geometry Nodes"
```

### Task 12: Looks, output settings, and keyframe helper

Make the materials, backdrop, lights, plate mat, and nozzle tip of spec section 10, and the render settings of spec 11.1. `keys.py` writes many keyframes fast with the Blender 5.2 layered action API.

**Files:**
- Create: `sliceranim/blender/keys.py`
- Create: `sliceranim/blender/output.py`
- Create: `sliceranim/blender/looks.py`
- Test: `tests/blender/test_looks.py`

**Interfaces:**
- Consumes: `make_object()` from `tests/blender/test_strands.py` (Task 11), `START_AZIMUTH` (Task 9).
- Produces:
  - `keys.CONSTANT = 0`, `keys.LINEAR = 1`, `keys.write(id_data, data_path, frames, values, interpolation, index=-1)`, `keys.write_vector(id_data, data_path, frames, values, interpolation)`, `keys.remove(id_data, data_paths)`.
  - `output.PRESETS`, `output.resolution(settings) -> (w, h)`, `output.apply(scene)`.
  - `looks.COLLECTION = "Slicer Animator"`, `looks.hex_to_linear(value) -> (r, g, b)`, `looks.collection(scene)`, `looks.put_object(scene, name, data)`, `looks.remove_object(name)`, `looks.filament_material()`, `looks.ghost_material()`, `looks.update_materials(scene)`, `looks.write_nozzle_keys(scene)`, `looks.apply(scene)`.
  - Object names: `SA Backdrop`, `SA Key Light`, `SA Fill Light`, `SA Rim Light`, `SA Plate Mat`, `SA Nozzle Tip`, `SA Print Head`. Material names: `SA Filament`, `SA Ghost`, `SA Textured PEI`, `SA Brass`, `SA Backdrop`.

Facts checked on 2026-10-15:

1. Blender 5.2 has no `Action.fcurves`. Use `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot).fcurves`.
2. `keyframe_insert` takes `index=-1` for a single value. `index=0` raises `TypeError` for a property that is not an array.
3. `image_settings.media_type` is `IMAGE` or `VIDEO` in Blender 5.2.
4. Light power: a first try at 1000 × distance² made every frame white. 60 / 25 / 50 × distance² (key / fill / rim, distance in m) gave a normal exposure on the sample render.

- [ ] **Step 1: Write the failing tests**

Create `tests/blender/test_looks.py`:

```python
import json

import bpy
import numpy as np
from helpers import settings
from test_strands import make_object

from sliceranim.blender import keys, looks, output


def setup():
    tp, obj = make_object()
    s = settings()
    s.toolpath_object = obj
    s.head_object = looks.put_object(bpy.context.scene, "SA Print Head", None)
    s.part_center = (5.0, 5.0, 0.3)
    s.part_radius = 7.1
    return s


def principled(name):
    material = bpy.data.materials[name]
    return next(n for n in material.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def test_hex_to_linear():
    np.testing.assert_allclose(looks.hex_to_linear("#808080"), [0.2158605] * 3, rtol=1e-5)
    np.testing.assert_allclose(looks.hex_to_linear("#FF6A1A"), [1.0, 0.1441285, 0.0103298], rtol=1e-4)


def test_default_look_makes_backdrop_and_three_lights_only():
    setup()
    looks.apply(bpy.context.scene)
    names = {o.name for o in bpy.data.collections["Slicer Animator"].objects}
    assert {"SA Backdrop", "SA Key Light", "SA Fill Light", "SA Rim Light"} <= names
    assert "SA Plate Mat" not in names and "SA Nozzle Tip" not in names


def test_finish_and_color_reach_the_filament_material():
    s = setup()
    s.use_file_color = False
    s.color = (1.0, 0.0, 0.0)
    s.finish = "TRANSLUCENT"
    bsdf = principled("SA Filament")
    assert tuple(bsdf.inputs["Base Color"].default_value)[:3] == (1.0, 0.0, 0.0)
    assert abs(bsdf.inputs["Transmission Weight"].default_value - 0.7) < 1e-6


def test_highlight_off_sets_the_emission_strength_to_zero():
    s = setup()
    s.highlight = False
    strength = bpy.data.materials["SA Filament"].node_tree.nodes["SA Highlight Strength"]
    assert strength.inputs[1].default_value == 0.0


def test_ghost_material_uses_opacity_and_dithered_blending():
    s = setup()
    s.ghost_opacity = 0.3
    assert abs(principled("SA Ghost").inputs["Alpha"].default_value - 0.3) < 1e-6
    assert bpy.data.materials["SA Ghost"].surface_render_method == "DITHERED"


def test_plate_mat_sits_on_the_bambu_plate_center_or_under_the_part():
    s = setup()
    s.plate_mat = True
    plate = bpy.data.objects["SA Plate Mat"]
    np.testing.assert_allclose(plate.location, (0.128, 0.128, 0.0))
    s.plate_centered_on_part = True
    looks.apply(bpy.context.scene)
    np.testing.assert_allclose(plate.location, (0.005, 0.005, 0.0))
    s.plate_mat = False
    assert "SA Plate Mat" not in bpy.data.objects


def test_nozzle_tip_follows_the_head_and_shows_in_line_shots_only():
    s = setup()
    s.line_frame_ranges = json.dumps([[1, 120], [481, 600]])
    s.nozzle = True
    nozzle = bpy.data.objects["SA Nozzle Tip"]
    assert nozzle.parent == s.head_object
    data = nozzle.animation_data
    from bpy_extras import anim_utils

    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find("hide_render")
    points = [tuple(k.co) for k in curve.keyframe_points]
    assert points == [(1.0, 0.0), (121.0, 1.0), (481.0, 0.0), (601.0, 1.0)]
    assert all(k.interpolation == "CONSTANT" for k in curve.keyframe_points)


def test_output_presets():
    s = setup()
    render = bpy.context.scene.render
    output.apply(bpy.context.scene)
    assert (render.resolution_x, render.resolution_y, render.fps) == (1920, 1080, 30)
    assert render.image_settings.media_type == "VIDEO"
    assert render.ffmpeg.codec == "H264"
    assert render.filepath == "//renders/cube_"
    s.format_preset = "UHD"
    s.fps = "60"
    s.file_type = "PNG"
    assert (render.resolution_x, render.resolution_y, render.fps) == (3840, 2160, 60)
    assert render.image_settings.file_format == "PNG"
    s.format_preset = "CUSTOM"
    s.custom_width, s.custom_height = 1080, 1920
    assert (render.resolution_x, render.resolution_y) == (1080, 1920)


def test_keys_write_replaces_old_keys():
    obj = bpy.data.objects.new("e", None)
    bpy.context.scene.collection.objects.link(obj)
    keys.write(obj, "location", [1, 2, 3], [0.0, 1.0, 2.0], keys.LINEAR, index=0)
    keys.write(obj, "location", [5, 6], [3.0, 4.0], keys.CONSTANT, index=0)
    bpy.context.scene.frame_set(6)
    assert obj.location.x == 4.0
    keys.remove(obj, {"location"})
    assert obj.animation_data.action is not None
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'keys' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/keys.py`:

```python
"""Fast keyframe writing for Blender 5.2 layered actions."""

import bpy
import numpy as np
from bpy_extras import anim_utils

CONSTANT, LINEAR = 0, 1  # values of the Keyframe.interpolation enum


def _channelbag(id_data):
    data = id_data.animation_data
    if data is None or data.action is None or data.action_slot is None:
        return None
    return anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot)


def write(id_data, data_path: str, frames, values, interpolation, index: int = -1) -> None:
    """Replace all keys of one channel. `index` is -1 for a single value, or the array index.

    `interpolation` is CONSTANT, LINEAR, or an array with one of them per key.
    """
    id_data.keyframe_insert(data_path, index=index, frame=float(frames[0]))
    curve = _channelbag(id_data).fcurves.find(data_path, index=max(index, 0))
    curve.keyframe_points.clear()
    count = len(frames)
    curve.keyframe_points.add(count)
    co = np.column_stack([np.asarray(frames, dtype=np.float32), np.asarray(values, dtype=np.float32)])
    curve.keyframe_points.foreach_set("co", co.ravel())
    modes = np.broadcast_to(np.asarray(interpolation, dtype=np.int32), (count,))
    curve.keyframe_points.foreach_set("interpolation", np.ascontiguousarray(modes))
    curve.update()


def write_vector(id_data, data_path: str, frames, values, interpolation) -> None:
    values = np.asarray(values)
    for axis in range(values.shape[1]):
        write(id_data, data_path, frames, values[:, axis], interpolation, index=axis)


def remove(id_data, data_paths) -> None:
    """Delete the channels whose data path is in `data_paths`."""
    bag = _channelbag(id_data)
    if bag is None:
        return
    for curve in [c for c in bag.fcurves if c.data_path in data_paths]:
        bag.fcurves.remove(curve)
```

Create `sliceranim/blender/output.py`:

```python
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
```

Create `sliceranim/blender/looks.py`:

```python
"""Materials, backdrop, lights, plate mat, and nozzle tip (spec section 10)."""

import json
import math

import bpy
import numpy as np
from mathutils import Vector

from ..core.camera_paths import START_AZIMUTH
from . import keys

MM = 0.001
COLLECTION = "Slicer Animator"
HIGHLIGHT_STRENGTH = 4.0
FINISHES = {
    # roughness, specular IOR level, sheen weight, transmission weight
    "MATTE": (0.6, 0.3, 0.0, 0.0),
    "GLOSSY": (0.15, 0.5, 0.0, 0.0),
    "SILK": (0.25, 0.7, 0.8, 0.0),
    "TRANSLUCENT": (0.2, 0.5, 0.0, 0.7),
}
# name: (azimuth from START_AZIMUTH, elevation, power factor). Power = factor x distance² (W, distance in m).
LIGHTS = {
    "SA Key Light": (math.radians(-40), math.radians(45), 60.0),
    "SA Fill Light": (math.radians(70), math.radians(20), 25.0),
    "SA Rim Light": (math.radians(180), math.radians(50), 50.0),
}
PLATE_SIZE_MM = 256.0
BAMBU_PLATE_CENTER_MM = (128.0, 128.0)
NOZZLE_HEIGHT_MM = 6.0
NOZZLE_LIFT_MM = 0.1  # strands are drawn centered on the nozzle height, so lift the tip by half a layer


def hex_to_linear(value: str) -> tuple[float, float, float]:
    """Turn "#RRGGBB" (sRGB) into linear RGB, the color space of Blender color properties."""
    value = value.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)


def collection(scene) -> bpy.types.Collection:
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def put_object(scene, name: str, data) -> bpy.types.Object:
    """Return the object `name` with new `data`, made and linked if needed."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, data)
        collection(scene).objects.link(obj)
    elif data is not None and obj.data is not data:
        old = obj.data
        obj.data = data
        if old is not None and old.users == 0:
            _remove_data(old)
    return obj


def remove_object(name: str) -> None:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    data = obj.data
    bpy.data.objects.remove(obj)
    if data is not None and data.users == 0:
        _remove_data(data)


def _remove_data(data) -> None:
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Light):
        bpy.data.lights.remove(data)
    elif isinstance(data, bpy.types.Camera):
        bpy.data.cameras.remove(data)


def _principled(material) -> bpy.types.Node:
    return next(n for n in material.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _material(name: str) -> tuple[bpy.types.Material, bool]:
    material = bpy.data.materials.get(name)
    if material is not None:
        return material, False
    return bpy.data.materials.new(name), True


def filament_material() -> bpy.types.Material:
    material, new = _material("SA Filament")
    if new:
        tree = material.node_tree
        bsdf = _principled(material)
        heat = tree.nodes.new("ShaderNodeAttribute")
        heat.attribute_type = "GEOMETRY"
        heat.attribute_name = "heat"
        strength = tree.nodes.new("ShaderNodeMath")
        strength.name = "SA Highlight Strength"
        strength.operation = "MULTIPLY"
        tree.links.new(heat.outputs["Fac"], strength.inputs[0])
        tree.links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])
    return material


def ghost_material() -> bpy.types.Material:
    material, new = _material("SA Ghost")
    if new:
        material.surface_render_method = "DITHERED"
    return material


def plate_material() -> bpy.types.Material:
    material, new = _material("SA Textured PEI")
    if new:
        tree = material.node_tree
        bsdf = _principled(material)
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 400.0
        noise.inputs["Detail"].default_value = 4.0
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*hex_to_linear("#5A4A32"), 1.0)
        ramp.color_ramp.elements[1].color = (*hex_to_linear("#A88C5A"), 1.0)
        bump = tree.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.2
        tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Roughness"].default_value = 0.7
    return material


def brass_material() -> bpy.types.Material:
    material, new = _material("SA Brass")
    if new:
        bsdf = _principled(material)
        bsdf.inputs["Base Color"].default_value = (*hex_to_linear("#B5893B"), 1.0)
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.3
    return material


def backdrop_material() -> bpy.types.Material:
    material, _ = _material("SA Backdrop")
    return material


def update_materials(scene) -> None:
    settings = scene.sliceranim
    color = tuple(settings.file_color) if settings.use_file_color else tuple(settings.color)
    roughness, specular, sheen, transmission = FINISHES[settings.finish]
    material = filament_material()
    bsdf = _principled(material)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = specular
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Emission Color"].default_value = (*settings.highlight_color, 1.0)
    strength = material.node_tree.nodes["SA Highlight Strength"]
    strength.inputs[1].default_value = HIGHLIGHT_STRENGTH if settings.highlight else 0.0
    ghost = _principled(ghost_material())
    ghost_color = color if settings.ghost_use_filament_color else tuple(settings.ghost_color)
    ghost.inputs["Base Color"].default_value = (*ghost_color, 1.0)
    ghost.inputs["Alpha"].default_value = settings.ghost_opacity
    ghost.inputs["Roughness"].default_value = 0.3
    _principled(backdrop_material()).inputs["Base Color"].default_value = (*settings.backdrop_color, 1.0)
    _principled(backdrop_material()).inputs["Roughness"].default_value = 0.8


def _part(settings) -> tuple[Vector, float]:
    """Part center (m) and bounding sphere radius (m)."""
    return Vector(settings.part_center) * MM, max(settings.part_radius * MM, 0.005)


def backdrop_mesh(radius: float, segments: int = 64) -> bpy.types.Mesh:
    """A round studio backdrop: a floor that curves up into a wall all around. Units: m."""
    bend = 0.3 * radius
    profile = [(radius * 0.001, 0.0), (radius - bend, 0.0)]
    for k in range(1, 12):
        a = k / 12 * math.pi / 2
        profile.append((radius - bend + bend * math.sin(a), bend - bend * math.cos(a)))
    profile += [(radius, bend), (radius, radius)]
    angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = [(r * math.cos(t), r * math.sin(t), z) for (r, z) in profile for t in angles]
    faces = []
    for i in range(len(profile) - 1):
        for j in range(segments):
            a, b = i * segments + j, i * segments + (j + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    mesh = bpy.data.meshes.new("SA Backdrop")
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth()
    mesh.materials.append(backdrop_material())
    return mesh


def nozzle_mesh() -> bpy.types.Mesh:
    """A cone with its tip at the origin and 6 mm high. Units: m."""
    segments = 24
    tip, top, height = 0.2 * MM, 3.5 * MM, NOZZLE_HEIGHT_MM * MM
    angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = [(tip * math.cos(t), tip * math.sin(t), 0.0) for t in angles]
    verts += [(top * math.cos(t), top * math.sin(t), height) for t in angles]
    verts += [(0.0, 0.0, 0.0), (0.0, 0.0, height)]
    faces = [(j, (j + 1) % segments, segments + (j + 1) % segments, segments + j) for j in range(segments)]
    faces += [(2 * segments, (j + 1) % segments, j) for j in range(segments)]
    faces += [(2 * segments + 1, segments + j, segments + (j + 1) % segments) for j in range(segments)]
    mesh = bpy.data.meshes.new("SA Nozzle Tip")
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth()
    mesh.materials.append(brass_material())
    return mesh


def plate_mesh() -> bpy.types.Mesh:
    half = PLATE_SIZE_MM / 2 * MM
    mesh = bpy.data.meshes.new("SA Plate Mat")
    mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
    mesh.materials.append(plate_material())
    return mesh


def _aim(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _update_lights(scene, center: Vector, radius: float) -> None:
    distance = max(4 * radius, 0.05)
    for name, (azimuth, elevation, factor) in LIGHTS.items():
        light = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
        light.shape = "DISK"
        light.size = 2 * radius
        light.energy = factor * distance**2
        obj = put_object(scene, name, light)
        a = START_AZIMUTH + azimuth
        obj.location = center + distance * Vector(
            (math.cos(elevation) * math.cos(a), math.cos(elevation) * math.sin(a), math.sin(elevation))
        )
        _aim(obj, center)


def write_nozzle_keys(scene) -> None:
    """Show the nozzle tip in Line shots only, with constant keys at the shot boundaries."""
    nozzle = bpy.data.objects.get("SA Nozzle Tip")
    if nozzle is None:
        return
    keys.remove(nozzle, {"hide_render", "hide_viewport"})
    ranges = json.loads(scene.sliceranim.line_frame_ranges or "[]")
    starts = {first for first, _ in ranges}
    hidden = {1: 1.0}
    for first, _ in ranges:
        hidden[first] = 0.0
    for _, last in ranges:
        if last + 1 not in starts:
            hidden[last + 1] = 1.0
    frames = sorted(hidden)
    values = [hidden[f] for f in frames]
    for path in ("hide_render", "hide_viewport"):
        keys.write(nozzle, path, frames, values, keys.CONSTANT)


def apply(scene) -> None:
    """Make the scene match the Look settings. Call this after any Look change."""
    settings = scene.sliceranim
    update_materials(scene)
    if settings.toolpath_object is None:
        return
    center, radius = _part(settings)
    floor = Vector((center.x, center.y, -0.2 * MM))
    if settings.backdrop:
        backdrop = put_object(scene, "SA Backdrop", backdrop_mesh(max(6 * radius, 0.05)))
        backdrop.location = floor
    else:
        remove_object("SA Backdrop")
    if settings.lights:
        _update_lights(scene, center, radius)
    else:
        for name in LIGHTS:
            remove_object(name)
    if settings.plate_mat:
        plate = put_object(scene, "SA Plate Mat", bpy.data.meshes.get("SA Plate Mat") or plate_mesh())
        if settings.plate_centered_on_part:
            plate.location = (center.x, center.y, 0.0)
        else:
            plate.location = (BAMBU_PLATE_CENTER_MM[0] * MM, BAMBU_PLATE_CENTER_MM[1] * MM, 0.0)
    else:
        remove_object("SA Plate Mat")
    if settings.nozzle and settings.head_object is not None:
        nozzle = put_object(scene, "SA Nozzle Tip", bpy.data.meshes.get("SA Nozzle Tip") or nozzle_mesh())
        nozzle.parent = settings.head_object
        nozzle.location = (0.0, 0.0, NOZZLE_LIFT_MM * MM)
        write_nozzle_keys(scene)
    else:
        remove_object("SA Nozzle Tip")
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `17 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/test_looks.py sliceranim/blender/keys.py sliceranim/blender/output.py sliceranim/blender/looks.py
git commit -m "Add looks, output settings, and the keyframe helper"
```

### Task 13: Shot cameras

Make one camera object per shot and key its location and rotation on the frames of that shot (spec section 9). My camera uses the user's camera without changes.

**Files:**
- Create: `sliceranim/blender/cameras.py`
- Test: `tests/blender/test_cameras.py`

**Interfaces:**
- Consumes: `camera_paths` (Task 9), `plan_frames`, `Shot` (Task 8), `keys`, `looks.put_object`, `looks.remove_object`, `output.resolution` (Task 12), `importer.toolpath_from_object` (Task 11), `setup()` from `tests/blender/test_looks.py`.
- Produces:
  - `cameras.TAG = "sliceranim_shot_camera"`, `cameras.LENS_MM = 50.0`, `cameras.SENSOR_MM = 36.0`.
  - `cameras.remove_shot_cameras()`, `cameras.framing(scene) -> (Bounds, distance_mm)`, `cameras.path_for_shot(scene, shot, head, previous) -> CameraPath`, `cameras.eulers(location, target) -> np.ndarray`, `cameras.build(scene, plan) -> list[Object]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/blender/test_cameras.py`:

```python
import math

import bpy
import numpy as np
from mathutils import Vector
from test_looks import setup

from sliceranim.blender import cameras, importer
from sliceranim.core.timing import Shot, plan_frames


def plan_for(s, rows):
    """Fill the shot list from (start, duration, style, camera) rows and plan the frames at 10 fps."""
    s.shots.clear()
    for start, duration, style, camera in rows:
        item = s.shots.add()
        item.start_at_end = start is None
        item.start_layer = start or 1
        item.duration, item.style, item.camera = duration, style, camera
    shots = [Shot(start, duration, style, camera) for start, duration, style, camera in rows]
    return plan_frames(importer.toolpath_from_object(s.toolpath_object), shots, 10)


def test_one_camera_per_shot_with_keys_on_its_own_frames():
    s = setup()
    plan = plan_for(s, [(1, 1.0, "LINE", "CLOSE_UP"), (2, 1.0, "LAYER", "TURNTABLE"), (None, 1.0, "HOLD", "REVEAL")])
    made = cameras.build(bpy.context.scene, plan)
    assert [c.name for c in made] == ["SA Shot 1 Camera", "SA Shot 2 Camera", "SA Shot 3 Camera"]
    assert all(c.get(cameras.TAG) for c in made)
    close_up = made[0]
    assert close_up.data.dof.use_dof and abs(close_up.data.dof.focus_distance - 0.03) < 1e-9
    bpy.context.scene.frame_set(15)
    orbit = made[1].matrix_world.translation
    center = np.array(s.part_center) * 0.001
    _, distance = cameras.framing(bpy.context.scene)
    assert abs(np.linalg.norm(np.array(orbit) - center) - distance * 0.001) < 1e-6


def test_cameras_look_at_their_target():
    s = setup()
    plan = plan_for(s, [(1, 1.0, "LAYER", "HERO"), (None, 1.0, "HOLD", "REVEAL")])
    made = cameras.build(bpy.context.scene, plan)
    bpy.context.scene.frame_set(1)
    camera = made[0]
    forward = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    to_center = Vector(s.part_center) * 0.001 - camera.matrix_world.translation
    assert forward.angle(to_center) < math.radians(0.01)


def test_rebuilding_cameras_removes_the_old_ones():
    s = setup()
    plan = plan_for(s, [(1, 1.0, "LAYER", "HERO"), (None, 1.0, "HOLD", "REVEAL")])
    cameras.build(bpy.context.scene, plan)
    cameras.build(bpy.context.scene, plan)
    assert len([o for o in bpy.data.objects if o.type == "CAMERA"]) == 2


def test_my_camera_is_used_as_is():
    s = setup()
    data = bpy.data.cameras.new("Mine")
    mine = bpy.data.objects.new("Mine", data)
    bpy.context.scene.collection.objects.link(mine)
    plan = plan_for(s, [(1, 1.0, "LAYER", "CUSTOM"), (None, 1.0, "HOLD", "REVEAL")])
    s.shots[0].custom_camera = mine
    made = cameras.build(bpy.context.scene, plan)
    assert made[0] == mine
    assert mine.animation_data is None
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'cameras' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/cameras.py`:

```python
"""One camera object per shot (spec section 9)."""

import bpy
import numpy as np
from mathutils import Euler, Vector

from ..core import camera_paths as paths
from ..core.timing import CLOSE_UP, CUSTOM, HERO, REVEAL, RISING, TURNTABLE
from . import keys, looks
from .output import resolution

MM = 0.001
LENS_MM = 50.0
SENSOR_MM = 36.0
TAG = "sliceranim_shot_camera"


def remove_shot_cameras() -> None:
    for obj in [o for o in bpy.data.objects if o.get(TAG)]:
        looks.remove_object(obj.name)


def framing(scene) -> tuple[paths.Bounds, float]:
    """Part bounds (mm) and the framing distance (mm) for the output aspect ratio."""
    settings = scene.sliceranim
    bounds = paths.Bounds(center=np.array(settings.part_center, dtype=np.float64), radius=settings.part_radius)
    width, height = resolution(settings)
    horizontal, vertical = paths.field_of_view(LENS_MM, SENSOR_MM, width, height)
    return bounds, paths.framing_distance(bounds.radius, min(horizontal, vertical))


def path_for_shot(scene, shot, head: np.ndarray, previous) -> paths.CameraPath:
    """Camera path of one shot. `head` is the print head (mm) for each frame of the shot."""
    bounds, distance = framing(scene)
    count = len(head)
    if shot.camera == TURNTABLE:
        return paths.turntable(bounds, distance, count, turns=shot.orbit_turns,
                               height_angle=shot.orbit_height, clockwise=shot.orbit_clockwise)
    if shot.camera == HERO:
        return paths.hero(bounds, distance, count, height_angle=shot.hero_height, side_angle=shot.hero_side)
    if shot.camera == RISING:
        return paths.rising_follow(bounds, shot.rising_distance or distance, head[:, 2], height_angle=shot.rising_height)
    if shot.camera == CLOSE_UP:
        if shot.closeup_target == "CURSOR":
            targets = np.tile(np.array(scene.cursor.location) / MM, (count, 1))
        else:
            targets = head
        return paths.close_up(targets, distance=shot.closeup_distance, smoothing=shot.closeup_smoothing)
    if shot.camera == REVEAL:
        return paths.final_reveal(bounds, distance, count, previous, spin=shot.reveal_spin,
                                  pullback_share=shot.reveal_pullback / 100.0)
    raise ValueError(shot.camera)


def eulers(location: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Rotation of a camera at `location` that looks at `target`, one Euler per frame, without flips."""
    out = np.zeros((len(location), 3))
    previous = Euler()
    for i, (here, there) in enumerate(zip(location, target)):
        previous = (Vector(there) - Vector(here)).to_track_quat("-Z", "Y").to_euler("XYZ", previous)
        out[i] = previous
    return out


def _custom_pose(scene, obj) -> tuple[np.ndarray, np.ndarray]:
    _, distance = framing(scene)
    matrix = obj.matrix_world
    location = np.array(matrix.translation) / MM
    forward = np.array(matrix.to_quaternion() @ Vector((0, 0, -1)))
    return location, location + forward * distance


def build(scene, plan) -> list:
    """Make one camera per shot with keyframes for its frames. Return the camera objects in shot order."""
    remove_shot_cameras()
    settings = scene.sliceranim
    result = []
    previous = None
    for row, shot in enumerate(settings.shots):
        first = plan.shot_first_frame[row]
        count = plan.shot_frame_count[row]
        if shot.camera == CUSTOM:
            result.append(shot.custom_camera)
            previous = _custom_pose(scene, shot.custom_camera)
            continue
        head = plan.head[first - 1 : first - 1 + count]
        path = path_for_shot(scene, shot, head, previous)
        data = bpy.data.cameras.new(f"SA Shot {row + 1}")
        data.lens = LENS_MM
        data.sensor_width = SENSOR_MM
        data.clip_start = 0.001
        data.clip_end = 1000.0
        if shot.camera == CLOSE_UP and shot.closeup_dof:
            data.dof.use_dof = True
            data.dof.aperture_fstop = shot.closeup_fstop
            data.dof.focus_distance = shot.closeup_distance * MM
        obj = looks.put_object(scene, f"SA Shot {row + 1} Camera", data)
        obj[TAG] = True
        frames = np.arange(first, first + count)
        keys.write_vector(obj, "location", frames, path.location * MM, keys.LINEAR)
        keys.write_vector(obj, "rotation_euler", frames, eulers(path.location, path.target), keys.LINEAR)
        previous = (path.location[-1], path.target[-1])
        result.append(obj)
    return result
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `21 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/test_cameras.py sliceranim/blender/cameras.py
git commit -m "Add one camera per shot"
```

### Task 14: Rebuild and import

Write all of spec 8.5 (Rebuild) and the complete import flow: read a source, merge, build the object, make the default shot list, apply the looks, and run Rebuild. The importer replaces the partial `importer.py` from Task 11.

**Files:**
- Create: `sliceranim/blender/shots.py`
- Modify: `sliceranim/blender/importer.py`
- Modify: `tests/blender/helpers.py`
- Test: `tests/blender/test_import.py`
- Test: `tests/blender/test_shots.py`

**Interfaces:**
- Consumes: Everything from Tasks 1 to 13.
- Produces:
  - `shots.MARKER_PREFIX = "SA Shot "`, `shots.shots_from_settings(settings) -> list[Shot]`, `shots.fill_default_shots(settings, layer_count)`, `shots.problems(scene) -> list[ShotProblem]`, `shots.signature(scene) -> str`, `shots.needs_rebuild(scene) -> bool`, `shots.clear(scene)`, `shots.rebuild(scene) -> FramePlan`.
  - `importer.POLYGON_LIMIT = 10_000_000`, `importer.Loaded(tp, kind, source_path, label, open_edges=False, source_mesh=None)`, `importer.slice_dir(project) -> Path`, `importer.read_file(context, filepath) -> Loaded`, `importer.read_mesh_object(context, obj) -> Loaded`, `importer.reload_source(context) -> Loaded`, `importer.prepare(context, loaded) -> ToolpathSet`, `importer.build(context, loaded, tp, *, keep_shots) -> Object`.
  - Test helpers `load(path)`, `polygons_at(frame)`, `keyframes(id_data, data_path, index=0)`, `box_object(name="Box", size=0.01)`.

Plan details that the spec leaves open:

1. The toolpath object is named `<file name> Toolpaths`, so it never takes the name of a user object.
2. Headless slicing writes to `<blend directory>/slices/<project name>/`, so two projects do not overwrite each other's `plate_1.gcode`.
3. The fallback slicer hides the source mesh (viewport and render), so it does not cover the animation.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/blender/helpers.py`:

```python
def load(path) -> None:
    """Load a file the way the Open File button does, without the polygon warning."""
    from sliceranim.blender import importer

    loaded = importer.read_file(bpy.context, str(path))
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)


def polygons_at(frame: int) -> int:
    bpy.context.scene.frame_set(frame)
    return evaluated_polygons(settings().toolpath_object)


def keyframes(id_data, data_path: str, index: int = 0) -> np.ndarray:
    """(frame, value) pairs of one channel."""
    from bpy_extras import anim_utils

    data = id_data.animation_data
    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find(data_path, index=index)
    co = np.empty(len(curve.keyframe_points) * 2, dtype=np.float32)
    curve.keyframe_points.foreach_get("co", co)
    return co.reshape(-1, 2)


def box_object(name: str = "Box", size: float = 0.01):
    """A closed box mesh object of `size` meters on z = 0. It becomes the active object."""
    s = size
    verts = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj
```

Create `tests/blender/test_import.py`:

```python
import tempfile
import zipfile
from pathlib import Path

import bpy
import numpy as np
from helpers import CUBE, box_object, keyframes, load, polygons_at, settings

from sliceranim.blender import importer, nodes
from sliceranim.core.errors import SlicerAnimError


def test_gcode_import_fills_the_source_summary():
    load(CUBE)
    s = settings()
    assert s.toolpath_object.name == "cube_3_layers Toolpaths"
    assert (s.layer_count, s.point_count) == (3, 42)
    assert s.slicer == "Bambu Studio 02.08.02.61"
    assert s.source_kind == "GCODE" and s.source_path == str(CUBE)
    np.testing.assert_allclose(s.file_color, (0.0129830, 0.2462013, 0.7835378), rtol=1e-4)  # #1E88E5
    assert abs(nodes.get_input(s.toolpath_object, "Profile Aspect") - 0.2 / 0.45) < 1e-6


def test_import_makes_the_short_print_shot_list_and_runs_rebuild():
    load(CUBE)
    scene = bpy.context.scene
    assert [(x.start_at_end, x.style, x.camera) for x in settings().shots] == [
        (False, "LINE", "TURNTABLE"),
        (True, "HOLD", "REVEAL"),
    ]
    assert (scene.frame_start, scene.frame_end) == (1, 720)
    assert [m.frame for m in scene.timeline_markers] == [1, 601]
    assert scene.render.engine == "BLENDER_EEVEE"


def test_the_build_grows_frame_by_frame():
    load(CUBE)
    assert polygons_at(720) == 30 * 4
    assert 0 < polygons_at(300) < 30 * 4
    obj = settings().toolpath_object
    progress = keyframes(obj, nodes.input_path(obj, "Progress"))
    assert len(progress) == 720 and progress[-1, 1] == 42
    assert np.all(np.diff(progress[:, 1]) >= 0)


def test_a_second_import_replaces_the_first():
    load(CUBE)
    load(CUBE)
    assert len([o for o in bpy.data.objects if o.name.endswith("Toolpaths")]) == 1


def test_sliced_3mf_loads_like_gcode():
    path = Path(tempfile.mkdtemp()) / "part.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", CUBE.read_text())
    load(path)
    assert settings().source_kind == "SLICED_3MF"
    assert settings().layer_count == 3


def test_mesh_object_goes_through_the_fallback_slicer():
    box = box_object(size=0.01)
    loaded = importer.read_mesh_object(bpy.context, box)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=False)
    s = settings()
    assert s.used_fallback and s.plate_centered_on_part
    assert (s.layer_count, s.source_kind) == (50, "MESH")
    assert box.hide_render
    assert len(settings().shots) == 4


def test_reload_reads_the_source_again_and_keeps_the_shots():
    load(CUBE)
    s = settings()
    s.shots[0].duration = 7.0
    s.merge_angle = 0.0
    loaded = importer.reload_source(bpy.context)
    importer.build(bpy.context, loaded, importer.prepare(bpy.context, loaded), keep_shots=True)
    assert s.shots[0].duration == 7.0
    assert s.built_merge_angle == 0.0


def test_reload_with_a_missing_source_raises_the_spec_error():
    copy = Path(tempfile.mkdtemp()) / "gone.gcode"
    copy.write_text(CUBE.read_text())
    load(copy)
    copy.unlink()
    try:
        importer.reload_source(bpy.context)
    except SlicerAnimError as error:
        assert str(error) == f"Source file not found: {copy}. Open the file again."
    else:
        raise AssertionError("no error")


def test_upper_case_file_extension_is_accepted():
    copy = Path(tempfile.mkdtemp()) / "PART.GCODE"
    copy.write_text(CUBE.read_text())
    load(copy)
    assert settings().layer_count == 3


def test_scaled_mesh_object_is_sliced_at_its_world_size():
    box = box_object(size=0.01)
    box.scale = (1.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    loaded = importer.read_mesh_object(bpy.context, box)
    assert loaded.tp.layer_count == 100  # 20 mm high at 0.2 mm per layer
```

Create `tests/blender/test_shots.py`:

```python
import json

import bpy
import numpy as np
from helpers import CUBE, keyframes, load, settings

from sliceranim.blender import shots
from sliceranim.core.errors import SlicerAnimError


def test_invalid_shot_list_is_reported_and_blocks_rebuild():
    load(CUBE)
    settings().shots[0].start_layer = 2
    assert [(p.row, p.rule) for p in shots.problems(bpy.context.scene)] == [(0, 1)]
    try:
        shots.rebuild(bpy.context.scene)
    except SlicerAnimError as error:
        assert str(error) == "The first shot must start at layer 1."
    else:
        raise AssertionError("rebuild did not refuse the bad shot list")


def test_rebuild_replaces_only_its_own_markers_and_cameras():
    load(CUBE)
    scene = bpy.context.scene
    scene.timeline_markers.new("My marker", frame=50)
    shots.rebuild(scene)
    shots.rebuild(scene)
    assert sorted(m.name for m in scene.timeline_markers) == ["My marker", "SA Shot 1", "SA Shot 2"]
    assert len([o for o in bpy.data.objects if o.type == "CAMERA"]) == 2
    assert all(m.camera is not None for m in scene.timeline_markers if m.name.startswith("SA Shot"))


def test_frame_rate_and_durations_set_the_frame_range():
    load(CUBE)
    settings().fps = "24"
    settings().shots[0].duration = 5.0
    shots.rebuild(bpy.context.scene)
    assert bpy.context.scene.frame_end == 24 * 9
    assert bpy.context.scene.render.fps == 24


def test_line_shots_use_linear_keys_and_other_shots_constant_keys():
    load(CUBE)
    obj = settings().toolpath_object
    from bpy_extras import anim_utils
    from sliceranim.blender import nodes

    data = obj.animation_data
    curve = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot).fcurves.find(
        nodes.input_path(obj, "Progress")
    )
    assert curve.keyframe_points[0].interpolation == "LINEAR"
    assert curve.keyframe_points[650].interpolation == "CONSTANT"


def test_my_camera_needs_a_camera_object():
    load(CUBE)
    s = settings()
    s.shots[0].camera = "CUSTOM"
    assert [p.message for p in shots.problems(bpy.context.scene)] == ["Choose a camera object for My camera."]
    mine = bpy.data.objects.new("Mine", bpy.data.cameras.new("Mine"))
    bpy.context.scene.collection.objects.link(mine)
    s.shots[0].custom_camera = mine
    shots.rebuild(bpy.context.scene)
    assert bpy.context.scene.timeline_markers["SA Shot 1"].camera == mine


def test_nozzle_keys_follow_the_line_shots():
    load(CUBE)
    s = settings()
    s.nozzle = True
    assert json.loads(s.line_frame_ranges) == [[1, 600]]
    assert keyframes(bpy.data.objects["SA Nozzle Tip"], "hide_render").tolist() == [[1.0, 0.0], [601.0, 1.0]]


def test_head_moves_during_the_line_shot():
    load(CUBE)
    head = keyframes(settings().head_object, "location", 0)
    assert np.ptp(head[:600, 1]) > 0


def test_needs_rebuild_tracks_changes_that_rebuild_reads():
    load(CUBE)
    scene = bpy.context.scene
    assert not shots.needs_rebuild(scene)
    settings().shots[0].duration = 10.0
    assert shots.needs_rebuild(scene)
    shots.rebuild(scene)
    settings().format_preset = "SQUARE"  # cameras depend on the aspect ratio
    assert shots.needs_rebuild(scene)
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'shots' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/shots.py`:

```python
"""Rebuild: write keyframes, markers, and cameras from the shot list (spec 8.5)."""

import hashlib
import json

import bpy
import numpy as np

from ..core.errors import SlicerAnimError
from ..core.timing import CUSTOM, LINE, Shot, ShotProblem, default_shots, plan_frames, validate_shots
from . import cameras, keys, looks, nodes, output

MM = 0.001
MARKER_PREFIX = "SA Shot "


def shots_from_settings(settings) -> list[Shot]:
    return [
        Shot(None if s.start_at_end else s.start_layer, s.duration, s.style, s.camera)
        for s in settings.shots
    ]


def fill_default_shots(settings, layer_count: int) -> None:
    settings.shots.clear()
    for shot in default_shots(layer_count):
        item = settings.shots.add()
        item.start_at_end = shot.start_layer is None
        item.start_layer = shot.start_layer or layer_count
        item.duration = shot.duration
        item.style = shot.style
        item.camera = shot.camera
    settings.active_shot = 0


def problems(scene) -> list[ShotProblem]:
    settings = scene.sliceranim
    if settings.toolpath_object is None:
        return [ShotProblem(-1, 0, "Load a file first.")]
    found = validate_shots(shots_from_settings(settings), settings.layer_count)
    for row, shot in enumerate(settings.shots):
        if shot.camera == CUSTOM and shot.custom_camera is None:
            found.append(ShotProblem(row, 0, "Choose a camera object for My camera."))
    return found


def signature(scene) -> str:
    """A fingerprint of everything that Rebuild reads. Preview compares it to see if Rebuild must run."""
    settings = scene.sliceranim
    data = {
        "shots": [{k: _plain(getattr(s, k)) for k in s.bl_rna.properties.keys() if k not in ("rna_type", "name")}
                  for s in settings.shots],
        "fps": settings.fps,
        "size": output.resolution(settings),
        "points": settings.point_count,
        "merge": round(settings.built_merge_angle, 6),
        "radius": round(settings.part_radius, 6),
        "cursor": [round(v, 6) for v in scene.cursor.location],
        "object": settings.toolpath_object.name if settings.toolpath_object else "",
    }
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _plain(value):
    if isinstance(value, bpy.types.ID):
        return value.name
    if hasattr(value, "__len__") and not isinstance(value, str):
        return [round(v, 6) for v in value]
    return round(value, 6) if isinstance(value, float) else value


def needs_rebuild(scene) -> bool:
    return scene.sliceranim.rebuild_signature != signature(scene)


def clear(scene) -> None:
    """Delete the markers, keyframes, and cameras that the last Rebuild made."""
    settings = scene.sliceranim
    for marker in [m for m in scene.timeline_markers if m.name.startswith(MARKER_PREFIX)]:
        scene.timeline_markers.remove(marker)
    obj = settings.toolpath_object
    if obj is not None:
        keys.remove(obj, {nodes.input_path(obj, "Progress"), nodes.input_path(obj, "Current Layer")})
    if settings.head_object is not None:
        keys.remove(settings.head_object, {"location"})
    cameras.remove_shot_cameras()


def rebuild(scene):
    """Write everything in spec 8.5. Raise SlicerAnimError when the shot list is not valid."""
    from . import importer

    found = problems(scene)
    if found:
        raise SlicerAnimError(found[0].message)
    settings = scene.sliceranim
    output.apply(scene)
    obj = settings.toolpath_object
    tp = importer.toolpath_from_object(obj)
    shot_list = shots_from_settings(settings)
    plan = plan_frames(tp, shot_list, int(settings.fps))
    clear(scene)
    frames = np.arange(1, plan.frame_count + 1)
    is_line = np.array([shot_list[i].style == LINE for i in plan.shot_index])
    keys.write(obj, nodes.input_path(obj, "Progress"), frames, plan.progress,
               np.where(is_line, keys.LINEAR, keys.CONSTANT))
    keys.write(obj, nodes.input_path(obj, "Current Layer"), frames, plan.current_layer, keys.CONSTANT)
    keys.write_vector(settings.head_object, "location", frames, plan.head * MM, keys.LINEAR)
    shot_cameras = cameras.build(scene, plan)
    for row, camera in enumerate(shot_cameras):
        marker = scene.timeline_markers.new(f"{MARKER_PREFIX}{row + 1}", frame=plan.shot_first_frame[row])
        marker.camera = camera
    scene.frame_start = 1
    scene.frame_end = plan.frame_count
    scene.camera = shot_cameras[0]
    settings.line_frame_ranges = json.dumps([
        [first, first + count - 1]
        for first, count, shot in zip(plan.shot_first_frame, plan.shot_frame_count, shot_list)
        if shot.style == LINE
    ])
    looks.write_nozzle_keys(scene)
    settings.rebuild_signature = signature(scene)
    scene.frame_set(scene.frame_current)
    return plan
```

Replace all of `sliceranim/blender/importer.py` with:

```python
"""Read a source and build the toolpath object (spec sections 6, 7, and 11.2)."""

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np

from ..core import bambu_cli, threemf
from ..core.camera_paths import part_bounds
from ..core.errors import SlicerAnimError, source_missing
from ..core.gcode_reader import read_gcode
from ..core.mesh_slicer import read_stl, slice_mesh
from ..core.timing import validate_shots
from ..core.toolpaths import ToolpathSet, merge_points, pack
from . import looks, nodes, output, prefs, shots

MM = 0.001
POLYGON_LIMIT = 10_000_000
HEAD = "SA Print Head"
ATTRIBUTES = (
    # name, Blender type, ToolpathSet field, scale
    ("layer", "INT", "layer", None),
    ("feature", "INT", "feature", None),
    ("tool", "INT", "tool", None),
    ("width", "FLOAT", "width", MM),
    ("height", "FLOAT", "height", MM),
    ("time", "FLOAT", "time", None),
)


@dataclass
class Loaded:
    tp: ToolpathSet
    kind: str  # GCODE, SLICED_3MF, PROJECT, STL, or MESH
    source_path: str  # the file that Reload reads
    label: str  # file or object name for the panel and the object name
    open_edges: bool = False
    source_mesh: object = None


def slice_dir(project: Path) -> Path:
    """`<blend directory>/slices/<project name>/` when the .blend file is saved, else a temporary directory."""
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent / "slices" / project.stem
    return Path(tempfile.mkdtemp(prefix="sliceranim_"))


def read_file(context, filepath: str) -> Loaded:
    path = Path(bpy.path.abspath(filepath))
    if not path.is_file():
        raise source_missing(str(path))
    name = path.name.lower()
    if name.endswith(".gcode"):
        return Loaded(read_gcode(path), "GCODE", str(path), path.name)
    if name.endswith(".3mf"):
        info = threemf.inspect_3mf(path)
        threemf.require_one_plate(info)
        if info.kind == threemf.SLICED:
            return Loaded(threemf.read_sliced_3mf(path), "SLICED_3MF", str(path), path.name)
        bambu = bambu_cli.find_bambu(prefs.bambu_path(context))
        gcode = bambu_cli.slice_project(path, slice_dir(path), bambu)
        return Loaded(read_gcode(gcode), "PROJECT", str(gcode), path.name)
    if name.endswith(".stl"):
        vertices, triangles = read_stl(path)
        tp, open_edges = slice_mesh(vertices, triangles)
        return Loaded(tp, "STL", str(path), path.name, open_edges)
    raise SlicerAnimError(f"Unsupported file type: {path.suffix}. Use .gcode, .gcode.3mf, .3mf, or .stl.")


def read_mesh_object(context, obj) -> Loaded:
    """Run the fallback slicer on a mesh object. Blender units become mm through the scene unit scale."""
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
        triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles)
    finally:
        evaluated.to_mesh_clear()
    matrix = np.array(obj.matrix_world)
    world = co.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]
    scale = context.scene.unit_settings.scale_length / MM
    tp, open_edges = slice_mesh(world * scale, triangles.reshape(-1, 3))
    return Loaded(tp, "MESH", "", obj.name, open_edges, obj)


def reload_source(context) -> Loaded:
    """Read the source of the current toolpath object again (spec section 7, Reload)."""
    settings = context.scene.sliceranim
    if settings.source_kind == "MESH":
        if settings.source_mesh is None:
            raise source_missing(settings.source_label)
        return read_mesh_object(context, settings.source_mesh)
    path = Path(settings.source_path)
    if not path.is_file():
        raise source_missing(str(path))
    if settings.source_kind == "SLICED_3MF":
        tp = threemf.read_sliced_3mf(path)
    elif settings.source_kind == "STL":
        tp, open_edges = slice_mesh(*read_stl(path))
        return Loaded(tp, "STL", str(path), settings.source_label, open_edges)
    else:
        tp = read_gcode(path)
    return Loaded(tp, settings.source_kind, str(path), settings.source_label)


def prepare(context, loaded: Loaded) -> ToolpathSet:
    """Merge points with the Merge angle from the panel."""
    return merge_points(loaded.tp, math.degrees(context.scene.sliceranim.merge_angle))


def toolpath_mesh(tp: ToolpathSet, name: str) -> bpy.types.Mesh:
    """One vertex per point (in meters), one edge per strand, and the point attributes."""
    n = tp.point_count
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(n)
    mesh.vertices.foreach_set("co", (tp.position.astype(np.float64) * MM).astype(np.float32).ravel())
    first = np.arange(n - 1, dtype=np.int32)[~tp.run_start_mask()[1:]]
    mesh.edges.add(len(first))
    mesh.edges.foreach_set("vertices", np.column_stack([first, first + 1]).ravel())
    mesh.attributes.new("order", "INT", "POINT").data.foreach_set("value", np.arange(n, dtype=np.int32))
    for attr, kind, field, scale in ATTRIBUTES:
        values = getattr(tp, field).astype(np.float64)
        if scale:
            values = values * scale
        dtype = np.int32 if kind == "INT" else np.float32
        mesh.attributes.new(attr, kind, "POINT").data.foreach_set("value", values.astype(dtype))
    mesh.update()
    return mesh


def _read_attribute(mesh, name: str, dtype) -> np.ndarray:
    values = np.empty(len(mesh.vertices), dtype=dtype)
    mesh.attributes[name].data.foreach_get("value", values)
    return values


def toolpath_from_object(obj) -> ToolpathSet:
    """Read the ToolpathSet back from the toolpath object. Rebuild needs no source file."""
    mesh = obj.data
    n = len(mesh.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edges)
    starts = np.ones(n, dtype=bool)
    starts[edges.reshape(-1, 2)[:, 1]] = False
    return pack(
        position=co.reshape(-1, 3).astype(np.float64) / MM,
        layer=_read_attribute(mesh, "layer", np.int32),
        feature=_read_attribute(mesh, "feature", np.int32),
        tool=_read_attribute(mesh, "tool", np.int32),
        width=_read_attribute(mesh, "width", np.float32) / MM,
        height=_read_attribute(mesh, "height", np.float32) / MM,
        time=_read_attribute(mesh, "time", np.float32),
        object_id=np.zeros(n),
        run_start=np.flatnonzero(starts),
    )


def _file_color(tp: ToolpathSet) -> tuple[float, float, float]:
    colors = tp.meta.get("filament_colors") or []
    tool = int(tp.tool[0]) if tp.point_count else 0
    if not colors:
        return looks.hex_to_linear("#808080")
    try:
        return looks.hex_to_linear(colors[tool if tool < len(colors) else 0][:7])
    except ValueError:
        return looks.hex_to_linear("#808080")


def _remove_toolpath_object(settings) -> None:
    obj = settings.toolpath_object
    if obj is None:
        return
    settings.toolpath_object = None
    looks.remove_object(obj.name)


def build(context, loaded: Loaded, tp: ToolpathSet, *, keep_shots: bool) -> bpy.types.Object:
    """Build the toolpath object and everything around it, then run Rebuild."""
    scene = context.scene
    settings = scene.sliceranim
    _remove_toolpath_object(settings)
    name = f"{Path(loaded.label).name.split('.')[0]} Toolpaths".strip()
    obj = looks.put_object(scene, name, toolpath_mesh(tp, name))
    nodes.ensure_modifier(obj, looks.filament_material(), looks.ghost_material())
    nodes.set_input(obj, "Profile Aspect", float(np.median(tp.height) / np.median(tp.width)))
    head = looks.put_object(scene, HEAD, None)
    head.empty_display_size = 0.002
    bounds = part_bounds(tp.position)
    settings.toolpath_object = obj
    settings.head_object = head
    settings.source_kind = loaded.kind
    settings.source_path = loaded.source_path
    settings.source_label = loaded.label
    settings.source_mesh = loaded.source_mesh
    settings.slicer = " ".join(v for v in (tp.meta.get("slicer", ""), tp.meta.get("slicer_version", "")) if v)
    settings.layer_count = tp.layer_count
    settings.point_count = tp.point_count
    settings.print_time = tp.total_time
    settings.used_fallback = bool(tp.meta.get("fallback"))
    settings.plate_centered_on_part = bool(tp.meta.get("fallback"))
    settings.built_merge_angle = math.radians(tp.meta.get("merge_angle", 0.0))
    settings.part_center = bounds.center.tolist()
    settings.part_radius = bounds.radius
    settings.file_color = _file_color(tp)
    current = shots.shots_from_settings(settings)
    if not keep_shots or not current or validate_shots(current, tp.layer_count):
        shots.fill_default_shots(settings, tp.layer_count)
    if not settings.engine_set:
        scene.render.engine = "BLENDER_EEVEE"
        settings.engine_set = True
    if loaded.source_mesh is not None:
        loaded.source_mesh.hide_set(True)
        loaded.source_mesh.hide_render = True
    nodes.apply_settings(scene)
    looks.apply(scene)
    output.apply(scene)
    shots.rebuild(scene)
    return obj
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `39 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/helpers.py tests/blender/test_import.py tests/blender/test_shots.py sliceranim/blender/shots.py sliceranim/blender/importer.py
git commit -m "Add Rebuild and the import flow"
```

### Task 15: Preview

Add the Preview button of spec 11.4. It runs Rebuild when needed, looks through the scene camera with Material Preview shading and the scene lights and world, drops frames to keep real speed, and plays from frame 1. The same button then reads Exit Preview and restores the view.

**Files:**
- Create: `sliceranim/blender/preview.py`
- Modify: `sliceranim/blender/__init__.py`
- Test: `tests/blender/test_preview.py`

**Interfaces:**
- Consumes: `shots.needs_rebuild`, `shots.rebuild` (Task 14).
- Produces:
  - `preview.find_view3d(screen)`, `preview.start(context)`, `preview.stop(context)`, `preview.SLICERANIM_OT_preview` (`sliceranim.preview`), `preview.CLASSES`.

Blender in background mode (`-b`) still has one window with a 3D view, so these tests can run Preview and Exit Preview.

- [ ] **Step 1: Write the failing tests**

Create `tests/blender/test_preview.py`:

```python
import bpy
from helpers import CUBE, load, settings

from sliceranim.blender import preview, shots


def view3d_space():
    return preview.find_view3d(bpy.context.screen).spaces.active


def test_preview_switches_the_view_and_exit_restores_it():
    load(CUBE)
    space = view3d_space()
    space.shading.type = "SOLID"
    space.region_3d.view_perspective = "PERSP"
    bpy.context.scene.sync_mode = "AUDIO_SYNC"
    assert bpy.ops.sliceranim.preview() == {"FINISHED"}
    assert settings().preview_active
    assert space.shading.type == "MATERIAL"
    assert space.shading.use_scene_lights and space.shading.use_scene_world
    assert space.region_3d.view_perspective == "CAMERA"
    assert bpy.context.scene.sync_mode == "FRAME_DROP"
    assert bpy.ops.sliceranim.preview() == {"FINISHED"}  # the same button is Exit Preview now
    assert not settings().preview_active
    assert space.shading.type == "SOLID"
    assert space.region_3d.view_perspective == "PERSP"
    assert bpy.context.scene.sync_mode == "AUDIO_SYNC"


def test_preview_runs_rebuild_first_when_the_shots_changed():
    load(CUBE)
    settings().shots[0].duration = 10.0
    assert shots.needs_rebuild(bpy.context.scene)
    bpy.ops.sliceranim.preview()
    assert not shots.needs_rebuild(bpy.context.scene)
    assert bpy.context.scene.frame_end == 14 * 30
    bpy.ops.sliceranim.preview()


def test_preview_is_off_without_a_toolpath_object():
    assert not bpy.ops.sliceranim.preview.poll()
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'preview' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/preview.py`:

```python
"""Preview: play the video in the 3D view without a render (spec 11.4)."""

import json

import bpy

from ..core.errors import SlicerAnimError
from . import shots


def find_view3d(screen):
    return next((area for area in screen.areas if area.type == "VIEW_3D"), None)


def start(context) -> None:
    scene = context.scene
    settings = scene.sliceranim
    area = context.area if context.area and context.area.type == "VIEW_3D" else find_view3d(context.screen)
    if area is None:
        raise SlicerAnimError("Open a 3D view to preview.")
    if shots.needs_rebuild(scene):
        shots.rebuild(scene)
    space = area.spaces.active
    state = {
        "area": list(context.screen.areas).index(area),
        "perspective": space.region_3d.view_perspective,
        "shading": space.shading.type,
        "scene_lights": space.shading.use_scene_lights,
        "scene_world": space.shading.use_scene_world,
        "sync": scene.sync_mode,
    }
    settings.preview_state = json.dumps(state)
    scene.sync_mode = "FRAME_DROP"
    space.shading.type = "MATERIAL"
    space.shading.use_scene_lights = True
    space.shading.use_scene_world = True
    scene.frame_set(1)
    space.region_3d.view_perspective = "CAMERA"
    settings.preview_active = True
    if not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def stop(context) -> None:
    scene = context.scene
    settings = scene.sliceranim
    if context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=False)
    state = json.loads(settings.preview_state or "{}")
    areas = list(context.screen.areas)
    if state and state["area"] < len(areas) and areas[state["area"]].type == "VIEW_3D":
        space = areas[state["area"]].spaces.active
        space.region_3d.view_perspective = state["perspective"]
        space.shading.type = state["shading"]
        space.shading.use_scene_lights = state["scene_lights"]
        space.shading.use_scene_world = state["scene_world"]
    if state:
        scene.sync_mode = state["sync"]
    settings.preview_active = False
    settings.preview_state = ""


class SLICERANIM_OT_preview(bpy.types.Operator):
    """Play the video in the 3D view. Click again to stop"""

    bl_idname = "sliceranim.preview"
    bl_label = "Preview"

    @classmethod
    def poll(cls, context):
        return context.scene.sliceranim.toolpath_object is not None and context.screen is not None

    def execute(self, context):
        try:
            if context.scene.sliceranim.preview_active:
                stop(context)
            else:
                start(context)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (SLICERANIM_OT_preview,)
```

Replace all of `sliceranim/blender/__init__.py` with:

```python
"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import prefs, preview, props

CLASSES = (prefs.SLICERANIM_AP_preferences, *preview.CLASSES)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `42 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/test_preview.py sliceranim/blender/preview.py sliceranim/blender/__init__.py
git commit -m "Add Preview in the 3D view"
```

### Task 16: Panel, operators, import menu, and drag and drop

Add the sidebar tab "Slicer Anim" with its four sections (spec 11.3), all operators, the File > Import entry, and drag and drop of `.gcode` and `.3mf` files (spec 11.2). The load operator takes `directory` and `files`, which is the pattern that Blender file handlers use for drag and drop.

**Files:**
- Create: `sliceranim/blender/ui.py`
- Modify: `sliceranim/blender/__init__.py`
- Test: `tests/blender/test_operators.py`

**Interfaces:**
- Consumes: `importer`, `shots` (Task 14), `preview` (Task 15), `output` (Task 12), `estimate_polygons` (Task 3).
- Produces:
  - Operators: `sliceranim.load_file`, `sliceranim.use_selected`, `sliceranim.reload`, `sliceranim.confirm_large`, `sliceranim.shot_add`, `sliceranim.shot_remove`, `sliceranim.shot_move`, `sliceranim.rebuild`, `sliceranim.render`. The load operators take `confirm_large` (bool).
  - `ui.ask_to_confirm()`, `ui._pending` (the print that waits for the large-print confirmation), `ui.menu_import`, `ui.CLASSES`.

In background mode, an operator that reports an error raises `RuntimeError` with the message. The tests use `expect_error()` for this.

- [ ] **Step 1: Write the failing tests**

Create `tests/blender/test_operators.py`:

```python
import math
import tempfile
import zipfile
from pathlib import Path

import bpy
from helpers import CUBE, box_object, settings

from sliceranim.blender import importer, ui


def run_load(path, **extra):
    path = Path(path)
    return bpy.ops.sliceranim.load_file(directory=str(path.parent), files=[{"name": path.name}], **extra)


def expect_error(call, text: str) -> None:
    """In background mode, an operator that reports an error raises RuntimeError."""
    try:
        call()
    except RuntimeError as error:
        assert text in str(error), str(error)
        return
    raise AssertionError("the operator did not report an error")


def test_open_file_operator_loads_gcode():
    assert run_load(CUBE) == {"FINISHED"}
    assert settings().layer_count == 3


def test_open_file_shows_the_two_plate_error():
    path = Path(tempfile.mkdtemp()) / "two.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "")
        archive.writestr("Metadata/plate_2.gcode", "")
    expect_error(lambda: run_load(path), "This file has 2 plates. Export one plate from your slicer and try again.")
    assert settings().toolpath_object is None


def test_large_print_waits_for_confirmation():
    limit, ask = importer.POLYGON_LIMIT, ui.ask_to_confirm
    asked = []
    importer.POLYGON_LIMIT = 10
    ui.ask_to_confirm = lambda: asked.append(True)  # the popup needs a person to click
    try:
        assert run_load(CUBE) == {"CANCELLED"}
        assert asked == [True]
        assert settings().toolpath_object is None
        assert ui._pending["polygons"] == 42 * 6
        assert bpy.ops.sliceranim.confirm_large() == {"FINISHED"}
        assert settings().layer_count == 3
    finally:
        importer.POLYGON_LIMIT, ui.ask_to_confirm = limit, ask
        ui._pending.clear()


def test_use_selected_object_operator():
    box_object()
    assert bpy.ops.sliceranim.use_selected() == {"FINISHED"}
    assert settings().used_fallback


def test_reload_operator_and_missing_source():
    copy = Path(tempfile.mkdtemp()) / "gone.gcode"
    copy.write_text(CUBE.read_text())
    run_load(copy)
    settings().merge_angle = math.radians(5)
    assert bpy.ops.sliceranim.reload() == {"FINISHED"}
    copy.unlink()
    expect_error(bpy.ops.sliceranim.reload, f"Source file not found: {copy}. Open the file again.")


def test_rebuild_button_is_off_while_the_shot_list_is_bad():
    run_load(CUBE)
    assert bpy.ops.sliceranim.rebuild.poll()
    settings().shots[0].duration = 0.0
    assert not bpy.ops.sliceranim.rebuild.poll()
    assert not bpy.ops.sliceranim.render.poll()


def test_shot_buttons_add_move_and_remove():
    run_load(CUBE)
    s = settings()
    s.active_shot = 0
    bpy.ops.sliceranim.shot_add()
    assert len(s.shots) == 3 and s.active_shot == 1 and s.shots[1].style == "HOLD"
    bpy.ops.sliceranim.shot_move(direction="UP")
    assert s.active_shot == 0 and s.shots[0].style == "HOLD"
    bpy.ops.sliceranim.shot_remove()
    assert len(s.shots) == 2 and s.shots[0].style == "LINE"


def test_import_menu_entry_exists():
    assert ui.menu_import in bpy.types.TOPBAR_MT_file_import._dyn_ui_initialize()
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `make test-blender`

Expected: FAIL with `ImportError: cannot import name 'ui' from 'sliceranim.blender'`.

- [ ] **Step 3: Write the implementation**

Create `sliceranim/blender/ui.py`:

```python
"""Panel, operators, import menu entry, and drag and drop (spec 11.2 and 11.3)."""

import os

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty

from ..core.errors import OPEN_MESH, SlicerAnimError, too_many_polygons
from ..core.toolpaths import estimate_polygons
from . import importer, output, preview, shots

_pending = {}  # a large print that waits for the user to confirm (spec section 7)


def ask_to_confirm() -> None:
    """Show the warning of spec section 12. The confirm operator builds the waiting print."""
    bpy.ops.sliceranim.confirm_large("INVOKE_DEFAULT")


def _finish_load(operator, context, loaded, *, keep_shots: bool) -> set:
    settings = context.scene.sliceranim
    tp = importer.prepare(context, loaded)
    polygons = estimate_polygons(tp, int(settings.strand_sides), settings.ghost)
    if polygons > importer.POLYGON_LIMIT and not operator.confirm_large:
        _pending.update(loaded=loaded, tp=tp, keep_shots=keep_shots, polygons=polygons)
        ask_to_confirm()
        return {"CANCELLED"}
    importer.build(context, loaded, tp, keep_shots=keep_shots)
    if loaded.open_edges:
        operator.report({"WARNING"}, OPEN_MESH)
    return {"FINISHED"}


class _LoadBase:
    confirm_large: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def run(self, context, read, *, keep_shots=False):
        try:
            return _finish_load(self, context, read(), keep_shots=keep_shots)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}


class SLICERANIM_OT_load_file(_LoadBase, bpy.types.Operator):
    """Load G-code, a 3MF file, or an STL file as an animated print"""

    bl_idname = "sliceranim.load_file"
    bl_label = "Open File"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    filter_glob: StringProperty(default="*.gcode;*.3mf;*.stl", options={"HIDDEN"})

    def invoke(self, context, event):
        if self.directory and len(self.files):
            return self.execute(context)  # drag and drop gives the file directly
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not len(self.files):
            self.report({"ERROR"}, "Choose a file.")
            return {"CANCELLED"}
        path = os.path.join(self.directory, self.files[0].name)
        return self.run(context, lambda: importer.read_file(context, path))


class SLICERANIM_OT_use_selected(_LoadBase, bpy.types.Operator):
    """Run the fallback slicer on the selected mesh object"""

    bl_idname = "sliceranim.use_selected"
    bl_label = "Use Selected Object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj != context.scene.sliceranim.toolpath_object

    def execute(self, context):
        return self.run(context, lambda: importer.read_mesh_object(context, context.active_object))


class SLICERANIM_OT_reload(_LoadBase, bpy.types.Operator):
    """Read the source again with the new Merge angle"""

    bl_idname = "sliceranim.reload"
    bl_label = "Reload"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.sliceranim.toolpath_object is not None

    def execute(self, context):
        return self.run(context, lambda: importer.reload_source(context), keep_shots=True)


class SLICERANIM_OT_confirm_large(bpy.types.Operator):
    """Build a print with more than 10 million polygons"""

    bl_idname = "sliceranim.confirm_large"
    bl_label = "Large Print"
    bl_options = {"INTERNAL", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Large print", message=too_many_polygons(_pending["polygons"]), confirm_text="Build Anyway"
        )

    def execute(self, context):
        if not _pending:
            return {"CANCELLED"}
        importer.build(context, _pending["loaded"], _pending["tp"], keep_shots=_pending["keep_shots"])
        _pending.clear()
        return {"FINISHED"}


class SLICERANIM_OT_shot_add(bpy.types.Operator):
    """Add a shot after the active shot"""

    bl_idname = "sliceranim.shot_add"
    bl_label = "Add Shot"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sliceranim
        item = settings.shots.add()
        item.style = "HOLD"
        item.start_at_end = True
        item.start_layer = max(settings.layer_count, 1)
        target = min(settings.active_shot + 1, len(settings.shots) - 1)
        settings.shots.move(len(settings.shots) - 1, target)
        settings.active_shot = target
        return {"FINISHED"}


class SLICERANIM_OT_shot_remove(bpy.types.Operator):
    """Remove the active shot"""

    bl_idname = "sliceranim.shot_remove"
    bl_label = "Remove Shot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.sliceranim.shots) > 0

    def execute(self, context):
        settings = context.scene.sliceranim
        settings.shots.remove(settings.active_shot)
        settings.active_shot = max(0, min(settings.active_shot, len(settings.shots) - 1))
        return {"FINISHED"}


class SLICERANIM_OT_shot_move(bpy.types.Operator):
    """Move the active shot up or down"""

    bl_idname = "sliceranim.shot_move"
    bl_label = "Move Shot"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        settings = context.scene.sliceranim
        target = settings.active_shot + (-1 if self.direction == "UP" else 1)
        if 0 <= target < len(settings.shots):
            settings.shots.move(settings.active_shot, target)
            settings.active_shot = target
        return {"FINISHED"}


class SLICERANIM_OT_rebuild(bpy.types.Operator):
    """Write the keyframes, markers, and cameras for the shot list"""

    bl_idname = "sliceranim.rebuild"
    bl_label = "Rebuild"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return not shots.problems(context.scene)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Rebuild",
            message="Rebuild replaces the shot markers and keyframes that it made before. Manual changes to them will be lost.",
            confirm_text="Rebuild",
        )

    def execute(self, context):
        try:
            shots.rebuild(context.scene)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class SLICERANIM_OT_render(bpy.types.Operator):
    """Render the video to the output folder"""

    bl_idname = "sliceranim.render"
    bl_label = "Render"

    @classmethod
    def poll(cls, context):
        return not shots.problems(context.scene)

    def execute(self, context):
        scene = context.scene
        if scene.sliceranim.preview_active:
            preview.stop(context)
        try:
            if shots.needs_rebuild(scene):
                shots.rebuild(scene)
        except SlicerAnimError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        output.apply(scene)
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        return {"FINISHED"}


class SLICERANIM_UL_shots(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        bad_rows = {p.row for p in shots.problems(context.scene)}
        row = layout.row(align=True)
        row.alert = index in bad_rows
        start = "End" if item.start_at_end else str(item.start_layer)
        row.label(text=f"{index + 1}. {start}")
        row.label(text=f"{item.duration:g} s")
        row.label(text=bpy.types.UILayout.enum_item_name(item, "style", item.style))
        row.label(text=bpy.types.UILayout.enum_item_name(item, "camera", item.camera))


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer Anim"


class SLICERANIM_PT_source(_Panel, bpy.types.Panel):
    bl_label = "Source"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.operator(SLICERANIM_OT_load_file.bl_idname, icon="FILEBROWSER")
        layout.operator(SLICERANIM_OT_use_selected.bl_idname, icon="MESH_DATA")
        if settings.toolpath_object is None:
            return
        if abs(settings.merge_angle - settings.built_merge_angle) > 1e-6:
            row = layout.row()
            row.alert = True
            row.operator(SLICERANIM_OT_reload.bl_idname, icon="FILE_REFRESH")
        box = layout.box()
        box.label(text=settings.source_label, icon="FILE")
        box.label(text=f"Slicer: {settings.slicer or 'unknown'}")
        hours, rest = divmod(int(settings.print_time), 3600)
        box.label(text=f"{settings.layer_count} layers, {hours} h {rest // 60} min")
        box.label(text=f"{settings.point_count:,} points")
        if settings.used_fallback:
            box.label(text="Fallback slicer: 2 walls, no infill.", icon="INFO")


class SLICERANIM_PT_look(_Panel, bpy.types.Panel):
    bl_label = "Look"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.use_property_split = True
        layout.prop(settings, "use_file_color")
        if not settings.use_file_color:
            layout.prop(settings, "color")
        layout.prop(settings, "finish")
        layout.prop(settings, "highlight")
        if settings.highlight:
            layout.prop(settings, "highlight_color")
            layout.prop(settings, "highlight_layers")
        layout.prop(settings, "ghost")
        if settings.ghost:
            layout.prop(settings, "ghost_use_filament_color")
            if not settings.ghost_use_filament_color:
                layout.prop(settings, "ghost_color")
            layout.prop(settings, "ghost_opacity")
        layout.prop(settings, "strand_sides")
        layout.prop(settings, "viewport_strand_sides")
        layout.prop(settings, "merge_angle")
        layout.prop(settings, "backdrop")
        if settings.backdrop:
            layout.prop(settings, "backdrop_color")
        layout.prop(settings, "lights")
        layout.prop(settings, "plate_mat")
        layout.prop(settings, "nozzle")


class SLICERANIM_PT_shots(_Panel, bpy.types.Panel):
    bl_label = "Shots"

    def draw(self, context):
        scene = context.scene
        settings = scene.sliceranim
        layout = self.layout
        row = layout.row()
        row.template_list("SLICERANIM_UL_shots", "", settings, "shots", settings, "active_shot", rows=4)
        column = row.column(align=True)
        column.operator(SLICERANIM_OT_shot_add.bl_idname, icon="ADD", text="")
        column.operator(SLICERANIM_OT_shot_remove.bl_idname, icon="REMOVE", text="")
        column.operator(SLICERANIM_OT_shot_move.bl_idname, icon="TRIA_UP", text="").direction = "UP"
        column.operator(SLICERANIM_OT_shot_move.bl_idname, icon="TRIA_DOWN", text="").direction = "DOWN"
        for problem in shots.problems(scene):
            where = f"Shot {problem.row + 1}: " if problem.row >= 0 else ""
            layout.label(text=where + problem.message, icon="ERROR")
        if not settings.shots or not 0 <= settings.active_shot < len(settings.shots):
            return
        shot = settings.shots[settings.active_shot]
        layout.use_property_split = True
        layout.prop(shot, "start_at_end")
        if not shot.start_at_end:
            layout.prop(shot, "start_layer")
        layout.prop(shot, "duration")
        layout.prop(shot, "style")
        layout.prop(shot, "camera")
        fields = {
            "TURNTABLE": ("orbit_turns", "orbit_height", "orbit_clockwise"),
            "HERO": ("hero_height", "hero_side"),
            "RISING": ("rising_distance", "rising_height"),
            "CLOSE_UP": ("closeup_target", "closeup_distance", "closeup_smoothing", "closeup_dof", "closeup_fstop"),
            "REVEAL": ("reveal_spin", "reveal_pullback"),
            "CUSTOM": ("custom_camera",),
        }[shot.camera]
        for name in fields:
            layout.prop(shot, name)


class SLICERANIM_PT_output(_Panel, bpy.types.Panel):
    bl_label = "Output"

    def draw(self, context):
        settings = context.scene.sliceranim
        layout = self.layout
        layout.use_property_split = True
        layout.prop(settings, "format_preset")
        if settings.format_preset == "CUSTOM":
            layout.prop(settings, "custom_width")
            layout.prop(settings, "custom_height")
        layout.prop(settings, "fps")
        layout.prop(settings, "file_type")
        layout.prop(settings, "output_folder")
        layout.use_property_split = False
        row = layout.row(align=True)
        row.operator(SLICERANIM_OT_rebuild.bl_idname, icon="FILE_REFRESH")
        label = "Exit Preview" if settings.preview_active else "Preview"
        row.operator(preview.SLICERANIM_OT_preview.bl_idname, text=label, icon="PLAY")
        layout.operator(SLICERANIM_OT_render.bl_idname, icon="RENDER_ANIMATION")


class SLICERANIM_FH_toolpaths(bpy.types.FileHandler):
    bl_idname = "SLICERANIM_FH_toolpaths"
    bl_label = "Print Toolpaths"
    bl_import_operator = "sliceranim.load_file"
    bl_file_extensions = ".gcode;.3mf"

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"


def menu_import(self, context):
    self.layout.operator(SLICERANIM_OT_load_file.bl_idname, text="Print Toolpaths (.gcode, .3mf, .stl)")


CLASSES = (
    SLICERANIM_OT_load_file,
    SLICERANIM_OT_use_selected,
    SLICERANIM_OT_reload,
    SLICERANIM_OT_confirm_large,
    SLICERANIM_OT_shot_add,
    SLICERANIM_OT_shot_remove,
    SLICERANIM_OT_shot_move,
    SLICERANIM_OT_rebuild,
    SLICERANIM_OT_render,
    SLICERANIM_UL_shots,
    SLICERANIM_PT_source,
    SLICERANIM_PT_look,
    SLICERANIM_PT_shots,
    SLICERANIM_PT_output,
    SLICERANIM_FH_toolpaths,
)
```

Replace all of `sliceranim/blender/__init__.py` with:

```python
"""Blender side of the extension. Everything here imports bpy."""

import bpy

from . import preview, prefs, props, ui

CLASSES = (prefs.SLICERANIM_AP_preferences, *preview.CLASSES, *ui.CLASSES)


def register():
    props.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(ui.menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(ui.menu_import)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `make test-blender`

Expected: `50 passed, 0 failed, 0 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/blender/test_operators.py sliceranim/blender/ui.py sliceranim/blender/__init__.py
git commit -m "Add the panel, operators, import menu, and drag and drop"
```

### Task 17: Sample checks, packaging, and the owner's check in the app

Check the success criteria of spec section 1 with the reference job, add the OrcaSlicer check of spec 15.5, build the installable zip, and let the owner check the parts that need a person: the panel, drag and drop, Preview, the final MP4, and an OrcaSlicer file.

**Files:**
- Test: `tests/blender/test_sample.py`
- Test: `tests/unit/test_orca_sample.py`

**Interfaces:**
- Consumes: Everything.
- Produces:
  - `dist/sliceranim-0.1.0.zip` (not committed).

Measured on 2026-10-15 on the M1: the sample loads in 3.7 s (slice, read, merge, build, Rebuild). A 480×270 Eevee frame renders in about 2 s.

- [ ] **Step 1: Write the sample checks**

Create `tests/blender/test_sample.py`:

```python
"""Checks with the client sample. They skip when samples/sample.3mf or Bambu Studio is not present."""

import tempfile
import time
from pathlib import Path

import bpy
from helpers import SAMPLE_3MF, Skip, load, polygons_at, settings

from sliceranim.core.bambu_cli import DEFAULT_PATHS


def need_sample():
    if not SAMPLE_3MF.is_file():
        raise Skip("samples/sample.3mf is not present")
    if not Path(DEFAULT_PATHS["darwin"]).is_file():
        raise Skip("Bambu Studio is not installed")


def test_sample_loads_in_less_than_10_seconds():
    need_sample()
    start = time.perf_counter()
    load(SAMPLE_3MF)
    seconds = time.perf_counter() - start
    s = settings()
    print(f"    load: {seconds:.2f} s, {s.layer_count} layers, {s.point_count} points after merging")
    assert s.layer_count == 764
    assert bpy.context.scene.frame_end == 720
    assert seconds < 10.0


def test_sample_frame_evaluation_time():
    """Reports the time to evaluate a frame with viewport settings (spec 11.4). It does not fail."""
    need_sample()
    load(SAMPLE_3MF)
    for frame in (100, 400, 700):
        start = time.perf_counter()
        count = polygons_at(frame)
        print(f"    frame {frame}: {time.perf_counter() - start:.3f} s, {count} polygons")


def test_sample_render_smoke():
    """Spec 15.4: render three frames of the sample at 480x270."""
    need_sample()
    load(SAMPLE_3MF)
    s = settings()
    s.format_preset = "CUSTOM"
    s.custom_width, s.custom_height = 480, 270
    s.file_type = "PNG"
    scene = bpy.context.scene
    folder = Path(tempfile.mkdtemp(prefix="sliceranim_render_"))
    for frame in (60, 360, 680):
        scene.frame_set(frame)
        scene.render.filepath = str(folder / f"frame_{frame:04d}.png")
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(f"    frame {frame}: rendered in {time.perf_counter() - start:.2f} s")
        assert (folder / f"frame_{frame:04d}.png").is_file()
    print(f"    look at the frames in {folder}")
```

Create `tests/unit/test_orca_sample.py`:

```python
"""Spec 15.5: one OrcaSlicer G-code file from the owner. The test skips until the file is in samples/."""

from pathlib import Path

import pytest

from sliceranim.core.gcode_reader import read_gcode
from sliceranim.core.toolpaths import FEATURE_CODE

ORCA = Path(__file__).resolve().parents[2] / "samples" / "orca_sample.gcode"


@pytest.mark.skipif(not ORCA.is_file(), reason="needs samples/orca_sample.gcode from the owner")
def test_orcaslicer_gcode_reads():
    tp = read_gcode(ORCA)
    tp.validate()
    assert tp.meta["slicer"] == "OrcaSlicer"
    assert tp.layer_count > 1
    assert FEATURE_CODE["outer_wall"] in set(tp.feature.tolist())
    assert tp.total_time > 0
```

- [ ] **Step 2: Run the tests and see them pass**

Run: `make test-blender`

Expected: `53 passed, 0 failed, 0 skipped`. Without the sample or Bambu Studio, expect `50 passed, 0 failed, 3 skipped`. Read the printed lines. Open the three PNG frames in the printed folder and make sure that you see the part, the layer lines, and the orange highlight.

- [ ] **Step 3: Run the unit tests**

Run: `make test`

Expected: `80 passed, 1 skipped`. The skipped test waits for the OrcaSlicer file of spec 15.5 (owner check, item 9).

- [ ] **Step 4: Build the zip file**

Run: `make build`

Expected: `created: "dist/sliceranim-0.1.0.zip"`.

- [ ] **Step 5: Owner check in Blender (about 20 minutes, plus the render time)**

Ask the owner to do these steps and to report each result:

1. In Blender 5.2, open Edit > Preferences > Get Extensions, open the menu at the top right, and click Install from Disk. Choose `dist/sliceranim-0.1.0.zip`.
2. Start a new file. Save it outside the repository, for example `~/Documents/Slicer Animator/sample.blend`.
3. Press N in the 3D view and open the Slicer Anim tab. Click Open File and choose `samples/sample.3mf`. Expected: the object appears in less than 10 seconds, and Source shows 764 layers.
4. Click Preview. Expected: the view looks through the shot cameras and plays. Note the frame rate in the top left of the 3D view. Click Exit Preview. Expected: the view returns to how it was.
5. Turn on Ghost and click Preview again. Expected: a clear shell shows the part that is not printed yet.
6. Drag `slices/sample/plate_1.gcode` (next to the saved .blend) onto the 3D view. Expected: it loads.
7. In Output, keep 1920×1080, 30 fps, and MP4. Click Render. Expected: a 24-second MP4 in `renders/` next to the .blend after about 1 to 1.5 hours (spec section 16).
8. Close Blender, open the .blend again, and look at frames 120, 400, and 700. Expected: the same frames as before.
9. In OrcaSlicer, slice any part on one plate and export the G-code to `samples/orca_sample.gcode`. Then run `make test`. Expected: `81 passed`. If the OrcaSlicer test fails, use superpowers:systematic-debugging on the reader with the first 200 lines of that file. Do not commit the file.

- [ ] **Step 6: Record the results**

Add the result of item 4 of the owner check (preview frame rate) to spec section 16 as a new row:

```
| Preview in the 3D view, viewport strand sides 4 | <frame rate that the owner saw> fps |
```

Then update `SESSIONS.md`: add a session entry and set the status table to "Version 1 built, owner check done" with any problems the owner found.

- [ ] **Step 7: Commit**

```bash
git add tests/blender/test_sample.py tests/unit/test_orca_sample.py docs/superpowers/specs/2026-10-15-slicer-animator-design.md SESSIONS.md
git commit -m "Add the sample checks and record the owner check"
```
