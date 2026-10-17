# Slicer Animator

Slicer Animator is a Blender 5.2 extension. It makes videos of a 3D print that grows layer by layer, from real G-code. The design is in `docs/superpowers/specs/2026-10-15-slicer-animator-design.md`.

## Install

1. Build the zip file with `make build`, or use the newest zip in `dist/`.
2. In Blender, open Edit > Preferences > Get Extensions. Open the menu at the top right and click Install from Disk. Choose the zip file.
3. In the 3D view, press N and open the Slicer Anim tab.

To slice STL files and mesh objects, install Bambu Studio. The add-on preferences hold its path and the printer, process, and filament presets.

The version is in `sliceranim/blender_manifest.toml`. `CHANGELOG.md` lists the changes in each build. `SESSIONS.md` has the project status.

## Development

You need Python 3.13 and Blender 5.2 in `/Applications/Blender.app`.

1. Make the virtual environment: `make venv`
2. Run the unit tests, which do not need Blender: `make test`
3. Run the Blender tests in headless Blender: `make test-blender`
4. Build the installable zip file into `dist/`: `make build`

Client files go in `samples/`. Git ignores this folder. Do not commit client files. The tests that need `samples/sample.3mf` skip when the file is not there.
