"""Read-only diagnostics for the selected Asset_00_07 triangle."""
import json
import math
import sys
from pathlib import Path
import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from polygroups_generator.core.mesh_fold_repair import inspect_triangle_quality, repair_local_folds, _plan, _boundary

obj = bpy.data.objects['SM_Asset_00_07_MID']
if obj.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bm = bmesh.new()
bm.from_mesh(obj.data)
for seq in (bm.verts, bm.edges, bm.faces):
    seq.ensure_lookup_table()
    seq.index_update()
bm.normal_update()
uv = bm.loops.layers.uv.active


def metric(face):
    a, b, c = [v.co for v in face.verts]
    cross = (b-a).cross(c-a).length
    quality = 2*math.sqrt(3)*cross / max(sum(e.calc_length()**2 for e in face.edges), 1e-300)
    points = [l[uv].uv for l in face.loops]
    u, v = points[1]-points[0], points[2]-points[0]
    j1 = u / max((b-a).length, 1e-300)
    j2 = (v-j1*((b-a).dot(c-a)/max((b-a).length, 1e-300)))/max(cross/max((b-a).length, 1e-300), 1e-300)
    trace = j1.length_squared+j2.length_squared
    det = abs(j1.x*j2.y-j1.y*j2.x)
    stretch = (trace+math.sqrt(max(0, trace*trace-4*det*det)))*.5/det if det else 1e300
    return dict(face=face.index, verts=[v.index for v in face.verts], selected=face.select,
                quality=quality, stretch=stretch, area=face.calc_area(),
                uv_area=abs(u.x*v.y-u.y*v.x)*.5,
                seams=[e.seam for e in face.edges],
                edge_neighbors=[[f.index for f in e.link_faces if f != face] for e in face.edges])


triangles = sorted([metric(f) for f in bm.faces if len(f.verts)==3], key=lambda d:d['stretch'], reverse=True)
print('ASSET007_DIAG', json.dumps(dict(counts=[len(bm.verts),len(bm.edges),len(bm.faces)],
    object_mode=obj.mode, selected=[f.index for f in bm.faces if f.select],
    invalid_edges=sum(not e.is_manifold for e in bm.edges), triangles=triangles[:25],
    quality=inspect_triangle_quality(bm)[1])), flush=True)
targets = {d['face'] for d in triangles[:5]} | {f.index for f in bm.faces if f.select and len(f.verts)==3}
face=bm.faces[3899];quad=bm.faces[392];patch={face,quad};boundary=_boundary(patch)
edge=min(boundary,key=lambda e:e.index);inside=next(f for f in edge.link_faces if f in patch)
loop=next(l for l in inside.loops if l.edge==edge)
ordered=[loop.vert,loop.link_loop_next.vert]
ordered.append(next(v for e in boundary for v in e.verts if v not in ordered))
a,b,c=[v.co for v in ordered];normal=(b-a).cross(c-a).normalized()
tip=next(v for v in face.verts if len(v.link_edges)==2)
corners=list(quad.verts);start=corners.index(tip);corners=corners[start:]+corners[:start]
p,q,r,s=[v.co for v in corners];n1=(q-p).cross(r-p).normalized();n2=(r-p).cross(s-p).normalized()
base=[v for v in face.verts if v!=tip];opposite=next(v for v in quad.verts if v not in face.verts)
direction=base[1].co-base[0].co
print('ASSET007_EAR_METRICS',json.dumps(dict(ordered=[v.index for v in ordered],normal=list(normal),
    allcoords={v.index:list(v.co) for f in patch for v in f.verts},
    tip_depth=abs((tip.co-a).dot(normal))/max(e.calc_length() for e in boundary),
    triangle_dot=face.normal.dot(normal),quad_dot=quad.normal.dot(normal),triangle_quad_dot=face.normal.dot(quad.normal),
    subtri_dot=n1.dot(n2),subtri_closing=[n1.dot(face.normal),n2.dot(face.normal)],
    side=direction.cross(tip.co-base[0].co).dot(direction.cross(opposite.co-base[0].co)),
    normalsoutside=[dict(face=f.index,dot=f.normal.dot(normal)) for e in boundary for f in e.link_faces if f not in patch],
    boundary=[dict(verts=[v.index for v in e.verts],seam=e.seam) for e in boundary])),flush=True)
for index in sorted(targets):
    face = bm.faces[index]
    neighbors = {f for v in face.verts for f in v.link_faces}
    print('ASSET007_PATCH', json.dumps(dict(face=index,
        verts=[dict(index=v.index, co=list(v.co), edges=len(v.link_edges), faces=[f.index for f in v.link_faces]) for v in face.verts],
        faces=[dict(index=f.index, verts=[v.index for v in f.verts],normal=list(f.normal),area=f.calc_area(),
                    material=f.material_index, uv=[list(l[uv].uv) for l in f.loops]) for f in sorted(neighbors,key=lambda f:f.index)],
        plan_neighbors=[dict(face=f.index,ear=_plan({face,f},list(bm.loops.layers.uv.values()),1e-7,True) is not None,
                             fold=_plan({face,f},list(bm.loops.layers.uv.values()),1e-7) is not None)
                        for f in neighbors if f!=face and len(set(f.edges)&set(face.edges))>=2])),flush=True)
work=bm.copy()
result=repair_local_folds(work,fix_zero_area=True)
print('ASSET007_EXISTING_REPAIR',json.dumps({k:sorted(v) if isinstance(v,set) else v for k,v in result.items()}),flush=True)
work.free()
bm.free()
