# AI Retopo Toolkit

Blender add-on for accelerating semi-automatic retopology workflows on generated AI 3D models.

The add-on currently targets Blender 5.0-5.2 and adds an `AI Retopo` tab to the 3D View sidebar.
The interface can be switched between English and Russian in the add-on preferences or directly in the main panel.
Add-on preferences include Git-based update checks and fast-forward updates from the configured `origin` remote.

## Current Tools

- `Model Preparation`
  - `Rename Objects`: renames selected objects as `Highpoly_Generated.001`, `Highpoly_Generated.002`, and so on, then moves them to the `Generated` collection.
  - `Apply Weld`: adds and applies a Weld modifier on selected mesh objects.
  - Default weld distance: `0.0001`.
  - Hide/Show All Highpoly and Retopo toggles Disable in Viewport (monitor icon) for matching `Highpoly_` / `Retopo_` objects in the current scene, including excluded collections. This object setting applies across View Layers; eye visibility and render visibility are preserved.
  - Isolate Other Collections excludes other numbered `Generated.N` collections. Previous/Next Collection switches them in numeric order and selects a visible object in the destination; unrelated collections are preserved.
- `Seam Preparation`
  - Knife Seam and Quick Knife Seam tools for preparing group boundaries.
  - Smooth Face Selection for relaxing selected face regions in Edit Mode.
  - Mark Selected Edges Seam for selected edges in Edit Mode.
  - Mark Selection Boundary Seam for selected faces in Edit Mode.
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
  - Proxies selected Quad Remesher controls when the `quad_remesher` add-on is installed and enabled.
  - Exposes Quad Count, Use Materials, Symmetry X, and Remesh It.
  - LOW/MID/HIGH default to 1,000 / 3,000 / 50,000 quads; customize these in add-on preferences. Separate Remesh LOW/MID/HIGH buttons also start remeshing.
- `PolyGroups`
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
