# Native projection artifact mask

Implemented and tested on 2026-10-10 in Blender 5.2.0 LTS, build fbe6228777e7.

## Shipped behavior

`Projection Artifact Mask` reads the actual raw tangent-normal bake before alpha
generation/background filling. It decodes the scene's normal swizzle, including
negative Z in another channel. Reversed-hemisphere seeds use epsilon 0.004 for
byte images (allowing 8-bit quantization) or 0.001 for float/private normal images.
Connected near-tangent regions with canonical Z <= 0.08 grow only from confirmed
inverted seeds, within their UV island. A steep positive-Z region alone is not a
seed. Confirmed defect texels are never eroded.

Full Projection additionally runs native Cycles white-emission projection with
zero margin (HIT) and lowpoly self-emission UV coverage with zero margin (UV).
Inside that UV domain, failed hits are white regardless of neutral normal RGB or
normal alpha. Diagnostic Surface overrides retain the Displacement graph. Every
material slot gets a private material and active target image; original slots,
links, active indices, selection, bake settings and engine restore after completion,
failure or cancellation. No Python per-texel approximation of Cycles rays is used.

The projection context is frozen before NORMAL: evaluated geometry, transforms,
corner normals, UVs, source shader graph, frame, cage, ray settings, swizzle and
actual image dimensions. Changes detected between passes fail the diagnostic.
Source image-pixel edits during a running bake are not independently hashed;
avoid editing input textures while baking.

Without the public Normal pass, a private native NORMAL diagnostic is used.
`Normal Inversion Only` omits HIT and does **not** detect ray misses. This reduced
cost mode still runs UV coverage. Default resolution matches the actual normal map,
including 8K. Manual output resolution only downsamples with conservative any-hit
resampling; it cannot exceed the normal resolution.

`Inherit Bake Margin` is enabled by default. `Additional Expansion (px)` defaults
to 2 and retains the existing `bake_artifact_radius` setting. Total mask expansion
is the actual frozen Bake Margin plus these extra pixels: margin 4 + extra 2 = 6.
With inheritance disabled, expansion is only the extra value. The shared UI shows
the live formula and total. Values are normal-resolution pixels before any manual
downsampling and are captured for the bake run.

Expansion uses eight-neighbor dilation inside the original UV island and its
surrounding gutter. Nearby UV islands compete for empty gutter texels; ambiguous
ties stop expansion, and other islands' interiors cannot receive padding. At image
edges, UV overlaps or tightly packed islands, expansion is clipped conservatively.
This gutter policy covers isolated islands' baked margins but does not claim exact
Blender native EXTEND ownership parity where competing margins overlap. Confirmed
core texels are preserved. The work region includes nearby competing islands and
is bounded around detected defects to avoid scanning empty distant image regions.

Legacy cage/highpoly intersections and cage self-intersections are separate,
optional additions, disabled by default. Their white pixels are warnings and can
include geometrically intersecting regions that bake correctly.

Prepare And Bake, Bake Selected and the modal BakeTask/Batch AutoBake use the same
session/pass/classifier API. The modal task launches one native OBJECT_BAKE job at
a time and waits before reading pixels or rolling back materials. Esc/Reset and
native object_bake_cancel cannot publish a current mask. UI controls are drawn by
the shared baking layout and appear in Classic, Custom and UI Panel modes.

## Autofill Artifacts

`Autofill Artifacts` is enabled by default. After normal classification and
background/alpha processing, it repairs requested Normal and Base Color textures
using the prepared white mask, including inherited margin and extra expansion.
Healthy donors are outside the mask, inside native UV coverage, have a confirmed
projection hit in Full Projection, and belong to the same unambiguous UV island.
An advancing eight-neighbor front averages boundary pixels inward; every wave
reads before writing. Islands and ambiguous gutter ownership cannot exchange
colors. Manual mask downsampling is expanded back to its native texel footprint
for repair, so the saved mask and repaired area agree.

`Autofill Blur (px)` defaults to 2 (0 disables smoothing). A separable Gaussian
with radius 2 and sigma 1 smooths only synthesized pixels, using valid neighbors
from the same island. Normal channels are decoded with signed/permuted XYZ
swizzles, averaged as vectors, normalized, and encoded again. Opposing vectors
use a valid donor fallback. Original pixels outside the mask are untouched by
Autofill; background processing still follows the existing bake settings.

The mask remains the original diagnostic map. Alpha coverage includes repaired
texels; the normal hash is sealed after repair, before texture export. Only enabled
bake maps are repaired; a private diagnostic normal is never published as a repaired
Normal output. A masked component with no healthy same-island boundary stays
unchanged and warns rather than borrowing from another island. Duplicate-axis
normal swizzles skip normal repair with a warning. Pixel-write failures restore
all already written regions and invalidate the current run through the bake caller.
JSON metadata records fill counts, unresolved counts and smoothing radius.

Work is bounded around the mask with a competing-island/blur halo. Memory and
runtime still scale with the repaired region, boundary size and maximum distance
to a healthy boundary; large mostly white 8K masks can require substantial work.
This propagates neighboring appearance, rather than recovering lost highpoly
detail. Acceptance includes native partial-hit bakes, both requested maps,
private-normal/Base-only baking, exact exterior preservation, unit normals,
island isolation, no-donor cases, PNG reload, write rollback, GUI async processing
and cancellation/reset (`tests/test_bake_artifact_fill_blender.py` and the modal
regression suite).

