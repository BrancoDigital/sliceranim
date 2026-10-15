# Slicer Animator: design spec

Date: 2026-10-15
Status: approved on 2026-10-15
Target: Blender 5.2 LTS (tested on 5.2.2), macOS

## 1. Purpose

Slicer Animator is a Blender extension. It makes videos that show a 3D-printed part grow layer by layer, the way the printer built it. The owner uses it to make videos of parts that were designed in Blender or CAD and printed for clients.

The plugin shows only the part as it grows. It does not show the printer. An optional plate mat and an optional nozzle tip are the only printer elements.

The users are the owner and a small group of people that the owner sends the extension to. The extension is not for public sale in version 1.

### Success criteria

1. You load `samples/sample.3mf` and get a toolpath object in less than 10 seconds on an Apple M1 with 8 GB of memory.
2. With the default shot list, Rebuild and Render produce a 24-second 1920×1080 MP4 without manual steps in Blender.
3. The video shows walls, infill, and top surfaces from the real G-code, with real layer lines.
4. All plugin settings are saved in the `.blend` file. When you open the file again, you get the same video.
5. Preview plays the video in the 3D view without a render and without manual changes to the view.

## 2. Scope

### In version 1

1. Input from Bambu Studio and OrcaSlicer G-code (`.gcode`, `.gcode.3mf`).
2. Headless slicing of a Bambu Studio project `.3mf` with one plate.
3. A fallback slicer for a `.stl` file or for a mesh object in the scene.
4. One filament color per print. The data format keeps a filament number for each point, for multi-color support later.
5. A shot list that controls build style, timing, and camera for each part of the video.
6. Six camera presets: turntable orbit, hero, rising follow, close-up, final reveal, and your own camera.
7. A filament material with finish presets, an active-layer highlight, a studio backdrop, an optional plate mat, and an optional nozzle tip.
8. An optional ghost: a transparent shell of the part that is not printed yet. The build fills it up.
9. A preview that plays the video in the 3D view.
10. Output presets for 16:9 1080p, 1:1, 16:9 4K, and a custom size.

### Not in version 1 (the later list)

1. Multi-color prints with the AMS (the Bambu automatic filament switcher).
2. Slicer preview colors, which give each toolpath type its own color.
3. Hide or ghost toolpaths by type.
4. Instancing of identical copies on a crowded plate.
5. PrusaSlicer and Cura G-code.
6. Files with more than one plate.
7. Smooth camera blends between shots. Version 1 uses hard cuts.
8. Headless slicing with OrcaSlicer. The OrcaSlicer 2.3.2 command line refuses project files that Bambu Studio 2.08 saved.
9. Tests on Windows and Linux.

## 3. Terms

| Term | Meaning |
|---|---|
| Toolpath | The path that the nozzle follows while it extrudes plastic. |
| Strand | One extruded line of plastic, drawn in Blender as a thin oval tube. |
| Run | A sequence of points that the nozzle extrudes without a stop or a travel move. |
| Feature | The toolpath type that the slicer gives a move, for example outer wall or sparse infill. |
| ToolpathSet | The internal data format. Every input becomes a ToolpathSet. |
| Progress | One animated number. It is the count of strand points that are already printed. |
| Ghost | A transparent shell that shows the part of the print that is not printed yet. |
| Print head | An invisible Blender empty that moves with the current nozzle position. |
| Shot | One part of the video with its own start layer, duration, build style, and camera. |
| Fallback slicer | Code in the plugin that cuts a mesh into layer outlines when no G-code exists. |

## 4. Architecture

```
inputs ──► ToolpathSet ──► Blender scene ◄── shot list
```

The plugin has seven parts. The parts in `core/` do not import `bpy`, so they run and get tested without Blender.

| Part | Location | Job |
|---|---|---|
| Inputs | `core/` | Read G-code, read 3MF files, run headless slicing, run the fallback slicer. Each input returns a ToolpathSet. |
| ToolpathSet | `core/` | Hold the points and their tags in numpy arrays. |
| Timing | `core/` | Turn the shot list into one Progress value, one print head position, and one current layer for each frame. |
| Toolpath object | `blender/` | Build one mesh with point attributes, plus the Geometry Nodes setup that draws strands. |
| Cameras | `blender/` | Make one camera for each shot and frame the part. |
| Looks | `blender/` | Make the materials, the backdrop, the lights, the plate mat, and the nozzle tip. |
| Panel and output | `blender/` | Show the sidebar panel, the import menu, drag and drop, the preview, and the render settings. |

