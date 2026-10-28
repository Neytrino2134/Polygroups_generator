"""General folded-region fixtures: polygon necks, open caps, triangulation, protection."""
import math,sys
from pathlib import Path
import addon_utils,bmesh,bpy
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.mesh_fold_repair import repair_local_folds


def fixture(sides=4,hole=False,triangulate=False,solid=False):
 bm=bmesh.new()
 lower=[bm.verts.new((math.cos(2*math.pi*i/sides),math.sin(2*math.pi*i/sides),-1)) for i in range(sides)]
 upper=[bm.verts.new((v.co.x,v.co.y,0)) for v in lower]
 bm.faces.new(list(reversed(lower)))
 for i in range(sides):bm.faces.new((lower[i],lower[(i+1)%sides],upper[(i+1)%sides],upper[i]))
 # A flat overfold with no degree-two tip; its neck can have 3,4,6,8 sides.
 tip=bm.verts.new((4,.2,.0001 if solid else 0))
 patch={bm.faces.new((upper[i],upper[(i+1)%sides],tip)) for i in range(sides)}
 if hole:
  face=min(patch,key=lambda f:f.calc_area());patch.remove(face);bmesh.ops.delete(bm,geom=[face],context='FACES_ONLY')
 if triangulate:bmesh.ops.triangulate(bm,faces=[f for f in bm.faces if f not in patch])
 uv=bm.loops.layers.uv.new('UVMap');uv2=bm.loops.layers.uv.new('DetailUV')
 for face in bm.faces:
  face.select_set(False)
  for loop in face.loops:
   loop[uv].uv=(loop.vert.co.x,loop.vert.co.y)
   loop[uv2].uv=(loop.vert.co.x*.3+.1,loop.vert.co.y*.3+.2)
 for f in patch:f.select_set(True)
 bm.normal_update();return bm,patch


def run(bm,selected=False):
 return repair_local_folds(bm,fix_folds=False,fix_degenerate=False,fix_dangling=True,selected_only=selected)

for sides in (3,4,6,8):
 for hole in (False,True):
  for triangulated in (False,True):
   for scale in (.001,1,1000):
    bm,patch=fixture(sides,hole,triangulated)
    transform=Matrix.Rotation(.73,4,Vector((1,2,3)))
    for v in bm.verts:v.co=transform@(v.co*scale)+Vector((7,-3,9))*scale
    bm.normal_update()
    original={v:tuple(v.co) for v in bm.verts}
    layers=list(bm.loops.layers.uv.values())
    uv_snapshot={f:tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers) for f in bm.faces if f not in patch}
    initial=len(bm.faces);result=run(bm,True)
    assert result['dangling_faces']==len(patch),(sides,hole,triangulated,scale,result)
    assert result['dangling_filled']==1,result
    assert all(edge.is_manifold for edge in bm.edges),(sides,hole,triangulated,scale)
    assert all(tuple(v.co)==original[v] for v in bm.verts)
    assert all(f.is_valid and tuple(tuple(tuple(l[layer].uv) for l in f.loops) for layer in layers)==uvs for f,uvs in uv_snapshot.items())
    assert run(bm)['dangling_faces']==0,'Repair must be idempotent'
    bm.free()
