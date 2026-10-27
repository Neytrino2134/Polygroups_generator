"""Nonblocking FAB JSON generation with main-thread inventory and result storage."""
import re
from pathlib import Path
import queue
import threading
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ExportHelper
from .ai_generation import _get_api_key
from ..services.ai_text import generate_text
from ..services import fab_media as media

_jobs = {}
_results = queue.Queue()


def _document(settings, prop, title, content):
    document = getattr(settings, prop)
    if document is None:
        document = bpy.data.texts.new(title)
        setattr(settings, prop, document)
    document.clear()
    document.write(content)
    return document


def _prepare(context, source=None):
    s = context.scene.airetopo_fab_media_settings
    source = media.inventory(context) if source is None else source
    hints = {key: getattr(s, key) for key in media.FIELD_DEFAULTS}
    notes = s.notes_text.as_string() if s.notes_text else s.notes
    document, prompt = media.prepare(hints, source, notes)
    for key in media.MEASURED:
        setattr(s, key, document['fields'][key])
    s.inventory_summary = document['fields']['assetsQuantityLine1'] + ' / ' + document['fields']['assetsQuantityLine2']
    if source['warnings']:
        s.inventory_summary += f' | {len(source["warnings"])} ignored meshes (see prompt)'
    _document(s, 'prompt_text', 'FAB Media Prompt', media.INSTRUCTIONS + '\n\n' + prompt)
    return document, prompt


def _worker(token, provider, key, model, prompt, limit, document):
    try:
        text, status = generate_text(provider, key, model, prompt, media.INSTRUCTIONS,
                                     limit, response_schema=media.SCHEMA)
        if status != 'Completed':
            raise ValueError('Incomplete response; increase Max Output Tokens and retry')
        content = media.dumps(media.finalize(text, document))
        result = content, 'JSON ready | ' + model
    except Exception as error:
        # Provider exceptions redact secrets; unexpected exceptions are kept generic.
        from ..services.ai_text import TextGenerationError
        result = None, str(error) if isinstance(error, (ValueError, TextGenerationError)) else 'JSON generation failed unexpectedly'
    _results.put((token, result))


def _apply_results():
    while not _results.empty():
        token, (content, status) = _results.get_nowait()
        scene = _jobs.pop(token, None)
        if scene is None:
            continue
        try:
            s = scene.airetopo_fab_media_settings
            s.is_generating = False
            s.last_status = status
            if content is not None:
                # A new document preserves previous results and any manual edits.
                s.result_text = bpy.data.texts.new('TexFlow FAB Media.json')
                s.result_text.write(content)
        except ReferenceError:
            pass
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return .2 if _jobs else None


@persistent
def stop_jobs(*args):
    for scene in list(_jobs.values()):
        try:
            scene.airetopo_fab_media_settings.is_generating = False
            scene.airetopo_fab_media_settings.last_status = 'Cancelled locally; submitted API requests may still finish'
        except ReferenceError:
            pass
    _jobs.clear()
    if bpy.app.timers.is_registered(_apply_results):
        bpy.app.timers.unregister(_apply_results)
    while not _results.empty():
        _results.get_nowait()


