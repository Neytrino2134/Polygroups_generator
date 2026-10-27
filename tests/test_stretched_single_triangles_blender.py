"""Singleton UV outlier center-weld, protections, UI and both batch routes."""
import sys
from pathlib import Path
import addon_utils
import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.mesh_fold_repair import repair_local_folds
from polygroups_generator.operators.import_queue import ImportQueue
from polygroups_generator.operators.phase2_processing import Phase2Queue


def fixture(scale=1.0, huge=True):
    bm=bmesh.new()
    coordinates=[(-1,-1,1),(1,-1,1),(0,1,1),(-1,-1,0),(1,-1,0),(0,1,0)]
    verts=[bm.verts.new(Vector(co)*scale) for co in coordinates]
    top=bm.faces.new([verts[i] for i in (0,1,2)])
    bm.faces.new([verts[i] for i in (5,4,3)])
    for corners in ((0,3,4,1),(1,4,5,2),(2,5,3,0)):
        bm.faces.new([verts[i] for i in corners])
    for name in ('UVMap','SecondUV'):
        layer=bm.loops.layers.uv.new(name)
        for face in bm.faces:
            points=((0,0),(1,0),(.5,1)) if len(face.verts)==3 else ((0,0),(1,0),(1,1),(0,1))
            factor=1 if face==top and huge else .005
            for loop,xy in zip(face.loops,points):
                loop[layer].uv=Vector(xy)*factor
    bm.normal_update()
    for seq in (bm.faces,bm.edges,bm.verts):seq.index_update()
    return bm,top


for scale in (.001,1,1000):
    bm,top=fixture(scale)
    center=sum((v.co for v in top.verts),Vector((0,0,0)))/3
    other={v:tuple(v.co) for v in bm.verts if v not in set(top.verts)}
    result=repair_local_folds(bm,fix_folds=False,fix_degenerate=False,fix_stretched_triangles=True)
    assert result['stretched']==1 and result['affected']=={0},result
    assert (len(bm.verts),len(bm.edges),len(bm.faces))==(4,6,4)
    assert min((v.co-center).length for v in bm.verts)<scale*1e-6
    assert all(tuple(v.co)==co for v,co in other.items())
    assert all(e.is_manifold for e in bm.edges)
    assert repair_local_folds(bm,fix_stretched_triangles=True)['stretched']==0
    bm.free()

for protection in ('disabled','modest_uv','uv_pin','edge_pin','hidden','unselected','connected_uv','high_threshold','open'):
    bm,top=fixture(huge=protection!='modest_uv')
    if protection=='uv_pin':top.loops[0][bm.loops.layers.uv.active].pin_uv=True
    if protection=='edge_pin':
        pin=bm.edges.layers.int.new('polygroups_pin_edge');top.edges[0][pin]=1
    if protection=='hidden':next(f for f in top.edges[0].link_faces if f!=top).hide_set(True)
    if protection=='unselected':
        for f in bm.faces:f.select_set(False)
    if protection=='connected_uv':
        edge=top.edges[0];outside=next(f for f in edge.link_faces if f!=top)
        for layer in bm.loops.layers.uv.values():
            for vertex in edge.verts:
                next(l for l in outside.loops if l.vert==vertex)[layer].uv=next(l[layer].uv for l in top.loops if l.vert==vertex)
    if protection=='open':
        bottom=next(f for f in bm.faces if f!=top and len(f.verts)==3)
        bmesh.ops.delete(bm,geom=[bottom],context='FACES_ONLY')
    result=repair_local_folds(bm,fix_folds=False,fix_degenerate=False,
        fix_stretched_triangles=protection!='disabled',selected_only=protection=='unselected',
        stretched_triangle_ratio=10000 if protection=='high_threshold' else 50)
    assert result['stretched']==0,(protection,result)
    assert top.is_valid
    bm.free()

context=bpy.context
settings=context.scene.polygroups_model_preparation_settings
assert settings.fold_repair_stretched_triangles and settings.fold_repair_stretch_ratio==50


def object_fixture(name):
    bm,top=fixture()
    mesh=bpy.data.meshes.new(name);bm.to_mesh(mesh);bm.free()
    obj=bpy.data.objects.new(name,mesh)
    col=bpy.data.collections.new('Triangle fixture');context.scene.collection.children.link(col);col.objects.link(obj)
    context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);context.view_layer.objects.active=obj
    return obj,col


obj,col=object_fixture('Manual triangle')
positions=[tuple(v.co) for v in obj.data.vertices]
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT',fix_folds=False,fix_degenerate=False)=={'FINISHED'}
edit=bmesh.from_edit_mesh(obj.data);edit.faces.index_update()
assert {f.index for f in edit.faces if f.select}=={0}
assert [tuple(v.co) for v in edit.verts]==positions
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',fix_folds=False,fix_degenerate=False)=={'FINISHED'}
assert len(bmesh.from_edit_mesh(obj.data).verts)==4
bpy.ops.object.mode_set(mode='OBJECT')

for route in ('IMPORT','PHASE2'):
    for enabled in (True,False):
        obj,col=object_fixture('Retopo_02_Highpoly_Generated.999')
        settings.fold_repair_stretched_triangles=enabled
        if route=='IMPORT':
            queue=ImportQueue.__new__(ImportQueue)
            queue.settings=settings;queue.batch_stages=True;queue.pass_method='QUAD';queue.pass_number=2
            queue.owned_meshes=set()
            settings.batch_first_geometry_repair=True
            queue.repair_completed_pass_geometry(context,[obj])
        else:
            queue=Phase2Queue(context,[],False,False,lambda *_:None)
            queue.collection=col
            settings.phase2_mesh_auto_repair=True
            queue.repair_mesh(context,low=obj,repack=False)
        assert len(obj.data.vertices)==(4 if enabled else 6),(route,enabled)
        bpy.data.objects.remove(obj,do_unlink=True)
settings.fold_repair_stretched_triangles=True
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui
context.scene.airetopo_panel_visibility_settings.topic_prepare_1=True
panel=capture(context,ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_model_preparation))
assert not panel.errors,panel.errors
properties={binding[2] for binding in panel.bindings.values() if binding[0]=='property'}
assert {'fold_repair_stretched_triangles','fold_repair_stretch_ratio'} <= properties
print('STRETCHED_SINGLE_TRIANGLE_CENTER_WELD_AND_PIPELINES_OK',flush=True)
