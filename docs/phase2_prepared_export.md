# Phase 2 / Batch Finalization / Export Prepared Models

Export selects prepared mesh objects from current-scene *_Collection assets:
_MID, _HIGH and _LODN meshes, plus Unity Prepare objects with Unity base/.LODN
naming. Temporary Multiview copies, texture preview planes, unrelated meshes
and collections from other scenes are excluded. Previously hidden collection
paths are revealed before selection.

The Unreal / FAB pipeline uses section 12 Export Selected Meshes. Unity uses
section 12 Export Unity Assets in prepared-model batch mode. Formats can be
combined: GLB (default), GLTF and FBX. Sort By defaults to LODs / Format, with
one shared format directory and Textures folder for all assets. LODs instead
uses one asset directory with format subdirectories.

Mesh Info JSON defaults on. Reports include per-mesh counts, asset grouping,
engine and polygon statistics. Common-folder reports aggregate the entire
selection, rather than being overwritten once per collection. Status is also
written to the common Phase 2 Processing Status.

FAB uses !Unreal beside the saved blend and the section-12 GLB/GLTF grouping
settings. Unity uses its configured directory, texture naming and GLB/GLTF
grouping settings. Unity autosave and overwrite permissions are respected;
autosave runs before temporary format overrides so manual exporter settings
remain intact in the saved blend. Unity Clear Asset Folder permits replacing
this batch's outputs, but shared format directories are not erased: unrelated
asset files remain intact. The model batch does not launch Unity render/video
tasks. Rigged Auto-Rig Pro exports remain in section 12's ordinary exporter.

GLB is also available in the ordinary Unity Export section and Unity presets.
The existing manual FBX/GLTF behavior is retained.

## Generated.N cleanup

Delete Generated.N after Successful Rename defaults off. When enabled, only
collections whose preparation/rename completed successfully are removed after
visibility and selection restoration. LOD generation alone does not delete the
source collection. Failed packs remain. Final *_Collection assets and objects
linked elsewhere are preserved. Objects exclusively left in the old processing
shell are removed; child collections are kept reachable.

## Validation in Blender 5.2

- test_phase2_prepared_export_blender.py exports two assets in all three formats
  through each pipeline, checks JSON counts, settings/transform restoration,
  GLB-only ordinary Unity export, hidden asset selection, successful cleanup,
  shared-object preservation, and failure retention.
- test_batch_finalization_blender.py checks existing LOD and rename workflows.
- test_unreal_lod_export_blender.py checks existing multi-format texture export.
- test_unity_export_workflow_blender.py checks existing Unity workflow/presets.
