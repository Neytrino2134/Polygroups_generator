# FAB Rename: independent Unreal LOD naming

FAB Rename now contains two independently collapsible groups:

- HIGH / MID / LOW: the original FAB settings, operators, visibility and queue.
- Unreal LOD Rename: independent asset name, name index, version index,
  material/texture preparation, texture copying and collection color settings.

Select the original and its LOD meshes and run Prepare / Rename LOD Meshes.
Multiple selected `Generated.N` collections are processed independently in
numeric collection order. Only selected meshes are included. For example,
starting with Name Index 19 and Version Index 01 yields `Asset_19_01`,
`Asset_19_02`, etc. Name Index remains fixed; the starting Version Index field
is retained so the same selection can be processed again without new indices.
Already renamed packs are grouped by their own asset collections on reruns.
Ambiguous collection membership and mixtures of Generated packs with unrelated
selected meshes are rejected. Every pack is preflighted before any renaming.

Evaluated polygon counts determine descending order; ties use object names.
The most detailed mesh becomes LOD0. Geometry and transforms are preserved.

For Tree_Tropic / 19 / 01, the collection is `Tree_Tropic_19_01_Collection` and contains
`SM_Tree_Tropic_19_01_LOD0`, `SM_Tree_Tropic_19_01_LOD1`, etc. Mesh datablocks
receive the same names. Selected meshes are moved out of their old collections;
unselected objects and old collection datablocks are retained.

With Keep Highest as High enabled, the most detailed mesh receives the
editable High Suffix (default `_HIGH`), and the remaining meshes start at
`LOD0`. For example: `SM_Tree_Tropic_19_01_HIGH`,
`SM_Tree_Tropic_19_01_LOD0`, `SM_Tree_Tropic_19_01_LOD1`.

Render > Quality and Output includes independent LOW, MID, HIGH filters and
a multiple-choice LODs menu (LOD0 through LOD5). Scan Queue and Start Render
use these filters for every asset collection. HIGH also accepts `_High` and
custom High suffixes tagged by Unreal LOD Rename. Selected variants use the
same Multiview, Hero, Freestyle and transparent-output settings as LOW/MID.
Existing selected-only Unreal collections are migrated to `_Collection` on rename.

Optional material preparation preserves material slots and shared-material
relationships while isolating unselected assets. Names use `M_<asset>` and
`T_<asset>_<channel>`, with textures copied to `Textures/<asset>`. Bake masks
are preserved without being treated as ordinary texture channels. Repeating
the operation on the prepared set reuses its materials and image datablocks.

The implementation lives in unreal_lod_rename.py and does not import Unity
preparation or use Unity settings. Unity and legacy FAB names are unchanged.

Blender 5.2 validation: test_unreal_lod_rename_blender.py,
test_unreal_lod_batch_blender.py, test_fab_all_generated.py, and
test_unity_export_workflow_blender.py passed.
