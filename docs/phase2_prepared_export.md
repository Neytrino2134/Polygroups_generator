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

## Export Blend Files

Batch Finalization has a second export box, Export Blend Files. Each top-level
*_Collection asset with objects is written to !Blend beside the saved blend as
its own file, named like the collection without _Collection (Stone_01_01.blend).
Every file holds a Scene, Camera, Light and the one collection; only the
textures used by that collection's materials are packed (Pack Textures, on by
default), and temporary packing is removed from the working file afterwards.
Existing files with the same name are overwritten. Open !Blend Folder shows the
result. Implementation: operators/phase2_blend_export.py. The scene is derived
from a copy of the active scene because bpy.data.scenes.new() crashes
libraries.write in Blender 5.2. Test: test_phase2_blend_export_blender.py.

Studio collections: when the source scene has Scene_Studio, Camera_Studio and
Light_Studio (tagged by Render Studio), they are linked into every exported
scene with all nested collections and objects, and the active camera is kept.
Their textures are packed too. A generated Camera/Light is used only when the
scene has no studio collections.

Export Generated.N Collections (off by default): also writes every Generated.N
collection that contains objects (Retopo / Resculpting meshes) to !Blend as
Generated.001.blend etc., using the same clean scene and packing only that
collection's textures.
