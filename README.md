# AI Retopo Toolkit

Blender add-on for accelerating semi-automatic retopology workflows on generated AI 3D models.

The add-on currently targets Blender 5.0-5.2 and adds an `AI Retopo` tab to the 3D View sidebar.
The interface can be switched between English and Russian in the add-on preferences or directly in the main panel.
Add-on preferences include Git-based update checks and fast-forward updates from the configured `origin` remote.

## Custom Autosave

Add-on preferences include a **Custom Autosave** section. Choose **Native** to use Blender's normal temporary-file autosave, or **Custom** to keep rotating copies beside a saved project (`file.blendAutosave1`, `file.blendAutosave2`, and so on). Unsaved projects are written to a session-specific folder under the system temp directory; that session folder is removed after the first regular save. The interval and retained version count are configurable. The timer writes only after scene/data activity since the previous autosave, so an idle dirty project is not repeatedly written to disk; **Create Autosave Now** remains an explicit forced save.

When Blender starts with an unsaved file, the expanded **Autosave and Restart** block in the N-panel lists recent custom autosaves. It includes recoveries from previous temporary sessions and autosaves beside projects in Blender's recent-files list. Clicking `name.blendAutosaveN` opens it and immediately creates `name_restored_YYYY-MM-DD_HH-MM-SS.blend` beside the original. The recovery block can overwrite the original with the recovered data and then remove that restored copy. Recoveries of projects that never had an original path use the add-on's recovered-temp folder and provide **Save Recovered File As** instead.

The top of the AI Retopo N-panel shows the latest save result plus separate times for the most recent custom autosave and regular project save. Existing timestamps are restored from file modification times when a project is opened.

The Outliner header orders compact controls as Highpoly (`H`) Hide/Show, Retopo lowpoly (`L`) Hide/Show, then Previous/Next Generated Collection. `Ctrl+Numpad +` and `Ctrl+Numpad -` navigate to the next/previous Generated collection only while the pointer is over the Outliner or the AI Retopo N-panel.

Object Mode's Apply menu (`Ctrl+A`) includes **Apply Cutter Seams**, using the same validated cutter operator as the AI Retopo panel.

## Current Tools

- `Model Preparation`
  - `Mesh Editing` → `Delete and Fill`: in Edit Mode, replace selected face patches with a triangular fill of their boundaries, removing unused interior edges and vertices. New triangles stay selected. Other holes, unselected islands, and boundary seams are preserved. Supports multiple edited meshes and Undo; an invalid boundary cancels before deleting geometry.
  - `Rename Objects`: renames selected objects as `Highpoly_Generated.001`, `Highpoly_Generated.002`, and so on. Objects already in a numbered `Generated.N` collection keep their collection memberships; other objects move to `Generated`.
  - `Apply Weld`: adds and applies a Weld modifier on selected mesh objects.
  - Default weld distance: `0.0001`.
  - Hide/Show All Highpoly and Retopo toggles Disable in Viewport (monitor icon) for matching `Highpoly_` / `Retopo_` objects in the current scene, including excluded collections. This object setting applies across View Layers; eye visibility and render visibility are preserved.
  - Isolate Other Collections excludes other numbered `Generated.N` collections. Previous/Next Collection switches them in numeric order and selects a visible object in the destination; unrelated collections are preserved.