## Persistence

Every new bake invalidates the old run association while reusing its image slot.
The mask is retained through an unlinked image node in the target bake material,
so batch ownership/cleanup and blend saving follow real datablock references.
After background filling and optional Autofill, the normal's pixel hash seals the association. Save
Textures rejects stale/edited-normal associations and missing current-run masks.
Existing externally assembled texture packs with no projection run still save.
Disabling mask generation allows saving the other texture maps without a mask.

`<name>_Bake_ArtifactMask.png` is written to a temporary file in the destination
directory, loaded as Non-Color, and compared pixel-for-pixel with opaque binary RGB
before atomic replacement. Errors restore the image's previous filepath/format.
A `.png.json` sidecar records run, normal association, dimensions, settings,
thresholds, counts and limitations. PNG and sidecar are replaced individually;
there is no filesystem transaction covering both files.

## Validation

- `tests/test_projection_artifact_mask_blender.py`: native valid/reversed/missed
  rays, partial misses with clean regions left black, nearest of multiple sources,
  a cage origin inside a closed highpoly with no boundary intersection, legitimate
  steep positive-Z normals, custom shading normals, signed normal swizzle,
  private normal pass, explicit cage, nonuniform/mirrored transforms, smoothing,
  manual downsampling, fast mode, edited normal rejection, opacity/save failure,
  geometry-change rollback, shared multi-slot materials, preservation of linked
  displacement nodes, native cancel notification, UV overlaps and UDIM rejection.
  Saved/reloaded PNGs match the binary mask exactly.
- `tests/test_projection_mask_modal_blender.py`: factory GUI native asynchronous
  bake success, reset/cancel while HIT runs, and injected failure after UV material
  override. No private images or bake state remain. Original materials restore.
- `tests/test_projection_mask_batch_blender.py`: actual checked Batch AutoBake
  handoff with AutoCage, PNG export, separate blend save/reopen and valid mask
  provenance, with an idle bake state in the reopened project.
- `tests/test_projection_mask_margin_blender.py`: actual native UV-island gutter
  expansion and saved PNG dimensions/pixels; 4+2=6, 6+2=8, disabled inheritance=2,
  diagonal corners, core preservation, neighboring-island protection and shared UI.
- Existing `test_bake_artifact_mask.py`, `test_bake_alpha_merge.py`,
  `test_batch_autobake.py`, and `test_custom_ui_blender.py`: legacy geometry,
  alpha/merge/background/export, queue handoff and shared UI regression coverage.
- Partial native mask/normal PNGs were opened for visual inspection; pixel checks
  assert that the missed half is white and the valid half remains black.

## Native CPU performance

Isolated plane fixture, one Cycles sample, fresh factory process per size. Numbers
are examples for this host, not timings for production highpoly meshes. Peak
working set includes Blender, its bake buffers, normal/HIT/UV images and the mask.
Background filling/AlphaMap work is outside this benchmark.
These measurements precede inherited-margin gutter expansion; that additional
cost depends on the padding radius and UV layout. The benchmark's full-domain
plane has no external UV gutter.

| Resolution | NORMAL | Additional mask | Peak working set |
| --- | ---: | ---: | ---: |
| 2048 | 0.59 s | 1.08 s | 1338 MiB |
| 4096 | 2.82 s | 5.44 s | 4449 MiB |
| 8192, including PNG verification | 11.13 s | 21.37 s | 16995 MiB |

The 8K PNG save/reload/full pixel comparison took another 2.66 s. Peak committed
memory was 18842 MiB in that run. UV ownership rasterization uses 64-row blocks;
native bake buffers and whole-image `foreach_get` still dominate memory. The
benchmark is reproducible with `tests/benchmark_projection_mask_blender.py --
8192 --save` in a factory background Blender process.

## Limits and acceptance boundary

UDIM/out-of-tile UVs and non-square output are explicitly unsupported. Overlapping
UVs warn because multiple surfaces share texels; overlap pixels cannot establish
unique ownership. Native coverage remains the authority for the UV domain; Python
island rasterization only restricts border growth/padding. Pixel-center differences
at island edges can conservatively suppress padding, never remove confirmed core.

Merged atlas masks are explicitly unsupported and warn on Merge and Save; export
masks on the original meshes. Positive-Z hits on the wrong component are not
automatically detected. Inverted/custom/two-sided shading normals can be a genuine
input problem or intentional shading, and are still marked as reversed normals.
Graph copying preserves displacement links; shader-driven displaced microgeometry
has not been exhaustively validated across Cycles GPU devices/adaptive subdivision.
Tests used CPU Cycles, not every GPU backend or every thin/concave geometry case.

The user's exact pictured mesh/cage was not provided, so that specific artifact
cannot be claimed verified. The implementation guarantees containment of the
detected reversed seeds and proven misses in supported, unambiguous UV domains;
it does not promise to recognize every visually undesirable baked normal.
