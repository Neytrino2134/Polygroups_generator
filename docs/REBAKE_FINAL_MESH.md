# ReBake Final Mesh — 2026-10-27

Operator: `object.polygroups_rebake_final_mesh`.
UI: Baking > Auto Prepare and Bake, immediately adjacent button **ReBake Final Mesh**.
Reload the add-on or restart Blender after updating.

## Usage

Make the final `SM_<asset>_<NN>_MID` mesh active and press the new button.
For example, `SM_Crystals_Pack_02_02_MID` resolves to
`Resculpting_01_Highpoly_Generated.002`, including when it belongs to a different
collection (`Generated.002`). An existing matching Highpoly in the current scene is reused. If absent, ReBake
automatically appends its Generated collection from a neighboring !Blend file
as described below. Ambiguous existing sources still stop before scene setup. Contradictory Generated collection
indices, linked data and shared mesh datablocks are rejected explicitly.

The operator runs the existing staged Bake Task (Base Color, tangent Normal,
configured AutoCage/Smart Cage, projection diagnostics and artifact autofill).
Enabled passes, margins and cage options come from the usual Bake Settings.
It forces selected-to-active, uses existing final texture resolution, retains
final UVs (no automatic repack), and suppresses Generated renaming and the
ordinary temporary Bake texture save path.

## Scene preparation and completion

- Reveal the target and Highpoly, including hidden/excluded ancestor collections.
- Enable Highpoly Multires for viewport/render and temporarily use its render
  subdivision level in the viewport so cage analysis sees the bake geometry.
- Align Highpoly world translation to MID, retaining both rotations/scales and
  mesh coordinates. MID stays at its existing world position.
- Prepare copied Highpoly materials and a separate temporary target material.
  Preserve all original final material slots and polygon material indices.
- Restore original placement, collection/object visibility, Multires settings,
  source materials, selection/mode and overridden bake options on completion,
  cancellation or failure. New final images remain assigned to final materials.

## Outputs

Existing final material image nodes own the output paths. Stale object
`polygroups_bake_*` properties referencing `Bake_Temp_*` do not override them.
Base Color and Normal require existing local square PNGs of matching size.
ReBake writes each enabled map to its existing filename and directory, reuses
its existing image datablock and refreshes other material users of that image.

For asset 02 the verified paths are:

- `Textures/Crystals_Pack_02_02/T_Crystals_Pack_02_02_BaseColor.png`
- `Textures/Crystals_Pack_02_02/T_Crystals_Pack_02_02_Normal.png`

MergeMask and enabled ArtifactMask use existing final `T_<asset>_*` references
when available, otherwise `T_<asset>_MergeMask.png` / `_ArtifactMask.png` beside
the enabled final color/normal texture. Artifact metadata is saved alongside
its PNG. ReBake does not create a Bakes/TempBake output directory. Working
images/materials and hidden staging directories are removed after the task.

Packed final images are temporarily unpacked without writing the old packed
bytes, reloaded from the replacement PNG and packed again. Thus external files
and embedded blend textures both reflect the new bake. The blend file itself
is not automatically saved.

All bake/postprocess passes must succeed before file replacement. Outputs are
staged in their destination directories; replacements are rolled back from
backups if any replacement fails. Cancellation before finalization leaves
existing PNGs untouched.

## Verification

`tests/test_rebake_final_blender.py` passed in installed Blender 5.2 using real
CPU Cycles bakes at 32px, with a tilted Multires Highpoly initially hidden in
an excluded collection. It verifies:

- Correct numbered source despite a different collection and spatial offset.
- Both selected-to-active passes, updated BaseColor pixels and Normal map.
- Existing final image identities, paths, resolution and packing retained.
- Old Bake_Temp image left untouched; no new temporary bake output tree.
- Final material slots, polygon material indices and UV coordinates retained.
- Collection/object visibility, translation, modifiers and settings restored.
- Artifact mask valid against the final normal, including saved metadata.
- Injected bake failure, PNG replacement failure and cancellation restore state;
  file replacement failure rolls back already replaced files.