## 5. ToolpathSet

A ToolpathSet holds all extruded points of one print in print order. Units are millimeters and seconds. The Blender importer converts millimeters to meters (factor 0.001).

| Array | Type | Meaning |
|---|---|---|
| `position` | float32, N×3 | Point position in plate coordinates |
| `layer` | int32, N | Layer index, starting at 0 |
| `feature` | uint8, N | Feature code (see the table below) |
| `tool` | uint8, N | Filament number (T0 to T3). Version 1 stores it but does not use it. |
| `width` | float32, N | Strand width |
| `height` | float32, N | Strand height (layer height of the move) |
| `time` | float64, N | Print time at this point, counted from the first extruded point |
| `object_id` | int32, N | Object number from the G-code. Kept for instancing later. |
| `run_start` | int32, R | Index of the first point of each run |
| `layer_start` | int32, L | Index of the first point of each layer |
| `layer_z` | float32, L | Height of each layer |

Point index is the print order. The first point of a run has no strand before it.

All indices in the ToolpathSet and in the Blender object count from 0. This includes point index, `layer`, and Current Layer. The panel shows layer numbers that count from 1. Layer number N in the panel is layer index N − 1.

The ToolpathSet also holds metadata: source slicer and version, file path, layer count, total print time, filament colors, and filament type.

### Feature codes

| Code | Name | Slicer labels |
|---|---|---|
| 0 | other | Any label that is not in this table |
| 1 | outer_wall | Outer wall |
| 2 | inner_wall | Inner wall, Floating vertical shell |
| 3 | overhang_wall | Overhang wall |
| 4 | sparse_infill | Sparse infill |
| 5 | solid_infill | Internal solid infill |
| 6 | top_surface | Top surface |
| 7 | bottom_surface | Bottom surface |
| 8 | bridge | Bridge |
| 9 | gap_fill | Gap infill |
| 10 | support | Support, Support transition |
| 11 | support_interface | Support interface |
| 12 | brim_skirt | Brim, Skirt |
| 13 | prime_tower | Prime tower |
| 14 | custom | Custom (start G-code, for example the purge line) |

The importer drops `custom` points by default. The purge line is not part of the client's part.

## 6. Inputs

### 6.1 G-code reader

The reader supports the comment format of Bambu Studio and OrcaSlicer. It reads the file line by line.

| G-code | Use |
|---|---|
| `; CHANGE_LAYER` | Start of a new layer |
| `; Z_HEIGHT: <z>` | Height of the layer |
| `; FEATURE: <name>` | Feature of the moves that follow |
| `; LINE_WIDTH: <w>` | Strand width of the moves that follow |
| `; LAYER_HEIGHT: <h>` | Strand height of the moves that follow |
| `; WIPE_START`, `; WIPE_END` | Moves between these two lines are not strands |
| `; OBJECT_ID: <id>` | Object number of the moves that follow |
| `G0`, `G1` | Straight moves |
| `G2`, `G3` | Arc moves (clockwise and counterclockwise) |
| `G90`, `G91` | Absolute or relative XYZ positions |
| `M82`, `M83` | Absolute or relative extrusion |
| `T<n>` | Filament change |
| `; filament_colour = ...` | Filament colors from the settings block at the end of the file |

These are the rules for each move:

1. A move is extrusion when the extrusion amount is more than zero, the XY position changes, the move is after the first layer marker, and the move is not inside a wipe block.
2. An extrusion move adds a point to the current run. A move that is not extrusion ends the current run.
3. A change of layer or feature ends the current run.
4. The reader converts each arc into straight segments of 0.5 mm or less. The sample G-code has 16,604 arc moves.
5. Move duration is segment length divided by feed rate (`F`, in millimeters per minute, divided by 60). The reader ignores acceleration. Travel moves do not add time, so the video does not show pauses where nothing happens.

If the file has no `; CHANGE_LAYER` marker, the reader stops with the error in section 12.

### 6.2 3MF files

The plugin opens a 3MF file as a zip archive and looks at its contents.

| Contents | Type | Action |
|---|---|---|
| `Metadata/plate_<n>.gcode` | Sliced 3MF | Read the G-code inside. |
| No G-code, `Metadata/model_settings.config` present | Bambu project | Slice it headless (section 6.3). |

