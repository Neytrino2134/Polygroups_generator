"""PNG previews shared by sidebar buttons and workspace tools."""
from pathlib import Path

_FILES = {
    "draw_cutter_plane": "Draw_Plane.png",
    "draw_cutter_grid": "Draw_Volume.png",
    "draw_cutter_arc": "Draw_Arc.png",
    "draw_cutter_local_ring": "Draw_Ring.png",
    "draw_cutter_local_contour": "Draw_Contour.png",
    "draw_cutter_path": "Draw_PointPath.png",
    "draw_cutter_draw": "Draw_LinePath.png",
    "knife_seam": "Knife_Seam_tool.png",
    "quick_knife_seam": "QuckKnife_Seam_tool.png",
    "connect_vertex_seam": "Vertex_Seam_Path.png",
    "connect_vertex_seam_pin": "Vertex_Seam_Path_PIN.png",
    "edge_seam_path": "Edge_Seam_Path.png",
    "edge_seam_path_pin": "Edge_Seam_Path_PIN.png",
    "smart_seams_generator": "Smart_Seam_Generator.png",
    "smart_seams_generator_pin": "Smart_Seam_Generator_PIN.png",
    "longitudinal_seam": "Long_Seam_Generator.png",
    "longitudinal_seam_pin": "Long_Seam_Generator_PIN.png",
    "seam_eraser": "Seam_Eraser.png",
    "seam_eraser_pin": "Seam_Eraser_PIN.png",
    "edge_seam_eraser": "Edge_seam_Eraser.png",
    "edge_seam_eraser_pin": "Edge_seam_Eraser_PIN.png",
    "pin_vertices": "Pin_Vertices.png",
    "unpin_vertices": "Unpin_Clear_Pin_Vertices.png",
}
_previews = None
_handles = {}
_tool_icons = {}


def _load_tool_icon(path):
    # Registration runs with restricted bpy.data: load prebuilt geometry directly.
    import bpy
    geometry = path.parent / "toolbar" / (path.stem + ".dat")
    return bpy.app.icons.new_triangles_from_file(str(geometry))


def icon_kwargs(key, fallback="NONE"):
    if _previews is not None and key in _previews:
        return {"icon_value": _previews[key].icon_id}
    return {"icon": fallback}


def tool_icon(key, fallback):
    return _handles.get(key, fallback)


def register():
    import bpy.utils.previews
    from bl_ui import space_toolsystem_common
    global _previews
    unregister()
    _previews = bpy.utils.previews.new()
    for key, filename in _FILES.items():
        path = Path(__file__).with_name("icons") / filename
        try:
            preview = _previews.load(key, str(path), 'IMAGE')
            icon_id = _load_tool_icon(path)
        except Exception as exc:
            print(f"AI Retopo: cannot load icon {path}: {exc}")
            continue
        # Blender 5.2 resolves WorkSpaceTool string handles through this cache.
        # Seed only our namespaced entries; do not patch Blender's resolver.
        handle = "polygroups_generator.png." + key
        space_toolsystem_common._icon_cache[handle] = icon_id
        _tool_icons[key] = icon_id
        _handles[key] = handle


def update_icons(context):
    """Build and validate replacements before changing any live icon IDs."""
    import bpy
    import bpy.utils.previews
    from bl_ui import space_toolsystem_common
    from .scripts.build_toolbar_icons import build_icon

    global _previews
    root = Path(__file__).with_name("icons")
    replacements = bpy.utils.previews.new()
    geometry_ids = {}
    payloads = {}
    try:
        for key, filename in _FILES.items():
            source = root / filename
            payload = build_icon(source)
            payloads[source.stem] = payload
            count = (len(payload) - 8) // 18
            geometry_ids[key] = bpy.app.icons.new_triangles(
                (255, 255), payload[8:8 + count * 6], payload[8 + count * 6:])
            replacements.load(key, str(source), 'IMAGE', force_reload=True)
        output = root / "toolbar"
        output.mkdir(exist_ok=True)
        for stem, payload in payloads.items():
            (output / (stem + ".dat")).write_bytes(payload)
    except Exception:
        for icon_id in geometry_ids.values():
            bpy.app.icons.release(icon_id)
        bpy.utils.previews.remove(replacements)
        raise

    old_previews = _previews
    old_ids = tuple(_tool_icons.values())
    _previews = replacements
    _tool_icons.clear()
    _tool_icons.update(geometry_ids)
    for key, icon_id in geometry_ids.items():
        handle = "polygroups_generator.png." + key
        _handles[key] = handle
        space_toolsystem_common._icon_cache[handle] = icon_id
    for icon_id in old_ids:
        bpy.app.icons.release(icon_id)
    if old_previews is not None:
        bpy.utils.previews.remove(old_previews)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    scene = getattr(context, "scene", None)
    if scene is not None:
        from .tools import update_dynamic_seam_tool_icons
        update_dynamic_seam_tool_icons(scene.polygroups_seam_preparation_settings, context)
    return len(geometry_ids)


def unregister():
    import bpy
    import bpy.utils.previews
    from bl_ui import space_toolsystem_common
    global _previews
    # Remove cache references before releasing the geometry icons we own.
    for handle in _handles.values():
        space_toolsystem_common._icon_cache.pop(handle, None)
    _handles.clear()
    for icon_id in _tool_icons.values():
        bpy.app.icons.release(icon_id)
    _tool_icons.clear()
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
