"""Per-area sessions, native handoffs and idempotent viewport lifecycle."""
import time
from types import SimpleNamespace
import bpy
from bpy.app.handlers import persistent
from .schema import Layout, capture, walk
from . import renderer
from .events import edit_key, parsed_value

SESSIONS = {}
_handle = None
_registered = False
_autostart = True
_HANDLE_KEY = 'airetopo.custom_ui.draw_handle'
_CLEANUP_KEY = 'airetopo.custom_ui.cleanup'


def preferences(context=None):
    from ..localization import get_preferences
    return get_preferences(context or bpy.context)


def key_for(context):
    # SpaceView3D moves between Areas when Blender maximizes/restores an editor.
    return str(context.window.as_pointer()) + ':' + str(context.space_data.as_pointer())


def resolve(session):
    """Refresh native wrappers exclusively from currently live screens."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            key = str(window.as_pointer()) + ':' + str(area.spaces.active.as_pointer())
            if key == session.key:
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    session.window, session.area, session.region = window, area, region
                    return True
    return False


def redraw(session):
    if resolve(session):
        session.area.tag_redraw()


class Session:
    def __init__(self, context):
        self.key = key_for(context)
        self.window, self.area, self.region = context.window, context.area, context.region
        self.scene = context.scene.as_pointer()
        self.prefs = preferences(context)
        self.section = self.prefs.custom_ui_section
        self.show_header = False
        self.scrolls = {}
        self.scroll = 0
        self.query = ''
        self.x, self.y, self.width, self.height = self.prefs.custom_ui_geometry
        self.collapsed = False
        self.closed = False
        self.hits = []
        self.hover = ''
        self.mouse = (0, 0)
        self.tooltip = ''
        self.hover_since = time.monotonic()
        self.note = ''
        self.max_scroll = 0
        self.drag = None
        self.edit = None
        self.dropdown = None
        self.slider = None
        self.refresh(context)

    @property
    def scale(self):
        return self.prefs.custom_ui_scale * bpy.context.preferences.system.ui_scale

    @property
    def tooltip_age(self):
        return time.monotonic() - self.hover_since

    def geometry(self, region):
        s = self.scale
        if self.prefs.ui_mode == 'UI_PANEL' and self.prefs.ui_panel_docked:
            width = min(self.prefs.ui_panel_width*s, max(1, region.width-16))
            # Reserve physical viewport pixels for its top toolbars/overlays.
            top = max(1, min(region.height-1, max(9, region.height-100)))
            available = max(1, top-8)
            h = min(44*s if self.collapsed else available, available)
            return max(8, region.width-width-8), top, width, h
        width = min(self.width*s, max(1, region.width-16))
        h = min((44 if self.collapsed else self.height)*s, max(1, region.height-16))
        x = min(max(8, self.x*s), max(8, region.width-width-8))
        top = min(region.height-8, max(h+8, region.height-self.y*s))
        return x, top, width, h

    def hit(self, rect, action, tooltip='', identity=''):
        self.hits.append((rect, action, tooltip, identity))

    def find(self, x, y):
        for hit in reversed(self.hits):
            rx, ry, w, h = hit[0]
            if rx <= x <= rx+w and ry <= y <= ry+h:
                return hit
        return None

    def refresh(self, context):
        started = time.perf_counter()
        from .. import ui
        from ..localization import t
        if self.scene != context.scene.as_pointer():
            self.edit = self.dropdown = self.slider = None
            self.scroll = 0
        self.titles = [f'{p.bl_order:02d} | {t(context, p.bl_text_key)}' for p in ui.SECTION_PANEL_CLASSES]
        self.icons = [p.bl_icon for p in ui.SECTION_PANEL_CLASSES]
        self.version = ui.addon_version_string()
        if self.show_header:
            model = Layout(key='global')
            old = ui._CUSTOM_CAPTURING, ui._CUSTOM_HEADER_ONLY
            ui._CUSTOM_CAPTURING, ui._CUSTOM_HEADER_ONLY = True, True
            try:
                ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model), context)
                appearance = model.box()
                appearance.label(text='Custom Interface')
                for name in ('ui_mode', 'custom_ui_scale', 'custom_ui_accent', 'custom_ui_brightness', 'custom_ui_rounding'):
                    appearance.prop(self.prefs, name)
                appearance.operator('wm.airetopo_reset_custom_appearance')
            finally:
                ui._CUSTOM_CAPTURING, ui._CUSTOM_HEADER_ONLY = old
        elif self.query:
            model = Layout(key='search')
            for index, title in enumerate(self.titles):
                captured = capture(context, index)
                captured.node.update(kind='section',text=title)
                model.node['children'].append(captured.node)
                model.bindings.update(captured.bindings)
                model.errors.extend(captured.errors)
        else:
            model = capture(context, self.section)
        signature = repr(model.node)
        changed = signature != getattr(self, 'signature', '')
        self.signature, self.model = signature, model
        self.scene = context.scene.as_pointer()
        self.capture_ms = (time.perf_counter()-started)*1000
        return changed

    def select(self, index, header=False):
        self.scrolls[(self.section, self.show_header)] = self.scroll
        self.section, self.show_header = index, header
        self.prefs.custom_ui_section = index
        self.scroll = self.scrolls.get((index, header), 0)


def _dispatch(session, identifier):
    """Dispatch deferred native actions using the current original viewport."""
    scene = session.scene
    binding = session.model.bindings.get(identifier)
    def run():
        if session.closed or session.key not in SESSIONS or not resolve(session):
            return None
        try:
            with bpy.context.temp_override(window=session.window, area=session.area, region=session.region):
                if bpy.context.scene.as_pointer() != scene:
                    return None
                # Refresh conditions after UI capture was released.
                session.refresh(bpy.context)
                current = session.model.bindings.get(identifier)
                if not current or not binding or current[0] != binding[0]:
                    raise RuntimeError('Control changed; try again')
                if current[0] == 'operator':
                    if current[1] != binding[1] or vars(current[2]) != vars(binding[2]) or current[3] != binding[3]:
                        raise RuntimeError('Operator settings changed; try again')
                elif current[0] in {'property', 'search'} and (current[1] != binding[1] or current[2] != binding[2]):
                    raise RuntimeError('Setting changed; try again')
                node = next((n for n in walk(session.model.node) if n['id'] == identifier), {})
                if not node.get('enabled', True):
                    raise RuntimeError('Tool unavailable for the current selection or mode')
                if current[0] == 'operator':
                    _, target, params, execution = current
                    category, name = target.split('.')
                    op = getattr(getattr(bpy.ops, category), name)
                    if not op.poll():
                        raise RuntimeError('Tool unavailable for the current selection or mode')
                    result = op(execution, **vars(params))
                    if 'CANCELLED' in result:
                        session.note = 'Operation cancelled; see Blender status'
                elif current[0] == 'property' and isinstance(getattr(current[1], current[2]), bool):
                    setattr(current[1], current[2], not getattr(current[1], current[2]))
                elif current[0] == 'property' and node.get('type') == 'ENUM' and node.get('options'):
                    session.dropdown = dict(id=identifier, node=node, offset=0)
                elif (current[0] == 'property' and not node.get('array') and not node.get('secret')
                      and node.get('type') in {'STRING', 'INT', 'FLOAT'}
                      and node.get('unit') in {'', 'NONE'}):
                    value = str(getattr(current[1], current[2]))
                    session.edit = dict(id=identifier, text=value, cursor=len(value), all=True, node=node)
                else:
                    bpy.ops.wm.airetopo_custom_property('INVOKE_DEFAULT', session_key=session.key, control=identifier)
                session.refresh(bpy.context)
                redraw(session)
        except Exception as exc:
            session.note = str(exc)
            redraw(session)
        return None
    bpy.app.timers.register(run, first_interval=0)


class AIRETOPO_OT_custom_property(bpy.types.Operator):
    """Use Blender's complete RNA editor for units, pointers and complex values."""
    bl_idname = 'wm.airetopo_custom_property'
    bl_label = 'Edit Setting'
    session_key: bpy.props.StringProperty()
    control: bpy.props.StringProperty()

    def invoke(self, context, event):
        session = SESSIONS.get(self.session_key)
        if not session:
            return {'CANCELLED'}
        self.binding = session.model.bindings.get(self.control)
        self.scene_pointer = context.scene.as_pointer()
        if not self.binding:
            return {'CANCELLED'}
        # RNA editing is immediate, as in Blender's own sidebar popovers.
        return context.window_manager.invoke_popup(self, width=380)

    def draw(self, context):
        if context.scene.as_pointer() != self.scene_pointer:
            self.layout.label(text='Scene changed; close this editor')
            return
        try:
            kind, owner, name, extra = self.binding
            if kind == 'list':
                self.layout.template_list(*owner, **name)
            elif kind == 'search':
                self.layout.prop_search(owner, name, extra[0], extra[1])
            else:
                self.layout.prop(owner, name, index=extra)
        except (ReferenceError, TypeError):
            self.layout.label(text='Setting is no longer available')

    def execute(self, context):
        return {'FINISHED'}


