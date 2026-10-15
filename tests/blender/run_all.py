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
