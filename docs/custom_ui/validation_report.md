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
