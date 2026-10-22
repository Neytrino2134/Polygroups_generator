"""Small original vector marks for the flat shell; no external image dependency."""
from . import primitives

_programs = {}


def draw(name,x,y,size,color):
    if size <= 0:
        return
    folder=[(.1,.15),(.9,.15),(.9,.7),(.46,.7),(.34,.86),(.1,.86),(.1,.15)]
    cube=[(.5,.9),(.9,.7),(.9,.25),(.5,.05),(.1,.25),(.1,.7),(.5,.9),(.5,.5),(.9,.7),(.5,.5),(.1,.7),(.5,.5),(.5,.05)]
    camera=[(.1,.15),(.9,.15),(.9,.7),(.68,.7),(.6,.85),(.35,.85),(.27,.7),(.1,.7),(.1,.15)]
    seam=[(.1,.15),(.35,.42),(.65,.28),(.9,.85)]
    layers=[(.1,.35),(.5,.15),(.9,.35),(.5,.55),(.1,.35),(.1,.6),(.5,.8),(.9,.6)]
    circles = []
    grid=[(.12,.12),(.88,.12),(.88,.88),(.12,.88),(.12,.12)]
    if name=='LOGO':
        paths=[[(.08,.12),(.5,.9),(.92,.12),(.65,.12),(.5,.4),(.35,.12),(.08,.12)]]
    elif name in {'FILE_FOLDER','IMPORT','EXPORT','FILE_BLEND'}:
        paths=[folder]
    elif name in {'FILE_REFRESH','MOD_REMESH','UV','MATERIAL','SPHERE'}:
        paths=[[ (.5,.1),(.5,.9)],[(.12,.5),(.88,.5)]]
        circles=[(.5,.5,.39)]
    elif name in {'RENDER_STILL','CAMERA_DATA','RENDER_ANIMATION'}:
        paths=[camera]
        circles=[(.5,.44,.18)]
    elif name in {'SCULPTMODE_HLT','MOD_MULTIRES','UV_SYNC_SELECT','TEXTURE'}:
        paths=[grid,[(.38,.12),(.38,.88)],[(.64,.12),(.64,.88)],[(.12,.38),(.88,.38)],[(.12,.64),(.88,.64)]]
    elif name in {'EDGE_SEAM','EDITMODE_HLT','TOOL_SETTINGS','PREFERENCES'}:
        paths=[seam,[(.1,.85),(.35,.58),(.65,.72),(.9,.15)]]
    elif name in {'AUTOMERGE_ON','MESH_DATA','MESH_CUBE'}:
        paths=[cube]
    else:
        paths=[layers]
    key = (tuple(tuple(path) for path in paths), tuple(circles))
    program = _programs.get(key)
    if program is None:
        # Union every stroke before blending: joins/intersections retain the
        # same opacity, including with translucent theme colors.
        distances = []
        for path in paths:
            for a, b in zip(path, path[1:]):
                distances.append(f'd = min(d, segment(p, vec2({a[0]}, {a[1]}), vec2({b[0]}, {b[1]})));')
        for cx, cy, radius in circles:
            distances.append(f'd = min(d, abs(length(p - vec2({cx}, {cy})) - {radius}));')
        fragment = '''
            float segment(vec2 p, vec2 a, vec2 b) {
                vec2 ab = b - a;
                return length(p - a - ab * clamp(dot(p - a, ab) / dot(ab, ab), 0.0, 1.0));
            }
            void main() {
                vec2 p = (localPos - vec2(2.0)) / iconSize;
                float d = 2.0;
        ''' + '\n'.join(distances) + '''
                d = d * iconSize - strokeWidth * 0.5;
                float aa = max(fwidth(d), 1.0);
                float coverage = 1.0 - smoothstep(-0.5 * aa, 0.5 * aa, d);
                fragColor = vec4(color.rgb, color.a * coverage);
            }
        '''
        program = primitives.create_shader(fragment, (('FLOAT', 'iconSize'), ('FLOAT', 'strokeWidth')))
        _programs[key] = program
    primitives.draw(program, (x-2, y-2, size+4, size+4), color,
                    iconSize=size, strokeWidth=max(1.2, size/12))


def clear():
    _programs.clear()
