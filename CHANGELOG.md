# Changelog

Version numbers are 0.1.x while the owner checks the add-on. Each build that goes to the owner gets the next patch number and an entry here. The version is set in `sliceranim/blender_manifest.toml`, and the Source section of the panel shows it.

## 0.1.1 (2026-10-16)

1. Every shot except Close-up keeps the whole part in the image. Rising follow stays far enough away for this.
2. Framing in the Shots section: Part (default), or Print volume to frame the whole Bambu Lab P1S print volume.
3. The backdrop grows to enclose the farthest shot camera. Before, a camera outside the backdrop showed a black frame.
4. The Source section shows the version of the add-on.

## 0.1.0 (2026-10-16)

The first build for the owner check, with the fixes from check rounds 1 and 2.

1. Load G-code, sliced 3MF files, and Bambu Studio projects. Slice STL files and mesh objects with Bambu Studio, with a Layer height setting.
2. Shot list with Line, Layer, and Hold styles and six camera presets. Rebuild, Preview, and Render.
3. Look settings: color, finish, highlight, ghost, strand detail, backdrop, lights with color and intensity, plate mat, and nozzle tip with size.
4. Reset to Defaults. The output folder is made for you.
5. A mesh larger than 1000 mm is read at 1 Blender unit = 1 mm, so the Blender STL import works.