class AIRETOPO_OT_custom_search(bpy.types.Operator):
    bl_idname = 'wm.airetopo_custom_search'
    bl_label = 'Search Tools and Settings'
    session_key: bpy.props.StringProperty()
    query: bpy.props.StringProperty(name='Search')

    def invoke(self, context, event):
        self.query = SESSIONS[self.session_key].query
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        self.layout.prop(self, 'query')
        self.layout.label(text='Search reveals matching groups without changing folds')

    def execute(self, context):
        session = SESSIONS.get(self.session_key)
        if session:
            session.query = self.query.strip()
            session.scroll = 0
            session.refresh(context)
            redraw(session)
        return {'FINISHED'}


class AIRETOPO_OT_custom_section(bpy.types.Operator):
    bl_idname = 'wm.airetopo_custom_section'
    bl_label = 'Workflow Section'
    session_key: bpy.props.StringProperty()
    section: bpy.props.IntProperty()

    @classmethod
    def description(cls, context, properties):
        from .. import ui
        from ..localization import t
        panel = ui.SECTION_PANEL_CLASSES[max(0, min(12, properties.section))]
        return f'{panel.bl_order:02d} | {t(context, panel.bl_text_key)}'

    def execute(self, context):
        preferences(context).custom_ui_section = max(0, min(12, self.section))
        session = SESSIONS.get(self.session_key or key_for(context))
        if session:
            session.select(max(0, min(12, self.section)), self.section == 13)
            session.refresh(context)
            redraw(session)
        return {'FINISHED'}


