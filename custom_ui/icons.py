"""Small original vector marks for the flat shell; no external image dependency."""
import math
import gpu
from gpu_extras.batch import batch_for_shader

_shader = None


def draw(name,x,y,size,color):
    global _shader
    folder=[(.1,.15),(.9,.15),(.9,.7),(.46,.7),(.34,.86),(.1,.86),(.1,.15)]
    cube=[(.5,.9),(.9,.7),(.9,.25),(.5,.05),(.1,.25),(.1,.7),(.5,.9),(.5,.5),(.9,.7),(.5,.5),(.1,.7),(.5,.5),(.5,.05)]
    camera=[(.1,.15),(.9,.15),(.9,.7),(.68,.7),(.6,.85),(.35,.85),(.27,.7),(.1,.7),(.1,.15)]
    seam=[(.1,.15),(.35,.42),(.65,.28),(.9,.85)]
    layers=[(.1,.35),(.5,.15),(.9,.35),(.5,.55),(.1,.35),(.1,.6),(.5,.8),(.9,.6)]
    circle=[(.5+math.cos(i*math.tau/20)*.39,.5+math.sin(i*math.tau/20)*.39) for i in range(21)]
    grid=[(.12,.12),(.88,.12),(.88,.88),(.12,.88),(.12,.12)]
    if name=='LOGO':
        paths=[[(.08,.12),(.5,.9),(.92,.12),(.65,.12),(.5,.4),(.35,.12),(.08,.12)]]
    elif name in {'FILE_FOLDER','IMPORT','EXPORT','FILE_BLEND'}:
        paths=[folder]
    elif name in {'FILE_REFRESH','MOD_REMESH','UV','MATERIAL','SPHERE'}:
        paths=[circle,[(.5,.1),(.5,.9)],[(.12,.5),(.88,.5)]]
    elif name in {'RENDER_STILL','CAMERA_DATA','RENDER_ANIMATION'}:
        paths=[camera,[(.5+math.cos(i*math.tau/16)*.18,.44+math.sin(i*math.tau/16)*.18) for i in range(17)]]
    elif name in {'SCULPTMODE_HLT','MOD_MULTIRES','UV_SYNC_SELECT','TEXTURE'}:
        paths=[grid,[(.38,.12),(.38,.88)],[(.64,.12),(.64,.88)],[(.12,.38),(.88,.38)],[(.12,.64),(.88,.64)]]
    elif name in {'EDGE_SEAM','EDITMODE_HLT','TOOL_SETTINGS','PREFERENCES'}:
        paths=[seam,[(.1,.85),(.35,.58),(.65,.72),(.9,.15)]]
    elif name in {'AUTOMERGE_ON','MESH_DATA','MESH_CUBE'}:
        paths=[cube]
    else:
        paths=[layers]
    if _shader is None:
        _shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    vertices=[]
    for path in paths:
        for a,b in zip(path,path[1:]):
            vertices.extend([(x+a[0]*size,y+a[1]*size,0),(x+b[0]*size,y+b[1]*size,0)])
    batch=batch_for_shader(_shader,'LINES',{'pos':vertices})
    _shader.bind()
    _shader.uniform_float('viewportSize',gpu.state.viewport_get()[2:])
    _shader.uniform_float('lineWidth',max(1.2,size/12))
    _shader.uniform_float('color',color)
    batch.draw(_shader)


def clear():
    global _shader
    _shader=None
