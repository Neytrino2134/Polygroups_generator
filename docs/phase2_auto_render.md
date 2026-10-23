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

Output Directory is shared with section 13. Existing skip/overwrite and optional
transparent companion settings are respected. Turning off the selection override
uses the current section 13 mesh filter. Texture output requires linked Base
Color and Normal images; unsupported/missing pairs are skipped by the existing
Prepare Textures operator.

## Scene and camera

The section 13 Reset Studio operator prepares the backdrop, camera and lights.
Foreign cameras/lights and old Scene_/Camera_/Light_ support objects are removed;
asset meshes are retained. Correct managed studio objects are reset and reused,
including recovery of tagged objects when their settings pointers were lost.
With setup disabled an existing active camera is required.

Each asset moves the existing Scene/Camera/Light Position empties. Temporary
multiview meshes use the same backend as Prepare Selected Multi View. MID and
LOD0 variants are aligned to a common preview origin without changing their
stored transforms. A union of the evaluated bounds of all three views and both
variants is fitted once, also allowing room for the texture pair. Perspective
camera distance is solved along Y, with X/Z centered on the union bounds; all
projected corners remain between 10% and 90% of the image. Hero and texture jobs
reuse the same camera matrix. No refitting occurs within an asset.

## Rendering and stopping

The implementation reuses Reset Studio, Prepare Textures, Scan Queue and the
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
  10% camera margins, identical camera matrices for every job within an asset,
  26 outputs with Freestyle pass/overlay, both texture preparation modes,
  foreign studio removal, tagged studio recovery without duplicate cameras or
  lights, original transforms/color spaces, switchable groups, injected failure
  cleanup, and a real unscaled 2048 x 1152 PNG. Multi-output stress checks render
  at reduced scale; the explicit 2K check uses the production 100% scale.
- test_phase2_auto_render_modal_blender.py: actual UI progress and stopping after
  the first rendered image, with temporary preview cleanup.
- Existing Render Queue Output, Render Textures, Render Studio, Batch
  Finalization and settings registration/persistence checks also pass.
