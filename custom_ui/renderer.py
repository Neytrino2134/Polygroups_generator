"""Pure drawing/layout. All scene access is captured before this callback."""
import math
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from . import theme as T
from . import icons

_shader = None
_geometry = {}


def tooltip_text_width(lines, scale, limit):
    blf.size(0, 11*scale)
    return min(limit, max((blf.dimensions(0, line)[0] for line in lines), default=0) + 20*scale)


def tooltip_bounds(anchor, size, viewport, mouse, scale=1):
    """Anchor above a control; fall back below/alongside at viewport edges."""
    ax, ay, aw, ah = anchor
    vw, vh = viewport
    margin, gap = 8*scale, 12*scale
    tw, th = size
    tw, th = min(tw, vw-2*margin), min(th, vh-2*margin)
    if tw <= 0 or th <= 0:
        return None
    center = min(max(margin, ax+(aw-tw)/2), vw-margin-tw)
    candidates = ((center, ay+ah+gap), (center, ay-gap-th),
                  (ax-gap-tw, ay+(ah-th)/2), (ax+aw+gap, ay+(ah-th)/2))
    mx, my = mouse
    for tx, ty in candidates:
        if tx < margin or ty < margin or tx+tw > vw-margin or ty+th > vh-margin:
            continue
        if tx-gap <= mx <= tx+tw+gap and ty-gap <= my <= ty+th+gap:
            continue
        return tx, ty, tw, th
    return None


def clear():
    global _shader
    _shader = None
    _geometry.clear()
    icons.clear()


def rect(x, y, w, h, color, radius=6):
    global _shader
    if w <= 0 or h <= 0:
        return
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    r = min(radius, w / 2, h / 2)
    key = (round(w, 2), round(h, 2), round(r, 2))
    points = _geometry.get(key)
    if points is None:
        points = [(w/2, h/2)]
        for cx, cy, start in ((w-r, h-r, 0), (r, h-r, 90), (r, r, 180), (w-r, r, 270)):
            for i in range(7):
                a = math.radians(start + i * 15)
                points.append((cx + math.cos(a)*r, cy + math.sin(a)*r))
        points.append(points[1])
        if len(_geometry) > 512:
            _geometry.clear()
        _geometry[key] = points
    vertices = [(x+px, y+py) for px, py in points]
    batch = batch_for_shader(_shader, 'TRI_FAN', {'pos': vertices})
    _shader.bind()
    _shader.uniform_float('color', color)
    batch.draw(_shader)


def text(value, x, y, size=13, color=T.TEXT, width=None):
    value = str(value).replace('\n', ' ')
    blf.size(0, size)
    if width is not None and blf.dimensions(0, value)[0] > width:
        while value and blf.dimensions(0, value + '…')[0] > width:
            value = value[:-1]
        value += '…'
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, value)


def value_text(node):
    value = node.get('value', '')
    if isinstance(value, list):
        return ', '.join(format(v, '.4g') if isinstance(v, (float, int)) else str(v) for v in value)
    if isinstance(value, float):
        return format(value, '.5g')
    return str(value)


def visible(node, query):
    if not query:
        return True
    hay = (node.get('text', '') + ' ' + node.get('property', '')).casefold()
    return all(word in hay for word in query.casefold().split()) or any(visible(c, query) for c in node.get('children', ()))


def workflow_query(session):
    """Session/settings cards are pinned outside the workflow search scope."""
    return '' if session.show_header else session.query


def children(node, query):
    # A matching group shows all its children; matching controls reveal ancestors.
    hay = node.get('text', '').casefold()
    match = query and all(word in hay for word in query.casefold().split())
    entries = [(c, '' if match else query) for c in node.get('children', ()) if match or visible(c, query)]
    if node['kind'] != 'column':
        return entries
    # Retain authored order while giving runs of fields a compact two-column
    # layout on wide cards. Narrow cards retain the original vertical sequence.
    result, run = [], []
    def flush():
        if len(run) >= 4:
            result.append((dict(kind='grid',id=run[0][0]['id']+'/grid',children=[c for c,q in run]),run[0][1]))
        else:
            result.extend(run)
        run.clear()
    for child,q in entries:
        if child['kind']=='property' and not child.get('array'):
            run.append((child,q))
        else:
            flush()
            result.append((child,q))
    flush()
    return result


