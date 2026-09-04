"""Run in a separate Blender window with --factory-startup --enable-event-simulate --python.

Results are written to the system temp directory; this test exits its Blender instance.
"""

import sys
import tempfile
import traceback
from pathlib import Path

import bpy
import addon_utils

bpy.context.preferences.view.show_splash = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
LOG = Path(tempfile.gettempdir()) / "airetopo_hotkey_ui_test.log"
LOG.write_text("Starting UI key dispatch test\n")


def log(text):
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(text + "\n")


def run():
    addon_utils.enable(ROOT.name, default_set=True)
    from polygroups_generator.properties import SECTION_VISIBILITY_PROPERTIES as sections
    from polygroups_generator import hotkeys
    from polygroups_generator.operators.section_hotkeys import PENDING
    context = bpy.context
    window = context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    space = area.spaces.active
    space.show_region_ui = True
    preferences = context.preferences.addons[ROOT.name].preferences
    preferences.enable_section_number_hotkeys = False
    settings = context.scene.airetopo_panel_visibility_settings
    for prop in sections:
        setattr(settings, prop, False)
    yield 0.5
    sidebar = next(region for region in area.regions if region.type == "UI")
    sidebar.active_panel_category = "AI Retopo"
    yield 0.5
    x, y = sidebar.x + sidebar.width // 2, sidebar.y + sidebar.height - 70
    log(f"Sidebar coords: {x}, {y}; category {sidebar.active_panel_category}")
    def press(key, char="", **kwargs):
        window.event_simulate(type=key, value="PRESS", unicode=char, x=x, y=y, **kwargs)

    def release(key):
        window.event_simulate(type=key, value="RELEASE", x=x, y=y)

    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    yield 0.2
    press("TWO", "2")
    release("TWO")
    yield 0.2
    assert not settings.show_batch_import_section, "Disabled option intercepted 2"
    preferences.enable_section_number_hotkeys = True
    yield 0.3
    press("TWO", "2")
    release("TWO")
    yield 0.3
    assert settings.show_batch_import_section, "Sidebar did not receive 2"
    assert space.show_region_ui and sidebar.active_panel_category == "AI Retopo"
    log("Sidebar toggle passed")
    press("ONE", "1")
    release("ONE")
    yield 0.1
    assert not settings.show_import_section
    press("ONE", "1")
    release("ONE")
    yield 0.3
    assert settings.show_ai_generation_section and not settings.show_import_section, "11 failed"
    press("ONE", "1")
    release("ONE")
    yield 0.5
    assert settings.show_import_section, "Single 1 timeout failed"
    press("ONE", "1")
    release("ONE")
    yield 0.1
    press("ESC")
    release("ESC")
    yield 0.5
    assert settings.show_import_section and not PENDING, "Escape did not cancel"
    for digit, prop in (("ZERO", "show_baking_section"), ("TWO", "show_mesh_finalization_section"),
                        ("THREE", "show_render_section")):
        press("ONE", "1")
        release("ONE")
        yield 0.1
        press(digit, {"ZERO": "0", "TWO": "2", "THREE": "3"}[digit])
        release(digit)
        yield 0.2
        assert getattr(settings, prop), f"Sequence 1 + {digit} failed"
    log("Single/double digits and Escape passed")

    viewport = next(region for region in area.regions if region.type == "WINDOW")
    x, y = viewport.x + viewport.width // 2, viewport.y + viewport.height // 2
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    yield 0.2
    before = settings.show_batch_import_section
    press("TWO", "2")
    release("TWO")
    yield 0.2
    assert settings.show_batch_import_section == before, "Sidebar scope leaked into viewport"
    preferences.section_hotkey_scope = "VIEWPORT"
    yield 0.3
    press("TWO", "2")
    release("TWO")
    yield 0.2
    assert settings.show_batch_import_section != before, "Viewport scope failed"
    with context.temp_override(window=window, area=area, region=viewport):
        bpy.ops.object.mode_set(mode="EDIT")
    yield 0.3
    select_mode = tuple(context.tool_settings.mesh_select_mode)
    before = settings.show_model_preparation_section
    press("THREE", "3")
    release("THREE")
    yield 0.2
    assert settings.show_model_preparation_section != before, "Edit Mode shortcut priority failed"
    assert tuple(context.tool_settings.mesh_select_mode) == select_mode, "Both Blender and addon handled 3"
    with context.temp_override(window=window, area=area, region=viewport):
        bpy.ops.object.mode_set(mode="OBJECT")
    log("Viewport and Edit Mode scope passed")

    # Transform modal operators must keep numerical input.
    obj = context.active_object
    before = settings.show_model_preparation_section
    original = obj.location.x
    press("G", "g")
    release("G")
    yield 0.1
    press("X", "x")
    release("X")
    press("THREE", "3")
    release("THREE")
    press("RET", "\r")
    release("RET")
    yield 0.3
    assert abs(obj.location.x - original - 3) < 0.001, "Transform numeric input failed"
    assert settings.show_model_preparation_section == before, "Transform input toggled section"
    log("Transform numeric input passed")

    # Number shortcuts must never open/close the sidebar or switch its category.
    space.show_region_ui = False
    yield 0.3
    before = settings.show_batch_import_section
    press("TWO", "2")
    release("TWO")
    yield 0.3
    assert settings.show_batch_import_section != before
    assert not space.show_region_ui, "Section shortcut opened the N-panel"
    space.show_region_ui = True
    yield 0.3
    sidebar.active_panel_category = "Item"
    yield 0.2
    before = settings.show_batch_import_section
    press("TWO", "2")
    release("TWO")
    yield 0.3
    assert settings.show_batch_import_section != before
    assert space.show_region_ui and sidebar.active_panel_category == "Item", "Shortcut switched sidebar category"
    sidebar.active_panel_category = "AI Retopo"
    log("Sidebar visibility and active category preserved")

    settings.single_section_mode = True
    press("FIVE", "5")
    release("FIVE")
    yield 0.2
    assert [getattr(settings, name) for name in sections] == [i == 4 for i in range(13)]
    press("FIVE", "5")
    release("FIVE")
    yield 0.2
    assert not any(getattr(settings, name) for name in sections)
    settings.single_section_mode = False
    log("Single Mode passed")

    bpy.types.Scene.test_section_text = bpy.props.StringProperty(default="")
    bpy.types.Scene.test_section_number = bpy.props.FloatProperty(default=0.0)
    class TestInput(bpy.types.Operator):
        bl_idname = "wm.test_section_input"
        bl_label = "Test input"
        field: bpy.props.StringProperty()
        def draw(self, ctx):
            row = self.layout.row()
            row.activate_init = True
            row.prop(ctx.scene, self.field)
        def invoke(self, ctx, event):
            return ctx.window_manager.invoke_props_dialog(self)
        def execute(self, ctx):
            return {"FINISHED"}
    bpy.utils.register_class(TestInput)
    for field, keys, expected in (
        ("test_section_text", (("ONE", "1"), ("TWO", "2"), ("THREE", "3")), "123"),
        ("test_section_number", (("FOUR", "4"), ("TWO", "2")), 42.0),
    ):
        before = [getattr(settings, name) for name in sections]
        with context.temp_override(window=window, area=area, region=viewport):
            bpy.ops.wm.test_section_input("INVOKE_DEFAULT", field=field)
        yield 0.3
        press("A", ctrl=True)
        release("A")
        for key, char in keys:
            press(key, char)
            release(key)
        press("RET", "\r")
        release("RET")
        yield 0.2
        press("RET", "\r")
        release("RET")
        yield 0.2
        assert getattr(context.scene, field) == expected, f"Field input failed: {field}={getattr(context.scene, field)}"
        assert before == [getattr(settings, name) for name in sections], "Field typing toggled sections"
    bpy.utils.unregister_class(TestInput)
    del bpy.types.Scene.test_section_text
    del bpy.types.Scene.test_section_number
    log("Text and numeric field input passed")

    # Re-registering preferences must not accumulate shortcuts.
    count = len(hotkeys.KEYMAP_ITEMS)
    hotkeys.refresh_keymaps()
    assert len(hotkeys.KEYMAP_ITEMS) == count
    press("ONE", "1")
    release("ONE")
    yield 0.1
    assert PENDING
    preferences.enable_section_number_hotkeys = False
    yield 0.5
    assert not PENDING
    assert not any(item.idname == "wm.airetopo_section_number" for km, item in hotkeys.KEYMAP_ITEMS)
    addon_utils.disable(ROOT.name, default_set=True)
    log("SECTION_HOTKEY_UI_TESTS_PASSED")


steps = run()


def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        log(traceback.format_exc())
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(tick, first_interval=1)
