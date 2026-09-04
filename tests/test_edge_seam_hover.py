"""Blender background regression for dense-mesh hover caching and invalidation."""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy, bmesh, addon_utils
from mathutils import Matrix
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)
from polygroups_generator.operators.edge_seam_path import hovered_vertex
from polygroups_generator.operators.connect_vertex_seam import edit_meshes
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('Dense grid')
bm=bmesh.new()
bmesh.ops.create_grid(bm, x_segments=300, y_segments=300, size=2)
bm.to_mesh(mesh)
bm.free()
obj=bpy.data.objects.new('Dense grid',mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active=obj
camera=bpy.data.objects.new('View', bpy.data.cameras.new('View'))
bpy.context.collection.objects.link(camera)
camera.matrix_world=Matrix.Translation((0,0,5))
camera.data.type='ORTHO'
camera.data.ortho_scale=5
bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get()
view=camera.matrix_world.inverted()
projection=camera.calc_matrix_camera(dg, x=1000, y=1000)
bpy.ops.object.mode_set(mode='EDIT')
ctx=SimpleNamespace(region=SimpleNamespace(width=1000,height=1000,x=0,y=0),
 region_data=SimpleNamespace(view_matrix=view,perspective_matrix=projection@view,is_perspective=False,view_perspective='ORTHO'),
 scene=bpy.context.scene,objects_in_mode_unique_data=bpy.context.objects_in_mode_unique_data,
 evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get,
 space_data=SimpleNamespace(shading=SimpleNamespace(type='SOLID',show_xray=False)))

bpy.context.view_layer.update()
from polygroups_generator.operators.edge_seam_path import _HOVER_TREES, clear_hover_cache, invalidate_hover_geometry
assert hovered_vertex(ctx,(500,500),12) is not None
cached_tree = next(iter(_HOVER_TREES.values()))[1]
for i in range(20):
    assert hovered_vertex(ctx,(500+i%3,500),12) is not None
    assert next(iter(_HOVER_TREES.values()))[1] is cached_tree
bm = bmesh.from_edit_mesh(mesh)
flags = [v.select for v in bm.verts]
assert hovered_vertex(ctx,(500,500),12) is not None
assert flags == [v.select for v in bm.verts]
# Same vertex count, different coordinates: invalidation must use geometry events.
for vert in bm.verts:
    vert.co.x += 10
bmesh.update_edit_mesh(mesh)
bpy.context.view_layer.update()
assert not _HOVER_TREES, 'Geometry update did not invalidate hover cache'
assert hovered_vertex(ctx,(500,500),12) is None
assert next(iter(_HOVER_TREES.values()))[1] is not cached_tree
addon_utils.disable(root.name, default_set=True)
assert not _HOVER_TREES
assert clear_hover_cache not in bpy.app.handlers.undo_post
assert clear_hover_cache not in bpy.app.handlers.redo_post
assert clear_hover_cache not in bpy.app.handlers.load_post
assert invalidate_hover_geometry not in bpy.app.handlers.depsgraph_update_post
print('EDGE_SEAM_HOVER_TESTS_PASSED', flush=True)