The plugin counts plates. In a sliced 3MF, it counts `Metadata/plate_*.gcode` files. In a project, it counts `<plate>` elements in `Metadata/model_settings.config`. If the count is more than one, the plugin stops with the error in section 12.

### 6.3 Headless slicing with Bambu Studio

The plugin runs this command:

```
<BambuStudio> --slice 1 --outputdir <dir> --export-3mf sliced.gcode.3mf <project.3mf>
```

On macOS, `<BambuStudio>` is `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`. On Windows, it is `C:\Program Files\Bambu Studio\bambu-studio.exe`. You can set another path in the add-on preferences.

The output directory is `<blend directory>/slices/` when the `.blend` file is saved. Otherwise it is a temporary directory. After the run, the plugin reads `result.json` from the output directory. If `return_code` is not 0, the plugin shows `error_string` from that file. If the run succeeds, the plugin reads `plate_1.gcode`.

Tested on 2026-10-15 with Bambu Studio 2.08.02.61: `samples/sample.3mf` sliced in 2.4 seconds to 764 layers and 4 h 11 min of print time. The G-code reader makes 378,247 strand points from it, with arcs split at 0.5 mm. Merging at 2° leaves 306,701 points.

### 6.4 Fallback slicer

The fallback slicer takes a triangle mesh in millimeters. The input is a `.stl` file or a mesh object that you select in the scene.

1. Cut the mesh with a horizontal plane at the middle of each layer. The default layer height is 0.2 mm.
2. Join the cut segments into closed loops.
3. Make two strand loops for each closed outline. The strand width (w) is 0.45 mm. Offset both loops toward the material side of the outline. This is inward for an outer outline and outward for a hole.
   - The outer loop is offset by w / 2 (0.225 mm), so the part keeps its true size. Its feature is `outer_wall`.
   - The inner loop is offset by 1.5 × w (0.675 mm). Its feature is `inner_wall`.
4. If the inner loop crosses itself or its area falls to 0 or below, drop that inner loop. This happens on features thinner than about 3 strand widths (1.35 mm).
5. In each layer, print the inner loops first and the outer loops after, as Bambu Studio does by default.
6. Give each point a print time from a constant speed of 100 mm/s.

The offset uses numpy only (section 13). The fallback output has no infill. The panel shows this when the fallback is in use.

## 7. Toolpath object

The importer builds one mesh object named after the source file:

1. One vertex for each ToolpathSet point, in meters.
2. One edge between two neighbor points of the same run.
3. Point attributes: `order` (the point index, from 0), `layer`, `feature`, `tool`, `width`, `height`.

A Geometry Nodes modifier draws the strands. It has these inputs: Progress (float), Current Layer (float), Strand Sides (integer), Viewport Strand Sides (integer), and Ghost (boolean).

1. Delete each point with `order` greater than `floor(Progress)`.
2. Move point `floor(Progress)` to the position between its previous point and itself, at the fraction `Progress - floor(Progress)`. This step makes the newest strand grow smoothly. It applies only when both points are in the same run.
3. Convert the mesh edges to curves.
4. Set the curve normal mode to Z Up, so that the strand profile stays flat.
5. Sweep an oval profile along each curve. The profile is a circle with Strand Sides points, scaled to height/width in its Y axis. The `width / 2` attribute goes into the Scale input of Curve to Mesh. In the 3D view, the profile uses Viewport Strand Sides instead (Is Viewport node). Renders always use Strand Sides.
6. Store a `heat` attribute: `clamp(1 - (Current Layer - layer) / highlight_layers, 0, 1)`. The material reads it.
7. Set smooth shading and the filament material.
8. If Ghost is on, draw the ghost from the points that are not printed yet (`order` greater than `floor(Progress)`). The ghost uses only the features `outer_wall`, `overhang_wall`, and `top_surface`, so it looks like a clear shell of the part. It uses Viewport Strand Sides in the 3D view and 4 sides in renders, and the ghost material from section 10.

The ghost leaves out inner walls and infill for two reasons. Many stacked transparent layers look like noise, and the shell adds fewer polygons.

### Strand detail

| Setting | Default | Effect |
|---|---|---|
| Strand sides | 6 | 4, 6, or 8 sides per strand in renders |
| Viewport strand sides | 4 | 3, 4, 6, or 8 sides per strand in the 3D view. Fewer sides make the preview faster. |
| Merge angle | 2° | Remove a point when the direction changes by less than this angle. 0 turns merging off. |

