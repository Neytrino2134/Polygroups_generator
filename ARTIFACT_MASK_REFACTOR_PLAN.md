# Projection Artifact Mask — refactoring plan for an implementation agent

Status: researched design, not an implemented production change. Production bake
and save functions remain unchanged in this planning task.

## Objective and acceptance contract

Replace geometric intersection-region guessing with a mask aligned to the actual
normal bake. White means a detected projection problem; black means no detected
problem. The saved mask must cover every detected reversed-hemisphere texel and
every proven ray miss inside the target UV domain. Its resolution, UV orientation,
target, sources and bake run must match the normal texture it accompanies.

This is a measurable guarantee for these defect classes, not a promise to identify
every visually undesirable normal. A hit on the wrong nearby component can still
have a positive tangent Z. Overlapping UVs, deliberately two-sided normals, malformed
shading normals and ambiguous geometry require separate warnings/diagnostics.

## Evidence from the current checkout

- `operators/baking.py:_generate_bake_artifact_mask` finds BVH overlaps, projects
  intersection segments into UVs, then estimates interior points only on faces
  recorded by those intersections. It does not inspect the normal bake or mirror
  its per-texel hit selection. A completely enclosed cage face may also escape
  processing if it never produces an intersection segment.
- The automatic cage diagnostic approximates geometry by extruding vertices using
  accumulated triangle normals. The actual bake configuration uses extrusion
  without an explicit cage unless Smart Cage is enabled. These are different paths.
- `_fill_cage_area_inside_mesh` uses arbitrary-direction parity for closed meshes
  and nearest-normal sign for open meshes. Neither proves the outcome of a bake ray.
- The mask has an independent resolution (default 2048, maximum 4096), so it can
  undersample a larger normal texture. Mark Radius mainly thickens intersection
  lines; it cannot guarantee that an entire inverted-normal region is filled.
- All three bake entry paths currently generate the mask AFTER
  `_finalize_bake_images`. Saving can still find a previous mask image if the new
  generation fails and is reduced to a warning. Prevent stale-mask export.

The isolated native probe `tests/probe_bake_projection_artifacts_blender.py` was
run with Blender 5.2.0 LTS, build fbe6228777e7, CPU Cycles, 32x32 pixels and zero
margin. Center-pixel results:

| Case | Tangent normal RGBA | White-emission projection RGBA |
| --- | --- | --- |
| Valid hit | (0.50001, 0.50001, 1.00001, 1) | (1, 1, 1, 1) |
| Reversed-normal hit | (0.50001, 0.50001, 0.00001, 1) | (1, 1, 1, 1) |
| Source outside the inward ray | (0.5, 0.5, 1, 1) | (0, 0, 0, 0) |

Thus blue inversion is not equivalent to a miss, and normal alpha alone is not a
reliable hit detector. This probe establishes a mechanism, not the cause of the
user's specific mesh: only screenshots were supplied for that mesh.

