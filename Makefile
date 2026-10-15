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