Merging runs in `core/` at import, before timing. Progress counts the points after merging. The next point keeps its own print time, so the total print time does not change. If you change Merge angle after import, the Source section shows a Reload button. Reload reads the source file again and builds the object again. If the source file is not there, Reload shows the error in section 12. This can happen after a restart when the headless slice went to a temporary directory.

If the estimated polygon count is more than 10 million, the plugin shows the warning in section 12 before it builds the object. The estimate is points × strand sides, plus ghost points × 4 when Ghost is on.

## 8. Timing and the shot list

### 8.1 Shot fields

| Field | Values | Meaning |
|---|---|---|
| Start layer | 1 to L, or End | The point in the print where the shot starts |
| Duration | Seconds, more than 0 | Screen time of the shot |
| Build style | Line, Layer, Hold | How the build moves in this shot |
| Camera | One of the six camera presets | Camera of the shot |
| Camera settings | Depends on the preset | See section 9 |

L is the layer count. Start layer N is the moment before the first point of layer N prints. End is the moment after the last point prints.

Each shot ends where the next shot starts. The last shot ends at End. The video length is the sum of all durations.

### 8.2 Build styles

| Style | Behavior |
|---|---|
| Line | Frames map linearly to print time between the start and the end of the shot. Each frame gets the point index at that print time, with a fraction for the partial strand. |
| Layer | The layers of the shot divide evenly over the frames. Each frame shows complete layers only. |
| Hold | The build does not move. It stays at the start point of the shot. |

### 8.3 Rules for a valid shot list

1. The first shot starts at layer 1.
2. Start layers do not decrease from one shot to the next.
3. Two neighbor shots have the same start layer only when the first of them is a Hold shot.
4. Only Hold shots start at End.
5. Each duration is more than 0.

If a rule fails, the panel shows the bad row in red and turns off Rebuild.

The panel helps you keep the list valid. When you check End on a shot, the shot becomes a Hold shot (rule 4). Add shot puts a Hold shot after the active shot, with the start of the next shot, or End when the active shot is the last one.

### 8.4 Default shot list

The importer makes this shot list. For the sample (764 layers) the video is 24 seconds.

| # | Start layer | Duration | Build style | Camera |
|---|---|---|---|---|
| 1 | 1 | 4 s | Line | Close-up |
| 2 | 6 | 12 s | Layer | Turntable orbit |
| 3 | L − 4 | 4 s | Line | Rising follow |
| 4 | End | 4 s | Hold | Final reveal |

If L is less than 20, shot 3 does not fit after shot 2. The importer then makes this shot list:

| # | Start layer | Duration | Build style | Camera |
|---|---|---|---|---|
| 1 | 1 | 20 s | Line | Turntable orbit |
| 2 | End | 4 s | Hold | Final reveal |

### 8.5 What Rebuild writes

The timing code computes one value for each frame. Rebuild then writes these values to Blender:

1. A keyframe on Progress for each frame. Line shots use linear interpolation. Layer and Hold shots use constant interpolation.
2. A keyframe on Current Layer for each frame. The value is the layer index of the newest strand point.
3. A keyframe on the print head location for each frame. The location is the position of the newest strand point.
4. One timeline marker for each shot, bound to the camera of the shot.
5. The scene start frame (1) and end frame.
6. The camera keyframes of each shot, from the presets in section 9.
7. Keyframes on the visibility of the nozzle tip, with constant interpolation. The tip is visible in Line shots and hidden in the other shots.

Rebuild deletes the markers and keyframes that it wrote before. Before it does this, it warns you that manual changes to these markers will be lost.

## 9. Cameras

Each shot gets its own camera object. Every preset frames the part from the bounding box of the complete toolpaths and the aspect ratio of the output. The framing distance is the radius of the bounding sphere divided by `sin(fov / 2)`, times a margin of 1.15. The fov is the smaller of the horizontal and vertical field of view.

| Preset | Behavior | Settings and defaults |
|---|---|---|
| Turntable orbit | Circles the center of the part | Turns per shot (1), height angle (25°), direction (counterclockwise) |
| Hero | Stays at a three-quarter view | Height angle (30°), side angle (35°) |
| Rising follow | Moves up with the current layer height and aims at the print head height | Distance (framing distance), height angle (20°) |
| Close-up | Frames the full layer that is printing. It aims at the center of that layer, or at a point that you pick with the 3D cursor, and stays at the framing distance of the layer. | Target (current layer), smoothing (15 frames), depth of field (off, f/2.8 when on) |
| Final reveal | Pulls back from the framing of the previous shot in the first 40% of the shot. Spins around the finished part in the remaining 60%. As the first shot, it starts at the framing distance. | Spin amount (90°), pull-back share (40%) |
| My camera | Uses a camera that you place. The plugin does not change it. | Camera object |

