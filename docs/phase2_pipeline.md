# Start Phase 2

The coordinator owns one queue and advances the existing Restore, LOD preparation,
prepared export, blend export, ZBrush and Auto Render implementations in that order.
Each selected pass has a queue entry, state and progress. Failures stop admission of
later passes. Completed output is retained. Progress and Queue shows either Phase 1
or Phase 2; the Phase 2 queue is also drawn under Start Phase 2 and in the viewport.

Restore automatically scans first. Its mode controls import-only, rebake or rebake
plus stage-01 resculpting; MID remesh is independent. Preparation uses one engine
for both LOD preparation and rename. Existing detailed export/render settings remain
in effect. The coordinator temporarily delays Generated cleanup until exports finish.

Pause finishes the current collection/file/render image before waiting. Resume keeps
the same iterator. Stop After Stage finishes the current pass and admits no next pass.
Stop Now permanently ends this run at the next safe host boundary; an active Blender
bake/render is allowed to return before input data or visibility is changed. A new
Start builds a new run, rather than replaying partially finished work automatically.

ZBrush completion requires the exact manifest job ID, a finished result with every
asset successful and each output ZTL nonempty. Missing/stale results wait without
cleanup. Error results stop the run, preserving inputs. ZBrush confirmation dialogs
can still block ZBrush; the coordinator never treats a blocked process as success.

Blender must stay open. Loading a file, Undo, Redo or disabling the addon terminates
the coordinator. Work is not resumed automatically after restart. Phase 1 integration
uses the common queue display; Start Import chaining is reserved for a later change.
