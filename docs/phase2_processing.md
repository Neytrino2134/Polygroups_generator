# Phase 2 Processing

Batch Import → Phase 2 Processing follows Start Import. Phase 1's processing
stages and the existing Retopo-only restore remain independent.

Scan Separated Files normally reads `<working blend>_Generated_N.blend` beside
the saved working file. All Blends + Subfolders scans every `.blend` in that
directory tree. It excludes the working file by resolved path, ignores `.blend1`
backups, uses natural path order, and reports file and Generated collection
counts separately. Scanning does not append scene data. Restore rescans before
starting, so changed scan settings never use a stale file list.

Restore appends each Generated collection into the smallest free positive
index, considering both existing collection names and object names. An occupied
`Generated.001` therefore makes the first imported collection `Generated.002`.
Imported highpoly and numbered Retopo objects are renamed together:

```
Generated.002
  Highpoly_Generated.002
  Retopo_02_Highpoly_Generated.002
  Retopo_12_Highpoly_Generated.002
```

Extra Blender numeric suffixes and wrong source indices are repaired. Duplicate
Retopo stages receive distinct free stages. A collection with multiple Highpoly
sources fails with a warning rather than silently selecting or deleting a source.
Malformed appends are cleaned up without removing pre-existing data.

Clear Current Generated.N Collections defaults off. When enabled, the queue
removes existing numbered Generated trees in the current scene before restoring.
Objects linked to an outside collection survive. No scan entries means no clear.

Auto Bake defaults on. The queue selects the canonical Highpoly and the Retopo
with the largest numeric stage, makes that Retopo active and calls the existing
checked Prepare And Bake operator. A missing source, Retopo or UV map fails that
item; the queue proceeds to the next collection. Current Bake Settings control
passes, resolution, cage and UV packing. Textures are saved beside the working
file using the normal Bake output folders.

Auto Repair Mesh defaults on and runs independently of Auto Bake. The existing
Mesh Editing repair operator repairs folded pockets and merges coincident
vertices on that highest Retopo only. It ignores selection-area restrictions;
shared mesh data is copied first to keep Highpoly and earlier Retopo stages
unchanged. Repair failure skips the bake and marks that collection failed.

Repack UV After Repair defaults off. Its separate Only If Changed sub-option
defaults on. When enabled, geometry/topology and all UV
layers are compared before and after repair. Only changed targets run the existing
UVPackmaster PACK operator, synchronously, before any optional bake. Unchanged
targets skip packing. Missing UVs or a failed PACK mark that item failed. This
option also works when Auto Bake is off. Existing Bake UV packing settings remain
independent.

Repair Projection Artifacts defaults on. During each bake it enables the full
projection mask, matching normal resolution and Autofill. These overrides and
selected-to-active/output saving settings are restored after each item.

The modal queue waits for each native bake. Stop after Current Bake preserves
the active bake and stops before the next restore; Esc is also passed to the
native bake cancellation handler. Completed collections get Color Tag 2;
incomplete or failed collections retain Color Tag 5. Prior completed items are
kept. Phase 1 and Phase 2 cannot run together. Results remain in the working
scene; LOD preparation and rendering are not implemented in this phase yet.

Validation: `tests/test_phase2_processing_blender.py` runs in background Blender
and includes a real Cycles bake. `tests/test_phase2_modal_blender.py` runs without
`--background` and verifies two sequential native bake tasks and exported maps.


## Blend file manager

Phase 2 has independent collapsible File Manager, Restore and Processing, and
Processing Status groups. The file manager scans beside the saved current blend,
including subfolders. It excludes the open blend and the top-level !Blend folder.
Move uses that scan and preserves relative subfolders inside !Blend. Existing
files are not overwritten; changed or missing sources count as errors. Status
reports moved files and errors. Successful moves enable recursive Phase 2 scanning
so restored Generated collections can be found in !Blend.

Auto Delete Backup Saves defaults off. When enabled, after moving it invokes the
existing Save Cleanup scan and clean operators on the entire current project
folder recursively (including !Blend), targeting only numbered .blendN and
.blendAutosaveN saves. Cleanup status is displayed separately. The manager does
not open or resave moved files.


Successful Phase 2 items are disabled before the next restore: viewport/render
visibility is off and their layer collection is excluded in the current view
layer. Failed items remain visible for inspection.

Delete Highpoly After Successful Bake and Delete Lower Retopo Stages After
Successful Bake default off. They apply only after a confirmed successful bake;
restore/repair-only jobs and failed bakes retain their meshes. The baked Retopo
is always kept. Objects linked outside the completed collection tree are only
unlinked from that tree, not deleted globally. The separate Delete All
Backup_Retopo Objects button removes local mesh objects with that prefix and
supports Undo; shared mesh data is kept while other objects use it.

When Only If Changed is off, every successful Auto Repair runs PACK if Repack UV
After Repair is enabled, even when the mesh and UVs were unchanged.

Manual cleanup buttons also find hidden/disabled objects. Delete Lower Retopo
Stages groups canonical Retopo_XX_Highpoly_Generated names by asset suffix,
keeps the maximum numbered stage per asset and deletes only earlier stages.
Delete All Highpoly_Generated Objects removes canonical Highpoly sources.
Both support Undo and are disabled while Phase 2 or baking is running.

See [Batch Finalization](batch_finalization.md) for sequential LOD preparation,
engine-specific renaming, shared status and Stop Processing.

See [Auto Render](phase2_auto_render.md) for fixed-quality asset previews,
per-asset camera fitting, Freestyle, Multiview and paired texture output.

## Retopo_01 follow-up processing

Restore and Processing includes two opt-in options beneath Auto Bake:

- Resculpting Retopo_01 runs the existing Setup Resculpting operator on
  Retopo_01_Highpoly_Generated.N after the highest Retopo has baked successfully.
  The resculpt Multires, Shrinkwrap and Apply Shrinkwrap settings are reused.
- Autobake Retopo_01 repairs and rebakes that mesh using the same enabled
  geometry repair and full artifact-mask/Autofill settings as the primary bake.
  If Auto Repair and Repack After Repair are enabled, its UVPackmaster PACK
  always runs, even when the repair signature is unchanged. Only If Changed
  continues to apply normally to the highest Retopo.
  During the Retopo_01 bake, its Multires modifiers are temporarily disabled in
  viewport and render. Their previous visibility is restored after completion,
  failure or cancellation; primary-target modifiers are unaffected.

Order: highest repair/conditional repack -> highest bake -> optional Retopo_01
resculpt -> optional Retopo_01 repair/forced repack/bake -> successful cleanup.
Requested follow-up processing requires exactly one Retopo_01 in the restored
collection. Missing targets or failures retain the highpoly and lower stages.
Keep Retopo_01 (Resculpted), enabled by default, preserves stage 01 during both
automatic Delete Lower Retopo and the manual lower-stage cleanup. Turning it
off allows that stage to be deleted along with the other lower stages.
The collection is disabled only after all requested stages succeed.

The secondary bake stores maps under Bakes/Generated.N_Resculpting_01 after
resculpting, or Bakes/Generated.N_Retopo_01 when only rebaking the original mesh,
with distinct image names. It does not overwrite the highest Retopo's maps under
Bakes/Generated.N. The output suffix remains on the Retopo_01 object so later
Save Textures operations use the same separate location.

test_phase2_retopo01_blender.py validates stage order, independent switches,
forced repack after unchanged repair, cleanup deferral, failure/stop retention
and restored bake preferences. It also performs real CPU Cycles normal and
artifact-mask/Autofill bakes for both targets and verifies separate saved maps.
UVPackmaster calls in the ordering test are mocked; native PACK is covered by
the existing optional installed-engine repair test.

The three manual cleanup operators (lower Retopo, all Highpoly, and backups)
are grouped in the collapsible Manual Cleanup subsection, closed by default.
Its Keep Retopo_01 checkbox controls the same retention setting as the checkbox
beneath Delete Lower Retopo.

## Periodic autosave

Autosave Completed Collections is opt-in. Successful Collections per Save
defaults to 1 and accepts any positive N. Only complete, successful collection
pipelines count: highest bake, optional Retopo_01 processing, restored modifier
visibility, cleanup and collection disabling all finish before the checkpoint.
Failed collections do not trigger or advance the successful-operation interval.
The current working blend is saved in place; partial intervals do not force an
extra save when the batch finishes. An autosave error stops before the next
collection and retains the successful processing count and error message.

test_phase2_periodic_autosave_blender.py checks actual checkpoints at N=2,
failure exclusion, saved cleanup/visibility, and save-failure stopping.
test_phase2_retopo01_blender.py checks one save only after both real native
bakes and all secondary processing have completed.

## Retopo backups on restore

Skip Retopo Backup Objects in Restore and Processing defaults off. The Phase 2
restore appends saved collection contents, which may already contain
Backup_Retopo objects originally created by cutter operations. When enabled,
the restore omits these objects from the appended collection hierarchy before
processing. Existing scene backups and mesh data shared with real asset objects
are preserved. Source blend files and manual cutter backup behavior are unchanged.

test_phase2_skip_retopo_backups_blender.py checks root and nested backups, name
collisions with existing backups, shared geometry, and both checkbox states.

## Processing preset switches

Three buttons precede Restore and Processing settings. Their pressed states
follow the actual settings, including later manual checkbox changes:

- Import Only disables Auto Bake, Auto Repair, Repack, artifact repair and both
  Retopo_01 follow-up operations.
- Import + Rebake enables Auto Bake, Auto Repair, Repack and artifact repair.
  It retains the independent Retopo_01 toggle state.
- Retopo_01 Resculpting toggles both Resculpting and Autobake Retopo_01. Turning
  it on also enables the primary rebake pipeline and Keep Retopo_01; turning it
  off leaves the primary rebake pipeline enabled.

Presets change settings only; they do not start processing. They preserve file
selection, restore/cleanup preferences, autosave, backup omission and Only If
Changed. Switching is disabled during processing/baking/rendering.
test_phase2_processing_presets_blender.py checks switching, pressed states,
unrelated-setting preservation and the busy-state guard.

## Resculpting mesh names

Successful Setup Resculpting (section 07 and the Phase 2 follow-up) replaces the
Retopo_ token with Resculpting_. Other mesh names receive _Resculpting. Existing
Resculpting names are retained on repeat setup. Naming conflicts cancel before
modifying the target. Arbitrary mesh names are accepted with an active low mesh
and selected highpoly; a generated highpoly alone is not accepted as lowpoly.

Restore preserves Resculpting_XX while assigning the new Generated.N index.
Source matching, rebaking, stage-01 retention, lower-stage cleanup and Batch
Finalization recognize the renamed stages. Backup_Resculpting objects are
covered by the existing backup-omission and backup-cleanup controls.
test_resculpt_auto_highpoly_blender.py checks manual naming, suffix/idempotence
and conflicts. test_resculpting_restore_names_blender.py checks restored names,
highpoly matching and retention. The full Retopo_01 test performs both native
bakes using the renamed Resculpting_01 mesh.

Manual Cleanup also provides Rename All Retopo_01 -> Resculpting_01. It renames
all local stage-01 mesh names, including hidden collections, without running
resculpting or changing geometry/modifiers. Other numbered stages are excluded.
All target names are checked before any changes; conflicts cancel the whole
rename. The operator supports Undo.
