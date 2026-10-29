"""Pause between Phase 1 and Phase 2 when Phase 1 had errors.

A 15 second countdown lets the user fix the failed Generated.N files; when it ends Phase 2
starts by itself. Pause keeps Phase 2 waiting, and the Phase 1, 2 import and Start Phase 2
buttons turn into Resume Phase 2 until it is resumed.
"""
import time

import bpy

GATE_SECONDS = 15.0
MAX_LISTED = 8
STATE = dict(mode='IDLE', deadline=0.0, failures=[], scene=None, view_layer=None, report=None)


def active():
    return STATE['mode'] != 'IDLE'


def paused():
    return STATE['mode'] == 'PAUSED'


def seconds_left():
    return max(0.0, STATE['deadline'] - time.monotonic())


def redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except (AttributeError, RuntimeError, ReferenceError):
        pass


def clear():
    STATE.update(mode='IDLE', deadline=0.0, failures=[], scene=None, view_layer=None, report=None)
    redraw()


def begin(scene, view_layer, report, failures):
    """Start the countdown and show the dialog."""
    STATE.update(mode='COUNTDOWN', deadline=time.monotonic() + GATE_SECONDS, failures=list(failures),
                 scene=scene, view_layer=view_layer, report=report)
    bpy.app.timers.register(_tick, first_interval=0.5)
    if not bpy.app.background:
        bpy.app.timers.register(_show_dialog, first_interval=0.3)
    redraw()


def pause():
    if STATE['mode'] != 'COUNTDOWN':
        return
    STATE['mode'] = 'PAUSED'
    from ..core.run_progress import end_combined
    end_combined()
    redraw()


def proceed():
    """Start Phase 2 now (from the countdown, its end, or a pause)."""
    if not active():
        return
    from .import_queue import schedule_phase2
    scene, view_layer, report = STATE['scene'], STATE['view_layer'], STATE['report']
    clear()
    try:
        schedule_phase2(scene, view_layer, report or (lambda *_: None))
    except ReferenceError:
        pass


def _tick():
    if STATE['mode'] != 'COUNTDOWN':
        return None
    if seconds_left() <= 0:
        proceed()
        return None
    redraw()
    return 0.5


def _show_dialog():
    if STATE['mode'] != 'COUNTDOWN':
        return None
    context = bpy.context
    window = next(iter(context.window_manager.windows), None)
    if window is not None:
        with context.temp_override(window=window):
            try:
                bpy.ops.object.polygroups_phase2_gate_dialog('INVOKE_DEFAULT')
            except RuntimeError:
                pass
    return None


def draw_failures(layout):
    for item in STATE['failures'][:MAX_LISTED]:
        where = item.get('collection') or item.get('file') or '?'
        stage = f" ({item['failed_stage']}" + (f", pass {item['failed_pass']})" if item.get('failed_pass') else ')') \
            if item.get('failed_stage') else ''
        layout.label(text=f'{where}{stage}', icon='ERROR')
    if len(STATE['failures']) > MAX_LISTED:
        layout.label(text=f"... and {len(STATE['failures']) - MAX_LISTED} more")


def draw_status(layout):
    """Countdown or pause box for the add-on panel; draws nothing when idle."""
    if not active():
        return
    box = layout.box()
    if paused():
        box.label(text='Phase 2 paused: fix the failed files, then resume', icon='PAUSE')
    else:
        box.label(text=f'Phase 1 had errors. Phase 2 starts in {seconds_left():.0f} s', icon='TIME')
    draw_failures(box.column(align=True))
    row = box.row(align=True)
    if not paused():
        row.operator('object.polygroups_phase2_gate', text='Pause', icon='PAUSE').action = 'PAUSE'
    row.operator('object.polygroups_phase2_gate', text='Resume Phase 2' if paused() else 'Continue Now',
                 icon='PLAY').action = 'CONTINUE'


class OBJECT_OT_polygroups_phase2_gate(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_gate'
    bl_label = 'Phase 2 Start Gate'
    bl_description = 'Pause the automatic Phase 2 start after Phase 1 errors, or continue now'
    bl_options = {'INTERNAL'}
    action: bpy.props.EnumProperty(items=(('PAUSE', 'Pause', ''), ('CONTINUE', 'Continue', '')),
                                   options={'SKIP_SAVE'})

    def execute(self, context):
        if self.action == 'PAUSE':
            pause()
        else:
            proceed()
        return {'FINISHED'}


class OBJECT_OT_polygroups_phase2_gate_dialog(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_gate_dialog'
    bl_label = 'Phase 1 finished with errors'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if STATE['mode'] != 'COUNTDOWN':
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text='Continue Now')

    def draw(self, context):
        layout = self.layout
        if not active():
            layout.label(text='Phase 2 has started')
            return
        if paused():
            layout.label(text='Phase 2 paused', icon='PAUSE')
        else:
            layout.label(text=f'Phase 2 starts in {seconds_left():.0f} s', icon='TIME')
        layout.label(text='These Generated.N files did not finish; Phase 2 will skip them:')
        draw_failures(layout.column(align=True))
        layout.label(text='Fix the files now, or pause Phase 2.')
        if not paused():
            layout.operator('object.polygroups_phase2_gate', text='Pause Phase 2', icon='PAUSE').action = 'PAUSE'

    def execute(self, context):
        proceed()
        return {'FINISHED'}


CLASSES = (OBJECT_OT_polygroups_phase2_gate, OBJECT_OT_polygroups_phase2_gate_dialog)
