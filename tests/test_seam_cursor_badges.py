"""Smoke test for seam-tool cursor callbacks and their labels."""

from pathlib import Path
import inspect
import sys


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))

from polygroups_generator import tools, ui


expected = {
    tools.VIEW3D_WST_polygroups_connect_vertex_seam: "draw_vertex_seam_cursor",
    tools.VIEW3D_WST_polygroups_edge_seam_path: "draw_edge_seam_cursor",
    tools.VIEW3D_WST_polygroups_smart_seams_generator: "draw_smart_seam_cursor",
    tools.VIEW3D_WST_polygroups_longitudinal_seam: "draw_longitudinal_seam_cursor",
    tools.VIEW3D_WST_polygroups_face_selector: "draw_face_selector_cursor",
    tools.VIEW3D_WST_polygroups_edge_seam_eraser: "draw_edge_seam_eraser_cursor",
}

for tool, callback_name in expected.items():
    assert tool.bl_cursor == "NONE", tool.bl_idname
    assert tool.draw_cursor.__name__ == callback_name, tool.bl_idname

for tool, operator_id in (
    (tools.VIEW3D_WST_polygroups_smart_seams_generator,
     "mesh.polygroups_smart_seams_generator_click"),
    (tools.VIEW3D_WST_polygroups_longitudinal_seam,
     "mesh.polygroups_longitudinal_seam_tool_click"),
):
    click_event = next(event for operator, event, _props in tool.bl_keymap
                       if operator == operator_id)
    assert click_event == {"type": "LEFTMOUSE", "value": "PRESS"}
    assert "Ctrl-click" not in tool.bl_description

smart_settings_source = inspect.getsource(
    tools.VIEW3D_WST_polygroups_smart_seams_generator.draw_settings
)
assert smart_settings_source.index("smart_seam_angle_limit") < smart_settings_source.index(
    "smart_seam_pin_generated"
)

island_settings_source = inspect.getsource(
    tools.VIEW3D_WST_polygroups_island_selector.draw_settings
)
assert island_settings_source.index("object.polygroups_smart_uv_unwrap") < island_settings_source.index(
    "island_selector_shape"
)
assert "small_island_selected_area" in island_settings_source

uv_panel_source = inspect.getsource(ui.VIEW3D_PT_polygroups_uv_preparation.draw)
assert "smart_seam_angle_limit" in uv_panel_source

face_keymap = tools.VIEW3D_WST_polygroups_face_selector.bl_keymap
more_event = next((event, props) for operator, event, props in face_keymap
                  if operator == "mesh.polygroups_face_selector_click"
                  and event["value"] == "PRESS"
                  and ("action", "MORE") in props["properties"])
double_click_event = next((event, props) for operator, event, props in face_keymap
                          if operator == "mesh.polygroups_face_selector_click"
                          and event["value"] == "DOUBLE_CLICK"
                          and ("action", "MORE") in props["properties"])
less_event = next((event, props) for operator, event, props in face_keymap
                  if operator == "mesh.polygroups_face_selector_click"
                  and ("action", "LESS") in props["properties"])
gesture_event = next(event for operator, event, _props in face_keymap
                     if operator == "mesh.polygroups_face_selector_gesture")
assert more_event[0] == {"type": "LEFTMOUSE", "value": "PRESS"}
assert double_click_event[0] == {"type": "LEFTMOUSE", "value": "DOUBLE_CLICK"}
assert less_event[0] == {"type": "LEFTMOUSE", "value": "PRESS", "ctrl": True}
assert gesture_event == {"type": "LEFTMOUSE", "value": "PRESS", "shift": True}

face_settings_source = inspect.getsource(
    tools.VIEW3D_WST_polygroups_face_selector.draw_settings
)
for operator_id in (
    "mesh.select_linked",
    "mesh.polygroups_delete_and_fill",
    "mesh.polygroups_mark_smart_angle_seams",
    "mesh.polygroups_pin_selected_seams",
    "mesh.polygroups_merge_small_islands",
    "mesh.polygroups_mark_longitudinal_seam",
    "mesh.polygroups_clear_inside_edges_seam",
):
    assert operator_id in face_settings_source

print("SEAM_CURSOR_BADGES_OK", flush=True)
