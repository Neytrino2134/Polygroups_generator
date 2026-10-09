# AI Retopo Toolkit — Custom Cyan UI Implementation Plan

Design update (2026-10-09): the user's second reference supersedes the first.
Use a modern flat style: solid dark surfaces, thin separators, a blue selected
navigation row with a cyan side marker, flat primary buttons, restrained
rounding, and no glow. Earlier references to gradients are superseded.

## Agent mission and scope

Implement a complete, production-ready Blender viewport interface for AI Retopo Toolkit, with persistent Classic / Custom selection in Add-on Preferences. Preserve all existing functionality, operator identifiers, RNA settings, localization, undo behavior, queues, hotkeys, integrations, and scene compatibility. Work in large cohesive implementation blocks, validate each block, and create verified local commits before implementation and after completion. Do not push unless separately requested.

This document is a plan; the UI has not been implemented. The supplied image is the visual direction, not an authoritative specification of existing functionality. Do not create fake controls, previews, diagnostic values, or capabilities solely because they appear in the image.

## Verified local architecture

- Reference: sibling `auto_unwrap/__init__.py`, `AUTOUNWRAP_Preferences`, `classic_panel`, `card_on`, `_apply_panel`, `_panel_later`, and `AUTOUNWRAP_OT_ui_switch`.
- Reference renderer: sibling `auto_unwrap/card.py`. Uses Blender `gpu`, `gpu_extras.batch`, and `blf`; not Skia, Qt, HTML, or an external UI framework. Rounded rectangles, gradients, text, icons, images, hit regions, scrolling, and fold state are implemented by the add-on.
- The reference installs a `SpaceView3D` WINDOW / POST_PIXEL draw handler. `AUTOUNWRAP_OT_overlay` handles input; `_run_later` schedules operator invocation with the originating window/area/region override. Its lifecycle uses cleanup and stale-handler protection in `bpy.app.driver_namespace`.
- The reference defers mode changes through a timer, saves user preferences, hides its classic panel when the card is active, and provides a classic fallback.
- Target: `ui.py` has a root panel, numbered child panels 01–13, `draw_topic` groups, nested subsection visibility, search filtering, and detached-group drawing.
- Target: `properties.py` owns operational settings; `preferences.py` owns global preferences; `localization.py` owns translated labels; `custom_icons.py` owns existing icons. `__init__.py` controls registration order.
- Target already includes a Windows Tkinter client in `standalone_ui/client.py`, and a main-thread bridge in `operators/detached_groups.py`. `core/window_schema.py` captures controls but currently flattens rows/columns/boxes into a list. It is useful groundwork, not a complete hierarchical model.
- Preserve the external client and its protocol. The requested primary Custom UI should run inside Blender, matching the reference architecture. Do not make an external executable mandatory for it.
- Inspect the reference for behavior and independently implement the target architecture. Do not copy large source blocks or assets without verifying reuse rights.

## Block 0 — Recovery checkpoint and complete functional inventory

1. Read applicable AGENTS.md instructions. Inspect `git status`, current branch, recent commits, and existing tests. Record the live baseline SHA and Blender executable/version.
2. Create a local baseline commit before changing implementation. Include only authorized source changes; do not silently stage user data, renders, API credentials, binaries, or unrelated work. If clean, an explicit empty checkpoint is acceptable. Verify `git show --stat` and `git status` afterward.
3. Generate `docs/custom_ui/control_inventory.json` from all panel draw paths, helper functions, preferences, menus, and nested subsections. Use static inspection plus live Blender snapshots across modes, selections, language, optional integrations, and expanded/collapsed states; a single snapshot is insufficient.
4. Every control record must contain stable section/group/subgroup ID, owner and RNA property or operator ID, operator parameters and execution context, label/translation key, icon, poll/enable conditions, RNA subtype/units/range, tooltip, update behavior, and required native dialog or viewport interaction.
5. Include header actions, autosave/restart, Expand All / Collapse All, search, preferences, floating windows, developer-only tools, notices, context menus, pie menus, and outliner/viewport assists. These supporting surfaces remain available even though they are outside the numbered navigation.
6. Commit the inventory and architecture together. No section may be declared complete with unclassified or inaccessible existing controls.

## Design and interaction contract

