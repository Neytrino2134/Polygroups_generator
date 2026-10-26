"""Cooperative rendering for the Phase 2 coordinator, using existing render setup."""
import re
import bpy
from ..core.render_progress import RenderProgressPreview


class PipelineRenderPreview(RenderProgressPreview):
    def __init__(self, context, run):
        super().__init__(context)
        self.run = run

    def draw(self):
        pass  # The universal pipeline overlay owns the lower-left status area.

    def render_steps(self, context, settings, job, completed, total):
        from .render_queue import _render_current_job_steps
        for options in _render_current_job_steps(context, settings, job):
            if bpy.app.background:
                result = bpy.ops.render.render(**options)
                if 'FINISHED' not in result:
                    raise RuntimeError('Render cancelled')
                yield (completed + 1)/max(1, total), f'Auto Render {completed+1}/{total}'
                continue
            state = dict(done=False, cancelled=False, percent=0)
            def complete(*_):
                state['done'] = True
            def cancel(*_):
                state['done'] = state['cancelled'] = True
            def stats(*args):
                text = ' '.join(str(arg) for arg in args if isinstance(arg, str))
                match = re.search(r'(?:Sample|Rendering)\s+(\d+)\s*/\s*(\d+)', text, re.I)
                if match and int(match[2]):
                    state['percent'] = 100*int(match[1])/int(match[2])
            callbacks = ((bpy.app.handlers.render_complete, complete),
                         (bpy.app.handlers.render_cancel, cancel),
                         (bpy.app.handlers.render_stats, stats))
            for handlers, callback in callbacks:
                handlers.append(callback)
            try:
                result = bpy.ops.render.render('INVOKE_DEFAULT', **options)
                if not ({'RUNNING_MODAL', 'FINISHED'} & result):
                    raise RuntimeError('Render could not start')
                if 'FINISHED' in result:
                    state['done'] = True
                while not state['done'] or bpy.app.is_job_running('RENDER'):
                    self.run.detail(state['percent'], f'Render {completed+1}/{total}')
                    yield (completed + state['percent']/100)/max(1, total), f'Rendering {completed+1}/{total}'
                if state['cancelled']:
                    raise RuntimeError('Render cancelled; completed files retained')
            finally:
                for handlers, callback in callbacks:
                    if callback in handlers:
                        handlers.remove(callback)
