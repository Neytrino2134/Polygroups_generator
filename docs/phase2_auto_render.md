# Phase 2 Auto Render

Auto Render follows Batch Finalization and uses the common Processing Status.
Start Render scans current-scene Asset_NameIndex_VersionIndex_Collection assets
recursively. Default selection is *_MID and *_LOD0; LOD0 renders use LOW filenames.

## Defaults

- Quality and Output: 16:9, 2K = 2048 x 1152, 100%, Eevee, PNG.
- Scene and Camera Setup: on; Auto Frame Camera: on, minimum 10% edge margins.
- Mesh Selection MID + LOD0: on.
- Freestyle: on; As Render Pass: on; color #E8E8E8FF (stored scene-linear).
- Multiview: on; offset 1 metre, angle -30 degrees, Hero on.
- Prepare Textures: on; All Assets First by default, Per Asset also available.
  Base Color and Normal are rendered Together in one image.

Output Directory is shared with section 13. Existing skip/overwrite settings
are respected; transparent companions use the Auto Render checkbox and prefix. Turning off the selection override
uses the current section 13 mesh filter. Texture output requires linked Base
Color and Normal images; unsupported/missing pairs are skipped by the existing
Prepare Textures operator.

## Scene and camera

The section 13 Prepare Scene operator creates missing studio support and reuses
managed objects, retaining tuned light powers and studio parameters. Foreign
cameras/lights and old Scene_/Camera_/Light_ support objects are removed when
scene setup is enabled; asset meshes are retained. Tagged studio pointers are
recovered before preparation. With setup disabled an active camera is required.

Auto Render uses the same `prepared_queue_job` path as Start Render: asset
isolation, prepared or temporary Multiview, Scene/Camera/Light Position movement,
Hero isolation, rendering and cleanup. Original mesh transforms and the exact
configured offset and rotations are retained. Bounds are measured through this
same preparation path before rendering, then normalized to each source origin
so MID and LOD0 share one camera fit. Camera X/Z are centered on the union and
distance is solved along Y with 10% edge margins. The fit is computed once per
asset; ordinary queue movement of the position controls is retained. Texture
jobs keep section 13's dedicated texture rendering behavior.

## Rendering and stopping

The implementation reuses Prepare Scene, Prepare Textures, Scan Queue and the
same image/Freestyle/texture rendering backend as section 13. Textures can be
prepared for the entire target set first or immediately before each asset.
Every asset is isolated; unrelated geometry and prepared previews do not leak
into its render. Source geometry/material/image color spaces are preserved.

The modal queue updates percentages in Processing Status and the workspace
status bar. Stop Render or Esc stops at the next image-job boundary. Native
rendering and its Freestyle companion passes finish before that boundary.
Temporary multiview objects are removed and working flags cleared on completion,
stop, error, file load, Undo/Redo or add-on unregister. Prepared texture planes
and the configured studio remain available for use in section 13.

## Validation

Blender 5.2.2:
- test_phase2_auto_render_blender.py: real render of two differently sized assets,
  10% camera margins, fixed camera fit relative to each source origin,
  26 outputs with Freestyle pass/overlay, both texture preparation modes,
  foreign studio removal, tagged studio recovery without duplicate cameras or
  lights, original transforms/color spaces, switchable groups, injected failure
  cleanup, and a real unscaled 2048 x 1152 PNG. Multi-output stress checks render
  at reduced scale; the explicit 2K check uses the production 100% scale.
- test_phase2_auto_render_modal_blender.py: actual UI progress and stopping after
  the first rendered image, with temporary preview cleanup.
- Existing Render Queue Output, Render Textures, Render Studio, Batch
  Finalization and settings registration/persistence checks also pass.


## Multiview visibility and transparent companions

Multiview uses section 13's exact configured offset (default one metre) and
rotations. Auto Render does not add spacing or resize the studio backdrop.
Hero uses the ordinary queue isolation of the front view and the same camera fit.

Render Transparent PNG (Without Scene) defaults off. Prefix Scene defaults to
Scene and maps to the existing section 13 transparent-background behavior.
When enabled, a separate _transparent.png is rendered with the backdrop prefix
hidden; the regular image is retained. Freestyle companions are also included
in existing-output completeness checks. Asset collections and their multiview
children are protected even if their asset names begin with Scene_.

The regression test test_phase2_multiview_visibility_blender.py checks visible
object counts and three transparent silhouettes versus one in Hero, together
with Scene_ prefix protection. test_auto_render_shared_queue_blender.py compares
manual and automatic queue transforms and output pixels, verifies the fixed
camera fit, and measures real light contribution from a manually configured rig.
