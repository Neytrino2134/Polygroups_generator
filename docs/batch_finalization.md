# Batch Finalization and sequential Smart LODs

Phase 2 now contains Blend File Manager, Restore and Processing, Batch
Finalization, and the common Processing Status group. File management, manual
cleanup, restore/bake and finalization publish their current status there.

## Batch Finalization

Prepare LODs and Rename are independently switchable. The LOD engine defaults
to Unreal; Unity is also available. Rename defaults to FAB, which uses the
second Unreal LOD Rename pipeline. Unity uses Unity Prepare (Auto LODs).
Generate uses triangle budgets, triangulation, zero-area cleanup, labels and
Arrange settings from Mesh Finalization / Smart LODs.

Execute opens Asset Name / Name Index / Version Index and Start. Each asset
increments Version Index. Names normalize whitespace/punctuation to underscores
and uppercase the first letter of each word: desert stones -> Desert_Stones.
The shared normalizer is also used by standalone Unity and FAB preparation.

The queue discovers the highest numbered Retopo in each scene Generated.N
collection, including excluded/hidden collections. With no such collections,
selected collection packs are supported. Duplicate source ownership is rejected.
Existing LOD names are checked before generation. Originals are not decimated.
FAB keeps the original Retopo as HIGH/MID when that option is on and renames
only generated LODs as LOD0 onward. Unity prepares generated meshes only.
Source collection visibility and temporary pipeline settings are restored.

## Progress and stopping

The source meshes are arranged first. Work then advances one LOD at a time in
Blender's modal event loop, updating panel progress and the workspace status
bar with percentages. Stop Processing or Esc stops at the next LOD boundary;
the native Decimate operation currently in progress finishes first. Completed
packs are retained and the incomplete pack is removed. Smart LODs refines its
preview grid at the end to account for small bounds changes from decimation.
Scripted/background Smart LODs calls remain synchronous for existing workflows.
Jobs are closed on file load, Undo/Redo, and add-on unregister.

## Unreal naming and colors

Keep Highest as HIGH/MID defaults on. Highest Mesh Suffix is now an enum:
_HIGH or _MID, with _MID as the default. Collection colors use the same icon
menu as Unity. Random Color Tag defaults on; disable it to use the chosen tag.
Saved blend properties retain their previously stored values.

## Validation

Blender 5.2.2:
- test_batch_finalization_blender.py: FAB/Unity and mixed engines, independent
  Generate/Rename, disabled collections, default/fixed/random colors and stop.
- test_lod_finalization_modal_blender.py: actual UI progress, Stop Processing,
  completed-pack retention, then modal Batch Finalization.
- test_batch_finalization_dialog_blender.py: actual dialog, Start via Enter,
  normalized name and successful generation/rename.
- Existing Smart LODs multiple/prepare/zero-area, Unreal batch/rename, Unity
  Export Workflow, FAB all-generated, Phase 2 processing and settings lifecycle.

The old test_unity_preparation.py still expects Asset_01 where both the
pre-change HEAD and current implementation produce Asset_00_01 (Name Index).
This pre-existing assertion mismatch was verified separately; the current
Unity Export Workflow and new Unity Batch Finalization tests pass.

## Portable texture references

Unity Prepare and Unreal LOD Rename now store copied texture references as
`//Textures/<asset>/...`, relative to the saved blend file, matching FAB Prepare
and AutoBake (which already use relative paths). Enable Copy Textures when
preparing an asset so external source images are actually copied beside the
blend. Save the blend after preparation/baking, then move the entire directory
including Textures and Bakes while retaining its internal structure. Existing
absolute references in an old blend require preparing again while the originals
are accessible, then saving the updated blend.

`tests/test_portable_texture_paths_blender.py` saves all four pipeline outputs,
moves the project so the original directory no longer exists, opens the moved
blend, and reloads the referenced images from their new locations.

### Recover missing textures

Find Missing Files is available under Save Cleanup and under Restore and
Processing / Manual Cleanup. It starts Blender's native recursive missing-file
search in the current saved blend directory, with no folder picker. Recovered
local texture paths are converted to blend-relative references and reloaded.
The shared status reports Relinked / Missing / Errors. Save the blend afterwards
to keep the repaired references. An unsaved blend must be saved first; missing
images absent from the project directory remain unresolved. As with Blender's
native search, matching uses filenames; review duplicates with identical names.