class AIRETOPO_OT_custom_placement(bpy.types.Operator):
    """Move the toolkit between its sidebar and floating presentation."""
    bl_idname = 'wm.airetopo_custom_placement'
    bl_label = 'Move Custom UI'
    placement: bpy.props.EnumProperty(items=(('DOCKED', 'Sidebar', ''), ('FLOATING', 'Floating', '')))

    def execute(self, context):
        prefs = preferences(context)
        prefs.ui_mode = 'UI_PANEL'
        prefs.ui_panel_docked = self.placement == 'DOCKED'
        session = SESSIONS.get(key_for(context))
        if session:
            session.select(prefs.custom_ui_section)
            session.refresh(context)
        for area in context.screen.areas:
            area.tag_redraw()
        request_update()
        return {'FINISHED'}


class AIRETOPO_OT_reset_custom_appearance(bpy.types.Operator):
    bl_idname = 'wm.airetopo_reset_custom_appearance'
    bl_label = 'Reset Custom Appearance'

    def execute(self, context):
        prefs = preferences(context)
        for name in ('custom_ui_scale', 'custom_ui_accent', 'custom_ui_brightness', 'custom_ui_rounding'):
            prefs.property_unset(name)
        request_update()
        return {'FINISHED'}


class AIRETOPO_OT_custom_ui(bpy.types.Operator):
    bl_idname = 'wm.airetopo_custom_ui'
    bl_label = 'Open Custom AI Retopo UI'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and not bpy.app.background

    def invoke(self, context, event):
        global _autostart
        if context.region.type != 'WINDOW':
            region = next(r for r in context.area.regions if r.type == 'WINDOW')
            with context.temp_override(region=region):
                return bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
        key = key_for(context)
        if preferences(context).ui_mode != 'UI_PANEL':
            preferences(context).ui_mode = 'UI_PANEL'
        if key in SESSIONS:
            redraw(SESSIONS[key])
            return {'CANCELLED'}
        self.session = Session(context)
        SESSIONS[key] = self.session
        _autostart = False
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        s = self.session
        if s.closed or s.key not in SESSIONS or not _registered or preferences(context).ui_mode == 'CLASSIC':
            self.cancel(context)
            return {'CANCELLED'}
        if not resolve(s):
            return {'PASS_THROUGH'}
        if s.prefs.ui_mode != 'UI_PANEL':
            return {'PASS_THROUGH'}
        # After screen restoration Blender may deliver modal events without an
        # Area context. Bind the live editor before invoking any native operator.
        with context.temp_override(window=s.window, area=s.area, region=s.region):
            return self._modal_view(context, event)

    def _modal_view(self, context, event):
        s = self.session
        mx, my = event.mouse_x-s.region.x, event.mouse_y-s.region.y
        if s.edit:
            action = edit_key(s.edit, event, context.window_manager)
            if action == 'cancel':
                s.edit = None
            elif action == 'commit':
                try:
                    binding = s.model.bindings[s.edit['id']]
                    value = parsed_value(s.edit, s.edit['node'])
                    setattr(binding[1], binding[2], value)
                    s.edit = None
                    s.refresh(context)
                except (ValueError, KeyError, TypeError) as exc:
                    s.note = str(exc)
            redraw(s)
            return {'RUNNING_MODAL'}
        if s.slider:
            if event.type == 'ESC' and event.value == 'PRESS':
                s.slider = None
            elif event.type == 'MOUSEMOVE':
                state = s.slider
                frac = max(0, min(1, (mx-state['x'])/state['width']))
                state['value'] = state['min'] + frac*(state['max']-state['min'])
                if state['type'] == 'INT':
                    state['value'] = round(state['value'])
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                binding = s.model.bindings.get(s.slider['id'])
                if binding:
                    setattr(binding[1], binding[2], s.slider['value'])
                s.slider = None
                s.refresh(context)
            redraw(s)
            return {'RUNNING_MODAL'}
        if s.dropdown:
            if event.type == 'ESC' and event.value == 'PRESS':
                s.dropdown = None
            elif event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
                count = len(s.dropdown['node']['options'])
                s.dropdown['offset'] = max(0,min(max(0,count-8),s.dropdown['offset']+(-1 if event.type=='WHEELUPMOUSE' else 1)))
            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                hit = s.find(mx,my)
                if hit and hit[1][0] == 'choice':
                    binding = s.model.bindings.get(s.dropdown['id'])
                    if binding:
                        value = hit[1][1]
                        if s.dropdown['node'].get('enum_flag'):
                            values = set(getattr(binding[1],binding[2]))
                            values.symmetric_difference_update({value})
                            value = values
                        setattr(binding[1],binding[2],value)
                    s.dropdown = None
                    s.refresh(context)
                else:
                    s.dropdown = None
            redraw(s)
            return {'RUNNING_MODAL'}
        if s.drag:
            action, sx, sy, original = s.drag
            if event.type == 'ESC' and event.value == 'PRESS':
                s.x, s.y, s.width, s.height = original
                s.drag = None
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                s.drag = None
                s.prefs.custom_ui_geometry = (s.x,s.y,s.width,s.height)
            elif event.type == 'MOUSEMOVE':
                dx, dy = (mx-sx)/s.scale, (my-sy)/s.scale
                ox, oy, ow, oh = original
                if action == 'move':
                    s.x, s.y = max(0, ox+dx), max(0, oy-dy)
                else:
                    s.width, s.height = max(360, ow+dx), max(240, oh-dy)
            redraw(s)
            return {'RUNNING_MODAL'}
        hit = s.find(mx, my)
        x, top, width, h = s.geometry(s.region)
        inside = x <= mx <= x+width and top-h <= my <= top
        if event.type == 'MOUSEMOVE':
            identity = hit[3] if hit else ''
            if identity != s.hover or (hit[2] if hit else '') != s.tooltip:
                s.hover, s.tooltip = identity, hit[2] if hit else ''
                s.hover_since = time.monotonic()
                redraw(s)
            s.mouse = mx, my
            return {'PASS_THROUGH'}
        if not inside:
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            s.scroll = min(s.max_scroll, max(0, s.scroll + (-70 if event.type == 'WHEELUPMOUSE' else 70)*s.scale))
            redraw(s)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if hit:
                action = hit[1]
                s.note = ''
                if action[0] == 'dock':
                    bpy.ops.wm.airetopo_custom_placement(placement='FLOATING' if s.prefs.ui_panel_docked else 'DOCKED')
                elif action[0] == 'binding':
                    _dispatch(s, action[1])
                elif action[0] == 'slider':
                    node = next(n for n in walk(s.model.node) if n['id'] == action[1])
                    s.slider = dict(id=node['id'], x=hit[0][0], width=hit[0][2],
                        min=node['soft_min'], max=node['soft_max'], type=node['type'], value=node['value'])
                    fraction = max(0,min(1,(mx-hit[0][0])/hit[0][2]))
                    s.slider['value'] = node['soft_min']+fraction*(node['soft_max']-node['soft_min'])
                    if node['type']=='INT':
                        s.slider['value'] = round(s.slider['value'])
                elif action[0] == 'section':
                    s.select(action[1])
                    s.refresh(context)
                elif action[0] == 'header':
                    s.select(s.section, True)
                    s.refresh(context)
                elif action[0] == 'classic':
                    preferences(context).ui_mode = 'CLASSIC'
                elif action[0] == 'close':
                    self.cancel(context)
                    return {'CANCELLED'}
                elif action[0] == 'collapse':
                    s.collapsed = not s.collapsed
                elif action[0] in {'move', 'resize'}:
                    if s.prefs.ui_panel_docked:
                        return {'RUNNING_MODAL'}
                    s.drag = (action[0], mx, my, (s.x, s.y, s.width, s.height))
                elif action[0] == 'search':
                    bpy.ops.wm.airetopo_custom_search('INVOKE_DEFAULT', session_key=s.key)
                elif action[0] == 'sections':
                    def menu(menu_self, menu_context):
                        for index, title in enumerate(s.titles + ['Session / Settings']):
                            op = menu_self.layout.operator('wm.airetopo_custom_section', text=title)
                            op.session_key, op.section = s.key, index
                    context.window_manager.popup_menu(menu, title='AI Retopo Toolkit')
                elif action[0] in {'expand', 'fold'}:
                    for node in walk(s.model.node):
                        if node['kind'] == 'group':
                            binding = s.model.bindings[node['id']]
                            setattr(binding[1], binding[2], action[0] == 'expand')
                    s.refresh(context)
            redraw(s)
            return {'RUNNING_MODAL'}
        # Keyboard shortcuts and other modal tools retain viewport control.
        return {'PASS_THROUGH'}

    def cancel(self, context):
        self.session.closed = True
        if SESSIONS.get(self.session.key) is self.session:
            SESSIONS.pop(self.session.key, None)
        redraw(self.session)


