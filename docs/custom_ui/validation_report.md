# Custom UI validation — 2026-10-09

Implemented the flat blue/cyan viewport interface across all 13 numbered stages,
using the existing functional builders. Classic / Custom selection, appearance,
active stage and geometry are Add-on Preferences. The normal Blender preference
save mechanism persists them. The original sidebar remains available through
the mode selector and the Custom launcher.

Recovery checkpoints: `b67e6c8` before implementation; `d4a2738` for the complete
shared schema, shell and workflow integration. The final polish/evidence commit
is identified by the accompanying completion message and `git log`.

## Runtime environment and evidence

Windows, Blender 5.2.0 LTS, build `fbe6228777e7`, using the installed executable
under `D:/Blender Library/Blender/daily/`. Tests used isolated factory-startup
scenes. New GUI tests explicitly disable preference autosaving; paid provider
requests and production asset overwrites were not performed.

| Check | Observed result |
| --- | --- |
| `test_custom_ui_blender.py` | Passed: 39 live captures (13 stages × Object/Edit/Sculpt), no capture errors, unique actionable IDs, stable bindings, no-selection cases, English/Russian labels, global search, inline parsing/clipboard logic, secret masking, scale and tiny-region bounds, registration cleanup. |
| `test_custom_ui_gpu.py` | Passed: actual POST_PIXEL GPU drawing of all 13 expanded stages, clipping and hit regions, default and narrow layouts, scales 1/1.5/2; captured real framebuffer images below. No continuously redrawn idle card was observed in the measured 1.5-second window. |
| `test_custom_ui_input.py` | Passed through Blender's actual event queue: `mesh.select_more` changed real edit-mesh selection; checkbox writes, numeric commit/Escape, slider rollback, group fold/unfold, custom enum choices, native Save As file-browser handoff/cancel, three Classic/Custom switch cycles without duplicate sessions. |
| `test_custom_ui_lifecycle.py` | Passed: two independent VIEW_3D sessions, idempotent registration, temporary blend save/load cleanup and restart, disable/re-enable, draw-handle and timer removal. |
| Existing `test_panel_search.py` | `PANEL_SEARCH_TESTS_PASSED`. |
| Existing `test_panel_visibility_stages.py` | `PANEL_VISIBILITY_STAGES_OK`. |
| Existing `test_panel_defaults.py` | `PANEL_DEFAULTS_OK`. |
| Existing `test_smart_cage_blender.py` | `SMART_CAGE_TESTS_OK`: real cage generation/diagnostics and baking validation. |
| Existing `test_unity_gltf_modes_blender.py` | `UNITY_GLTF_MODES_TEST_PASSED`: combined embedded output and separate LOD outputs sharing real external textures; mesh/image counts, data URIs, files, reports, selection and transform restoration checked. |
| Existing `test_standalone_windows_ui.py` | Passed: 70 detached group schemas, real bundled client process/window ownership, RNA editing, operator dispatch, stale-action rejection and cleanup. |

The first extended GLTF run also exercised the enabled render pipeline: each
mode produced seven image renders and one 300-frame video in temporary asset
folders, and passed its output/transform assertions. The dedicated GLTF fixture
now explicitly disables autosave and extra renders so its scope is reproducible
with an unsaved factory scene. The detached-window fixture was updated from a
legacy group name to the current `topic_seam_prep_0` identifier. Add-on defaults
and business algorithms were not changed by these fixture corrections.

`control_inventory.json` contains the 39 live snapshots and 1,009 static UI call
sites with source locations and conditional paths. Static analysis complements
live snapshots for branches requiring assets or optional integrations; it does
not prove that every such branch was executed. Folded manual subpanels are
captured through read-only proxies and remain folded in the rendered card until
expanded or matched by search. Scene settings are not changed during capture.

`gpu_validation.json` records per-stage CPU wall times for capture, layout and
draw dispatch. The measured draw-dispatch samples were approximately 2–5 ms
in the validation run, with zero idle redraws in the sampled 1.5 seconds. These
are CPU observations for this scene, not GPU timings, FPS measurements or a
claimed improvement over Classic.

## Actual screenshots

These are framebuffer captures of the implemented Blender interface, rather
than design mockups.

- [01 Import](gpu_section_01.png)
- [04 Seam Preparation](gpu_section_04.png)
- [10 Baking](gpu_section_10.png)
- [13 Render](gpu_section_13.png)
- [Narrow layout at scale 1.5](gpu_narrow_scale_1_5.png)
- [Scale 2](gpu_scale_2.png)

## Practical limits

Colors, unit-aware typed values, object searches, passwords, array editors and
complex palette lists use full native Blender popups. File browsers and tool
dialogs retain existing Blender behavior. The flat shell uses original vector
marks rather than an imported icon library. No cage illustration or diagnostic
number was fabricated to match the reference image.

Real paid AI requests and installed third-party remesher/packer execution were
not exercised; their existing controls and dispatch paths are reused. The test
matrix does not exhaust every asset-specific branch, every OS window layout,
or switching during every possible long-running third-party job. Independent
viewport sessions and file-load cleanup were tested directly. Operational jobs
remain owned by the original modules, outside Custom UI cleanup.

