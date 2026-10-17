# Unity same-index reexport

Select the prepared meshes for one asset, open Prepare and Export, and keep
the same Name Index and Version Index. Matching prepared meshes/materials are
reused instead of generating more LODs, materials, and image datablocks. This
also leaves the version unchanged when Auto Increment is enabled.

With Clear Asset Folder Before Start enabled, both Prepare and Export and
Export Unity Assets stage all material images (including disconnected nodes,
nested groups, and service masks) in a temporary directory before clearing
`Textures/<asset>` and `<Unity export directory>/<asset>`.

Unmodified source files and packed bytes are copied without re-encoding.
Edited/generated images are saved from current pixels; floating point buffers
use EXR for staging. The texture folder is rebuilt and image paths rebound
before exporting. A failure while rebuilding restores both old directories.
This rollback covers texture refresh, not a later exporter/render failure.

Already prepared same-index meshes retain their datablock identities. New or
unprepared meshes still run Prepare Meshes Auto LODs. Service masks remain
excluded from FBX/GLTF materials. With cleanup disabled, existing Overwrite
behavior is retained.

Verified in Blender 5.2 with:

- `test_unity_asset_texture_isolation_blender.py`: repeat same index, no new
  datablocks, Auto Increment, disconnected texture preservation, source files
  inside the deleted export directory, both folder cleanups, injected restore
  failure rollback, neighboring asset preservation, and working-file reopen.
- `test_unity_export_workflow_blender.py`: generation, Skip LODs, reexport.
- `test_bake_mask_export_blender.py`: service mask exclusion/restoration.
