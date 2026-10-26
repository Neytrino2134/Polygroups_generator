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

Overall progress gives each enabled pass one equal share; it is a completion metric,
not an estimated remaining time. Restore collection timing starts when that collection
begins processing, excluding a pause before its admission. Total/pass timers are wall
clock time, including pauses. All completed collection durations remain in runtime
queue state; the panel displays the most recent four.

Native file export, mesh preparation and auxiliary texture/freestyle image operations
are synchronous Blender calls; progress advances when those calls return. Main scene
renders run asynchronously in the GUI, with per-image progress and sample statistics
when supplied by the render engine. Output settings and original visibility are
restored through the existing stage implementations. The coordinator does not save
or overwrite the working blend automatically on completion.

Validation: native two-collection restore -> LOD/rename -> GLB + FBX + Blend + OBJ ->
verified synthetic ZBrush result -> cleanup -> transparent/scene PNG chain, controls,
wrong/incomplete/failed ZBrush result rejection. A separate GUI Blender test exercises
real asynchronous rendering, pause after the current image and resume. Full ZBrush
execution itself is not part of the automated coordinator tests.

Pause/Resume/Stop are also written to a job-ID-scoped control file for ZBrush.
The ZBrush job reads it between complete ZTL assets, so it never interrupts an
in-progress import/projection/save. Stop Now ends the Blender coordinator immediately
when its own host is safe and requests ZBrush to stop after its current asset.
A modal confirmation already blocking ZBrush still requires manual confirmation;
control messages do not dismiss dialogs or terminate the application process.
