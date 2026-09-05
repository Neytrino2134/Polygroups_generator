"""Authenticated loopback bridge. All bpy work runs in the main-thread timer."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import bpy
from bpy.app.handlers import persistent

SESSIONS = []
MAX_MESSAGE = 1024 * 1024


def python_runtime(context):
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    configured = getattr(prefs, 'panel_python_executable', '')
    candidates = [bpy.path.abspath(configured)] if configured else []
    candidates += [shutil.which('python'), str(Path(bpy.app.binary_path).parent / '5.2/python/bin/python.exe')]
    for path in dict.fromkeys(p for p in candidates if p):
        try:
            probe = subprocess.run([path, '-c', 'import tkinter'], timeout=8,
                                   capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if probe.returncode == 0:
                return path
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError('Set Python with Tkinter in add-on preferences → Floating Windows.')


class Session:
    def __init__(self, context, section, group, title, runtime):
        self.window, self.area = context.window.as_pointer(), context.area.as_pointer()
        self.section, self.group, self.title = section, group, title
        self.token = secrets.token_hex(32)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.setblocking(False)
        self.connection = None
        self.authenticated = False
        self.incoming, self.outgoing = b'', b''
        self.bindings, self.revision = {}, ''
        self.last_model, self.next_refresh = None, 0
        self.created = time.monotonic()
        env = os.environ.copy()
        env['AIRETOPO_PANEL_PORT'] = str(self.listener.getsockname()[1])
        env['AIRETOPO_PANEL_TOKEN'] = self.token
        env['AIRETOPO_PANEL_CONFIG'] = str(Path(bpy.utils.user_resource('CONFIG')) / 'airetopo_windows')
        client = Path(__file__).resolve().parents[1] / 'standalone_ui' / 'client.py'
        try:
            self.process = subprocess.Popen([runtime, str(client)], env=env,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            self.listener.close()
            raise

    def close(self):
        if self.connection:
            self.connection.close()
        self.listener.close()
        if self.process.poll() is None:
            self.process.terminate()

    def send(self, message):
        self.outgoing += (json.dumps(message, ensure_ascii=False) + '\n').encode('utf8')
        if len(self.outgoing) > MAX_MESSAGE * 2:
            raise RuntimeError('Panel client is not responding')

    def context(self):
        window = next((w for w in bpy.context.window_manager.windows if w.as_pointer() == self.window), None)
        if window is None:
            raise RuntimeError('Source Blender window was closed')
        area = next((a for a in window.screen.areas if a.as_pointer() == self.area and a.type == 'VIEW_3D'), None)
        if area is None:
            area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
        if area is None:
            raise RuntimeError('Open a 3D View in the source Blender window')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        return bpy.context.temp_override(window=window, area=area, region=region)

    def model(self):
        from .. import ui
        from ..core.window_schema import Layout
        layout = Layout()
        ui.draw_detached_group(bpy.context, layout, self.section, self.group)
        identities = []
        for key, binding in layout.bindings.items():
            kind, target, name, extra = binding
            identities.append((key, kind, target if kind == 'operator' else target.path_from_id(),
                               vars(name) if kind == 'operator' else name, extra))
        fingerprint = json.dumps([identities, [{k: v for k, v in i.items() if k not in {'value', 'enabled'}} for i in layout.items]], default=str)
        for identity in identities:
            layout.items[int(identity[0])]['key'] = hashlib.sha256(json.dumps(identity[1:], default=str).encode()).hexdigest()[:20]
        self.revision = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        self.bindings = layout.bindings
        active = bpy.context.active_object
        return dict(type='model', title=self.title, section=self.section, group=self.group,
                    revision=self.revision, items=layout.items,
                    context=f'{bpy.context.mode} · {active.name if active else "No active object"}')

    def handle(self, message):
        if not self.authenticated:
            if not secrets.compare_digest(str(message.get('token', '')), self.token):
                raise RuntimeError('Invalid panel token')
            self.authenticated = True
            with self.context():
                from ..ui import collect_window_groups
                self.send(dict(type='catalog', groups=collect_window_groups(bpy.context)))
            return
        command = message.get('type')
        if command == 'select':
            from ..ui import collect_window_groups
            with self.context():
                match = next((g for g in collect_window_groups(bpy.context)
                              if g['section'] == message.get('section') and g['group'] == message.get('group')), None)
            if match:
                self.section, self.group, self.title = match['section'], match['group'], match['title']
                self.last_model = None
                self.next_refresh = 0
            return
        if command != 'action':
            return
        try:
            with self.context():
                current = self.model()
                if message.get('revision') != self.revision:
                    raise RuntimeError('Controls changed in Blender. Please try again.')
                control = next((i for i in current['items'] if i['id'] == message.get('id')), None)
                if not control or not control['enabled'] or control['id'] not in self.bindings:
                    raise RuntimeError('This control is currently unavailable')
                from ..core.window_schema import apply
                apply(self.bindings[control['id']], message.get('value'))
                for area in bpy.context.screen.areas:
                    area.tag_redraw()
            self.send(dict(type='result', ok=True, text='Applied · interactive tools continue in Blender'))
        except Exception as error:
            self.send(dict(type='result', ok=False, text=str(error)))
        self.next_refresh = 0

    def tick(self):
        if self.process.poll() is not None:
            return False
        if self.connection is None:
            try:
                self.connection, _ = self.listener.accept()
                self.connection.setblocking(False)
            except BlockingIOError:
                return time.monotonic() - self.created < 30
        try:
            data = self.connection.recv(65536)
            if not data:
                return False
            self.incoming += data
        except BlockingIOError:
            pass
        if len(self.incoming) > MAX_MESSAGE:
            return False
        for _ in range(12):
            if b'\n' not in self.incoming:
                break
            line, self.incoming = self.incoming.split(b'\n', 1)
            self.handle(json.loads(line))
        now = time.monotonic()
        if self.authenticated and now >= self.next_refresh:
            with self.context():
                model = self.model()
            if model != self.last_model:
                self.send(model)
                self.last_model = model
            self.next_refresh = now + .4
        if self.outgoing:
            try:
                sent = self.connection.send(self.outgoing)
                self.outgoing = self.outgoing[sent:]
            except BlockingIOError:
                pass
        return self.authenticated or now - self.created < 30


def pump():
    for session in list(SESSIONS):
        try:
            live = session.tick()
        except Exception as error:
            print('AI Retopo window:', error)
            live = False
        if not live:
            session.close()
            SESSIONS.remove(session)
    return .05 if SESSIONS else None


@persistent
def cleanup_windows(*_):
    for session in SESSIONS:
        session.close()
    SESSIONS.clear()
    if bpy.app.timers.is_registered(pump):
        bpy.app.timers.unregister(pump)


class WM_OT_airetopo_detach_group(bpy.types.Operator):
    bl_idname = 'wm.airetopo_detach_group'
    bl_label = 'Open Floating Window'
    bl_description = 'Open independent, customizable controls without another 3D View'
    section: bpy.props.StringProperty()
    group: bpy.props.StringProperty()
    title: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return not bpy.app.background and context.area and context.area.type == 'VIEW_3D'

    def execute(self, context):
        try:
            runtime = python_runtime(context)
            SESSIONS.append(Session(context, self.section, self.group, self.title, runtime))
            if not bpy.app.timers.is_registered(pump):
                bpy.app.timers.register(pump, first_interval=.05)
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class WM_OT_airetopo_group_window_control(bpy.types.Operator):
    bl_idname = 'wm.airetopo_group_window_control'
    bl_label = 'Close All Floating Windows'
    def execute(self, context):
        cleanup_windows()
        return {'FINISHED'}
