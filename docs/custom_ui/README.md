# Interface Modes

Choose **Classic**, **Custom**, or **UI Panel** in the AI Retopo sidebar or addon
preferences. Classic is the original sidebar; Custom is the compact native
sidebar with icon navigation. UI Panel is the flat blue/cyan GPU interface.
**Open UI Panel** opens or restores a docked card only in the invoking 3D editor.
Blender's normal preference saving controls persistence of the selected mode.

The left navigation contains all 13 workflow stages. Click group headings to
fold their children; **All** and **Fold** affect the current stage. **Search**
searches every stage and temporarily reveals matching branches without changing
saved group states. Empty the search text to return to the selected stage.
**Session / Settings** contains the existing autosave/restart, notices and global
settings, plus appearance controls. Narrow cards use an icon-only navigation
column with stage names in tooltips.

UI Panel starts docked to the right of the viewport, leaving 200 px above and
22 px at the right, occupying its available
height. **Detach** in the title enables free movement and resizing; **Dock**
anchors the same card to the right again. Its colors, groups, controls and active
stage remain the same. Docked width is configurable in addon preferences.
When detached, drag the title to move the card, drag the bottom-right corner to resize, and use
the mouse wheel to scroll. Position, size and active workflow stage are add-on
preferences; scroll offsets are remembered per stage while the card is open.
The minus button collapses the card, and the cross closes it in the current
viewport. Each viewport can host its own session.

Checkboxes and enum choices apply immediately. Text and simple numeric fields
edit inside the card: Enter commits, Escape cancels, Ctrl+A selects all,
Ctrl+C/X/V supports the clipboard, and arrow/Home/End keys move the cursor.
Sliders stage their value until mouse release; Escape cancels the drag. Blender
handles unit-aware typed values, colors, object searches, passwords, array
editors and complex palette lists in native popups. File selectors and tool
dialogs retain their existing Blender behavior.

The visual design follows the user's second reference: flat dark surfaces,
blue primary buttons, cyan focus and selection markers, thin borders, and
moderate rounding. Scale, accent, brightness and rounding are configurable.
These settings do not recolor Blender's global theme.

## Architecture

`custom_ui/schema.py` records the existing `ui.py` draw builders into a tree.
The `_CUSTOM_CAPTURING` branch of `draw_collapsible_box` records stable groups
and captures folded children without modifying their RNA state. Rows, columns,
boxes, enable states, icons, property metadata, dynamic enum choices, search
fields, palette lists, and operator parameters are retained. The renderer
applies folding and search to this tree. No mesh operation is implemented in
the renderer.

`custom_ui/lifecycle.py` owns sessions per Blender window/area and a POST_PIXEL
handler. A main-thread timer refreshes live bindings at 2 Hz and requests a
redraw only when content changes or a tooltip becomes visible. Pointer hover,
drag and scroll request redraw directly. Deferred actions recheck the scene,
control identity, parameters, enabled state and operator poll before dispatch
under the originating VIEW_3D WINDOW context. Loading a file, disabling the
add-on or changing mode closes sessions and clears bindings.

`custom_ui/events.py` stages inline values; `renderer.py` lays out and draws
flat GPU surfaces and BLF text; `theme.py` owns palette tokens. Complex controls
use native editors, retaining Blender's RNA validation rather than reducing
their capabilities. Render initialization failures restore Classic mode.

Existing menus, hotkeys, viewport assists, and the detached Tkinter client are
kept. Its protocol and `core/window_schema.py` are unchanged; the in-process
tree is a separate adapter over the same draw builders, avoiding a protocol
migration for existing external windows.

## Validation commands

Use the installed Blender 5.2 executable with:

```text
--background --factory-startup --python-exit-code 1 --python tests/test_custom_ui_blender.py
--factory-startup --python tests/test_custom_ui_gpu.py
--factory-startup --enable-event-simulate --python tests/test_custom_ui_input.py
--factory-startup --python tests/test_custom_ui_lifecycle.py
```

GUI tests write explicit pass/failure results to `gpu_test.log`,
`input_test.log` and `lifecycle_test.log` in this directory. Their process exit code alone
does not indicate success. They use isolated factory-startup scenes and close
their own Blender instance. No user preference save, paid AI generation, or
production asset overwrite is performed.

## Custom sidebar and UI Panel

Custom mode lives in the AI Retopo N-panel. Its compact icon column
selects the 13 workflow stages; hover an icon for its numbered stage name.
The sidebar uses native Blender RNA controls and group boxes, inheriting the
Blender theme. Open UI Panel switches to the separate blue/cyan GPU mode.
Dock anchors that GPU panel to the viewport right edge, and Detach frees it.
Neither action switches it to native Blender controls. Narrow floating windows use a
compact icon column; wide windows keep numbered text navigation. Section,
scene fold settings and the floating window geometry survive placement changes.
Dock/Detach are local to each open panel. Appearance preferences never open additional panels.
