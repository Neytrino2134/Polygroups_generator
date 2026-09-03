# AI Retopo Toolkit

Blender add-on for accelerating semi-automatic retopology workflows on generated AI 3D models.

The add-on currently targets Blender 5.0-5.2 and adds an `AI Retopo` tab to the 3D View sidebar.
The interface can be switched between English and Russian in the add-on preferences or directly in the main panel.
Add-on preferences include Git-based update checks and fast-forward updates from the configured `origin` remote.

## Current Tools

- `Model Preparation`
  - `Mesh Editing` → `Delete and Fill`: in Edit Mode, replace selected face patches with a triangular fill of their boundaries, removing unused interior edges and vertices. New triangles stay selected. Other holes, unselected islands, and boundary seams are preserved. Supports multiple edited meshes and Undo; an invalid boundary cancels before deleting geometry.
  - `Rename Objects`: renames selected objects as `Highpoly_Generated.001`, `Highpoly_Generated.002`, and so on. Objects already in a numbered `Generated.N` collection keep their collection memberships; other objects move to `Generated`.
  - `Apply Weld`: adds and applies a Weld modifier on selected mesh objects.
  - Default weld distance: `0.0001`.
  - Hide/Show All Highpoly and Retopo toggles Disable in Viewport (monitor icon) for matching `Highpoly_` / `Retopo_` objects in the current scene, including excluded collections. This object setting applies across View Layers; eye visibility and render visibility are preserved.
  - Isolate Other Collections excludes other numbered `Generated.N` collections. Previous/Next Collection switches them in numeric order and selects a visible object in the destination; unrelated collections are preserved.
- `Seam Preparation`
  - Local Contour is experimental: automated geometry tests pass, but contour creation still fails in the reported user workflow and needs further investigation.
  - `Cutter Tweak: Local Contour` creates a filled disk fitted to one closed mesh cross-section, useful for limbs and other local parts. Select the target, choose the tool beside Local Ring, Ctrl-click A, then click B across the desired section. Keep the middle of the line over the part you want to cut. Apply with `Apply Cutter Seams To Active` using Boolean or Knife.
  - `Contour Points` controls the outline vertex count (default 64); `Contour Offset` adds outward clearance (default 0.002). Coarse outlines compensate for fitting error so the disk reaches beyond the surface. The tool reads evaluated geometry and creates a separate cutter in `Seam Cutters Local Contour`. Open sections or offsets that overlap another section require repositioning the line or adjusting the settings.
  - Knife Seam and Quick Knife Seam tools for preparing group boundaries.
  - Knife Seam's Stable View Cut shows start/end points, a live cut segment, the extended cutting-plane guide, and on-screen hints. Click the end point, then Enter/Space to cut; Esc/right-click cancels.
  - Knife Seam's Knife Mode menu (in the panel and toolbar settings) switches between Plane Cut and Multi-Point Knife. Multi-Point Knife uses the standard interactive Knife: click several points, use right-click to start another line, then Space/Enter applies all cuts and marks them as seams. Esc cancels. Cutting and seam marking share one Undo step.
  - Smooth Face Selection for relaxing selected face regions in Edit Mode.
  - Mark Selected Edges Seam for selected edges in Edit Mode.
  - Mark Selection Boundary Seam for selected faces in Edit Mode.
  - Clear Selected Edges Seam removes seams only from selected edges.
  - Clear Inside Edges Seam removes interior seams from selected faces and marks their boundary, including open mesh borders and holes. Selection and seams outside the region are preserved. Both clear tools support multiple meshes in Edit Mode.
  - `Mark and Clear Seams` → `Edge Seam Path`: select exactly two vertices in the same mesh to select and mark a path along existing edges. Routing favors continuous quad rows and few turns over stair-step shortcuts, including on curved surfaces; triangles and poles use geometric direction. Hidden edges are excluded. No vertices, edges or faces are created or removed. The resulting path is selected in Edge mode.
  - `Edge Seam Path Tool` in the same group and toolbar marks successive paths by clicking A → B → C. Its crosshair turns amber near a visible vertex (or a vertex behind the surface when X-Ray is enabled); no guide line is drawn. Space/Esc/right-click ends the chain, Ctrl+Z undoes a segment. Both new commands are available in the searchable Pie Menu catalogue. One or two turns are preferred when the topology permits; obstacles or irregular topology can require more.
  - Selection, Mark and Clear Seams, Seam Checks, and Cutting Tools are grouped under headings with horizontal separators.
  - Connect Vertices with Seam runs Blender's Connect Vertex Path for two selected vertices and marks the connecting edges as seams.
  - Vertex Seam Path in the toolbar (beside Knife Seam / Quick Knife Seam) connects clicked vertices A → B → C. Only the latest endpoint remains selected. Space/Esc/right-click finishes the chain without removing completed seams; each segment has its own Undo step. The tool displays the start point, a cursor guide, and hints, and uses Blender's vertex picking with the current X-Ray setting.
- `Import`
  - `Import Files`: imports several selected files one by one through Blender's file browser, with its own auto rename and Weld options.
  - `Batch Import`: imports supported mesh files from a folder one by one, with separate auto rename and Weld options.
  - `Scan Folder`: counts supported mesh files in the selected batch folder without importing them.
  - `Auto Remesh`: independently available in Import and Batch Import with LOW/MID/HIGH counts from add-on preferences. Each file completes Import → Rename → Weld → Remesh before the next file starts; Rename and Weld follow their checkboxes.
  - The panel shows the file count, completed/failed/remaining counts, current file, processing stage, and overall progress.
  - Timers show total active time, current file time, and approximate remaining time based on the average of successfully completed files. Pauses are excluded; the estimate appears after the first completed file.
  - `Pause` waits until the current file finishes; `Resume` continues. `Stop` finishes the current file and keeps results. `Cancel` (or Esc) aborts remeshing and removes objects created by the current import run.
  - `Each file in a separate collection` groups the imported file and its remeshed objects in `Generated.001`, `Generated.002`, etc. Automatic arrangement moves each file's objects together.
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
Before each commit, bump the add-on patch version in `bl_info` by `0.0.1`.
