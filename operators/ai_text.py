"""Asynchronous text generation; only the main-thread timer touches Blender."""
import queue
import threading
import uuid
import bpy
from bpy.app.handlers import persistent
from .ai_generation import _get_api_key
from ..services.ai_text import generate_text, TextGenerationError

PROVIDERS = (('OPENAI', 'OpenAI', ''), ('GOOGLE', 'Google', ''))
_results = queue.Queue()
_jobs = {}


def settings_for(scene, provider):
    return getattr(scene, 'airetopo_google_text_settings' if provider == 'GOOGLE' else 'airetopo_openai_text_settings')


def _worker(token, provider, key, model, prompt, instructions, limit):
    try:
        text, status = generate_text(provider, key, model, prompt, instructions, limit)
        result = (text, status)
    except TextGenerationError as error:
        result = (None, str(error))
    except Exception:
        result = (None, 'Text generation failed unexpectedly')
    _results.put((token, result))


def _apply_results():
    while not _results.empty():
        token, (text, status) = _results.get_nowait()
        job = _jobs.pop(token, None)
        if job is None:
            continue
        scene, provider, model = job
        try:
            settings = settings_for(scene, provider)
            settings.is_generating = False
            settings.last_status = status + ' | ' + model
            if text is not None:
                document = bpy.data.texts.new(provider.title() + ' Text Result')
                document.write(text)
                settings.result_text = document
        except ReferenceError:
            continue
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return .2 if _jobs else None


@persistent
def stop_text_jobs(*args):
    for scene, provider, model in list(_jobs.values()):
        try:
            settings = settings_for(scene, provider)
            settings.is_generating = False
            settings.last_status = 'Cancelled locally; a submitted API request may still finish'
        except ReferenceError:
            pass
    _jobs.clear()
    if bpy.app.timers.is_registered(_apply_results):
        bpy.app.timers.unregister(_apply_results)
    while not _results.empty():
        _results.get_nowait()


class OBJECT_OT_airetopo_generate_text(bpy.types.Operator):
    bl_idname = 'object.airetopo_generate_text'
    bl_label = 'Generate Text'
    bl_description = 'Generate text or translate using the existing provider API key'
    provider: bpy.props.EnumProperty(items=PROVIDERS)

    def execute(self, context):
        s = settings_for(context.scene, self.provider)
        if s.is_generating:
            return {'CANCELLED'}
        prompt = s.input_text.as_string() if s.input_text is not None else s.prompt
        model = s.custom_model.strip() if s.model == 'CUSTOM' else s.model
        if not prompt.strip() or not model:
            self.report({'WARNING'}, 'Enter source text and a model ID')
            return {'CANCELLED'}
        instructions = s.instructions.strip()
        if s.task == 'TRANSLATE':
            if not s.language.strip():
                self.report({'WARNING'}, 'Enter a target language')
                return {'CANCELLED'}
            instructions = ('Translate the user text into ' + s.language.strip() +
                            '. Preserve formatting and meaning. Return only the translation.\n' + instructions)
        key = _get_api_key(context, self.provider)
        if not key:
            s.last_status = self.provider + ' API key is missing in addon preferences'
            self.report({'WARNING'}, s.last_status)
            return {'CANCELLED'}
        token = uuid.uuid4().hex
        _jobs[token] = (context.scene, self.provider, model)
        s.is_generating = True
        s.last_status = 'Generating | ' + model
        try:
            threading.Thread(target=_worker, args=(token, self.provider, key, model, prompt, instructions, s.max_tokens), daemon=True).start()
            if not bpy.app.timers.is_registered(_apply_results):
                bpy.app.timers.register(_apply_results, first_interval=.2)
        except Exception:
            _jobs.pop(token, None)
            s.is_generating = False
            s.last_status = 'Could not start text generation'
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_airetopo_text_document(bpy.types.Operator):
    bl_idname = 'object.airetopo_text_document'
    bl_label = 'Text Document'
    provider: bpy.props.EnumProperty(items=PROVIDERS)
    action: bpy.props.EnumProperty(items=(('INPUT', 'Edit Multiline Input', ''), ('RESULT', 'Open Result', ''),
                                        ('COPY', 'Copy Result', ''), ('PASTE', 'Paste Multiline Input', '')))

    def execute(self, context):
        s = settings_for(context.scene, self.provider)
        if self.action == 'COPY':
            if s.result_text is None:
                return {'CANCELLED'}
            context.window_manager.clipboard = s.result_text.as_string()
            return {'FINISHED'}
        if self.action in {'INPUT', 'PASTE'}:
            if s.input_text is None:
                s.input_text = bpy.data.texts.new(self.provider.title() + ' Text Input')
                s.input_text.write(s.prompt)
            document = s.input_text
            if self.action == 'PASTE':
                document.clear()
                document.write(context.window_manager.clipboard)
                return {'FINISHED'}
        else:
            document = s.result_text
        if document is None:
            return {'CANCELLED'}
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'TEXT_EDITOR':
                    area.spaces.active.text = document
                    return {'FINISHED'}
        if bpy.app.background:
            return {'FINISHED'}
        previous = set(context.window_manager.windows)
        bpy.ops.wm.window_new()
        window = next((w for w in context.window_manager.windows if w not in previous), None)
        if window:
            area = max(window.screen.areas, key=lambda a: a.width*a.height)
            area.type = 'TEXT_EDITOR'
            area.spaces.active.text = document
        return {'FINISHED'}


CLASSES = (OBJECT_OT_airetopo_generate_text, OBJECT_OT_airetopo_text_document)


def register():
    from . import asset_translation
    asset_translation.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_text_jobs not in handlers:
            handlers.append(stop_text_jobs)


def unregister():
    from . import asset_translation
    asset_translation.unregister()
    stop_text_jobs()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_text_jobs in handlers:
            handlers.remove(stop_text_jobs)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
