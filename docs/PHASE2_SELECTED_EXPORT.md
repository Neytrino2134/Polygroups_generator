# Phase 2 selected export

Batch Finalization now includes two additional manual buttons:

- **Export Selected** under Export Prepared Models.
- **Export Selected Blend** under Export Blend Files.

Both reuse their existing operator with `selected_only=True`; normal Export
and automatic Phase 2 calls retain the original all-assets behavior.

## Model export

Only the current mesh selection is passed to the existing Unreal/Unity
exporter. Selected non-mesh objects are excluded from the export. Formats
(GLB/GLTF/FBX), combined/separate modes, folder sorting, Unity destination and
MeshInfo JSON follow the existing Phase 2 settings. Existing output files are
replaced. Unity Overwrite is temporarily enabled for this action, folder
clearing disabled, and both original options restored afterwards. Unselected
mesh export files are left in place. Selection and the active object are
restored, including selected non-mesh objects.

## Selected blend files

The selected meshes are grouped by their owning asset collections and saved
under the existing `!Blend/<asset>.blend` paths. Unselected siblings and other
assets are excluded, even when the all-export Generated.N option is enabled.
Explicitly selected Generated.N meshes can also be exported. Ambiguous
membership in multiple asset collections is reported rather than writing
multiple overlapping files.

The existing texture packing, reset-Y and studio/camera/light behavior is
retained. Export-only object copies preserve geometry/materials and selected
parent relationships. Unselected parents are detached at the current world
transform; copied constraints/animation links are cleared for this static
snapshot. Original mesh objects, transforms, parenting, collection membership,
names and selection are preserved. Existing blend files are replaced only
after the new file was written successfully; temporary files are cleaned up
on failure.

## Validation

`tests/test_phase2_selected_export_blender.py` passed in Blender 5.2:

- Actual GLB/GLTF/FBX exports for Unreal and Unity with existing-file replacement.
- GLB node inspection and MeshInfo confirm selected meshes only.
- An existing unselected mesh export file remains untouched.
- Selected blend subsets across two multi-mesh assets contain their own meshes,
  collection and textures only; an unselected parent and Generated asset do not leak.
- Selected objects, active object, parenting, source names, memberships and
  positions are retained. Reset-Y affects only the saved copy.
- An injected blend-write failure keeps the previous file and working state.
- Empty mesh selections stop without export; both selected-action UI bindings exist.

Existing `test_phase2_prepared_export_blender.py` and
`test_phase2_blend_export_blender.py` passed, covering the original all-assets
export paths, packed textures, studio collections and Generated.N export.
