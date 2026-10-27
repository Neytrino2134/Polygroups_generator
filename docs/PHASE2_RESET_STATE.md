# Start Phase 2: Reset State

`Reset State` is a separate recovery button in Start Phase 2. Its row is outside
the disabled processing-options column, so stale `running` flags do not prevent
recovery after an exception or interrupted session.

The reset closes Phase 2 stage generators, restores overridden processing
settings, aborts an owned pending remesh, cancels an idle bake coordinator,
releases timers/overlays and clears queue/progress/time/counter state to Ready.
The old modal owners are marked finished so queued events cannot resume them.
Recovery continues through individual cleanup errors and reports those errors.
The manual ReBake queue also closes on Reset; its model list is retained and
its per-item statuses return to pending.

Pending ZBrush success-cleanup is disarmed and receives a matching STOP control
file. Late completion must not delete source collections after a reset. Completed
meshes and exported files are retained; user processing options are retained.

The button is unavailable while Blender is actually baking/rendering or when
an unrelated import/remesh/render/finalization owner is active. It checks real
host jobs and owner references rather than stale progress flags.

Validation in Blender 5.2:

- `tests/test_phase2_reset_state_blender.py`: stale flags and malformed queue
  JSON; usable recovery UI; preserved objects/files/options; host-job guards;
  active and broken pipeline generators; orphan remesh; bake cleanup fallback;
  actual idle BakeTask; finalization cleanup; ZBrush watcher cancellation;
  repeated reset and unrelated-job guards.
- `tests/test_phase2_reset_modal_blender.py`: separate GUI host, actual modal
  pipeline and bake timers/draw handles removed, no old-run resumption.
- Phase 2 pipeline, real Cycles ReBake Final Mesh, and imported-source ReBake
  regressions passed after adding explicit bake-task ownership.
