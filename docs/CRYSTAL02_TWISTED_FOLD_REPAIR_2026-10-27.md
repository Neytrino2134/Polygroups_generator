# Crystals_Pack_02_02: twisted backtracking ear — 2026-10-27

Object: `SM_Crystals_Pack_02_02_MID`.
Input: `Crystals_Pack_02_02.blend` in the pack's `!Blend` directory.
Output: `Crystals_Pack_02_02_REPAIRED.blend` alongside the source.

## Observed cause

The selected triangle is face 3167 (vertices 120, 67, 567). Vertex 67 has only
two incident edges, both shared with quad 3142 (67, 120, 568, 567). It projects
past the closing edge: the quad doubles back instead of forming an ordinary
surface subdivision. Unlike the nearly planar defect in asset 18, this quad
is strongly twisted. Its two triangles along diagonal 67–568 have a normal
dot product of about 0.08 (roughly 85 degrees apart). The closing triangle
opposes both (normal dots roughly -0.67 and -0.79).

The internal tip lies about 7.11% of the outer boundary span off its plane.
The averaged quad normal aligns with the retained boundary normal by only
0.751, and the closing triangle by -0.419. Thus asset 18's flat-ear thresholds
(5% depth, quad alignment >= 0.99, triangle alignment <= -0.9) correctly did
not accept this different shape.

This mesh contains no zero-area or thin-triangle findings at the configured
thresholds. Quad 3142 has two severe UV-stretch findings. The closing triangle
is a separate UV island despite its two shared edges not being marked Seam;
its UV area is about 0.11075, occupying 11.1% of the unit atlas. A simple
zero-area cleanup cannot address it. These observations establish the defect,
but do not identify which earlier modeling or remeshing operation created it.

## Added rule

The existing flat-ear limits remain unchanged. A separate twisted-ear branch
requires a closed manifold triangle/quad patch, one internal degree-two tip,
a triangular outer boundary, and projection backtracking across the closing
edge. Additional requirements: tip depth <= 10% of span, retained normal
alignment >= 0.5, closing triangle alignment <= -0.2, triangle/quad mutual
normal dot <= -0.9, quad triangle mutual dot <= 0.25, and both quad triangles
opposing the closing triangle with dot <= -0.5. Existing hidden, UV-pin,
internal seam, pinned-edge and material protections remain in force.

The accepted repair uses the directed weld already used for flat ears:
vertex 67 -> nearest neighbor 567. Every surviving vertex retains its exact
coordinate. The closing triangle is removed; the quad becomes a triangle.
Only the retained triangle is unfolded, anchored to an adjacent uncut UV edge.
Other faces' UVs remain unchanged. The rule is reached by both Find Problems
and Repair through `fix_folds`; public operator IDs and property defaults stay
unchanged. An explanatory tooltip was added to Repair Folded Pockets.

## Validation

- Targeted counts: 3150/6340/3192 -> 3149/6338/3191 vertices/edges/faces.
- Every surviving vertex kept its exact original coordinate.
- All other 3190 faces kept their vertex order and all corner UVs exactly.
- Entire mesh stays manifold; zero-area and thin findings remain zero.
- Severe UV-stretch findings: 2 -> 0.
- Repeated selected-area repair applies no further change.
- Public operator Find selects exactly faces 3142 and 3167 without changing
  geometry. Repair performs one fold repair and is idempotent on this area.
- Full-mesh mode also finds two pre-existing independent pockets already
  handled by the old algorithm. The saved copy repairs only the reported area.
- `test_twisted_ear_blender.py`: passed at scales .001, 1, 1000 and after a
  rotation; includes hidden, seam, pinned-edge, UV-pin, material, ordinary
  subdivision and unselected-area protection cases.
- `test_crystal02_fold_blender.py`: real mesh and optional copy save passed.
- `test_crystal02_operator_blender.py`: Find/Repair passed in Blender 5.2.
- Existing `test_mesh_fold_repair.py`, `test_backtracking_ear_blender.py` and
  real-asset `test_crystal_fold_blender.py` (asset 18) passed.
- `check_repaired_crystal02_blender.py`: saved copy reopened in Blender 5.2.

Source SHA256 before/after: A74DB573B5885F3681FFD6B2B4DF30118DD7DA62A1EB135991A54B835F2BE451.
The source was not overwritten. It uses file version 502.45, newer than the
installed 5.2 binaries. As with asset 18, the output copy was saved using
installed Blender 5.3 Beta and reopened successfully in 5.2. Opening it in
5.2 produces the expected newer-file warning.