def height(node, width, scale, query=''):
    kind = node['kind']
    if kind == 'separator':
        return 8 * scale
    if 'children' not in node:
        if slider_node(node):
            return 48*scale
        return (26 if kind == 'label' else 36) * scale
    if kind == 'group' and not node['opened'] and not query:
        return 40 * scale
    entries = children(node, query)
    pad = 12 * scale if kind in {'box', 'group','section'} else 0
    inner = max(30 * scale, width - 2*pad)
    # Narrow rows are wrapped rather than forcing unreadably small controls.
    row = kind == 'row' and len(entries) <= max(1, int(inner / (145*scale)))
    gap = 6 * scale
    grid = grid_entries(entries, kind, inner, scale)
    if grid:
        h = sum(max(height(c, inner/2-gap, scale,q) for c,q in entries[i:i+2])+gap for i in range(0,len(entries),2))
    elif row and entries:
        h = max(height(c, inner/len(entries)-gap, scale, q) for c, q in entries)
    else:
        h = sum(height(c, inner, scale, q) + gap for c, q in entries)
    return h + 2*pad + (38*scale if kind in {'group','section'} else 0)


def slider_node(node):
    return (node['kind']=='property' and node.get('type') in {'INT','FLOAT'}
            and not node.get('array') and node.get('soft_max',0)>node.get('soft_min',0)
            and abs(node.get('soft_max',0))<1e8 and abs(node.get('soft_min',0))<1e8)


def grid_entries(entries, kind, width, scale):
    return kind in {'column','grid'} and width>=480*scale and len(entries)>=4 and all(c['kind']=='property' for c,q in entries)