Native reference, pinned to the installed build:
[Blender bake.cc](https://github.com/blender/blender/blob/fbe6228777e7/source/blender/render/intern/bake.cc).
The explicit-cage ray starts at the corresponding cage point and points toward
the lowpoly point. The extrusion path derives its ray from the interpolated low
normal. Highpoly hits are selected by world-space distance; zero distance limit
means unlimited. Missing tangent normals are filled with a neutral normal.
Normal compression also has a small bias and configurable channel swizzling.
Use these rules to validate the design; do not implement a second Python ray tracer.

## Recommended algorithm

### A. Freeze one bake context

Create an immutable `BakeProjectionContext` after AutoCage/Smart Cage preparation:
target and selected sources, evaluated transforms/topology, UV layer, frame,
actual width/height, cage object/use_cage/extrusion, max ray distance, normal space
and channel swizzle, normal margin and margin mode. Include a run identifier.
Do not recompute AutoCage between passes. Do not change target/source selection
or geometry during the diagnostics. Reject invalid topology and unsupported UV
configurations before launching; report overlapping UVs as ambiguous.

### B. Capture normal evidence before add-on postprocessing

Use the normal image immediately after the NORMAL pass finishes, before background
fill, image merging, saving or reloading. Its native bake margin may already be
present: distinguish this from the add-on's later postprocessing.
Read Non-Color pixel data, undo channel swizzle/sign and the documented bias,
and reconstruct canonical tangent Z. Do not infer canonical Z blindly from blue
when the channel mapping differs. If Z is absent from a custom mapping, reject
that classifier or run a private canonical-normal diagnostic without modifying
the user's normal output.

### C. Measure hits through Cycles itself

Bake a private white EMIT hit image `H0` with the same projection context and
margin=0. Override source Surface output with white emission, retaining displacement
and all geometry-affecting evaluation. The output is white on a source hit and
black on a miss. Account for every material slot and shared/linked materials;
use temporary local copies rather than editing shared originals.

Also obtain the lowpoly UV-domain image `U0` through a private white self-EMIT
bake, selected-to-active disabled and margin=0. This distinguishes a ray miss
inside a UV island from the ordinary empty texture background. Existing geometric
UV coverage is only an optimization after its border parity with native coverage
is proven; do not use normal alpha as a substitute for U0 or H0.

Temporary surface overrides must not change evaluated geometry. Test shader
displacement explicitly. If equivalence cannot be guaranteed for a source, return
an unsupported/incomplete diagnostic status rather than claiming exact coverage.

### D. Classify reason masks

Let `U` and `H` be validated binary domain/hit flags from U0/H0, and `Z` the
decoded tangent Z. Use non-color linear values, not display-transformed PNG colors.

```text
reversed_seed = U AND H AND (Z < -epsilon)
ray_miss      = U AND NOT H
edge_candidate = U AND H AND (Z <= edge_z_limit)
reversed_region = connected_grow(reversed_seed, edge_candidate, within_same_UV_island)
core = reversed_seed OR reversed_region OR ray_miss
```

Choose epsilon from actual float/8-bit quantization, with test evidence. An initial
edge_z_limit around 0.05–0.10 is a tunable proposal, not a validated universal default.
Connected growth should absorb the near-zero transition around a reversed region
without marking every legitimate steep normal elsewhere. Always retain every
seed and miss; never erode them during cleanup. Do not flood-fill an entire island
or lowpoly triangle merely because one point is problematic.

Maintain separate reason flags internally: reversed normal, ray miss, uncertain
edge, optional geometric/self-intersection warning. Default saved ArtifactMask
combines reversed regions and proven misses. Geometric warnings remain optional
so harmless intersections do not override the result-based mask.

### E. Conservative borders and resolution

Work at the actual normal texture resolution by default, including 8K when used.
Expose Match Normal Resolution; retain legacy manual resolution only as an advanced
mode. Never bilinearly shrink a binary diagnostic: downsample using any-hit/max
pooling, then expand conservatively when comparing/exporting at normal resolution.

Add a small configurable safety dilation (initial proposal 1–2 pixels), with UV
ownership constraints. Core expansion cannot jump into a neighboring island.
Handle texture gutters separately from core classification. Validate native EXTEND
margin parity; Python has no assumed public access to native per-pixel extension
ownership. Use conservative padding where exact ownership is unavailable and
report the policy. Do not mistake margin-filled holes for valid hits: H0 has no margin.

Keep the core binary (0/1), with final white RGB=1 and alpha=1. A separate optional
soft/confidence preview must never reduce coverage in the binary exported mask.

### F. Associate and save the result transactionally

Keep the existing target image property and `_Bake_ArtifactMask.png` naming for
compatibility. Store producer/version, run id, target/source identifiers, normal
image association, dimensions, cage configuration, thresholds, padding and counts.
Invalidate current-run mask status when a new normal bake starts. A failed or
cancelled diagnostic must not cause export of the previous mask as the current one.

Write the new mask to a temporary PNG in the destination directory; reopen and
verify dimensions, Non-Color values and white/black preservation before replacing
the final path. Restore image filepath/format on failure. Use a separate mask save
helper rather than extending side effects of `_save_image_as_png` for all textures.
Saved metadata belongs in a small sidecar when needed; do not include credentials.

## Implementation blocks and commits

1. **Context, provenance and diagnostic contracts.** Extract context/result types
   and pixel classification helpers into `core/bake_projection.py` and
   `core/bake_artifact_mask.py`. Keep the current geometric function available
   under an explicit legacy diagnostic name. Establish stale-image invalidation
   and mathematical unit fixtures. Checkpoint first, then commit this coherent block.
2. **Native coverage passes with full rollback.** Add H0 and U0 passes sharing one
   frozen context. Centralize material/node, engine/bake settings, active image,
   selection, frame and cage rollback. Do not launch another OBJECT_BAKE job while
   one is running. Verify actual Cycles hits/misses and displaced/multi-source cases.
3. **Result-based region classifier.** Decode normal pixels, compute reason masks,
   connected borders and conservative dilation. Implement Match Normal resolution
   and valid UV ownership. Verify containment assertions against native normal data,
   not against the old geometric mask.
4. **Pipeline integration and UI.** Route Prepare And Bake, Bake Selected, regular
   bake and batch AutoBake through one diagnostic API. Add modal stages
   NORMAL_WAIT -> HIT_COVERAGE -> UV_COVERAGE -> ARTIFACT_CLASSIFY -> POSTPROCESS -> SAVE.
   The background executor must call the same operations sequentially. Preserve
   cancellation, reset and queue continuation. Shared UI changes propagate to all
   three modes. Keep existing enable/property identifiers; clarify the description
   as Projection Artifact Mask, with separate optional geometric/self checks.
5. **Reliable persistence and merged output.** Implement run association and atomic
   PNG persistence. Update Save Textures to reject/skip stale masks with a visible
   reason. Audit merged bake paths: transform/max-compose each mask using the SAME
   atlas remap as its normal, or explicitly mark unsupported instead of silently
   dropping it. Test original mesh, merged output, reload and separate batch files.
6. **Acceptance, performance and final commit.** Run the fixture matrix below in
   real Blender, compare mask overlays, document time/peak memory at 2K/4K/8K, and
   inspect final saved PNGs. Commit only after focused checks pass. No push.

## Required fixture matrix

- Clean enclosing cage: no reversed or missed core texels.
- Highpoly protruding beyond cage: miss and/or reverse-hit regions are fully covered.
- Entire cage face inside a closed source with no boundary intersections.
- Reversed hit vs true miss: distinguish reason flags; normal alpha is not accepted
  as proof of a hit. Reuse the included native research probe.
- Open shell, thin double surface, concavity, intersecting components and multiple
  sources at different distances. Keep unresolved positive-Z wrong-hit cases visible
  in diagnostic limitations instead of labeling them automatically correct.
- Explicit Smart Cage and extrusion-only AutoCage; smooth/flat/custom normals,
  nonuniform and mirrored transforms, normal channel swizzles.
- UV seams, touching gutters, mirrored islands, overlap warnings, material slots,
  active UV selection and normal margin behavior. UDIM requires tilewise native
  coverage/classification/export; if not supported initially, reject it explicitly.
- 2K/4K/8K normal maps and manual diagnostic resolution; a one-texel seed survives.
- No normal pass requested: if the user requests full artifact analysis, create a
  private canonical normal pass or explicitly offer geometry-only diagnostics.
- Cancellation and failure at each extra pass and at disk save: settings/materials
  restore, queues unlock, old masks do not masquerade as new results.
- Actual save/reopen: dimensions agree, alpha=1, white remains 255, black remains 0.

For fixture reference defect set A, assert `A AND NOT SavedMask == empty` at the
normal resolution. Assert a low false-positive rate on clean/legitimate steep-normal
fixtures. Inspect the user's exact protrusion case once its mesh is available;
screenshots alone cannot establish its cage/ray/source geometry.

## Performance and implementation constraints

Prefer native bake passes and vectorized/tiled classification over Python BVH ray
casts per texel. Read normal pixels once into a contiguous float buffer. Process
classification in bounded row blocks with compact reason/domain/hit buffers. Python
foreach_get generally still requires a whole-image buffer: do not claim zero-copy
streaming unless the chosen backend actually supplies it.

At 8K a single float RGBA buffer is about 1 GiB; three byte-per-pixel buffers add
about 192 MiB, excluding Blender image storage. Reuse the read buffer for mask RGBA
upload after classification, release scratch images promptly, and measure peak
memory rather than assuming that row-wise classification eliminates the read cost.
Offer a documented reduced-cost mode that detects normal inversion only; it must
not claim ray-miss coverage. Freeze the actual sources once and reuse context data.

## Work completed for this plan

Inspected the current geometric classifier, AutoCage calculation, bake settings,
normal finalization, all mask invocation sites and PNG save path. Verified the native
hit/miss distinction with six actual Cycles bakes in a factory scene. Added the
reproducible research probe and this plan only; no production refactor is applied.
