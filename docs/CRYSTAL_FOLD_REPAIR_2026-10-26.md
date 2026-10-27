# Crystal backtracking ear repair — 2026-10-26

Asset: `Crystals_Pack_02_18.BLEND`, object `SM_Crystals_Pack_02_18_MID`.
Output: sibling `Crystals_Pack_02_18_REPAIRED.blend`; original untouched.

## Diagnosis

Original face 3156 (triangle 35/278/16) and quad 70 (16/278/279/35)
share two edges. Vertex 16 has only two incident edges and two faces. Its
projection lies beyond the boundary of the replacement triangle, making a
backtracking ear, with opposite triangle/quad normals. The triangle is a
separate UV island even though its two shared edges are not marked as seams.
Its packed right-triangle UV occupies a large portion of the atlas. Quad 70
also contains a distorted UV triangle. This establishes the topology of the
defect; the file alone does not establish which earlier modeling operation
created it.

## Rule under Repair Folded Pockets

Detect a closed manifold triangle/quad patch with three boundary edges and
one internal degree-two vertex. Require a reversed ear normal (dot <= -0.9),
a retained quad normal aligned to the boundary normal (dot >= 0.99), a tip
within 5% of the patch span from the boundary plane, and backtracking across
the closing edge. Hidden geometry, internal seams, pinned edges, pinned UVs,
and material boundaries remain protected. Ordinary thin faces are not removed
merely because they are thin. The rule uses topology and relative geometry,
not asset names or indices.

Weld the tip into its nearest adjacent vertex, retaining that vertex's exact
position; never average neighboring positions. Here vertex 16 merges into 278.
The folded triangle disappears and quad 70 becomes a triangle. Unfold only
that retained triangle, anchoring its longest uncut boundary to the adjacent
UV edge and constructing the third UV corner from 3D edge lengths. Surrounding
UVs stay fixed. Preserve boundary seam/sharp flags and mark remaining UV cuts.
Both Find Problems and Repair use the same planner through the existing
operator, including its Selected Area Only option and batch callers.

## Validation

- Counts: 3223/6496/3272 -> 3222/6494/3271 vertices/edges/faces.
- Every surviving vertex retains exactly its original coordinate.
- All 3270 other faces retain their corner UVs and vertex order exactly.
- No new open/non-manifold edges; repaired boundary remains manifold.
- UV stretch findings >= 50: 1 -> 0. Zero-area triangles: 0 -> 0.
- Two separate thin-triangle findings remain outside this targeted repair.
- Repeated repair finds no further fold.
- `test_mesh_fold_repair.py`: passed in Blender 5.2.
- `test_backtracking_ear_blender.py`: scale, protection, UV-neighbor and topology checks.
- `test_crystal_fold_blender.py`: real-asset assertions and optional copy save.
- `check_repaired_crystal_blender.py`: saved copy reopened successfully in Blender 5.2.

The source uses file version 502.45, newer than the installed Blender 5.2
binaries. The copy was therefore saved with installed Blender 5.3 Beta,
then explicitly reopened and checked in Blender 5.2. Blender 5.2 reports the
expected newer-file warning. The original file remains available unchanged.
