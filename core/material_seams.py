"""Shared material-boundary seam generation for manual and remesh actions."""
import bmesh


def mark_material_boundary_seams(obj):
    mesh = obj.data
    editing = mesh.is_editmode
    bm = bmesh.from_edit_mesh(mesh) if editing else bmesh.new()
    try:
        if not editing:
            bm.from_mesh(mesh)
        marked_count = 0
        for edge in bm.edges:
            if len({face.material_index for face in edge.link_faces}) > 1:
                if not edge.seam:
                    marked_count += 1
                edge.seam = True
        if editing:
            bmesh.update_edit_mesh(mesh)
        else:
            bm.to_mesh(mesh)
            mesh.update()
        return marked_count
    finally:
        if not editing:
            bm.free()