- `Seam Preparation`
  - Grid Volume also offers `Generate Auto`, which creates the configured grid from the active object's evaluated world bounding box, including modifiers, rotation and scale. Enable `Auto Rotate` to switch to an orthographic side view after the second base click: a front-view X/Z base switches to the right view for direct Y-depth placement. The third click sets the depth boundary. Cancel restores the original view; completing the grid leaves the side view active. Both controls are available in the toolbar and N-panel; Generate Auto is also available in Pie Menu settings.
  - `Cutter Tweak: Grid Volume` draws a world-aligned box filled with finite cutter planes. Set enabled X/Y/Z axes and plane counts in the toolbar or N-panel (default 3 per axis, maximum 64 each). Ctrl-click the first base corner, click the opposite corner, then move vertically to set depth and click to create; Esc/right-click cancels. The base uses the world plane most directly facing the view. A colored grid preview and live X/Y/Z sizes show the volume before confirmation. Planes are evenly spaced inside the box, grouped in a separate collection, and selected together with the active target. Grid Apply Method offers Bisect (default, cuts the whole active mesh like Cutter Tweak Plane) or Knife Intersect (uses the finite plane faces). Grid planes have no Solidify thickness; legacy grid Solidify modifiers are ignored during application. Creation supports Undo/Redo; the tool is also available in the Pie Menu catalogue.
  - `Cutter Tweak: Local Ring` makes a coarse circular disk from surface intersections near the drawn line. It accepts open, branched and fragmented sections without the strict proximity/closure checks used by Local Contour. `Snap To Volume` estimates the section size; `Surface Diameter` also uses the drawn diameter. Sparse sections fall back to the stroke radius. Nearby geometry may also be covered by the circle; use Local Contour for precise isolation. The line must still hit the target, and the final radius must remain positive.
  - Local Contour intersects evaluated triangles directly and stitches the resulting section segments. Duplicate triangles and coincident split vertices are supported without rebuilding source faces; the source mesh remains unchanged. Truly open or branching sections cannot produce a closed cutter.
  - `Cutter Tweak: Local Contour` creates a filled disk fitted to one closed mesh cross-section, useful for limbs and other local parts. Select the target, choose the tool beside Local Ring, then short Ctrl-click and release at A, followed by a click at B across the desired section. The B click may also use Ctrl. Keep the middle of the line over the part you want to cut. Apply with `Apply Cutter Seams To Active` using Boolean or Knife.
  - The main `Cutter Tweak: Local Contour` tool has three gestures: short Ctrl-click and release at A, then click B for the original two-point section; Ctrl-drag to draw a freehand projected contour (release completes the stroke); Ctrl+Shift-click successive points for Path, then press Space. Path and Draw can begin outside the silhouette. Both create a temporary mesh sheet whose paired front/back rails follow ray hits on both sides of the target with only `Contour Offset` clearance. Long stroke tails outside the silhouette are trimmed to a short lead-in, with their depth interpolated from nearby surface hits. Select the sheet and use Tab/Edit Mode to reshape either side from any view. Return to Object Mode and choose `Finalize Local Contour` in the Cutter panel or tool header. The sheet then becomes a Local Contour cutter that uses the normal Boolean/Knife apply action. Before finalization it is only an editable sketch and cannot be applied as a cutter.
  - If the exact Local Contour section is open or ambiguous, creation tries up to nine nearby alternatives automatically (ten attempts total), with shifts up to 0.5% of the stroke length and tilts up to 1.5 degrees. Shifted anchors are projected back to the evaluated surface. Every accepted result still requires a closed local loop and passes the clearance and neighboring-section checks; a genuinely open surface may remain unfillable.
  - `Contour Points` controls the outline vertex count (default 64); `Contour Offset` adds outward clearance (default 0.002). At zero offset the sampled vertices lie on the surface section. Positive offsets compensate for coarse-outline fitting error so the filled disk reaches beyond the surface. The tool reads evaluated geometry and creates a separate cutter in `Seam Cutters Local Contour`. Open sections or offsets that overlap another section require repositioning the line or adjusting the settings.
  - Knife Seam and Quick Knife Seam tools for preparing group boundaries.
  - Knife Seam's Stable View Cut shows start/end points, a live cut segment, the extended cutting-plane guide, and on-screen hints. Click the end point, then Enter/Space to cut; Esc/right-click cancels.
  - Knife Seam's Knife Mode menu (in the panel and toolbar settings) switches between Plane Cut and Multi-Point Knife. Multi-Point Knife uses the standard interactive Knife: click several points, use right-click to start another line, then Space/Enter applies all cuts and marks them as seams. Esc cancels. Cutting and seam marking share one Undo step.
  - Smooth Face Selection for relaxing selected face regions in Edit Mode.
  - Face Selector in the Edit Mesh toolbar grows a face selection with each click and shrinks it with Ctrl-click. Hold Shift to add polygons with the selected Box, Circle, or Lasso gesture. Its tool settings expose Select Linked (Seam), Delete and Fill, Generate Smart Seams, Pin Selected Seams, Merge Small Islands, Create Longitudinal Seam, and Clear Inside Edges Seam. Delete and Fill is also available from the standard Edit Mesh Delete (`X`) menu.
  - Mark Selected Edges Seam for selected edges in Edit Mode.
  - Mark Selection Boundary Seam for selected faces in Edit Mode.
  - Clear Selected Edges Seam removes seams only from selected edges.
  - Clear Inside Edges Seam removes interior seams from selected faces and marks their boundary, including open mesh borders and holes. Selection and seams outside the region are preserved. Both clear tools support multiple meshes in Edit Mode.
  - `Mark and Clear Seams` → `Edge Seam Path`: select exactly two vertices in the same mesh to select and mark a path along existing edges. Routing favors continuous quad rows and few turns over stair-step shortcuts, including on curved surfaces; triangles and poles use geometric direction. Hidden edges are excluded. No vertices, edges or faces are created or removed. The resulting path is selected in Edge mode.
  - `Edge Seam Path Tool` in the same group and toolbar marks successive paths by clicking A → B → C. Its crosshair turns amber near surface vertices using cached local ray queries instead of scanning every vertex on each redraw; no guide line is drawn. Hover feedback is approximate; clicks retain Blender's native vertex picking and X-Ray behavior. The hover cache refreshes after geometry edits, Undo/Redo and file loading. Space/Esc/right-click ends the chain, Ctrl+Z undoes a segment. Both new commands are available in the searchable Pie Menu catalogue. One or two turns are preferred when the topology permits; obstacles or irregular topology can require more.
  - Selection, Mark and Clear Seams, Seam Checks, and Cutting Tools are grouped under headings with horizontal separators.
  - Connect Vertices with Seam runs Blender's Connect Vertex Path for two selected vertices and marks the connecting edges as seams.
  - Vertex Seam Path in the toolbar (beside Knife Seam / Quick Knife Seam) connects clicked vertices A → B → C. Only the latest endpoint remains selected. Space/Esc/right-click finishes the chain without removing completed seams; each segment has its own Undo step. The tool displays the start point, a cursor guide, and hints, and uses Blender's vertex picking with the current X-Ray setting.
