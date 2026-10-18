# FAB Rename: independent Unreal LOD naming

FAB Rename now contains two independently collapsible groups:

- HIGH / MID / LOW: the original FAB settings, operators, visibility and queue.
- Unreal LOD Rename: independent asset name, name index, version index,
  material/texture preparation, texture copying and collection color settings.

Select the original and its LOD meshes and run Prepare / Rename LOD Meshes.
Evaluated polygon counts determine descending order; ties use object names.
The most detailed mesh becomes LOD0. Geometry and transforms are preserved.

For Tree_Tropic / 19 / 01, the collection is `Tree_Tropic_19_01` and contains
`SM_Tree_Tropic_19_01_LOD0`, `SM_Tree_Tropic_19_01_LOD1`, etc. Mesh datablocks
receive the same names. Selected meshes are moved out of their old collections;
unselected objects and old collection datablocks are retained.

Optional material preparation preserves material slots and shared-material
relationships while isolating unselected assets. Names use `M_<asset>` and
`T_<asset>_<channel>`, with textures copied to `Textures/<asset>`. Bake masks
are preserved without being treated as ordinary texture channels. Repeating
the operation on the prepared set reuses its materials and image datablocks.

The implementation lives in unreal_lod_rename.py and does not import Unity
preparation or use Unity settings. Unity and legacy FAB names are unchanged.

Blender 5.2 validation: test_unreal_lod_rename_blender.py,
test_fab_all_generated.py, and test_unity_export_workflow_blender.py passed.
