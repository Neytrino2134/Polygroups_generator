# Local mesh fold repair

Current complete Auto Repair rules and usage: [General mesh repair](dangling_mesh_repair.md).
This document describes the original small-pocket and exact-edge rules; its
triangular-boundary limits do not apply to the separate generalized dangling-region rule.

Available in **Model Preparation → Mesh Editing → Auto Repair** and
**Seam Preparation → Mesh Editing → Auto Repair**. The existing tools remain
under **Manual Editing**. These subsections are shared by the sidebar and
the custom UI.

1. Enable **Repair Folded Pockets**, **Merge Coincident Vertices**, or both.
   Use **Repair Zero Area / Preserve UV Seams** for triangles whose endpoints
   coincide exactly but adjacent seam/sharp/pinned-edge flags differ. This
   separate option does not extend the seam-crossing merge tolerance to slivers.
2. Optionally enable **Selected Area Only** in Edit Mode. Select any defect
   face as a seed; the repair includes its minimal enclosing patch.
3. **Find Problems** selects the patches without changing geometry or UVs.
4. **Repair Mesh + UV** applies the repair to the active mesh. Blender Undo
   restores the previous state.
5. **Find Thin Triangles / UV Problems** only selects diagnostic candidates.
   Default triangle quality is below 0.01 (1 is equilateral); UV stretch is the
   Jacobian singular-value ratio, flagged at 50 or higher. Both thresholds can
   be adjusted in the operator redo panel. These findings are not auto-deleted.

The operator works in Object Mode and single-object Edit Mode. Repair requires
local, single-user mesh data without shape keys. It runs on a working BMesh
and commits only after validation. It does not save the blend file.

## What it repairs

- Folded pockets where two faces share multiple edges. Adjacent concave faces
  are absorbed when needed to recover a simple triangular outer boundary.
  The replacement uses existing boundary vertices; surrounding vertices stay
  in place. Every UV layer is rebuilt from the corresponding boundary corners.
- Near-zero edges belonging to degenerate triangles. Only vertices already
  connected by such an edge can be merged. The tolerance is `1e-7` of the
  object's local bounding-box diagonal. This is not a global Merge by Distance.
- A collapsed edge can expose another folded pocket; enabling both options
  handles the two steps in one operation.
- Exact zero-edge repair preserves the UVs of every surviving corner. Seam,
  sharp and pinned-edge flags on duplicate sides are combined onto the surviving
  edge. It does not delete collinear triangles with three distinct endpoints.

The diagnosed stone contains both cases: the first pocket uses faces
920/8410/8411; the second starts with coincident vertices 2088/8481 and face
8511. Both options together repair two pockets and collapse one edge, leaving
8,488 vertices, 17,123 edges and 8,637 faces, with no open or non-manifold edges.
The implementation does not depend on those face/vertex indices.

In `Gravestones 2.blend`, models 02 and 06 each have two exactly zero-area
triangles in each LOD0–LOD4. The exact zero-area option removes these with one
vertex weld per mesh, preserving every surviving face's coordinates and UVs.
Model 02 also contains pre-existing open/non-manifold edges, near-zero slivers
and distorted UVs; fixing the two exact-zero triangles does not certify the
entire asset as clean. The result separates exact zeros from near-zero faces.

## Conservative limits

The ordinary pocket/near-zero repair skips hidden patches, internal seams, pinned edges/UV corners,
material boundaries, ambiguous UV boundaries and patches whose outer boundary
cannot safely become one triangle. It rejects repairs that introduce open or
non-manifold edges. A small face or a tiny UV island alone is not a defect.
The separate exact-zero option may combine pinned/seam sides while retaining
their flags; UV-pinned patches and unsafe manifold contractions are still skipped.

UV coordinates outside the repaired patch remain unchanged. Consequently,
existing distortion in the surrounding island remains unchanged too: this
tool is not a replacement for UV unwrap/relax. Existing baked textures can
require rebaking after geometry or UV changes.

## Validation

Run with installed Blender, optionally opening the diagnostic stone first:

```text
blender --background --factory-startup --disable-autoexec [stone.blend] --python-exit-code 1 --python tests/test_mesh_fold_repair.py
```

Tests cover both actual defects (when the stone is loaded), selected seeds,
independent options, idempotence, several mesh scales, hidden/pinned/material
protection, a valid surface, zero-edge contraction, preservation of surviving
neighbor UVs, registration, the two UI trees and operator execution in Edit Mode.
