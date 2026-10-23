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

Repack UV After Repair defaults off. When enabled, geometry/topology and all UV
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
