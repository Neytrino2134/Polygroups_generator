# Floating tool windows

Click the duplicate icon on an N-panel group header. It opens an independent
system window, with no new Blender editor. You may open several windows or use
**+ Group** to add group tabs to one window.

Tabs switch only the tool content. The window shell is kept alive, so its screen
position and dimensions do not jump or reload. Each tab also remembers its own
content scroll position while the window remains open. The active tab is joined
visually to the content area; inactive tabs use the raised surface color.
Every tab has an **×** button. Closing the active tab selects its nearest neighbor;
closing the last tab closes the floating window.

- Drag the title strip; resize using the bottom-right grip. The window has no
  native Windows frame. Its narrow scrollbar is drawn in the panel's theme.
- The window, buttons, fields, tabs and dropdowns have rounded corners. Windows
  clipping regions are refreshed when a control changes size, including when
  the window is collapsed or expanded. Corner radii are defined in `client.py`;
  `rounded.py` applies the clipping without adding another window frame.
- **−** collapses/restores the window. **◆ / ◇** toggles always-on-top.
- The panel is owned by the Blender window that opened it. With **◇** it stays
  above Blender while other Windows applications can cover it. **◆** additionally
  enables system-wide always-on-top. New and migrated windows start with **◇**.
- **×** closes the window. Clicking outside never closes it.
- The palette, fonts, spacing and control order are defined in code. There is no
  appearance customization dialog; older saved appearance overrides are ignored.
- Enum fields use the panel's own borderless dark dropdown, including hover,
  selection color and narrow themed scrollbar; no native white menu is shown.
- Text and numeric fields apply on **Enter** or **Apply**. Booleans and enum
  selections apply immediately. Interactive tools and Blender file selectors
  continue in the originating Blender window.
- Tabs, pin state and geometry are saved per group under Blender's user
  configuration directory, in `airetopo_windows`. These files contain UI
  preferences, not model or texture data.

## Runtime

The release includes `bin/airetopo_panel.exe`, a Windows x64 client containing
its own Python and Tkinter runtime. Users do not need to install Python or set a
path. **Development Python Fallback** is used only when that executable is absent.
The source client still uses only Python's standard library.
**Close All Floating Windows** closes the add-on's clients. Loading another
blend file or disabling the add-on closes them to avoid stale scene bindings.

## Custom interface development

`client.py` owns the appearance and widgets. Change `DEFAULT_STYLE` for the
default palette; change `build_shell` / `render_item` for a different shell or
control design. Existing group layout code remains the functional source in
`ui.py`; `core/window_schema.py` translates it into controls. New widget types
can be added there and in `render_item` without changing mesh operators.

Rows are presented as a vertical list so groups fit narrow tool windows.
Tools requiring
viewport interaction still run in Blender; the external client does not replace
Blender's own viewport, file browser, undo history or operator dialogs.

## Bridge and lifecycle

`operators/detached_groups.py` starts a loopback listener on an ephemeral port
and a client process with a per-window random authentication token. Client
messages reference server-generated control IDs and revisions. Arbitrary RNA
paths, operators or Python expressions are not accepted from the client.

Blender's main-thread timer captures the original 3D context, refreshes state,
checks enabled controls and dispatches existing operators. No background thread
touches `bpy`. Buffers and per-tick message counts are bounded. The child closes
on disconnect; add-on cleanup terminates only its own child processes.

## Verification

Run in a separate Blender instance:

```
blender --factory-startup --python tests/test_standalone_windows_ui.py
```

Then, using Python with Tkinter:

```
python tests/test_window_client.py
```

The Blender test writes its result and captured factory-state group schemas to
the system temp directory. Tests cover all 13 sections, RNA changes, operator
dispatch, stale request rejection, child cleanup, client widgets and appearance.

Build the bundled Windows x64 client with `standalone_ui/build_client.ps1`.
PyInstaller is a build dependency only; it is not required on user devices. The
script writes the executable and its SHA-256 file into `standalone_ui/bin`.
It also copies the redistribution notices for Python, Tcl and Tk
into `standalone_ui/bin/licenses` so the binary can be shipped with the add-on.
