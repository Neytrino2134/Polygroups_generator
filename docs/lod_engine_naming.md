# Smart LOD engine naming

The Unity / Unreal selector above Generate LODs controls both Generate LODs and
Smart LODs + Prepare. LOD Count budgets start at LOD0. Existing saved triangle
budgets keep their RNA property identifiers (`smart_lods_target_1` is LOD0).

| Mode | Generated meshes | Combined preparation |
| --- | --- | --- |
| Unity | `Source.LOD0`, `Source.LOD1`, … | Existing Unity preparation/export |
| Unreal | `Source_LOD0`, `Source_LOD1`, … | Unreal LOD Rename/material preparation |

Unity preparation retains its established bare asset name for prepared LOD0 and
`.LOD1`, `.LOD2`, … for later meshes. Legacy `.LOD.1` generated meshes remain
readable as one-based Unity input. Generation refuses to duplicate a legacy pack.

Unreal combined preparation respects LOD Count; it no longer forces three
HIGH/MID/LOW meshes through the FAB preparation operator. FAB's separate variant
workflow remains available independently.

Both original Generated.N/Retopo sources and renamed asset collections work.
For Unreal, trailing `_HIGH`, `_MID`, `_LOW` or an existing LOD suffix is replaced
when building target names, rather than stacking suffixes. For example:

```
GraveStones_02_01_Collection
  SM_GraveStones_02_01_MID       # original source retained
  SM_GraveStones_02_01_LOD0
  SM_GraveStones_02_01_LOD1
  SM_GraveStones_02_01_LOD2
```

Combined preparation recognizes that source asset's name and indices and keeps
its identity, temporarily overriding Unreal fields without changing their saved
values. Generated.N input uses the displayed Unreal asset/name/version fields.
Unselected original quality variants remain in the existing asset collection.
Existing conflicting LOD objects are never overwritten. Selecting multiple
source quality variants that resolve to the same output pack is rejected before
generation.

Validation covers both buttons, engines and HIGH/MID inputs; unchanged source
geometry, labels, decimation budgets, zero-area cleanup, legacy Unity input and
Unity/Unreal export regressions. The older `test_unity_preparation.py` still
expects the obsolete single-index `Asset_01` scheme; the current pre-refactor
Unity function already returns `Asset_00_01`. `test_unity_export_workflow_blender.py`
verifies the current two-index workflow, including actual GLTF export.
