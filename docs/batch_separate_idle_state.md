# Idle state in separate Batch Import results — 2026-10-10

Save Each Generated.N Separately uses Save As Copy while the import queue is
running. Its output previously serialized the working scene's active queue UI
state, including stage, progress, current filename and counts. Opening a result
could display ongoing import processing until Reset Import State was used.

The copy writer now temporarily resets transient import, bake and remesh state
for every saved scene. A finally block restores the live values and original
RNA property-set state after successful or failed writes. It does not stop the
queue or change import configuration. The existing manual batch reset and copy
writer share one definition of the idle batch state. Existing copies are not
rewritten; the fix applies to newly generated copies.

Blender 5.2 factory-startup validation:

- `test_batch_separate_idle_state_blender.py`: real Save As Copy and reopen,
  multiple scenes, idle state after load, exact live-state restoration, configuration
  retention and injected write failure. BATCH_SEPARATE_IDLE_STATE_TESTS_PASSED.
- `test_batch_separate_save.py`: actual OBJ queue processing, separate copies,
  retopo-only restore, continuation after an injected remesh failure, reopening
  successful queue outputs with idle state. Passed.
- `test_batch_autobake.py`: bake handoff plus actual separate copy writing. Passed.

Broader tests stop on pre-existing default mismatches before reaching this change:
`test_import_queue.py:59` expects stage-4 LOW but properties.py defines MID;
`test_batch_smart_finalization.py:36` expects finalization LOD1=3000 but properties.py
defines 2900. properties.py was not changed by this repair.
