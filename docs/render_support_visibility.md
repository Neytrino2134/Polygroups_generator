# Render support visibility repair — 2026-10-10

The preflight previously treated Blender's root `Scene Collection` as a studio
collection, then recursively revealed every collection and object beneath it.

Studio collection recognition now excludes the root and matches Scene, Camera,
and Light at a name boundary (including Scene_Studio and Blender numeric suffixes),
or the add-on's explicit studio collection role. Nested studio contents remain
supported. Camera/light objects and tagged studio objects can still be recovered
in legacy mixed collections without revealing unrelated meshes in those collections
or their ancestors. Unrelated layer exclusion states survive ancestor changes.
Turnaround scene preservation uses the same recognition rule, and its visibility
snapshot precedes preflight so render completion restores original collection and
object render/viewport flags.

Verified with Blender 5.2.0 LTS, factory startup:

- `tests/test_render_support_visibility_blender.py`: repeated preflight, hidden root
  and ancestor meshes, mixed camera/mesh collections, unrelated excluded collections,
  prefix lookalikes, nested and renamed tagged studio collections; turnaround isolation
  with scene preservation enabled/disabled and restoration. Passed.
- `tests/test_unity_labels_render_blender.py`: separate LOD render operator execution,
  camera framing and moving legacy lighting; final render calls intercepted. Passed.
- `tests/test_turnaround_animation.py`: actual Eevee/FFmpeg two-frame video,
  PNG sequence and four rotation views, render-time visibility and restoration. Passed.
- `tests/test_unity_turnaround_blender.py`: Unity turnaround settings and dispatch. Passed.