class OBJECT_OT_airetopo_fab_media(bpy.types.Operator):
    bl_idname = 'object.airetopo_fab_media'
    bl_label = 'FAB Media JSON'
    action: bpy.props.EnumProperty(items=[(key, key.title(), '') for key in (
        'FILL', 'CLEAR', 'GENERATE', 'PROMPT', 'RESULT', 'COPY', 'NOTES', 'CANCEL')])

    def execute(self, context):
        s = context.scene.airetopo_fab_media_settings
        if self.action == 'CANCEL':
            for token, scene in list(_jobs.items()):
                if scene == context.scene:
                    _jobs.pop(token)
            s.is_generating = False
            s.last_status = 'Cancelled locally; submitted API request may still finish'
            return {'FINISHED'}
        if self.action in {'FILL', 'CLEAR', 'GENERATE'} and s.is_generating:
            return {'CANCELLED'}
        try:
            if self.action == 'CLEAR':
                for key in media.FIELD_DEFAULTS:
                    setattr(s, key, '')
                s.notes = ''
                s.notes_text = None
                s.prompt_text = None
                s.result_text = None
                s.inventory_summary = ''
                s.last_status = 'Fields cleared'
                return {'FINISHED'}
            if self.action in {'FILL', 'GENERATE', 'PROMPT'}:
                source = None
                if s.is_generating:
                    return {'CANCELLED'}
                if self.action == 'FILL':
                    for key, default in media.FIELD_DEFAULTS.items():
                        if not getattr(s, key):
                            setattr(s, key, default)
                    if not s.assetHeadline:
                        source = media.inventory(context)
                        stem = source['assets'][0]['collection'][:-len('_Collection')]
                        s.assetHeadline = re.sub(r'_\d+(?:_\d+)*$', '', stem).removeprefix('SM_')
                    if not s.mainHeadline1:
                        words = s.assetHeadline.replace('_', ' ').split()
                        split = max(1, len(words) // 2)
                        s.mainHeadline1, s.mainHeadline2 = ' '.join(words[:split]), ' '.join(words[split:])
                document, prompt = _prepare(context, source)
                if self.action == 'FILL':
                    s.last_status = 'Fields filled; review pack facts and Nanite labels before generating'
                    return {'FINISHED'}
                if self.action == 'GENERATE':
                    provider = 'GOOGLE' if s.model.startswith('gemini-') else 'OPENAI'
                    key = _get_api_key(context, provider)
                    if not key:
                        raise ValueError(provider + ' API key is missing in addon preferences')
                    token = uuid.uuid4().hex
                    _jobs[token] = context.scene
                    s.is_generating = True
                    s.last_status = 'Generating | ' + s.model
                    try:
                        threading.Thread(target=_worker, args=(token, provider, key, s.model, prompt,
                                         s.max_tokens, document), daemon=True).start()
                        if not bpy.app.timers.is_registered(_apply_results):
                            bpy.app.timers.register(_apply_results, first_interval=.2)
                    except Exception:
                        _jobs.pop(token, None)
                        s.is_generating = False
                        raise ValueError('Could not start JSON generation') from None
                    return {'FINISHED'}
            if self.action == 'COPY':
                if s.result_text is None:
                    raise ValueError('Generate JSON first')
                context.window_manager.clipboard = media.dumps(media.validate(s.result_text.as_string()))
                return {'FINISHED'}
            if self.action == 'NOTES' and s.notes_text is None:
                _document(s, 'notes_text', 'FAB Pack Facts', s.notes)
            prop = {'NOTES': 'notes_text', 'PROMPT': 'prompt_text', 'RESULT': 'result_text'}[self.action]
            document = getattr(s, prop)
            if document is None:
                raise ValueError('Generate JSON first')
            if not bpy.app.background:
                area = next((a for w in context.window_manager.windows for a in w.screen.areas
                             if a.type == 'TEXT_EDITOR'), None)
                if area is None:
                    previous = set(context.window_manager.windows)
                    bpy.ops.wm.window_new()
                    window = next(w for w in context.window_manager.windows if w not in previous)
                    area = max(window.screen.areas, key=lambda a: a.width * a.height)
                    area.type = 'TEXT_EDITOR'
                area.spaces.active.text = document
            return {'FINISHED'}
        except (ValueError, RuntimeError) as error:
            s.last_status = str(error)
            self.report({'WARNING'}, s.last_status)
            return {'CANCELLED'}


class OBJECT_OT_airetopo_save_fab_media(bpy.types.Operator, ExportHelper):
    bl_idname = 'object.airetopo_save_fab_media'
    bl_label = 'Save FAB Media JSON'
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})

    def invoke(self, context, event):
        if context.scene.airetopo_fab_media_settings.result_text is None:
            self.report({'WARNING'}, 'Generate JSON first')
            return {'CANCELLED'}
        self.filepath = str(Path(bpy.data.filepath).parent / 'texflow-fab-media.json') if bpy.data.filepath else 'texflow-fab-media.json'
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        s = context.scene.airetopo_fab_media_settings
        try:
            if s.result_text is None:
                raise ValueError('Generate JSON first')
            content = media.dumps(media.validate(s.result_text.as_string()))
            Path(self.filepath).write_text(content, encoding='utf-8')
        except (ValueError, OSError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        s.last_status = 'Saved: ' + self.filepath
        return {'FINISHED'}


CLASSES = (OBJECT_OT_airetopo_fab_media, OBJECT_OT_airetopo_save_fab_media)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_jobs not in handlers:
            handlers.append(stop_jobs)


def unregister():
    stop_jobs()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if stop_jobs in handlers:
            handlers.remove(stop_jobs)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
