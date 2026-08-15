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
- `Seam Preparation`
  - Knife Seam and Quick Knife Seam tools for preparing group boundaries.
  - Smooth Face Selection for relaxing selected face regions in Edit Mode.
  - Mark Selected Edges Seam for selected edges in Edit Mode.
  - Mark Selection Boundary Seam for selected faces in Edit Mode.
- `Import`
  - `Import Files`: imports several selected files one by one through Blender's file browser, with its own auto rename and Weld options.
  - `Batch Import`: imports supported mesh files from a folder one by one, with separate auto rename and Weld options.
  - `Scan Folder`: counts supported mesh files in the selected batch folder without importing them.
- `Remesh`
  - Proxies selected Quad Remesher controls when the `quad_remesher` add-on is installed and enabled.
  - Exposes Quad Count, Use Materials, Symmetry X, and Remesh It.
- `PolyGroups`
  - Generate material-based PolyGroups from seam-bounded mesh islands.
  - Convert sculpt Face Sets to materials.
  - Clear PolyGroups materials.
- `AI Generation`
  - Generate image references from collapsible OpenAI Image and Google Image groups.
  - OpenAI supports `gpt-image-1` and `gpt-image-1-mini`.
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

## Development Notes

This repository should track source files only. Python caches, Blender backups, local editor settings, build folders, archives, and logs are ignored through `.gitignore`.
The built-in updater expects this folder to stay a clean git repository; commit or stash local changes before running `Update`.
Before each commit, bump the add-on patch version in `bl_info` by `0.0.1`.