- `Import`
  - `Import Files`: imports several selected files one by one through Blender's file browser, with its own auto rename and Weld options.
  - `Batch Import`: imports supported mesh files from a folder one by one, with nested folders included by default and separate auto rename and Weld options.
  - `Scan Folder`: counts supported mesh files in the selected batch folder without importing them.
  - `Auto Remesh`: enabled by default in Import and Batch Import with HIGH and Clear Material selected. Choose the mutually exclusive Quad backend (LOW/MID/HIGH counts from add-on preferences) or Blender's native Voxel Remesh modifier (default voxel size `0.003`). Each file completes Import → Rename → Weld → Remesh before the next file starts; Rename and Weld follow their checkboxes.
  - The panel shows the file count, completed/failed/remaining counts, current file, processing stage, and overall progress.
  - Timers show total active time, current file time, and approximate remaining time based on the average of successfully completed files. Pauses are excluded; the estimate appears after the first completed file.
  - `Pause` waits until the current file finishes; `Resume` continues. `Stop` finishes the current file and keeps results. `Cancel` (or Esc) aborts remeshing and removes objects created by the current import run.
  - `Start Import` includes a Save File action and a reminder to save the blend file first. Optional Auto Save writes the current blend file after every configured number of source mesh objects successfully completes the full batch pipeline. An unsaved blend is never interrupted by a Save As dialog during the queue; Auto Save waits until the file has a path and reports a warning instead.
  - `Each file in a separate collection` groups the imported file and its remeshed objects in `Generated.001`, `Generated.002`, etc. Before the next batch file starts, the completed collection is excluded from the current View Layer; the final collection stays enabled. Automatic arrangement moves each file's objects together.
