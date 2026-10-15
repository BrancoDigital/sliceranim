# Slicer Animator

Slicer Animator is a Blender 5.2 extension. It makes videos of a 3D print that grows layer by layer, from real G-code. The design is in `docs/superpowers/specs/2026-10-15-slicer-animator-design.md`.

## Development

You need Python 3.13 and Blender 5.2 in `/Applications/Blender.app`.

1. Make the virtual environment: `make venv`
2. Run the unit tests, which do not need Blender: `make test`
3. Run the Blender tests in headless Blender: `make test-blender`
4. Build the installable zip file into `dist/`: `make build`

Client files go in `samples/`. Git ignores this folder. Do not commit client files. The tests that need `samples/sample.3mf` skip when the file is not there.
