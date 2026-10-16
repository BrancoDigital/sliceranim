import re
from pathlib import Path

import sliceranim

ROOT = Path(__file__).resolve().parents[2]


def test_version_comes_from_the_manifest_and_is_0_1_x():
    assert re.fullmatch(r"0\.1\.\d+", sliceranim.version())
    assert f'version = "{sliceranim.version()}"' in (ROOT / "sliceranim" / "blender_manifest.toml").read_text()


def test_changelog_has_an_entry_for_the_current_version():
    assert f"## {sliceranim.version()} " in (ROOT / "CHANGELOG.md").read_text()