- `Remesh`
  - All add-on Remesh buttons and Auto Remesh during import disable Quad Remesher's `Detect Hard Edges by angle` before every engine run, including when it was manually enabled again.
  - Proxies selected Quad Remesher controls when the `quad_remesher` add-on is installed and enabled.
  - Exposes Quad Count, Use Materials, Symmetry X, and Remesh It.
  - LOW/MID/HIGH default to 1,000 / 3,000 / 50,000 quads; customize these in add-on preferences. Separate Remesh LOW/MID/HIGH buttons also start remeshing.
  - Remesh displays its starting/running/importing status, percentage, elapsed time, and actual result polygon count. Cancel stops the current engine job.
  - Results keep the source collection memberships and base name: `Highpoly_Generated.001` → `Retopo_Highpoly_Generated.001` → `Retopo_02_Highpoly_Generated.001`. Existing names advance the Retopo generation counter without changing the source suffix.
  - After the first successful remesh of `Retopo_Highpoly_Generated.001`, that source becomes `Retopo_01_Highpoly_Generated.001`; the new result is generation `02`. Cancelling or failing the remesh leaves the source name unchanged.
- `PolyGroups`
  - Generate PolyGroups accepts `Retopo_*` objects, including `Retopo_Highpoly_Generated.001`, as prepared and starts without the Rename/Weld confirmation.
  - Generate material-based PolyGroups from seam-bounded mesh islands.
  - Convert sculpt Face Sets to materials.
  - Clear PolyGroups materials.
