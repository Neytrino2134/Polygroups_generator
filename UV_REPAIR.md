# Smart UV Repair

Edit Mode → AI Retopo → **09 UV Preparation → Smart UV Repair** contains all
detection, routing, pin and relax settings plus separate **Select Regions** and
**Repair UV** buttons. The compact operator is also available beside the Boundary /
Longitudinal seam controls, in the UV Editor sidebar under **AI Retopo → Smart UV
Repair**, and through F3. Requires an existing active UV map and one editable mesh.

Use **Select Regions** to inspect detection without editing topology or UVs.
Use **Repair UV** to add boundary seams, connect boundary loops with longitudinal
cuts, and unwrap only the repaired patches. Results remain selected. Pack islands
after repair when required: this operation does not rearrange unaffected islands
and does not guarantee that repaired islands avoid them.

## Detection

Triangle UV Jacobians measure directional distortion. Area density is compared
against the area-weighted median of each UV island, so independent packing scales
do not trigger false positives. Either metric can seed a critical region.
Hysteresis grows the region down to a lower distortion threshold; majority-based
face smoothing fills boundary notches. Growth respects UV discontinuities, existing
seams, hidden geometry, the selection restriction and Surface Angle.

- **Critical Stretch Ratio**: higher values find only severe distortion; default 4.
- **Region Growth Ratio**: lower values include more of the surrounding surface;
  default 1.8. Internally limited to the critical threshold.
- **Boundary Smoothing**: number of face-neighborhood notch-filling passes.
- **Surface Angle**: maximum change of neighboring face normals during growth,
  also used by smart seam routing.
- **Prefer Sharp Longitudinal Edges**: biases shortest paths toward creases.
- **Create New Edges**: allows the existing smart seam router to split faces when
  that improves the longitudinal route; it does not force new edges on straight paths.
- **Pin Generated Seams**: uses the toolkit's edge pin attribute. Existing UV pin
  flags are temporarily released for the repaired patch and then restored.
- **Merge Small UV Islands**: before pinning, removes only newly generated borders
  around islands smaller than **Small Island Area (%)**. The percentage is measured
  against each repaired region's physical area; unrelated mesh area and existing
  seams do not participate.
- **Smart Relax Generated**: applies the existing surface-projected seam relaxation
  only to generated seams. This moves mesh vertices; disabled by default.
- **Average Island Scale**: after repair, selects the whole active mesh and runs
  Blender's Average Islands Scale so every UV island gets consistent texel density.
- **Native Blender Pack**: then packs every UV island with Blender's native Pack
  Islands. Both post-processes restore the repaired-face selection afterwards.

## UV Artifact Cleanup

The embedded mini-operator detects UV islands up to **Maximum Island Faces** (7 by
default) only when they are also collapsed, critically stretched, or needle-shaped.
**Select Artifacts** previews the matching mesh faces. **Apply Artifact Cleanup**
either deletes those faces from the mesh or merges each physically connected artifact
to its center. **Clean UV Artifacts During Repair** runs the same cleanup as the first
Smart UV Repair step. Selection scope is shared with **Selected Faces Only**.

Two or more boundary loops are joined by paths. A single boundary is connected to
its geodesically farthest interior vertex, supporting capped protrusions and cones.
Closed regions without boundaries, branching boundaries and nonmanifold patches
are skipped. This is a distortion-based heuristic, not a general cylinder recognizer;
use selection scope and detection thresholds for ambiguous geometry. UV overlap
without local distortion is not detected.

Existing seams and pinned edges are protected during routing. New topology is
planned on a mesh copy; failures after applying the copy restore the original mesh.
Blender Undo is supported. No automatic invocation after Smart UV Unwrap is enabled.

Validation: `tests/test_uv_repair_blender.py` runs in background Blender and covers
healthy/distorted cylinders, detection-only mode, both routing modes, pins, selected
scope, unaffected hidden UVs, Smart Relax, one-boundary cuts and failure rollback.
