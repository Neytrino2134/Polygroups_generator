# Batch import order and partial recovery — 2026-10-11

Folder scanning and file selection use a natural comparison of each path
component. Queue collection numbering and automatic placement retain that order.

Esc and modal cancellation retain imported objects and finished remesh outputs.
Processing failures retain the current file's objects instead of clearing its
Generated.N collection. Separate saving writes partial output without unloading
it; interrupted queues also reload completed collections saved by that queue.
The recovered working file is saved after its running flag has been cleared.

Separate-file isolation now runs in a hidden background Blender process over
the saved copy. It no longer removes earlier Generated.N objects from the
working scene. This adds a Blender process startup to each separate save.

Blender 5.2 factory-startup checks passed:

- `test_batch_order_recovery_blender.py`: actual GLB scan/import order, natural
  numbering, placement independent of mesh names, Esc with and without separate
  saving, completed and partial mesh recovery, and working-file reopen.
- `test_batch_separate_save.py`: separate output isolation, injected remesher
  failure, retained failed import, persisted partial output, and next-file success.
- `test_batch_separate_idle_state_blender.py`: copied projects open idle.

`test_import_queue.py` stops at an existing default assertion before queue
execution: it expects stage 4 preset LOW while properties.py specifies MID.
Actual paid Quad Remesher engine execution was not part of these tests; its
failure path was injected into the live Blender queue.