- `AI Generation`
  - Use a shared user prompt library with folder-based collections and `.txt` prompt files.
  - Generate image references from collapsible OpenAI Image and Google Image groups.
  - OpenAI supports `gpt-image-2`, `gpt-image-1`, and `gpt-image-1-mini`.
  - Google supports Gemini image models such as `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, and `gemini-3-pro-image`.
  - Show generated results in Blender's Image Editor and save them next to the `.blend` file.
  - Send an existing Blender image, active object's Base Color texture, or Normal Map texture as image context for prompt-based editing.
  - Configure API keys in add-on preferences or through `OPENAI_API_KEY` and `GEMINI_API_KEY` environment variables.

## Installation

Place this folder here:

```text
Blender/5.2/scripts/addons/polygroups_generator
```

Then enable the add-on in Blender:

```text
Edit > Preferences > Add-ons > AI Retopo Toolkit
```

## Pie Menu Presets

In the add-on preferences, open `Pie Menu Settings`. Click any of the eight slots
to search commands by their English or translated name. The command list includes
selection, seam marking/clearing, seam gap checks, mesh repair, Cutter Tweak tools,
and LOW/MID/HIGH remesh presets. `Select Linked (Seam)` always limits selection by seams.
Slots 1–8 run clockwise from the top; direction labels in preferences show their
positions. Blender's small numeric hints are its standard numpad shortcuts, not slot numbers.

- `General` provides the original broad workflow layout. `Seam Work` contains
  Select Less/More, Delete and Fill, Select Linked (Seam), Mark Seam, Clear Selected
  Seams, Mark Boundary Seam, and Knife Seam Tool.
- Selecting an active preset loads its eight slots immediately. `Current / Custom`
  preserves the previous custom layout and the most recently edited slots.
- `Save As New` creates a named user preset; `Save` updates the active user preset.
  The reload button restores its saved slots. Built-in presets cannot be overwritten.
- `Export JSON` exports the current layout; `Import As New` adds a separate preset,
  automatically giving duplicate names a numbered suffix. Delete removes only a user
  preset and keeps its current slots available.

Presets and the active layout are stored in Blender preferences. If preference
Auto-Save is disabled, use Blender's `Save Preferences` to retain them after restart.
The pie menu shortcut remains Shift+C by default.

## Section Number Shortcuts

Enable `Toggle Sections with Number Keys 0–9` in the add-on's Hotkeys preferences.
It is off by default. The default scope is the AI Retopo sidebar; the optional
Entire 3D View scope takes priority over the usual number shortcuts, including
mesh selection modes in Edit Mode. Numpad shortcuts are unchanged.

- `2`–`9` toggle the corresponding section immediately; `0` toggles section 10.
- `1` waits 0.35 seconds before toggling section 1. Change this interval in preferences.
- Quickly type `10`, `11`, `12`, or `13` to toggle that section without first toggling section 1.
- `Esc` cancels the pending first digit. Starting another command also cancels the wait.
- Single Mode still closes the other sections when one opens. Text/number fields and
  transform numeric input retain their normal keyboard handling.
- Number shortcuts only change section expansion; they preserve the N-panel's
  open/closed state and active sidebar category.

## Development Notes

This repository should track source files only. Python caches, Blender backups, local editor settings, build folders, archives, and logs are ignored through `.gitignore`.
The built-in updater expects this folder to stay a clean git repository; commit or stash local changes before running `Update`.
Bump the add-on patch version in `bl_info` by `0.0.1` only when the user requests a push to the remote repository. Include the version bump in a commit before pushing; ordinary commits do not change the version.


### Batch reports and separate blend output

Each run creates `batch_reports/<timestamp>_<id>/` beside the working `.blend`
(or beside the first input file if the scene has not been saved).
`summary.json` contains total, successful, failed, interrupted and unprocessed
file counts and triangle totals. `files.json` contains per-file input/output
triangles, output path, stages, pass numbers and failure details.
`events.jsonl` is the separate append-only journal of stage transitions,
operator messages and full exception tracebacks. Quad Remesher failures include
available engine progress contents, engine message, process exit code and paths.
Reports update after every file; stopping or cancelling records an interrupted
file separately from failures. A missing engine explanation remains unknown.

Separate output contains only the current Generated collection and the static
scene collections. Previous Generated contents are removed before saving;
empty numbered placeholders remain in the working scene for Retopo restore.
Failed file objects are removed in separate-output mode and their empty
placeholder reserves the collection number. Camera, lights and other objects
outside Generated collections remain in the output.


### Render studio setup

Open Render → Scene Setup and click Prepare Scene to create a curved floor and
backdrop, three Area lights and a camera. The default camera is at (0, -8, 0.5),
looking at (0, 0, 0.5), for an approximately one-metre asset at the origin.
Camera and each light have a movable Aim empty with Track To (-Z, up Y).
The panel exposes positions, aim points, camera projection and focal length,
light color/power/size and backdrop color/width/depth/height/distance/bend radius.
Backdrop dimensions and color update immediately. Bend radius is limited to
the available backdrop height and depth.

Repeated preparation preserves adjusted transforms, camera lens and light
settings and repairs missing elements. Rig objects live in Scene_Studio,
Camera_Studio and Light_Studio collections. The backdrop is compatible with
the render queue's default Scene prefix for transparent-background rendering.

Studio position controls use arrow buttons with a shared configurable movement step (0.1 metre by default) and show
current world coordinates in metres. Camera and camera Aim expose Y/Z only;
lights and their Aim points expose X/Y/Z. Increasing Y moves forward toward
the backdrop; increasing Z moves upward. New Key/Fill lights use 50 W and Rim
uses 100 W. Repeated preparation keeps existing manually adjusted settings.

Reset Entire Studio restores camera, all lights and backdrop defaults. Separate
reset buttons restore the camera, all lights, backdrop or a single light without
changing other sections. Resets include transforms and Aim positions, camera
projection/lens, light color/power/size/visibility, and backdrop color/dimensions.
Missing elements in the selected section are recreated. Each reset supports Undo.

Movement Step (m) applies to every camera, light and Aim arrow. Set it to 1
for one-metre moves. The entire-studio reset returns the step to 0.1 metre.

Light Color Presets offers Neutral, Warm/Cool, Cool/Warm, Sunset, Cyan/Magenta
and Gold/Violet. The first color describes front Key/Fill lighting and the
second describes the Rim light. Palettes change only light colors; positions,
Aim points, power, source sizes and backdrop color remain as adjusted. Prepare
the studio first. Individual light colors remain editable after applying a preset.

Delete all scenes removes every collection whose name starts with Scene_,
Camera_ or Light_ throughout the blend file, including all nested collections
and their objects. Objects also linked to collections outside the removed
hierarchy are preserved there. Unused mesh/camera/light data belonging to deleted
objects is cleaned up. Studio pointers clear automatically and Prepare Scene
can recreate the rig. The operation supports Undo.


### Batch finalization stages 11 and 12

Batch Import adds optional Stage 11 Smart Decimate and Stage 12 Smart LODs.
Enabling one disables the other. Both run after optional baking and before
saving, on the latest processing results. Smart Decimate exposes only a triangle
limit (3000 by default, arrows change it by 1000) and applies its two modifiers
to the final mesh. It requires UV seam edges, as the Mesh Finalization operator
does. Smart LODs exposes 1–5 LODs, a triangle budget per LOD, Final Decimate
Fallback and Triangulate. It uses the existing LOD generator and keeps generated
LODs in the source collection; batch controls do not overwrite the separate
Mesh Finalization settings. Reports include actual triangle counts and whether
requested budgets were reached; unattainable budgets follow the operators'
existing warning behavior.

Mesh Finalization → Decimate → Smart Decimate all generated applies that
section's current settings to the highest numbered original Retopo in every
Generated.N collection in the current scene. Retopo generation numbers are
compared numerically; unnumbered Retopo counts as generation 1. LODs and
SmartDecimated copies are excluded. Hidden collections and objects are temporarily
revealed and restored, and each failed target is reported without stopping other
collections. Selection is restored after processing.

Smart LOD defaults in Batch Import and Mesh Finalization: 5 LODs with budgets
3000, 1500, 1000, 500 and 150 triangles. Saved custom values remain unchanged.


Decimate also provides Hide LOW After Decimate, Show all LOW and Delete all
decimated. Hide LOW disables the source object's viewport display only after
successful single or all-generated decimation. Show all LOW enables the latest
original Retopo per Generated.N collection, revealing its collection path while
preserving unrelated excluded branches; it leaves render visibility unchanged.
Delete all decimated removes SmartDecimated mesh copies throughout the blend
(including legacy names containing _SmartDecimated) and their unused mesh data.
Original Retopo meshes with Decimate modifiers are preserved. Both buttons
support Undo. Batch Stage 11 keeps its independent settings and does not use
the Mesh Finalization Hide LOW option.


### FAB Auto Prepare all generated

FAB Rename adds Auto Prepare all generated. In numeric Generated.N order it
requires the exact Highpoly_Generated.N (HIGH), the highest numbered original
Retopo (MID), and that MID's exact SmartDecimated copy (LOW). It skips incomplete
sets with a warning instead of falling back to an older Retopo or its LOW.
Only this triplet moves to AssetName_NN_Collection; earlier passes and LODs stay
in Generated. One index is shared across HIGH/MID/LOW, mesh data, materials and
texture names, and the indexed Textures/AssetName_NN directory. MID and LOW keep
the established shared M_AssetName_NN / T_AssetName_NN naming; HIGH uses _HIGH.
Shared source materials and images are isolated from other assets before rename.

The all-generated action allocates a unique numeric index per complete set,
advances it once per asset and skips already occupied indices. It starts at the
Index field and leaves the next index there. Incomplete sets do not consume an
index. This batch action increments indices for every asset; the Auto +1 toggle
continues to control the individual and selected-set actions. Collection names
and texture folders for selected-set preparation also include the current index.


Auto Prepare all generated now opens an Asset Name reminder/edit dialog before
starting from the panel. Interactive runs use a timer-driven queue: each asset
is announced to the panel before preparation, allowing progress to update
between assets. FAB Rename shows the queue and each item's status, current
collection, processed/total progress and prepared/skipped/error counts. Blender's
native progress indicator is updated too. Stop Queue or Esc stops between
assets and preserves completed work. A failed asset is marked with its error
and subsequent assets continue; partial work on the failed asset remains
available for inspection or Undo. Settings are captured at queue start.
Scene loading and add-on unregistering stop the queue and release its timer.
Background/script execution uses the same queue synchronously.


Scene Setup provides Collection Color Tag, defaulting to Color 8. It applies to
Scene_Studio, Camera_Studio and Light_Studio and updates existing studio tags
immediately. Preparation moves those root collections ahead of other roots in
Scene → Camera → Light order, preserving visibility, selection and exclusions
across view layers. When new studio collections are created, View Layer Outliners
switch off alphabetic sorting and collapse the tree to show collapsed top-level
collections. This also folds other top-level collection branches. Entire-studio
reset restores Color 8; other scoped resets retain the chosen tag.