- Desktop shell: compact left navigation with all 13 numbered sections; right content area with the active section and nested collapsible cards. Header contains name/version, autosave/restart, search, settings, and collapse/expand actions.
- At small viewport widths use a compact section selector and one content column; never shrink text to fit. Allow resize, move, collapse, and restore. Clamp geometry after workspace or resolution changes; avoid covering essential gizmos and viewport toolbars by default.
- Proposed sRGB palette: background `#08121B`, surface `#0D1D29`, raised surface `#142B3B`, border `#25485E`, primary blue `#009FE8`, cyan `#00D5F5`, text `#EAF3FF`, secondary text `#A8BED1`. Success `#46D6AA`, warning `#FFBC66`, error `#FF6F82`. Convert consistently for the rendering path and verify actual on-screen colors.
- Cyan identifies selection, enabled toggles, focus, and primary actions. Use restrained borders and subtle gradients; avoid glow on every control. Rounded cards 10–12 logical pixels, controls 6–8; spacing follows a 4/8/12/16 grid. Make the theme token-driven.
- One primary action per task card; destructive actions use an explicit label and the existing operator confirmation behavior. Preserve existing defaults and required confirmation dialogs.
- Header click toggles a group; chevrons indicate state. Store active section and per-section scroll; retain current group/subgroup visibility where practical. Expand All / Collapse All have clear scope; search temporarily reveals matching ancestors and restores previous fold state when cleared.
- Use real settings and real results. Bake coverage, intersection counts, cage preview, export flags, and AI status appear only when backed by existing data or separately implemented features. A mockup value such as 99.8% must never be displayed as measured output.
- Preferences add `ui_mode = CLASSIC | CUSTOM`, scale, accent preset/color, surface brightness, and rounding with restrained defaults and Reset Appearance. Default existing installations to CLASSIC for safe migration. Preferences remain reachable in Blender Preferences and through a Custom settings button.
- Switching changes presentation only. Keep the same RNA values, active scene, selected objects, queues, operator progress, and undo stack. UI state belongs to preferences/runtime storage; mesh/bake/import settings remain in their existing owners.
- Text: readable at Blender UI scale, clear focus states, tooltips, keyboard editing, Enter to commit, Escape to cancel, clipboard support, unit-aware numeric entry, and proper Unicode/localized labels. Long paths and labels receive truncation plus full tooltips.
- Slider edits require rollback on Escape, valid range handling, and correct update callbacks. Avoid generating an undo step for each mousemove. Properties with complex native editors may open a native popover rather than a reduced substitute.
- Pointer events outside the card pass through. Scrolling affects only the hovered scroll container. Block viewport shortcuts while editing text, release capture on cancel or area loss, and suspend or yield to active seam/cutter/sculpt operators.

## Complete numbered panel hierarchy

Keep the numbered order below. Existing `draw_topic` keys remain stable identifiers. Card titles may be improved without changing underlying settings. The inventory determines every child control, including helper-generated and conditional controls.

| Section | Existing groups and required nested content |
| --- | --- |
| 01 Import | `import_0` Source; `import_1` Simple Processing; `import_3` Automatic Processing; `import_2` Progress. Preserve file selectors, source modes, processing options, and import timing/status. |
| 02 Batch Import | `batch_0` Source/Queue; `batch_1` Processing; `batch_2` Arrange Objects; `batch_3` Run; `batch_4` Progress. Preserve queue items/actions, processing branches, redo, separate-save, automatic bake/finalization, cancellation, and reports wherever currently exposed. |
| 03 Model Preparation | `prepare_0` Prepare; `prepare_1` Mesh Edit; `prepare_2` Manage; `prepare_3` Seams. Preserve all conditional helpers, selection checks, cleanup, collections, material/preview controls, and seam options. |
| 04 Seam Preparation | `seam_prep_0` Selection; `seam_prep_1` Mesh Edit; `seam_prep_2` Mark/Clear; `seam_prep_3` Smart Mark; `seam_prep_4` Small Islands; `seam_prep_5` Interactive Tools; `seam_prep_6` Check; `seam_prep_7` Cut. Preserve all nested tool settings, edge/vertex paths, knife, cutters including local contour, relax, overlays, gap checks, and context-dependent availability. |
| 05 Polygroups | `polygroups_0` Generate; `polygroups_1` Small Islands / UV; `polygroups_2` Manage. Preserve material/face-set behavior and all current generation and island-management controls. |
| 06 Remesh | `remesh_0` Controls; `remesh_1` Progress. Preserve remesher selection, external integration availability, settings, material/seam options, running-state controls, cancel, progress, and existing undo behavior. |
| 07 Resculpting | `sculpt_0` Multires and Shrinkwrap; `sculpt_1` Prepare Sculpting. Preserve modifiers, target pointers, native sculpt handoff, and conditional controls. |
| 08 Seam Finalization | `seam_final_0` Settings; `seam_final_1` Mark Seams; `seam_final_2` Gap Check; `seam_final_3` Checker Preview; `seam_final_4` UV Unwrap; `seam_final_5` UV Seam Tools. Preserve all nested preview, repair, and interactive settings. |
| 09 UV Preparation | `uv_0` Unwrap; `uv_3` Repair; `uv_2` Narrow Island Splitter; `uv_1` UVPackmaster Packing. Preserve all repair/relax branches, checker controls, packer availability and native integration settings. |
| 10 Baking | `bake_0` Save Project; `bake_1` Cage; `bake_2` Bake Settings; `bake_3` Operations; `bake_4` Cleanup. Visually subgroup existing settings into map selection, quality, output, and preferences only where they actually exist. Preserve source/target selection, AutoCage diagnostics, artifact masks, alpha merge, path controls, run/cancel, and cleanup. Do not invent extra export or map options from the image. |
| 11 AI Generation | `ai_0` Prompt Library; `ai_1` OpenAI Image; `ai_2` Google Image. Preserve provider-specific controls, prompt presets, inputs/results, and existing asynchronous behavior. Credentials stay in their current secure preference paths; never serialize secrets into UI snapshots or logs. Live paid generation requires existing task authorization. |
| 12 Mesh Finalization | Preserve every top-level control before export groups and all helper-defined subsections. `export_3` GLTF; `export_0` Fab; `export_1` Unity; `export_2` Blend Assets. Preserve naming, preparation, Smart LOD workflows, collections, texture modes, presets, export dialogs, queues, reports, and all current output variants. |
| 13 Render | `render_1` Quality/Output; `render_6` Scene Setup with Camera/Lights/Scene children; `render_7` Arrange Objects; `render_2` Multiple Views; `render_9` Render Textures; `render_0` Queue; `render_4` Progress; `render_8` Color Palettes; `render_5` Animation. Preserve Multiple Views before Queue, all light roles/aim controls, image formats, transparent companions, palettes, LOD labels, queue selection, output actions, and animation settings. |

