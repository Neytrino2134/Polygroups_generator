# Export ZBrush (Phase 2 > Batch Finalization)

Turns the Blender multires of the `Resculpting_NN_Highpoly_Generated.N` meshes into one ZTL per mesh whose ZBrush
subdivision levels match the Blender multires levels (base mid-poly = level 1, top = level N+1), keeping UV and
polygroups (Blender sculpt face sets, one OBJ group each).

## Buttons
- **Export Active Mesh / Export All Generated.N**: current blend file, scene-level.
  Export All uses exactly `Resculpting_01_Highpoly_Generated.N` with Multires
  from each `Generated.N` collection; unrelated Multires meshes are skipped.
  The source and its collection paths are temporarily enabled, including excluded
  View Layer collections. Viewport/render/select restrictions and eye visibility
  are restored after export and on failure. Temporary copies are always enabled.
- **Export Folder of Generated.N.blend**: every `Generated.N.blend` of the folder, each opened in a background
  Blender (modal, Esc cancels), merged into one job.
- **Launch ZBrush**: starts ZBrush with the job. A running ZBrush refuses a second instance, so close it first
  (or run `zbrush_job.py` through ZScript > Python Scripting > Load).
- **Delete All Generated.N Collections + Meshes**: removes the current scene's Generated.N
  collections, their child collections and all objects inside. Blender Undo is supported.
- **Delete Temporary OBJ Files**: removes the entire `Mesh/` directory and all its
  contents, reporting deleted files / folders (including the root Mesh folder).
  ZTL files outside Mesh are retained.

**Return to Blender and Cleanup after ZBrush** is off by default. Enable it before
Export All Generated.N to watch that exact job while Blender stays open. The watcher
also works when ZBrush is launched later using Launch ZBrush. Cleanup requires a finished
result with the same job ID, success for every exported asset and nonempty ZTL files.
It deletes only the exported collections and that job's OBJ files, then asks Windows
to bring Blender forward (Windows can restrict foreground activation). Unrelated
collections and OBJ files are retained. If collection contents changed, a job failed,
or a ZTL is missing, cleanup is cancelled. Disable the option to cancel waiting.
Loading another file or restarting Blender cancels automatic cleanup; it is not resumed.
The blend file is not saved automatically after cleanup.

ZBrush.exe is set in Preferences > Add-ons > External Programs (default
`C:\Program Files\Maxon ZBrush 2027\ZBrush.exe`).

## Output (`!ZBrush` beside the saved blend file, or the Output folder)
```
Mesh/<name>/<name>_L0..Ln.obj   OBJ per multires level (kept for other tools)
ZTL/<name>.ztl                  result, saved at the second level
job.json  zbrush_job.py         manifest and the script ZBrush runs
job_result.json  job_log.txt    written by ZBrush (job_result.json has "finished": true at the end)
```

## Level building (ZBrush 2027, `Levels` setting)
- **Reconstruct**: imports the top level, then `Reconstruct Subdiv` down to the base. ~1.5 s per mesh. The top level
  is bit-exact; the lower levels are reconstructed (base differs ~0.2 mm mean / 3 mm max on a 1.2 m object). Fails
  for bases ZBrush cannot reconstruct (seen with n-gons): the face count check then rejects it.
- **Project All**: imports the base, `Divide` per level and projects the Blender level onto it. ~70-100 s per mesh,
  ~0.5 mm error, and the export offset of the resulting tool differs. `Delete subtool` shows ZBrush's
  "not an undoable operation" note, which times out after ~10 s.
- **Auto** (default): Reconstruct, falling back to Project All when the face counts do not match.

## Notes
- ZBrush welds coincident vertices on import, so point counts may differ by a few; face counts must match.
- ZBrush must be closed normally: a killed session shows "most recent session was abnormally terminated" at the
  next start. The job script ends ZBrush with `sys.exit(0)` when started from the command line.
- The user's objects are never modified: a temporary copy with polygroup materials is exported.