Blender startup emitted an existing Wintab driver warning and warnings about
other installed add-ons lacking `bl_info`; the explicit UI pass logs and output
assertions were checked rather than treating process exit alone as a GUI pass.

## Verification and recovery

Run the commands in `README.md`. The GUI pass markers are in `gpu_test.log`,
`input_test.log`, `lifecycle_test.log`, and the standalone test's temp log. Logs
are ignored by Git; this report and the captured images are the saved evidence.
Set `AIRETOPO_UI_VALIDATION_OUTPUT` to a temporary directory when rerunning the
new UI tests without replacing committed evidence files.

Before any recovery, preserve subsequent work with a commit or backup. Inspect
`git show b67e6c8` for the baseline and `git show d4a2738` for the implementation
checkpoint. To inspect the baseline without changing this checkout, use a
separate Git worktree at that revision. No destructive reset or remote push was
performed.

## Viewport maximize and crash repair (2026-10-09)

The supplied crash log identifies EXCEPTION_ACCESS_VIOLATION in
blender::ED_area_tag_redraw, called by custom_ui/lifecycle.py cancel().
The old implementation kept an Area wrapper after Blender replaced that Area.
Sessions now use the surviving SpaceView3D identity and resolve current native
Area/Region wrappers before input, deferred dispatch and redraw. Hidden editors
remain parked during maximization; deleted spaces and closed windows are cleaned
up using live Blender data, without touching stale wrappers.

Real Blender 5.2 validation: test_custom_ui_maximize.py passed 12 alternating
screen.screen_full_area(use_hide_panels=False) transitions (the Ctrl+Space
operator), asserting the screen really changed and the same rendered session and
Baking section survived. This tests the operator directly, not physical keyboard
input. The lifecycle regression also passed independent viewports, file load and
addon disable/re-enable. Preferences were not saved during these tests.
The restored panel also passed simulated mouse clicks on collapse/reopen,
confirming its modal input handler remained active. The full input regression
passed mesh operator dispatch, checkbox/numeric editing, slider rollback, groups,
enum dropdowns, native file-browser cancel and Classic/Custom switching.

## Docked / floating presentation (2026-10-09)

Added default DOCKED placement in the actual AI Retopo N-panel, with native
Blender controls and 13 icon-only stage selectors with descriptive tooltips.
FLOATING retains the blue/cyan GPU surface and saved geometry. Detach / Dock
preserve the active stage and existing session. Narrow floating navigation uses
an icon rail instead of hiding stages behind a section menu.

Real Blender GUI: test_custom_ui_docking.py passed all 13 sidebar content
captures, detach/dock state retention and 13 interactive compact navigation
hits. test_custom_ui_maximize.py passed 12 maximize/restore transitions plus
collapse/reopen input after restoration. The existing floating tests explicitly
select FLOATING, since Custom placement now defaults to DOCKED.
The existing input regression and 39 mode/stage schema captures also passed
on the final implementation (CUSTOM_UI_INPUT_TESTS_PASSED and
CUSTOM_UI_BLENDER_TESTS_PASSED).

## Three interface modes and GPU docking (2026-10-09)

This supersedes the preceding presentation description. Interface now exposes
CLASSIC, CUSTOM and UI_PANEL. CUSTOM preserves the compact native N-panel.
UI_PANEL uses the same blue/cyan GPU renderer both when docked and detached.
Dock anchors that renderer at the right edge and fills the available height;
Detach restores its saved floating geometry. Docked movement/resize handles are
removed. Docked width, placement and mode are persisted in addon preferences.

Real GUI regression passed native Custom captures for all 13 sections, three
mode availability, right-edge geometry at different viewport sizes, actual
maximize/restore while docked, simulated Detach and Dock clicks, and simulated
free dragging after detach. The native modal context is rebound to the live
Area/Region after screen transitions before invoking Blender operators.
The real framebuffer capture is ui_panel_docked.png.
Final validation also passed CUSTOM_UI_INPUT_TESTS_PASSED,
CUSTOM_UI_MAXIMIZE_TESTS_PASSED (12 transitions and post-restore clicks),
CUSTOM_UI_LIFECYCLE_TESTS_PASSED and CUSTOM_UI_BLENDER_TESTS_PASSED.

## Anchored tooltips (2026-10-09)

GPU tooltips anchor above the current hovered hit rectangle with a 12 px scaled
gap, rather than following the cursor. They clamp horizontally to the viewport;
when the upper edge has insufficient room, placement falls back below or beside
the control. Candidates covering the cursor are rejected; impossible placements
are suppressed. Stale hover descriptions are not drawn after layout changes.

CUSTOM_UI_BLENDER_TESTS_PASSED includes above-control, viewport-edge and cursor
exclusion checks at scales 1, 1.5 and 2. CUSTOM_UI_TOOLTIP_TESTS_PASSED verifies
actual GPU tooltip placement after simulated hover in docked and floating modes.

