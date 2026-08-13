# PolyGroups Generator

Blender add-on for accelerating semi-automatic retopology workflows on generated AI 3D models.

The add-on currently targets Blender 5.0-5.2 and adds a `PolyGroups` tab to the 3D View sidebar.

## Current Tools

- `Model Preparation`
  - `Rename Objects`: renames selected objects as `Highpoly_Generated.001`, `Highpoly_Generated.002`, and so on, then moves them to the `Generated` collection.
  - `Apply Weld`: adds and applies a Weld modifier on selected mesh objects.
  - Default weld distance: `0.0001`.
- `Import`
  - `Import Files`: imports several selected files one by one through Blender's file browser, with its own auto rename and Weld options.
  - `Batch Import`: imports supported mesh files from a folder one by one, with separate auto rename and Weld options.
  - `Scan Folder`: counts supported mesh files in the selected batch folder without importing them.
- `PolyGroups`
  - Generate material-based PolyGroups from seam-bounded mesh islands.
  - Convert sculpt Face Sets to materials.
  - Clear PolyGroups materials.
  - Knife Seam and Quick Knife Seam tools for preparing group boundaries.

## Installation

Place this folder here:

```text
Blender/5.2/scripts/addons/polygroups_generator
```

Then enable the add-on in Blender:

```text
Edit > Preferences > Add-ons > PolyGroups Generator
```

## Development Notes

This repository should track source files only. Python caches, Blender backups, local editor settings, build folders, archives, and logs are ignored through `.gitignore`.