Hierarchy: Toolkit → numbered section → stable task group → existing nested subsection → rows/controls → status/actions. Preserve conditional visibility and SECTION_SUBSECTION_PROPERTIES relationships. Never infer completeness from the table alone.

## Block 1 — Shared hierarchical UI model and bindings

Implement `custom_ui/schema.py`, `bindings.py`, and `state.py` or equivalently scoped modules. Extract reusable section builders from `ui.py` incrementally so Classic and Custom consume the same functional definitions. Avoid duplicating 13 panels into two independently maintained code paths.

Represent section, group, subsection, row, column, split, separator, label, property, operator, progress, image, and list nodes. Nodes need stable semantic IDs; list-index IDs are unsuitable across conditional redraws. Preserve icons, layout ratios, enabled/active inheritance, operator_context, post-creation operator parameters, property index, dynamic enums, enum flags, pointers/collections, prop_search, units, and readonly state. Model meaningful functionality rather than incidental native layout calls.

The existing flattened window schema cannot be directly reused as the full model. Introduce a compatibility adapter so the standalone client remains functional. Adapt `draw_topic`, search wrappers, and helper layouts deliberately; record unsupported layout APIs and resolve every relevant one.

Bindings run only on Blender's main thread and resolve against the current scene/context when activated. Recheck poll and conditions on dispatch. Queue native INVOKE operations after releasing UI capture, retaining the originating VIEW_3D WINDOW context. Reject stale scene/control revisions after file load or context changes. Do not evaluate arbitrary Python or arbitrary client RNA paths.

Verification gate: inventory-to-schema parity across all 13 sections; dynamic enum flags, pointer search, disabled inheritance, operator kwargs, native dialogs, localization, and external-client compatibility. Commit this entire foundation after passing the gate.

## Block 2 — GPU widgets, shell, preferences, and lifecycle

Implement `custom_ui/theme.py`, `renderer.py`, `widgets.py`, `events.py`, and `lifecycle.py`; integrate registration with `__init__.py`, preferences with `preferences.py`, and launch/switch controls with `ui.py`.

Build cached geometry, rounded cards/buttons, borders, restrained gradients, BLF text, icon textures, toggles, sliders, numeric/text fields, dropdowns, lists, tooltips, progress, scissor-clipped scrolling, and focus handling. Geometry and hit testing share one scaled layout result. Restore GPU state after drawing and handle clipping in nested containers. Do not call operators, mutate scene data, or scan the whole scene inside draw callbacks.

Use per-window/per-area sessions; avoid one global geometry or scroll state shared by all viewports. Redraw on hover/state change or bounded active progress updates. Cache fonts/images/shaders and invalidate on scale/theme/data changes. No continuous idle redraw loop without evidence that it is needed.