def _draw():
    context = bpy.context
    if not context.window or not context.area or not context.region or context.region.type != 'WINDOW':
        return
    session = SESSIONS.get(key_for(context))
    if session and not session.closed and session.prefs.ui_mode == 'UI_PANEL':
        try:
            started = time.perf_counter()
            renderer.draw(session, context.region)
            session.draw_ms = (time.perf_counter()-started)*1000
        except Exception as exc:
            print('AI Retopo Custom UI renderer:', exc)
            session.note = str(exc)
            session.closed = True
            preferences(context).ui_mode = 'CLASSIC'


def cleanup():
    for session in list(SESSIONS.values()):
        session.closed = True
    SESSIONS.clear()
    renderer.clear()


@persistent
def _load_pre(_):
    cleanup()


@persistent
def _load_post(_):
    if _handle:
        bpy.app.driver_namespace[_HANDLE_KEY] = _handle
        bpy.app.driver_namespace[_CLEANUP_KEY] = unregister
    request_update()


def request_update():
    global _autostart
    _autostart = True
    if _registered and not bpy.app.background and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=.1)


def _tick():
    global _autostart
    if not _registered or bpy.app.background:
        return None
    prefs = preferences()
    if not prefs or prefs.ui_mode == 'CLASSIC':
        cleanup()
        return .5
    if prefs.ui_mode != 'UI_PANEL':
        return .5
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                key = key_for(bpy.context)
                session = SESSIONS.get(key)
                if session:
                    session.window, session.area, session.region = window, area, region
                    try:
                        if session.refresh(bpy.context) or (session.tooltip and .6 < session.tooltip_age < 1.2):
                            area.tag_redraw()
                    except (ReferenceError, RuntimeError) as exc:
                        session.note = str(exc)
                elif _autostart:
                    try:
                        bpy.ops.wm.airetopo_custom_ui('INVOKE_DEFAULT')
                    except Exception as exc:
                        print('AI Retopo Custom UI startup:', exc)
                        prefs.ui_mode = 'CLASSIC'
    # Hidden editors remain parked during maximization and native file browsers.
    # Their modal handlers must never dereference the old Area/Region wrappers.
    windows = {str(w.as_pointer()) for w in bpy.context.window_manager.windows}
    spaces = {str(space.as_pointer()) for screen in bpy.data.screens
              for area in screen.areas for space in area.spaces}
    for key in list(SESSIONS):
        window_id, space_id = key.split(':')
        if window_id not in windows or space_id not in spaces:
            SESSIONS.pop(key).closed = True
    _autostart = False
    return .5