Close-up smoothing is a moving average of the layer center and the layer size over the given number of frames. It stops the camera from jumping when the next layer has another size.

## 10. Looks

| Item | Behavior | Defaults |
|---|---|---|
| Filament material | Principled BSDF. The color comes from the file, and you can override it. | Color from file. Gray `#808080` when the file has no color. |
| Finish presets | Matte, Glossy, Silk, Translucent. Each preset sets roughness, specular, sheen, and transmission. | Matte |
| Active-layer highlight | The material mixes an emission color with the filament color by the `heat` attribute. | On, orange `#FF6A1A`, 3 layers |
| Studio backdrop | A curved floor-and-wall mesh with no visible horizon, 6 times the size of the part | Light gray `#D9D9D9` |
| Lights | Key, fill, and rim area lights, scaled to the size of the part | On |
| Plate mat | A 256 mm × 256 mm plane at z = 0 with a procedural textured PEI material. No image files. | Off |
| Nozzle tip | A brass cone, 6 mm high, parented to the print head. Visible only in Line shots. | Off |
| Ghost | A transparent material on the ghost shell (section 7, step 8). Eevee uses the Dithered render method. You set the color and the opacity. | Off, filament color, 15% opacity |

## 11. Output and panel

### 11.1 Output

| Setting | Values | Default |
|---|---|---|
| Format preset | 1920×1080, 1080×1080, 3840×2160, Custom | 1920×1080 |
| Custom size | Width and height in pixels | 1920 × 1080 |
| Frame rate | 24, 25, 30, 60 | 30 |
| File type | MP4 (H.264), PNG frames | MP4 |
| Output folder | Path | `//renders/` |

The plugin makes the output folder when it applies the output settings and when you save the .blend file. A relative path such as `//renders/` needs a saved .blend file, so the folder appears after the first save.

The render engine is Eevee by default. You can switch to Cycles. The plugin does not change the engine after the first import.

### 11.2 Loading a file

All of these use the same load operator:

1. Panel: Source, then Open file. Accepts `.gcode`, `.gcode.3mf`, `.3mf`, and `.stl`.
2. Menu: File, then Import, then Print Toolpaths (.gcode, .3mf, .stl).
3. Drag and drop of a `.gcode` or `.3mf` file onto the 3D view. The plugin does not take `.stl` drops, because the Blender STL import already takes them.
4. Panel: Source, then Use selected object. This runs the fallback slicer on the selected mesh object.

### 11.3 Panel

The panel is a tab named "Slicer Anim" in the sidebar of the 3D view. It has four sections, in the order that you use them:

1. Source: the load buttons from 11.2, Reload (section 7), a summary of slicer, layer count, print time, and point count, and Reset to Defaults. Reset to Defaults asks you to confirm. Then it sets the Look and Output settings and the shot list back to their defaults and runs Rebuild. The loaded print stays.
2. Look: color, finish, highlight, ghost, strand detail, backdrop, plate mat, nozzle tip.
3. Shots: the shot list, with buttons to add, remove, and move shots.
4. Output: the settings from 11.1, plus Rebuild, Preview, and Render.

The plugin stores its settings in a property group on the scene. The Bambu Studio path is an add-on preference.

### 11.4 Preview

Preview plays the video in the 3D view. It does not render, and you do not change view settings by hand. When you click Preview, the plugin does these steps:

1. If the shot list or the timing changed since the last Rebuild, run Rebuild.
2. Set the 3D view to look through the scene camera. The timeline markers switch the camera at each shot, as in the render.
3. Set the shading of the 3D view to Material Preview, with the scene lights and the scene world on. The preview then shows the filament material, the highlight, the ghost, and the backdrop.
4. Set playback to drop frames when the 3D view is slow, so the video plays at its real speed.
5. Start playback at frame 1.

The Preview button then changes to Exit Preview. Exit Preview stops playback and restores the view, the shading, and the playback setting that you had before.

The frame rate of the preview on the reference machine is not measured yet. The first Blender test measures it.