Keep panels registered where possible and gate numbered Classic panel visibility through poll; preserve auxiliary menus and header hooks. Maintain a small launcher/fallback surface reachable in Custom mode. Defer preference transitions outside draw callbacks; register/remove timers and handlers idempotently. Save preference selection without silently changing global Blender preference behavior.

Cancel sessions and clear bindings on file load, add-on disable/reload, lost areas, closed windows, and mode transition. Remove only this add-on's handlers/resources. On renderer initialization failure, show a visible error and restore accessible Classic controls. In background Blender, register functionality without starting drawing/modal UI.

Verification gate: actual Blender GUI checks for theme, DPI, input, move/resize, responsive layout, Classic/Custom persistence, two viewports/windows, file load, reload, cleanup, renderer failure, and modal-tool coexistence. Commit the complete engine and shell.

## Block 3 — Migrate geometry workflow sections 01–09

Implement all nine sections in one coherent functional batch using the shared builders and widgets. Preserve nested groups and conditional settings instead of copying only the currently visible controls. Integrate import/batch progress, remesh status, preview toggles, selection/mode requirements, optional remesh/UVPackmaster availability, and viewport tool handoff.

Verification gate: compare Classic and Custom action/property bindings against the inventory. Run focused existing panel/search/visibility, import/queue, remesh/undo, seam/cutter, polygroups, sculpt, and UV tests. Execute representative reversible tools in real Blender and verify mesh changes/undo. Open native file selectors and interactive tools from Custom, confirm cancellation and continued viewport control. Commit this complete workflow batch.

## Block 4 — Migrate production workflow sections 10–13 and global surfaces

Implement Baking, AI Generation, Mesh Finalization/Export, Render, and all global header/settings surfaces as one cohesive batch. Present real asynchronous status and cancellation using existing job state; avoid UI polling that alters operation semantics.

Preserve bake source/cage controls, artifact diagnostics, output/cleanup, prompt libraries and provider branches, all export workflows, render studio hierarchy, multi-view ordering, palettes, animation, and output links. Use temporary test assets/output directories. UI planning and migration do not authorize paid AI requests or unrelated external actions.

Verification gate: binding parity plus relevant bake, export, Unity/LOD, render, transparent-output, animation, and AI UI tests. Validate real file outputs for local workflows where integrations are installed. Missing optional providers must show a useful state without crashing. Do not substitute fake success for unavailable integrations. Commit the complete production workflow batch.

## Block 5 — Acceptance, performance, and release checkpoint

1. Run syntax/whitespace checks and focused automated tests. Run actual Blender 5.2 registration and behavioral tests; headless tests cannot validate GPU appearance or pointer behavior.
2. Perform GUI acceptance for all 13 sections in Classic and Custom, Object/Edit/Sculpt contexts, no selection/multiple selection, absent optional integrations, both supported languages, long paths, dynamic options, and expanded nested panels.
3. Verify actual render appearance at UI scales 1.0/1.5/2.0 and narrow/wide viewports. Capture screenshots in a validation report; ensure visually aligned hit regions, readable labels, clipping, and subdued cyan styling.
4. Stress switch repeatedly during running jobs without duplicating or cancelling those jobs. Check file load, workspace switches, multiple windows, disable/re-enable, and development reload for leaked handlers/timers, blocked shortcuts, and stale bindings.
5. Measure idle redraw frequency, layout/draw timing, hover/scroll responsiveness, texture memory, and viewport interaction impact against the baseline using the same scene. Set budgets after baseline measurement; do not claim performance gains from code inspection.
6. Reconcile every inventory item. Unsupported items need a working native handoff and documented justification; no silently omitted function. Verify existing detached windows, hotkeys, menus, and saved settings.
7. Repair failures before completion. Update architecture/user documentation and `docs/custom_ui/validation_report.md` with tested conditions, actual results, limitations, and output evidence.
8. Review `git diff --check`, final diff, and staged files. Create the final local commit, verify its SHA/content with `git show --stat`, rerun appropriate checks against committed HEAD, and confirm a clean worktree. Report baseline/final SHAs and recovery command guidance without executing a destructive reset.

## Completion criteria and execution discipline

Finish all five implementation blocks plus baseline/inventory; a colored shell or one polished Baking screen is insufficient. Keep business logic in the existing operators/core modules. Do not rewrite remeshing/baking/export algorithms as part of this presentation migration. Add focused tests for binding dispatch, state cleanup, hierarchy/parity, and meaningful user behavior; avoid tests that merely duplicate implementation constants.

After each large block, report what is working, validation evidence, remaining failures, and commit SHA. If a required integration or GUI surface cannot be tested, record the exact limitation and complete independent work; do not describe the result as fully verified. At completion, report the files changed, all 13-section coverage, preference behavior, real Blender checks, known limitations, and verified commit state.
