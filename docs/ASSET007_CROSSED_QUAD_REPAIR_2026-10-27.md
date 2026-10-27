# Asset_00_07: crossed-quad ear and singleton UV triangle repair

## Reported asset

Source: `Crystals_Pack_01/!Blend/Asset_00_07.blend`, object `SM_Asset_00_07_MID`.
The saved selection contains faces 392 (quad) and 3899 (triangle).

The triangle is `(626, 121, 857)`. Vertex 121 has only two edges; both its faces
belong to the same triangle/quad pocket. The quad is `(121, 626, 856, 857)`.
The patch has the outer triangular boundary `(626, 856, 857)`.

This differs from the earlier flat and twisted backtracking ears:

- Closing triangle / outer-boundary normal dot: 0.9615.
- Quad / outer-boundary normal dot: 0.9582.
- The quad's two tip-diagonal subtriangle normals have dot -0.7624.
- One subtriangle opposes the closing triangle (-0.8517); the other agrees (0.9807).
- Projected barycentric coordinates of the tip are approximately
  `(0.6973, -0.2083, 0.5110)` relative to `(626, 857, 856)`.
- Normalized tip depth is 0.03683; surrounding face joins agree by 0.9547–0.9906.

The tip lies beyond an outer edge and the quad crosses back over itself. Averaged
face normals hide the reversal, so the earlier opposite-normal rules correctly
did not recognize this variant. The closing triangle occupies 0.1120 UV units
of area (11.2% of a unit UV square), despite only 0.00001952 mesh units of area.
Its UV anisotropy is only 2.47: size/density and shape distortion are different.

## Directed weld

`Repair Folded Pockets` now includes a separate crossed-quad ear branch. It
requires a closed triangular boundary, one degree-two interior tip, reversed
quad subtriangles, an exterior tip projection, small depth and consistent
outside normals. Existing hidden/material/UV-pin/internal-seam protections stay
in force. Ordinary concave quads with an interior tip are excluded.

On this asset, vertex 121 welds to its nearest neighbor, original vertex 857.
No other vertex moves. The surviving quad becomes a triangle and receives a
local conformal UV layout anchored to its uncut neighboring edge.

- Before: 3925 vertices / 7911 edges / 3988 faces.
- After: 3924 vertices / 7909 edges / 3987 faces.
- All 3986 faces outside the two-face patch retain their topology and UVs.
- No open/non-manifold edges before or after.
- Severe UV diagnostic findings: 1 → 0.
- Repeating all repair modes makes no further changes.

Saved sibling: `Asset_00_07_REPAIRED.blend`. It was written with installed
Blender 5.3 Beta and reopened/validated in installed Blender 5.2 LTS (which emits
its usual newer-file warning). The source was not overwritten; its SHA-256
remains `81198358D837424B940334C9A0FB08A35C4DEEAB04B5373F2D68EC07AB4E66B5`.
Changed local UVs require rebaking existing textures.

## Merge Stretched Single Triangles

Auto Repair has a separate enabled-by-default checkbox and a stretch-ratio
control (default 50). Find Problems previews the candidate; Repair merges its
three mesh vertices to their arithmetic center.

The generic center merge targets a singleton triangle UV island surrounded by
distinct non-triangle faces, independently of the directed pocket weld above.
It checks real UV cuts as well as seams, and compares either UV anisotropy or
linear texel scale to the median density of the three edge neighbors. A linear
scale ratio of 50 corresponds to a UV-area/mesh-area density ratio of 2500.

Before merging it verifies a single closed vertex fan, no duplicated surviving
faces, no flipped/degenerate neighboring tessellation, and no hidden or pinned
local data. It preserves surviving corner UVs per face and unions seam/sharp
flags. Neighboring quads may become triangles; only the contracted three
vertices move. Newly created triangles are not recursively collapsed.

The same checkbox/threshold are passed to Phase 1 Batch Import Geometry Repair
(completed remesh passes) and Phase 2 Auto Repair, including repair after
Resculpting. Turning the checkbox off disables this center-merge rule in both
routes while retaining their other repairs.

## Validation

- `test_asset007_fold_blender.py`: real asset, full/default and selected repair,
  public Find/Repair, unchanged neighbors, repaired copy save.
- `check_repaired_asset007_blender.py`: reopen in Blender 5.2, manifold, UV and idempotence.
- `test_crossed_quad_ear_blender.py`: synthetic scale variations, ordinary
  interior tip, thick/hidden/seam/material/pinned negative cases.
- `test_stretched_single_triangles_blender.py`: center merge at three scales,
  pin/hidden/open/UV continuity/threshold protections, public selection/repair,
  UI controls and real Import/Phase 2 operator paths with the checkbox on/off.
- Previous flat/twisted ear, mesh fold, Batch Geometry Repair and Phase 2 Mesh
  Repair regressions passed in Blender 5.2.
