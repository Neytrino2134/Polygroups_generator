"""Smoke test for seam-tool cursor callbacks and their labels."""

from pathlib import Path
import sys


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))

from polygroups_generator import tools


expected = {
    tools.VIEW3D_WST_polygroups_connect_vertex_seam: "draw_vertex_seam_cursor",
    tools.VIEW3D_WST_polygroups_edge_seam_path: "draw_edge_seam_cursor",
    tools.VIEW3D_WST_polygroups_smart_seams_generator: "draw_smart_seam_cursor",
    tools.VIEW3D_WST_polygroups_longitudinal_seam: "draw_longitudinal_seam_cursor",
    tools.VIEW3D_WST_polygroups_edge_seam_eraser: "draw_edge_seam_eraser_cursor",
}

for tool, callback_name in expected.items():
    assert tool.bl_cursor == "NONE", tool.bl_idname
    assert tool.draw_cursor.__name__ == callback_name, tool.bl_idname

print("SEAM_CURSOR_BADGES_OK", flush=True)