def draw_node(session, node, x, top, width, scale, query='', clip=None):
    kind = node['kind']
    h = height(node, width, scale, query)
    bottom = top - h
    if clip and (top < clip[0] or bottom > clip[1]):
        return h
    prefs = session.prefs
    accent = T.accent(prefs)
    enabled = node.get('enabled', True)
    color = T.text_color(prefs, muted=not enabled)
    if kind in {'box', 'group','section'}:
        rect(x, bottom, width, h, T.surface(T.BORDER, prefs), prefs.custom_ui_rounding*scale)
        rect(x+scale, bottom+scale, width-2*scale, h-2*scale, T.surface(T.SURFACE, prefs), prefs.custom_ui_rounding*scale)
    if 'children' in node:
        if kind == 'section':
            text(node['text'],x+12*scale,top-25*scale,14*scale,T.heading(prefs),width-24*scale)
            top -= 38*scale
        if kind == 'group':
            text('▾' if node['opened'] or query else '▸',x+10*scale,top-25*scale,12*scale,T.heading(prefs))
            icons.draw(node.get('icon',''),x+26*scale,top-29*scale,18*scale,T.heading(prefs))
            text(node['text'], x+52*scale, top-25*scale, 14*scale, T.heading(prefs), width-64*scale)
            session.hit((x, top-38*scale, width, 38*scale), ('binding', node['id']), node['text'])
            if not node['opened'] and not query:
                return h
            top -= 38*scale
        pad = 12*scale if kind in {'group', 'box','section'} else 0
        x += pad
        top -= pad
        width -= 2*pad
        entries = children(node, query)
        row = kind == 'row' and len(entries) <= max(1, int(width/(145*scale)))
        gap = 6*scale
        if grid_entries(entries,kind,width,scale):
            cw = (width-gap)/2
            for i in range(0,len(entries),2):
                rh = 0
                for j,(child,q) in enumerate(entries[i:i+2]):
                    rh = max(rh,draw_node(session,child,x+j*(cw+gap),top,cw,scale,q,clip))
                top -= rh+gap
        elif row and entries:
            factor = node.get('factor')
            widths = ([width*factor-gap/2, width*(1-factor)-gap/2]
                      if factor and len(entries) == 2 else [(width-gap*(len(entries)-1))/len(entries)]*len(entries))
            for (child, q), cw in zip(entries, widths):
                draw_node(session, child, x, top, cw, scale, q, clip)
                x += cw + gap
        else:
            for child, q in entries:
                top -= draw_node(session, child, x, top, width, scale, q, clip) + gap
        return h
    label = node.get('text', '')
    if kind == 'separator':
        return h
    if kind == 'label':
        text(label, x+3*scale, top-18*scale, 12*scale, T.heading(prefs) if enabled else color, width-6*scale)
        return h
    hot = session.hover == node['id']
    if kind == 'progress':
        rect(x, bottom+4*scale, width, h-8*scale, T.surface(T.RAISED, prefs))
        rect(x, bottom+4*scale, width*min(1, max(0, node['value'])), h-8*scale, accent)
        text(label, x+10*scale, top-23*scale, 12*scale, color, width-20*scale)
        return h
    boolean = kind == 'property' and node.get('type') == 'BOOLEAN' and not node.get('array')
    picked = node.get('depress', False)
    if boolean:
        rect(x+4*scale, bottom+10*scale, 34*scale, 18*scale, accent if node['value'] else T.surface(T.BORDER, prefs), 9*scale)
        rect(x+(21 if node['value'] else 6)*scale, bottom+12*scale, 14*scale, 14*scale, T.TEXT, 7*scale)
        text(label or node.get('property', ''), x+46*scale, top-23*scale, 12*scale, color, width-50*scale)
    else:
        rect(x, bottom+2*scale, width, h-4*scale, accent if picked else T.button(prefs) if kind == 'button' else T.surface(T.RAISED if hot else T.SURFACE, prefs), prefs.custom_ui_rounding*scale)
        rect(x, bottom+2*scale, 2*scale, h-4*scale, accent if hot or picked else T.surface(T.BORDER, prefs), 0)
        if kind == 'property':
            rendered = ('••••••' if node.get('secret') else value_text(node))
            if node.get('type') == 'ENUM':
                rendered = next((label for code,label,description in node.get('options',()) if code==node['value']),rendered)+'  ▾'
            if session.edit and session.edit['id']==node['id']:
                e = session.edit
                rendered = e['text'][:e['cursor']]+'│'+e['text'][e['cursor']:]
                rect(x,bottom+2*scale,width,h-4*scale,T.SELECTED,prefs.custom_ui_rounding*scale)
            if session.slider and session.slider['id']==node['id']:
                rendered = format(session.slider['value'],'.5g')
            text(label, x+10*scale, top-14*scale, 10*scale, T.text_color(prefs, muted=True), width-20*scale)
            text(rendered or '—', x+10*scale, top-29*scale, 12*scale, color, width-20*scale)
            if slider_node(node):
                lo,hi = node['soft_min'],node['soft_max']
                val = session.slider['value'] if session.slider and session.slider['id']==node['id'] else node['value']
                frac = max(0,min(1,(val-lo)/(hi-lo)))
                rect(x+10*scale,bottom+8*scale,width-20*scale,4*scale,T.surface(T.BORDER,prefs),2*scale)
                rect(x+10*scale,bottom+8*scale,(width-20*scale)*frac,4*scale,accent,2*scale)
                rect(x+6*scale+(width-20*scale)*frac,bottom+5*scale,10*scale,10*scale,accent,5*scale)
        else:
            if kind=='list':
                label = f'{label} · {node["count"]} items  ▾'
            glyph = {'ADD':'+','REMOVE':'−','FILE_FOLDER':'▱','FILE_REFRESH':'↻',
                     'TRIA_UP':'▴','TRIA_DOWN':'▾','X':'×','PREFERENCES':'⚙','CHECKMARK':'✓',
                     'PLAY':'▶','PAUSE':'Ⅱ','HIDE_ON':'◉','HIDE_OFF':'○','XRAY':'▣'}.get(node.get('icon'),'⋯')
            text(label or glyph, x+10*scale, top-23*scale, 12*scale, T.surface(T.BACKGROUND,prefs) if picked else color, width-20*scale)
    if enabled:
        tip=node.get('description') or label
        if kind=='property' and not node.get('secret') and node.get('type')=='STRING':
            tip += '\n'+value_text(node)
        session.hit((x, bottom, width, h), ('binding', node['id']), tip, node['id'])
        if slider_node(node):
            session.hit((x+10*scale,bottom+3*scale,width-20*scale,12*scale),('slider',node['id']),node.get('description',''),node['id'])
    else:
        session.hit((x,bottom,width,h),('disabled',),node.get('description') or label,node['id'])
    return h


