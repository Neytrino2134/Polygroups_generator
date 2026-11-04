"""Show topology counts for a single selected mesh in the viewport."""

import blf
import bmesh
import bpy


_DRAW_HANDLE = None


def mesh_counts(obj):
    """Count the editable mesh, including unsaved Edit Mode changes."""
    mesh = obj.data
    if mesh.is_editmode:
        bm = bmesh.from_edit_mesh(mesh)
        faces = len(bm.faces)
        triangles = sum(len(face.verts) - 2 for face in bm.faces)
        return faces, triangles, len(bm.edges), len(bm.verts)
    faces = len(mesh.polygons)
    return faces, len(mesh.loops) - 2 * faces, len(mesh.edges), len(mesh.vertices)


def selected_meshes(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def selected_mesh(context):
    objects = context.selected_objects
    if len(objects) != 1 or objects[0].type != "MESH":
        return None
    return objects[0]


def total_counts(objects):
    """Faces, triangles, edges and vertices summed over all given mesh objects."""
    totals = [0, 0, 0, 0]
    for obj in objects:
        for index, value in enumerate(mesh_counts(obj)):
            totals[index] += value
    return tuple(totals)


def draw_object_stats():
    context = bpy.context
    space = context.space_data
    region = context.region
    if (space is None or space.type != "VIEW_3D" or region is None
            or not space.overlay.show_overlays or not space.overlay.show_text):
        return
    objects = selected_meshes(context)
    if not objects:
        return
    faces, triangles, edges, vertices = total_counts(objects)
    scale = context.preferences.system.ui_scale
    # Leave room for Blender's view name, object name and unit scale (and the view's extra line).
    top = 140 if not space.overlay.show_stats else 250
    x = 110 * scale
    y = region.height - top * scale
    color = context.preferences.themes[0].view_3d.space.text_hi
    blf.size(0, 12 * scale)
    blf.color(0, *color[:3], 1.0)
    blf.enable(0, blf.SHADOW)
    blf.shadow(0, 3, 0.0, 0.0, 0.0, 0.8)
    blf.shadow_offset(0, 1, -1)
    try:
        lines = [
            f"Faces: {faces:,} / Tris: {triangles:,}",
            f"Edges: {edges:,} / Vertices: {vertices:,}",
        ]
        if len(objects) > 1:
            lines.insert(0, f"Selected meshes: {len(objects)} (total)")
        for line in lines:
            blf.position(0, x, y, 0)
            blf.draw(0, line)
            y -= 18 * scale
    finally:
        blf.disable(0, blf.SHADOW)


def register():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            draw_object_stats, (), "WINDOW", "POST_PIXEL"
        )


def unregister():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