## 12. Errors

| Condition | Message |
|---|---|
| More than one plate | This file has N plates. Export one plate from your slicer and try again. |
| Bambu Studio is not found | Bambu Studio not found. Set its path in preferences, or import a sliced file. |
| Headless slicing fails | Slicing failed: `<error_string from result.json>` |
| No layer markers in the G-code | No layer markers found. Supported slicers: Bambu Studio, OrcaSlicer. |
| No extrusion moves | No printed lines found in this file. |
| More than 10 million estimated polygons | This print makes about N million polygons. Lower Strand sides or raise Merge angle to make it faster. |
| Shot list rule fails | The row turns red and shows the rule that failed. |
| Fallback slicer on a mesh with open edges | The mesh has holes, so some layers can be incomplete. |
| Reload when the source file is gone | Source file not found: `<path>`. Open the file again. |

## 13. Packaging

1. Blender extension format, with `blender_manifest.toml`. The id is `sliceranim`, and the name is Slicer Animator.
2. Build command: `blender --command extension build`. The output is an installable `.zip` file.
3. License: GPL-3.0-or-later. Blender requires this license for add-ons that use its Python API.
4. Dependencies: none outside Blender. Blender ships with numpy.
5. Minimum Blender version: 5.2.0.

## 14. Code layout

```
sliceranim/                  the extension
  blender_manifest.toml
  __init__.py
  core/                      no bpy imports
    toolpaths.py             ToolpathSet
    gcode_reader.py
    threemf.py               3MF detection, plate count, G-code extraction
    bambu_cli.py             headless slicing
    mesh_slicer.py           fallback slicer
    timing.py                shot list to per-frame values
  blender/
    importer.py              ToolpathSet to mesh object
    nodes.py                 Geometry Nodes setup
    shots.py                 Rebuild: keyframes, markers, cameras
    cameras.py
    looks.py
    ui.py                    panel, menu entry, drag and drop
    preview.py               Preview and Exit Preview in the 3D view
    props.py                 scene property group
    prefs.py                 add-on preferences
tests/
  fixtures/                  small G-code files made by hand, committed
  unit/                      pytest tests for core/, no Blender
  blender/                   headless Blender 5.2 tests and a render smoke test
docs/
samples/                     client files, ignored by git
```

## 15. Testing

1. Unit tests run with pytest (a Python test runner) in a local virtual environment with numpy. They cover the G-code reader, arcs, feature mapping, merging, 3MF detection, plate count, the fallback slicer, timing, and the default shot list for short prints.
2. Test fixtures are small G-code files made by hand. Client files are never committed.
3. Blender tests run with `Blender -b --factory-startup --python-exit-code 1 -P <test>`. They build the toolpath object, run Rebuild, and compare evaluated polygon counts with expected values.
4. The render smoke test renders three frames of `samples/sample.3mf` at 480×270. If the file is not present, the test is skipped.
5. One OrcaSlicer G-code file is used to make sure that the reader works with OrcaSlicer output. The owner supplies it during the build.

## 16. Measured on the reference machine

A throwaway probe ran on 2026-10-15 on an Apple M1 with 8 GB of memory, Blender 5.2.2, with the G-code of the vape display part (764 layers).

| Step | Result |
|---|---|
| Read G-code | 0.55 s for 313k points (throwaway probe reader) |
| Read G-code with the plugin reader | 1.1 s for 378,247 points. Merging at 2° takes 0.2 s and leaves 306,701 points. |
| Build mesh with attributes | 0.18 s |
| Complete print as strands (6 sides) | 1.9 million polygons |
| Eevee render at 960×960, after shader compile | 3.4 s per frame |

Estimated render time for a 30-second video at 1080p and 30 fps: 1 to 1.5 hours. 4K takes about four times longer.

## 17. Blender 5.2 API notes

The probe found these changes from older Blender versions. The implementation must use the 5.2 form.

1. Geometry Nodes modifier inputs: set them with `mod.properties.inputs.<Socket_N>.value`. The old form `mod["Socket_N"]` raises `TypeError`. To keyframe an input, call `obj.keyframe_insert(path)`, where `path` comes from `input.path_from_id("value")`.
2. Curve to Mesh does not scale the profile by the curve radius. Connect the strand radius to its `Scale` input.
3. Set Curve Normal has no `mode` property. Its mode is a menu input socket: `node.inputs["Mode"].default_value = "Z Up"`.
