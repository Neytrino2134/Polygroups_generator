# PolyGroups Generator

Blender add-on for accelerating semi-automatic retopology workflows on generated AI 3D models.

The add-on currently targets Blender 5.0-5.2 and adds a `PolyGroups` tab to the 3D View sidebar.

## Current Tools

- `Model Preparation`
  - `Apply Weld`: adds or updates a Weld modifier on selected mesh objects.
  - Default weld distance: `0.0001`.
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