def draw(session, region):
    prefs = session.prefs
    scale = session.scale
    session.hits = []
    x, top, width, h = session.geometry(region)
    bottom = top-h
    blend = gpu.state.blend_get()
    scissor = gpu.state.scissor_get()
    # Blender exposes scissor_get but no scissor_test_get. POST_PIXEL starts
    # outside our clipping scope; always release it before leaving the handler.
    scissor_test = False
    try:
        gpu.state.blend_set('ALPHA')
        rect(x, bottom, width, h, T.surface(T.BACKGROUND, prefs), prefs.custom_ui_rounding*scale)
        icons.draw('LOGO',x+14*scale,top-33*scale,25*scale,T.heading(prefs))
        text('AI Retopo' if width<500*scale else 'AI Retopo Toolkit', x+48*scale, top-29*scale, 17*scale, T.heading(prefs), width=width-260*scale)
        if width>=570*scale:
            text('v'+session.version,x+235*scale,top-27*scale,11*scale,T.text_color(prefs, muted=True))
        docked = prefs.ui_mode == 'UI_PANEL' and session.docked
        for offset, label, action in ((186, 'Autosave', 'header'), (116, 'Detach' if docked else 'Dock', 'dock'), (50, '−' if not session.collapsed else '+', 'collapse'), (18, '×', 'close')):
            text(label, x+width-offset*scale, top-28*scale, 12*scale, T.text_color(prefs, muted=True))
            session.hit((x+width-offset*scale-4*scale, top-40*scale, (65 if action=='header' else 40)*scale, 34*scale), (action,), 'Autosave and Restart' if action=='header' else label)
        if not docked:
            session.hit((x, top-42*scale, width-195*scale, 42*scale), ('move',), 'Drag to move')
        if session.collapsed or h<190*scale:
            return
        compact = width < 670*scale
        nav = (42 if compact else 220)*scale
        content_x = x+nav+14*scale
        content_w = width-nav-28*scale
        content_top = top-102*scale
        if nav:
            rect(x+nav, bottom+12*scale, scale, h-62*scale, T.surface(T.BORDER,prefs), 0)
            for index, title in enumerate(session.titles):
                step = min(36*scale, max(8, (h-155*scale)/13)) if compact else 36*scale
                yt = top-108*scale-index*step
                if yt < bottom+40*scale:
                    break
                if index == session.section and not session.show_header:
                    rect(x+8*scale, yt-step+3*scale, nav-16*scale, step-2*scale, T.SELECTED)
                    rect(x+8*scale, yt-step+3*scale, 3*scale, step-2*scale, T.accent(prefs), 1)
                size = min(19*scale, step-5*scale)
                icons.draw(session.icons[index],x+(13 if compact else 17)*scale,yt-step+6*scale,size,T.heading(prefs))
                if not compact:
                    text(title, x+44*scale, yt-19*scale, 12*scale, T.heading(prefs), nav-54*scale)
                session.hit((x+8*scale, yt-step+3*scale, nav-16*scale, step-2*scale), ('section', index), title)
            if session.show_header:
                rect(x+8*scale, top-90*scale, nav-16*scale, 32*scale, T.SELECTED)
                rect(x+8*scale, top-90*scale, 3*scale, 32*scale, T.accent(prefs), 1)
            icons.draw('PREFERENCES',x+(13 if compact else 17)*scale,top-81*scale,19*scale,
                       T.heading(prefs))
            if not compact:
                text('Autosave and Restart', x+44*scale, top-78*scale, 12*scale, T.heading(prefs), nav-54*scale)
            session.hit((x+8*scale, top-90*scale, nav-16*scale, 32*scale), ('header',), 'Autosave and Restart')
        title = ('Search Results' if session.query and not session.show_header else
                 'Autosave and Restart' if session.show_header else session.titles[session.section])
        icons.draw(session.icons[session.section] if not session.show_header else 'PREFERENCES',content_x,top-74*scale,29*scale,T.heading(prefs))
        text(title, content_x+42*scale, top-66*scale, 17*scale, T.heading(prefs), content_w-197*scale)
        if not nav:
            session.hit((content_x, top-78*scale, content_w-150*scale, 32*scale), ('sections',), 'Choose workflow section')
        for offset, label, action in ((145, 'Search', 'search'), (82, '+', 'expand'), (40, '−', 'fold')):
            text(label, content_x+content_w-offset*scale, top-66*scale, 11*scale, T.accent(prefs))
            tooltip = {'expand': 'Expand next level', 'fold': 'Collapse deepest open level'}.get(action, label)
            session.hit((content_x+content_w-offset*scale, top-78*scale, 48*scale, 30*scale), (action,), tooltip)
        if session.query:
            text('Search: '+session.query+'  (click Search to clear/edit)', content_x, top-90*scale, 11*scale, T.text_color(prefs, muted=True), content_w)
        view_bottom = bottom+26*scale
        view_h = content_top-view_bottom
        gpu.state.scissor_test_set(True)
        gpu.state.scissor_set(int(content_x), int(view_bottom), max(1, int(content_w)), max(1, int(view_h)))
        query = workflow_query(session)
        total = height(session.model.node, content_w, scale, query)
        session.max_scroll = max(0, total-view_h)
        session.scroll = min(session.scroll, session.max_scroll)
        draw_node(session, session.model.node, content_x, content_top+session.scroll, content_w, scale, query, (view_bottom, content_top))
        gpu.state.scissor_set(*scissor)
        gpu.state.scissor_test_set(scissor_test)
        if session.max_scroll:
            track = max(20*scale, view_h)
            thumb = max(24*scale, view_h*view_h/max(view_h, total))
            ty = content_top-thumb-(track-thumb)*session.scroll/session.max_scroll
            rect(x+width-9*scale, ty, 3*scale, thumb, T.accent(prefs), scale)
        text(session.note or ('Docked right · Detach to move · wheel to scroll' if docked else 'Drag title to move · corner to resize · wheel to scroll'), content_x, bottom+9*scale, 10*scale, T.ERROR if session.note else T.text_color(prefs, muted=True), content_w)
        if not docked:
            session.hit((x+width-22*scale, bottom, 22*scale, 22*scale), ('resize',), 'Drag to resize')
            text('◢', x+width-18*scale, bottom+6*scale, 12*scale, T.MUTED)
        # Ignore controls clipped outside the content viewport.
        session.hits = [hit for hit in session.hits if hit[1][0] not in {'binding','slider','disabled'} or (hit[0][1] >= view_bottom and hit[0][1]+hit[0][3] <= content_top)]
        if session.dropdown:
            options = session.dropdown['node']['options']
            offset = session.dropdown['offset']
            anchor = next((hit[0] for hit in session.hits if hit[3]==session.dropdown['id']), (content_x,content_top-40*scale,content_w,36*scale))
            dx,dy,dw,_ = anchor
            count = min(8,len(options)-offset)
            dh = (count*32+12)*scale
            dt = max(bottom+dh+25*scale,min(top-45*scale,dy))
            rect(dx,dt-dh,dw,dh,T.surface(T.RAISED,prefs),prefs.custom_ui_rounding*scale)
            for index,(code,label,description) in enumerate(options[offset:offset+8]):
                cy = dt-(index+1)*32*scale
                value=session.dropdown['node']['value']
                if code==value or (isinstance(value,list) and code in value):
                    rect(dx+4*scale,cy,dw-8*scale,30*scale,T.SELECTED)
                text(label,dx+12*scale,cy+10*scale,12*scale,T.text_color(prefs),dw-24*scale)
                session.hit((dx,cy,dw,32*scale),('choice',code),description)
        hovered = session.find(*session.mouse)
        if (session.tooltip and session.tooltip_age > .6 and hovered
                and hovered[2] == session.tooltip):
            tw = min(420*scale, region.width-16*scale)
            lines=[]
            blf.size(0,11*scale)
            for source_line in session.tooltip.splitlines():
                line=''
                for char in source_line:
                    if blf.dimensions(0,line+char)[0]>tw-20*scale:
                        lines.append(line)
                        line=''
                    line+=char
                if line:
                    lines.append(line)
            lines=lines[:max(0, min(8, int((region.height-30*scale)/(15*scale))))]
            tw = tooltip_text_width(lines, scale, tw)
            tip_h=(len(lines)*15+14)*scale
            bounds = tooltip_bounds(hovered[0], (tw, tip_h),
                                    (region.width, region.height), session.mouse, scale)
            if bounds and lines:
                tx, ty, tw, tip_h = bounds
                rect(tx,ty,tw,tip_h,T.surface(T.RAISED,prefs))
                for index,line in enumerate(lines):
                    text(line,tx+10*scale,ty+tip_h-(index*15+20)*scale,11*scale,T.text_color(prefs))
    finally:
        gpu.state.scissor_set(*scissor)
        gpu.state.scissor_test_set(scissor_test)
        gpu.state.blend_set(blend)
