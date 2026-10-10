# Progressive section folding

Sections 01–13 share a hierarchy discovered from their actual layout captures.
Fold ownership includes section visibility, topic properties, each tool's own
settings (including Mesh Finalization), inline triangle folds and Import/Batch
Import's stage bitmask. Newly added collapsible groups automatically participate.

`+` opens one visible depth, from sections to subsections to deeper groups. `−`
closes the deepest visible open depth first. Hidden children do not consume a
collapse click. Opening a closed ancestor clears latent child expansion so the
next floor opens on the next click. Fully open/closed hierarchies are no-ops.

Classic global buttons and keyboard commands operate across sections 01–13;
section header buttons operate only within that section. Custom adds section
header buttons. Custom/UI Panel keyboard commands operate within the selected
section, matching UI Panel's `+`/`−` buttons. Existing Session / Save and Restart /
Autosave fold states are independent of the 01–13 global hierarchy.

Keyboard inputs are NumPad +/− and the main keyboard's Shift+= / −. Preferences
still control whether hotkeys are enabled and their sidebar/viewport scope. UI
Panel also accepts these inputs when the pointer is inside that panel. Active
field editing, dropdowns and dragging retain their existing input handling;
Ctrl+NumPad +/− retains collection navigation.

Validation uses actual Blender capture/registered operators for all 13 sections
in Object, Edit and Sculpt, native event simulation for the Classic shortcuts,
and real clicks/keys for docked and floating UI Panel. See
`tests/test_hierarchical_folds_blender.py`, `tests/test_hierarchical_folds_ui.py`
and `tests/test_section_hotkeys_ui.py`.
