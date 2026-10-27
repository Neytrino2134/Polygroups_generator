# UV boundary relaxation after Smart Decimate / Smart LODs

Smart LODs relaxes the active UV map after each applied inherited modifier,
seam-decimation pass, body-decimation pass, optional final decimation pass,
triangulation and zero-area cleanup that actually removes geometry. Each LOD
therefore passes its corrected UVs to the next LOD.

Smart Decimate has **Reunwrap UV / Pin Island Borders**, enabled by default.
With an existing UV map, this applies its seam and body modifiers to the current
mesh, with UV relaxation after each pass. If Duplicate And Apply is selected,
it processes that copy. Disabling the UV option retains the previous live-modifier
workflow. The All Generated variant uses the same option. Meshes without UV maps
are not assigned a new UV map and retain the previous apply/duplicate behavior.

The helper finds marked seams, open mesh boundaries and actual UV discontinuities
even without marked seams. It temporarily pins their corner UVs, adds temporary
seams along UV splits and runs Angle Based unwrap. Existing user pins remain fixed.
Boundary coordinates are restored exactly after the solver. Original pin flags,
seam flags, mesh/UV selection and selection modes are restored afterward. Other
UV maps remain untouched. There is no packing, average-island-scale operation or
global UV atlas relocation. A UV-less mesh is a no-op.

Smart Decimate snapshots its mesh before applying passes. If UV repair fails,
the pre-apply mesh and configured modifier stack are restored, and the operator
reports the failure. Smart LODs uses its existing generated-LOD rollback path.

This relaxes interior UV distortion on the reduced topology. It cannot recover
detail already removed by decimation, and border positions refer to the mesh
immediately after each pass. Visual results on production textured assets still
need inspection; heavily altered geometry may need texture rebaking.

`test_uv_boundary_relax_blender.py` checks exact boundary preservation, user pins,
secondary UV maps, unmarked UV splits, the reduction of interior distortion on a
planar grid, invocation for both Smart Decimate passes and multiple LODs, source
preservation and restoration after an injected solver failure. Existing Smart
LOD/Decimate tests cover budgets, multiple sources, preparation and zero-area cleanup.