CLASSES = (AIRETOPO_OT_custom_property, AIRETOPO_OT_custom_search, AIRETOPO_OT_custom_section,
           AIRETOPO_OT_custom_placement, AIRETOPO_OT_reset_custom_appearance, AIRETOPO_OT_custom_ui)


def register():
    global _handle, _registered
    if _registered:
        return
    old_cleanup = bpy.app.driver_namespace.get(_CLEANUP_KEY)
    if old_cleanup and old_cleanup is not unregister:
        old_cleanup()
    old = bpy.app.driver_namespace.pop(_HANDLE_KEY, None)
    if old:
        bpy.types.SpaceView3D.draw_handler_remove(old, 'WINDOW')
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _registered = True
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')
        bpy.app.driver_namespace[_HANDLE_KEY] = _handle
        bpy.app.driver_namespace[_CLEANUP_KEY] = unregister
        bpy.app.handlers.load_pre.append(_load_pre)
        bpy.app.handlers.load_post.append(_load_post)
        request_update()


def unregister():
    global _handle, _registered
    if not _registered:
        return
    _registered = False
    cleanup()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    bpy.app.driver_namespace.pop(_HANDLE_KEY, None)
    bpy.app.driver_namespace.pop(_CLEANUP_KEY, None)
    for collection, handler in ((bpy.app.handlers.load_pre, _load_pre), (bpy.app.handlers.load_post, _load_post)):
        if handler in collection:
            collection.remove(handler)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
