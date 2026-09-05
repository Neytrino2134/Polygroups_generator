"""Independent group windows; native Windows pinning is limited to this process."""
import os
import sys

import bpy

WINDOW_GROUPS = {}


def _windows_api():
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('user32', use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    api.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.IsWindowVisible.argtypes = [wintypes.HWND]
    api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    api.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    return ctypes, wintypes, api, callback


def own_windows():
    if sys.platform != 'win32':
        return set()
    ctypes, types, api, callback = _windows_api()
    handles = set()
    @callback
    def visit(hwnd, _):
        pid = types.DWORD()
        api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid() and api.IsWindowVisible(hwnd):
            handles.add(hwnd)
        return True
    api.EnumWindows(visit, 0)
    return handles


def pin_window(handle, pinned, title=None):
    if not handle or handle not in own_windows():
        return False
    _, _, api, _ = _windows_api()
    if title:
        api.SetWindowTextW(handle, 'AI Retopo | ' + title)
    return bool(api.SetWindowPos(handle, -1 if pinned else -2, 0, 0,
                                600 if title else 0, 650 if title else 0,
                                0x0010 | 0x0002 | (0 if title else 0x0001)))


def draw_window_group(context, layout):
    live = {window.as_pointer() for window in context.window_manager.windows}
    for key in list(WINDOW_GROUPS):
        if key not in live:
            WINDOW_GROUPS.pop(key)
    state = WINDOW_GROUPS.get(context.window.as_pointer())
    if state is None:
        return False
    row = layout.row(align=True)
    row.operator('wm.airetopo_group_window_control', text='',
                 icon='TRIA_RIGHT' if state['collapsed'] else 'TRIA_DOWN').action = 'COLLAPSE'
    row.label(text=state['title'])
    row.operator('wm.airetopo_group_window_control', text='',
                 icon='PINNED' if state['pinned'] else 'UNPINNED', depress=state['pinned']).action = 'PIN'
    row.operator('wm.airetopo_group_window_control', text='', icon='X').action = 'CLOSE'
    if not state['collapsed']:
        from ..ui import draw_detached_group
        draw_detached_group(context, layout, state['section'], state['group'])
    return True


class WM_OT_airetopo_detach_group(bpy.types.Operator):
    bl_idname = 'wm.airetopo_detach_group'
    bl_label = 'Open Group in New Window'
    bl_description = 'Duplicate this group in an independent window, pinned on top on Windows'
    section: bpy.props.StringProperty()
    group: bpy.props.StringProperty()
    title: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return not bpy.app.background and context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        before = {window.as_pointer() for window in context.window_manager.windows}
        native_before = own_windows()
        result = bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
        if 'FINISHED' not in result:
            return {'CANCELLED'}
        new = next((w for w in context.window_manager.windows if w.as_pointer() not in before), None)
        if new is None:
            self.report({'ERROR'}, 'Blender did not create a group window')
            return {'CANCELLED'}
        state = dict(section=self.section, group=self.group, title=self.title,
                     collapsed=False, pinned=False, handle=None)
        window_id = new.as_pointer()
        WINDOW_GROUPS[window_id] = state
        attempts = 0
        def configure():
            nonlocal attempts
            attempts += 1
            target = next((w for w in bpy.context.window_manager.windows if w.as_pointer() == window_id), None)
            if target is None:
                return None
            for area in target.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.show_region_ui = True
                    area.spaces.active.show_region_toolbar = False
                    for region in area.regions:
                        if region.type == 'UI':
                            try:
                                region.active_panel_category = 'AI Retopo'
                            except AttributeError:
                                area.tag_redraw()
                                return .2 if attempts < 10 else None
                    area.tag_redraw()
            handles = own_windows() - native_before
            if len(handles) == 1:
                state['handle'] = handles.pop()
                state['pinned'] = pin_window(state['handle'], True, state['title'])
                return None
            return .2 if attempts < 10 and sys.platform == 'win32' else None
        bpy.app.timers.register(configure, first_interval=.2)
        return {'FINISHED'}


class WM_OT_airetopo_group_window_control(bpy.types.Operator):
    bl_idname = 'wm.airetopo_group_window_control'
    bl_label = 'Group Window'
    action: bpy.props.EnumProperty(items=[('COLLAPSE','Collapse / Expand',''), ('PIN','Always on Top',''), ('CLOSE','Close','')])

    def execute(self, context):
        state = WINDOW_GROUPS.get(context.window.as_pointer())
        if state is None:
            return {'CANCELLED'}
        if self.action == 'CLOSE':
            WINDOW_GROUPS.pop(context.window.as_pointer(), None)
            return bpy.ops.wm.window_close('EXEC_DEFAULT')
        if self.action == 'COLLAPSE':
            state['collapsed'] = not state['collapsed']
        elif pin_window(state['handle'], not state['pinned']):
            state['pinned'] = not state['pinned']
        else:
            self.report({'WARNING'}, 'Native window pinning is unavailable')
        context.area.tag_redraw()
        return {'FINISHED'}


def cleanup_windows():
    for state in WINDOW_GROUPS.values():
        if state['pinned']:
            pin_window(state['handle'], False)
    WINDOW_GROUPS.clear()
