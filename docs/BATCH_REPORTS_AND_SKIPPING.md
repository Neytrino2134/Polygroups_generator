# Batch reports and failure-tolerant Phase 2

## Report folders

Every run writes to `batch_reports/` beside the working blend.

* Phase 1: `batch_reports/<time>_<id>/`
* Phase 2: `batch_reports/<time>_<id>_phase2/`

| File | Content |
| --- | --- |
| `summary.json` | totals, `successful_collections`, `failed_collections`, `skipped_collections` (each with `error`, `failed_stage`, `failed_pass` and a `log` link to its per-file report) |
| `files.json` | compact index, one row per file / `Generated.N` collection (no stages or traceback) |
| `files/<Generated.N>.json` | the complete record of one file / collection: stages, traceback, Quad Remesher diagnostics |
| `events.jsonl` | chronological event stream |

## Phase 1 failures do not stop the run

A file that fails (for example Quad Remesher crashes on pass 3) is saved as `Generated.N` with
`Highpoly_Generated.N` and the passes that finished. Its collection is stamped in the blend
(`polygroups_failed`, error text, time). Phase 2 now starts after Phase 1 as long as at least
one file succeeded.

## Phase 2 reads the logs

Before processing, Phase 2 reads the Phase 1 `files.json` index files (newest run wins, a later
success clears an older failure). A `Generated.N` blend is treated as unfinished when its record
is `failed`, `interrupted` or `cancelled`, or when the stamp inside the blend is present. A file
saved more than two minutes after the failure counts as repaired by hand.

An unfinished collection is still imported, but:

* it is marked (`polygroups_skip` on the collection and all of its objects) and coloured red;
* repair, MID remesh, bake, resculpt and their deletions are skipped;
* Highpoly and the finished Retopo passes stay for manual work;
* `Delete All Generated.N`, the Lower Retopo / Highpoly / Resculpting / Backup clear operators,
  Export Blend, ZBrush export and Cleanup leave marked collections and meshes alone;
* Prepare LODs / Rename keeps its asset slot, so with `Generated.008` skipped `Generated.009`
  is still the ninth asset.

A collection that fails inside Phase 2 is marked the same way, and the run continues. The run only
fails when no collection was processed at all.

## Pause before Phase 2

When Phase 1 had failed files and Phase 2 is enabled, a dialog lists the failed Generated.N collections and counts down 15 s (also shown in the panel) before Phase 2 starts. Pause holds Phase 2; the Phase 1, 2 import button and Start Phase 2 Process then read Resume Phase 2. Reset State clears the hold.

## Fixing a failed file by hand

Open the failed `<name>_Generated_NNN.blend`, finish the collection and save it. Phase 2 compares the file's save time with the Phase 1 record (more than 5 s later means edited) and, when the Phase 1 log is missing, with the stamp inside the file (more than 2 min later). A repaired file is processed like a normal one, its stamp is removed from the restored collection and the Phase 2 report row gets `repaired_after_phase1: true`.

## Resume Selected

Select a `Retopo_` / `Retopo_NN_Highpoly_Generated.N` mesh in its Generated.N collection and press Resume Selected (Phase 1 start group, below Do Selected). `Retopo_` or `Retopo_01` = first remesh pass done: resumes at 3. Narrow Island Splitter and runs the second and third remesh passes. `Retopo_02` resumes at 6. and runs the third pass. `Retopo_03` is the end of Phase 1: the button is disabled (is finished). The run ends at stage 8 even when 13. Phase 2 is on, and it never starts Phase 2. A finished collection loses its failure stamp, and a saved result clears the failure in the Phase 1 report.