# Long polygon strips, including an internal missing face, must not depend on
# the old 128-face limit or a triangular neck / degree-two tip.
for sides,steps in ((3,55),(4,45),(8,25)):
 for hole in (False,True):
  bm=bmesh.new()
  bottom=[bm.verts.new((math.cos(2*math.pi*i/sides),math.sin(2*math.pi*i/sides),-1)) for i in range(sides)]
  previous=[bm.verts.new((v.co.x,v.co.y,0)) for v in bottom]
  bm.faces.new(list(reversed(bottom)))
  for i in range(sides):bm.faces.new((bottom[i],bottom[(i+1)%sides],previous[(i+1)%sides],previous[i]))
  patch=set();bands=[]
  for step in range(1,steps+1):
   radius=1/(step+1)
   ring=[bm.verts.new((step*.2+radius*math.cos(2*math.pi*i/sides),radius*math.sin(2*math.pi*i/sides),0)) for i in range(sides)]
   band=[bm.faces.new((previous[i],previous[(i+1)%sides],ring[(i+1)%sides],ring[i])) for i in range(sides)]
   patch.update(band);bands.append(band);previous=ring
  patch.add(bm.faces.new(previous))
  if hole:
   removed=bands[steps//2][0];patch.remove(removed);bmesh.ops.delete(bm,geom=[removed],context='FACES_ONLY')
  bm.normal_update();result=run(bm)
  assert result['dangling_faces']==len(patch),(sides,steps,hole,result)
  assert all(edge.is_manifold for edge in bm.edges)
  bm.free()
for protection in ('solid','hidden','uv_pin','edge_pin','seam','materials','unselected'):
 bm,patch=fixture(4,solid=protection=='solid')
 if protection=='hidden':next(iter(patch)).hide_set(True)
 if protection=='uv_pin':next(iter(patch)).loops[0][bm.loops.layers.uv.active].pin_uv=True
 if protection=='edge_pin':
  pin=bm.edges.layers.int.new('polygroups_pin_edge');next(iter(patch)).edges[0][pin]=1
 if protection=='seam':next(e for f in patch for e in f.edges if all(n in patch for n in e.link_faces)).seam=True
 if protection=='materials':next(iter(patch)).material_index=1
 if protection=='unselected':
  for f in patch:f.select_set(False)
 before=(len(bm.verts),len(bm.edges),len(bm.faces));result=run(bm,protection=='unselected')
 assert result['dangling_faces']==0,(protection,result)
 assert before==(len(bm.verts),len(bm.edges),len(bm.faces)),protection
 bm.free()
# Existing cap and extra internal incidence: reuse/repair the cap instead of
# attempting to create a duplicate face or deleting the retained surface.
bm,patch=fixture(3)
# The three rim vertices each meet a vertical body edge; the tip has degree 3.
neck={v for v in bm.verts if v.co.z==0 and v.co.x<2}
ordered=sorted(neck,key=lambda v:math.atan2(v.co.y,v.co.x))
cap=bm.faces.new(ordered);cap.normal_flip();layers=list(bm.loops.layers.uv.values())
for loop in cap.loops:
 for layer in layers:loop[layer].uv=(loop.vert.co.x,loop.vert.co.y)
bm.normal_update();result=run(bm)
assert result['dangling_faces']==3 and cap.is_valid,result
assert all(edge.is_manifold for edge in bm.edges)
assert cap.normal.z>.9
bm.free()
# Mixed defects: Find must preserve topology/UV and display faces plus wire/vertex
# debris together; face-only flushing used to hide the wire selection.
bm,patch=fixture(4)
a=bm.verts.new((10,0,0));b=bm.verts.new((11,0,0));bm.edges.new((a,b));bm.verts.new((12,0,0))
mesh=bpy.data.meshes.new('Mixed defects');bm.to_mesh(mesh);bm.free()
obj=bpy.data.objects.new('Mixed defects',mesh);bpy.context.collection.objects.link(obj)
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
before=(len(mesh.vertices),len(mesh.edges),len(mesh.polygons))
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='SELECT')=={'FINISHED'}
edit=bmesh.from_edit_mesh(mesh)
assert before==(len(edit.verts),len(edit.edges),len(edit.faces))
assert sum(f.select for f in edit.faces)==4
assert all(e.select for e in edit.edges if not e.link_faces)
assert all(v.select for v in edit.verts if not v.link_edges)
assert bpy.context.tool_settings.mesh_select_mode[:]==(True,True,True)
assert bpy.ops.mesh.polygroups_repair_mesh_folds(action='REPAIR',selected_only=True)=={'FINISHED'}
edit=bmesh.from_edit_mesh(mesh)
assert all(e.is_manifold for e in edit.edges) and all(v.link_edges for v in edit.verts)
bpy.ops.object.mode_set(mode='OBJECT')
print('GENERAL_REPAIR_POLYGON_NECK_OPEN_TRIANGULATED_SCALED_ROTATED_AND_PROTECTED_OK',flush=True)
