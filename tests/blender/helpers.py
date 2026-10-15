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