- Missing/ambiguous sources rejected and UI button adjacent to AutoBake.

Read-only `test_rebake_final_asset_blender.py` verified the real asset's 2048px
packed BaseColor/Normal image bindings. That exported blend does not include
its Resculpting Highpoly, so no real asset texture was rebaked or overwritten.
The operator now loads the missing Generated.002 collection automatically from
!Blend/Generated.002.blend when that source file is present.

Existing `test_bake_auto_source.py`, `test_batch_autobake.py` and
`test_projection_mask_batch_blender.py` passed in Blender, including ordinary
Batch AutoBake output and separate blend reopening.

## Manual Phase 2 button and optional LODs

A second ReBake Final Mesh button is directly below **Start Phase 2 Process**.
Its **Create LODs** checkbox is off by default. This is a separate manual action:
it is not a stage of the automatic Phase 2 run and does not change its queue.
The Baking-section ReBake button retains its bake-only default.

With Create LODs enabled, the manual button captures:

- Phase 2's Pipeline selector above Start (`FAB` -> Unreal, or Unity).
- The existing asset identity from the active MID name; Phase 2 naming values
  are a fallback for a legacy MID name without the full identity.
- Current Smart LOD count, triangle budgets, decimation, cleanup, arrangement,
  label and engine-specific material/texture preparation options.

Only after all bake passes and final texture replacement succeed, the action
creates LODs from the active MID and prepares only those generated meshes for
the chosen engine. MID keeps its geometry, original materials and placement;
Highpoly and scene setup are already restored before LOD generation starts.
The original engine settings and selection/mode are restored afterwards.
Unreal's Keep High is disabled for this scoped operation so MID is not renamed
or treated as LOD0. The MID's existing identity takes precedence over stale Phase 2 naming defaults,
so rebaking asset 02_02 cannot replace asset 02_01 because of an old Version Index. Unity's optional index increment does not modify the
Phase 2 defaults after this operation.

Existing LOD meshes are detected by the selected asset's final/raw LOD name
patterns or explicit source/index/engine metadata, within the current scene.
This includes stale levels beyond the newly configured LOD count and LODs in
other collections belonging to this same asset. Different asset numbers and
the other engine's prepared LODs remain intact. A non-mesh name collision or
an object belonging to a different scene is reported rather than deleted.

After a successful bake, old LODs and their text labels are held in an unlinked
backup collection, freeing names and collection membership while replacements
are generated and prepared. Only after complete success are the old objects
and unused mesh/curve datablocks removed. On failure new meshes/labels are
removed and original names, meshes, collection links and labels restored.
MID, Highpoly, existing materials/images and unrelated assets are preserved.
The status distinguishes a successful rebake from failed LOD creation.

The real-Cycles integration test also verifies Unreal and Unity output names,
LOD count/budgets, MID preservation, unchanged Phase 2 state, the Phase 2 button
position and checkbox, collisions, no LODs after a failed bake, and bake-only
behavior when the manual option was not passed. Existing Phase 2 pipeline and
Smart LOD preparation regression tests passed as well.


Replacement regression (2026-10-27): real Cycles integration covers both engines,
repeated rebakes with existing LODs, removal of stale LOD4 when requesting two
levels, associated text labels, restoration of original objects/data/collection
links after an injected LOD generation failure, and preservation of five
02_01 LOD meshes in another collection while rebaking 02_02 with stale 01
Phase 2 naming defaults. The automatic Phase 2 pipeline remains unchanged.

## Export Selected FBX / Blend after manual ReBake

Under Create LODs in **Start Phase 2**, the new **Export Selected FBX / Blend**
checkbox is off by default and available only with Create LODs enabled. The
manual button passes this option explicitly; the Baking-section button and
automatic Phase 2 run retain their previous behavior.

After successful texture saving and LOD preparation, the action selects mesh
objects in the current MID asset collection and the newly generated LODs.
Other-engine LODs, preview planes and other assets are excluded. MID remains
active and the exported mesh set remains selected. Highpoly in Generated.N is
not included. Unity's newly generated per-level collections are included in
this current-asset set without changing their working collection layout.

