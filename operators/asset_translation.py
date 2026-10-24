"""Nonblocking Asset Name translation; Blender data is only changed on the main thread."""
import queue
import threading
import uuid
import bpy
from bpy.app.handlers import persistent
from .ai_generation import _get_api_key, _get_preferences
from ..services.asset_translation import translate_asset_name
from ..services.ai_text import TextGenerationError

FIELDS = ('fab_asset_name', 'unity_asset_name', 'unreal_lod_asset_name', 'asset')
_jobs = {}
_results = queue.Queue()
_dialogs = {}
_status = {}


def bind_dialog(target):
    token = uuid.uuid4().hex
    _dialogs[token] = target
    return token


def release_dialog(token):
    target = _dialogs.pop(token, None)
    if target is not None:
        for key, job in list(_jobs.items()):
            if job[0] == target:
                _jobs.pop(key, None)
        _status.pop((target.as_pointer(), 'asset'), None)


def busy(target, field):
    return any(job[0] == target and job[1] == field for job in _jobs.values())


def draw_asset_name(layout, context, target, field, text='Asset Name', dialog=''):
    row = layout.row(align=True)
    row.prop(target, field, text=text)
    button = row.row(align=True)
    button.enabled = not busy(target, field)
    op = button.operator('object.polygroups_translate_asset_name', text='', icon='WORLD')
    op.field = field
    op.dialog = dialog
    status = _status.get((target.as_pointer(), field), '')
    if status:
        layout.label(text=status, icon='INFO')


def _worker(token, provider, key, model, source):
    try:
        result = translate_asset_name(provider, key, model, source)
        error = ''
    except TextGenerationError as exc:
        result, error = None, str(exc)
    except Exception:
        result, error = None, 'Translation failed; original name retained'
    _results.put((token, result, error))


def _apply_results():
    while not _results.empty():
        token, result, error = _results.get_nowait()
        job = _jobs.pop(token, None)
        if job is None:
            continue
        target, field, source, model = job
        try:
            key = (target.as_pointer(), field)
            if getattr(target, field) != source:
                _status[key] = 'Name changed while translating; result skipped'
            elif result is None:
                _status[key] = error
            else:
                setattr(target, field, result)
                _status[key] = 'Translated | ' + model
        except (ReferenceError, RuntimeError):
            continue
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return .2 if _jobs else None


@persistent
def stop_translation_jobs(*args):
    _jobs.clear()
    _dialogs.clear()
    _status.clear()
    if bpy.app.timers.is_registered(_apply_results):
        bpy.app.timers.unregister(_apply_results)
    while not _results.empty():
        _results.get_nowait()


class OBJECT_OT_translate_asset_name(bpy.types.Operator):
    bl_idname = 'object.polygroups_translate_asset_name'
    bl_label = 'Translate Asset Name to English'
    bl_description = 'Translate into English with underscores using the default text model from API preferences'
    field: bpy.props.EnumProperty(items=[(name, name, '') for name in FIELDS])
    dialog: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        target = _dialogs.get(self.dialog) if self.dialog else context.scene.polygroups_mesh_finalization_settings
        if target is None or (self.field == 'asset' and not self.dialog):
            return {'CANCELLED'}
        if busy(target, self.field):
            return {'CANCELLED'}
        source = getattr(target, self.field).strip()
        if not source:
            self.report({'WARNING'}, 'Enter an Asset Name first')
            return {'CANCELLED'}
        preferences = _get_preferences(context)
        model = preferences.default_text_task_model if preferences else 'gpt-6-luna'
        provider = 'GOOGLE' if model.startswith('gemini-') else 'OPENAI'
        key = _get_api_key(context, provider)
        if not key:
            self.report({'WARNING'}, provider + ' API key is missing in addon preferences')
            return {'CANCELLED'}
        token = uuid.uuid4().hex
        _jobs[token] = (target, self.field, getattr(target, self.field), model)
        _status[(target.as_pointer(), self.field)] = 'Translating | ' + model
        try:
            threading.Thread(target=_worker, args=(token, provider, key, model, source), daemon=True).start()
            if not bpy.app.timers.is_registered(_apply_results):
                bpy.app.timers.register(_apply_results, first_interval=.2)
        except Exception:
            _jobs.pop(token, None)
            _status[(target.as_pointer(), self.field)] = 'Could not start translation'
            return {'CANCELLED'}
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_translate_asset_name)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_translation_jobs not in handlers:
            handlers.append(stop_translation_jobs)


def unregister():
    stop_translation_jobs()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_translation_jobs in handlers:
            handlers.remove(stop_translation_jobs)
    bpy.utils.unregister_class(OBJECT_OT_translate_asset_name)