## Docked top clearance (2026-10-09)

Docked UI Panel reserves 100 physical pixels at the top of the WINDOW region
for viewport toolbars and overlays. Its available height is reduced accordingly;
floating geometry is unchanged. Very small regions clamp safely. The real GUI
docking regression passed, including 100 px geometry checks before and after
maximize/restore, Detach/Dock clicks and free dragging.

Docked top clearance increased to 200 physical pixels at the user's request.
The real Blender docking regression passed the updated geometry checks,
maximize/restore, Dock/Detach and floating movement (supersedes 100 px above).

## Per-editor launch and placement (2026-10-09)

Docked right clearance is now 22 physical pixels (top remains 200 px).
Open UI Panel always opens/reopens docked in its invoking editor. Docking is
stored on each Session, rather than a shared addon preference. Dock/Detach
modify only that session and never invoke a panel in a different editor.
The timer maintains existing sessions; it can create a new session only for an
explicitly requested editor key. Switching to UI Panel from a VIEW_3D schedules
that editor alone; appearance changes, registration and file-load callbacks do
not launch panels across the workspace. File-load tests now reopen explicitly.

Real GUI: CUSTOM_UI_VIEWPORT_SCOPE_TESTS_PASSED checks a two-editor split,
origin-only opening, independent placements, Open resetting only its own card to
docked, 22 px right clearance and no automatic resurrection of a closed card.
Docking, input, lifecycle and 12 maximize/restore regressions also passed.

## Relocate project with used textures (2026-10-10)

Added wm.airetopo_relocate_project to the shared Autosave and Restart section.
Custom now has an explicit session-section action; UI Panel has an Autosave
header button. All modes expose the same relocation operator. Output is a new
or empty directory, with collision-free per-image folders and relative paths.
Image reachability starts at active material outputs on mesh face-used slots,
traverses groups and excludes disconnected images/unused material slots.

Real Blender 5.2: test_relocate_project_blender.py passed saved and unsaved
project variants, clean source-byte copies, packed images, generated/edited
pixel export, UDIM sets, nested material groups, missing-file preflight and
reopening after the original texture directory was renamed away. It also
verified the new operator in Classic/Custom/UI Panel captures. Linked IDs are
explicitly rejected; no paid services or unrelated files were touched.

Real GUI: test_relocate_project_restart.py launched an actual second factory
Blender, checked its new .blend path and loaded texture pixels, retained the
production ready handshake, and verified the original test Blender exited.
PROJECT_RELOCATION_RESTART_TESTS_PASSED was recorded. The docking regression
also passed a real Autosave header click and relocation-button availability.
Sequence/movie code paths are implemented but were not exercised with video.

## Save / autosave subgroups (2026-10-10)

Autosave and Restart now contains independently collapsible Save and Restart
and Autosave groups in all three modes. Relocation, regular-save status/actions
and existing developer restart controls are in Save and Restart. Autosave
status, latest autosave actions, recovery and recent autosaves are in Autosave.
The GPU capture adapter now supports preference-owned group IDs.

The relocation dialog explicitly labels its rename field Blend Filename / Имя
файла .blend; it saves the destination with that name and adds .blend if needed.
The original file keeps its name. Runtime tests passed subgroup membership in
Classic/Custom/UI Panel, real independent collapse/reopen clicks, project rename
and texture relocation; CUSTOM_UI_BLENDER_TESTS_PASSED,
PROJECT_RELOCATION_TESTS_PASSED and CUSTOM_UI_DOCKING_TESTS_PASSED.

## Native fold regression repair (2026-10-10)

Fixed an indentation error: autosave_group was initialized only inside the open
Save and Restart branch. Closing Save and Restart in native Classic/Custom
could therefore raise UnboundLocalError and abort the rest of panel drawing.
Autosave initialization is now a sibling branch. SESSION_GROUP_VISIBILITY_TESTS_PASSED
covers all four Save/Autosave fold combinations on the native draw path in
Classic and Custom and confirms all 13 Classic stage headers remain present.

## Workflow search scope and pinned session card (2026-10-10)

Classic keeps Autosave and Restart above search results, outside the search
filter, preserving its independent parent and subgroup fold states. Workflow
search still probes exactly sections 1–13. Custom's session tab stays accessible.
UI Panel's session/settings view ignores the retained workflow query when drawing
or measuring its content. Submitting a nonempty search from that view switches to
the thirteen workflow search sections; returning to Autosave retains the query
without filtering the session view or its actions.

Blender 5.2 factory-startup checks passed: PANEL_SEARCH_SCOPE_TESTS_PASSED covers
EN/RU queries, matching/missing queries, open/closed session cards, exactly thirteen
probed sections, unchanged stored workflow folds, native Custom session content,
UI Panel content measurement and actual search operator dispatch.
PANEL_SEARCH_TESTS_PASSED, SESSION_GROUP_VISIBILITY_TESTS_PASSED and
CUSTOM_UI_BLENDER_TESTS_PASSED also passed.