The shared Export Selected model operator is invoked with temporary FBX-only
format flags and the engine used to create the LODs. Existing output paths,
folder sorting, texture copying and MeshInfo options are reused. Unity's
working-file autosave is temporarily disabled so temporary flags are not
saved into the source blend. All original export flags are restored afterwards.
New LOD texture copies are saved during preparation when necessary for FBX;
the user's material/texture-copy setting defaults are restored after generation.

One selected-asset blend is written to `!Blend/<current-asset>.blend`, using
the same selected-collection copy writer, packing and Reset Y settings as
Export Selected Blend. This includes the current MID and newly generated Unity
LODs together even when the working LODs live in separate collections. Existing
FBX and blend destinations are replaced. The working blend is not autosaved.

A bake or LOD failure prevents follow-up export. An export error is reported
separately from successful rebaking/LOD creation, retaining those completed
results. The feature is a manual follow-up and is not an automatic Phase 2 stage.

Extended real-Cycles integration tests passed for Unreal and Unity: FBX and
blend sentinel files were replaced, the exact MID + new LOD mesh set exported,
other-asset files excluded, no GLB/GLTF emitted even when their UI flags were
enabled, one clean selected-asset blend inspected, and original format flags,
Unity overwrite/autosave options and source working-file hash retained. An
injected LOD failure did not invoke export or replace the previous blend.
Existing selected-export and full Phase 2 pipeline regression tests passed.


## Automatic temporary Highpoly import

When the numbered Resculpting source is absent from the current scene, ReBake
looks for `!Blend/Generated.NNN.blend` beside the saved working blend. If the
working asset already resides in `!Blend`, it looks for `Generated.NNN.blend`
in that same directory instead of requiring another nested !Blend folder.
Equivalent numeric padding is accepted when the canonical filename is absent.
The open file itself cannot be used as its own missing-source library.

For `SM_Crystals_Pack_02_02_MID`, the fallback is `Generated.002.blend`, collection
`Generated.002`, mesh `Resculpting_01_Highpoly_Generated.002`. File/collection and
unique-source names are checked before the bake; collection membership and mesh
type are checked after append. No source data is appended during constructor
preflight. Other ReBake validations must pass before actual scene setup.

The collection is appended locally, with a direct reference to the requested
Highpoly ID. Blender may assign temporary different names on collisions;
existing same-named collections or objects, including objects in other scenes,
are never renamed or removed. A shared imported mesh is isolated locally when
needed. Numbered lookup refers to names in the library, not to the collision
suffix Blender chooses after append. File-relative Highpoly texture paths and
Multires are handled by the normal append and bake pipeline.

Append-owned datablocks are recorded by exact ID snapshots. The import remains
available through baking, optional LOD creation and optional FBX/Blend export.
Only after all requested operations end is the temporary import removed. Error
and cancellation paths also remove the temporary data, after restoring scene
state. Cleanup does not purge pre-existing objects/data or rebake-created final
images and LODs. The source Generated.NNN.blend remains unchanged. A final blend
export that would overwrite this source library is refused before importing.

`tests/test_rebake_source_import_blender.py` passed in Blender 5.2 with real
Cycles and an actual separate Generated.002 library, including:

- Missing-source lookup from the project root and from inside !Blend.
- Correct BaseColor pixels from an unpacked, file-relative Highpoly texture.
- Multires enabled for baking and an imported extra backup mesh excluded.
- Existing same-named collection, excluded/hidden layer, image and an exact
  source-name object in another scene retained unchanged.
- Full bake + projection diagnostics + LOD + FBX/Blend export, confirming the
  import is present during export but absent afterwards and absent from the output.
- Source library hash retained and append-owned materials/meshes/images removed.
- Cancellation restoring Edit Mode, injected bake failure cleanup, and rejection
  of missing files or a Highpoly outside the requested collection with no leaks.

The existing local-source ReBake integration and ordinary Batch AutoBake
projection/reopen regression tests also passed.
