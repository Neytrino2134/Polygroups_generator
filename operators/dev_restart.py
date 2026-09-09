"""Restart Blender from a recovery copy or the saved current file."""
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import bpy

_restart_pending = False


def restart_directory():
    return Path(tempfile.gettempdir()) / "airetopo_dev_restart"


def cleanup_copies(current_file):
    root = restart_directory().resolve()
    current = Path(current_file).resolve() if current_file else None
    removed = 0
    if not root.exists():
        return removed
    for path in root.iterdir():
        # No recursion or symlink traversal; retain the open recovery copy and backups.
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            continue
        if not path.name.startswith("restart_") or path.suffix not in {".blend", ".blend1", ".blend2", ".ready"}:
            continue
        if current and path.stem == current.stem:
            continue
        path.unlink()
        removed += 1
    return removed


class WM_OT_airetopo_dev_cleanup(bpy.types.Operator):
    bl_idname = "wm.airetopo_dev_cleanup"
    bl_label = "Clean Restart Temp Files"
    bl_description = "Delete this tool's temporary restart copies, except the currently open copy"

    def execute(self, context):
        try:
            count = cleanup_copies(bpy.data.filepath)
        except OSError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Removed {count} temporary restart file(s)")
        return {'FINISHED'}


def _restart_poll():
    return not _restart_pending and not bpy.app.background


def _execute_restart(operator, context, save_current, use_saved_current=False):
    global _restart_pending
    if any(bpy.app.is_job_running(job) for job in ('RENDER', 'OBJECT_BAKE')):
        operator.report({'ERROR'}, "Wait for rendering or baking to finish before restarting")
        return {'CANCELLED'}
    settings = context.scene.polygroups_model_preparation_settings
    if settings.batch_is_running or context.scene.polygroups_remesh_status.is_running:
        operator.report({'ERROR'}, "Wait for import or remesh to finish before restarting")
        return {'CANCELLED'}
    root = restart_directory()
    token = 'restart_' + time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex
    current_file = Path(bpy.data.filepath) if bpy.data.filepath else None
    if save_current:
        copy = current_file or root / (token + '.blend')
    elif use_saved_current:
        copy = current_file
    else:
        copy = root / (token + '.blend')
    ready = root / (token + '.ready')
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not use_saved_current and context.object and context.object.mode == 'EDIT':
            for obj in context.objects_in_mode:
                obj.update_from_editmode()
        if use_saved_current:
            if copy is not None and not copy.is_file():
                raise RuntimeError("The current blend file no longer exists")
            result = {'FINISHED'}
        elif save_current:
            result = bpy.ops.wm.save_as_mainfile(
                filepath=str(copy), copy=False, check_existing=False)
        else:
            result = bpy.ops.wm.save_as_mainfile(
                filepath=str(copy), copy=True, relative_remap=True, check_existing=False)
        if 'FINISHED' not in result or (copy is not None and not copy.is_file()):
            raise RuntimeError("Could not save the restart file")
        # Quit this process only after the replacement Blender confirms startup.
        if copy is None:
            expression = (
                "import bpy; from pathlib import Path; "
                f"bpy.app.timers.register(lambda: (Path({str(ready)!r}).write_text('ready') and None), "
                "first_interval=2.0)"
            )
            command = [bpy.app.binary_path, '--python-expr', expression]
        else:
            expression = (
                "import bpy; from pathlib import Path; "
                f"bpy.app.timers.register(lambda: (Path({str(ready)!r}).write_text('ready') and None) "
                f"if Path(bpy.data.filepath).resolve() == Path({str(copy)!r}).resolve() else None, first_interval=2.0)"
            )
            command = [bpy.app.binary_path, str(copy), '--python-expr', expression]
        child = subprocess.Popen(command)
    except (OSError, RuntimeError) as error:
        operator.report({'ERROR'}, f"Restart failed; current Blender remains open: {error}")
        return {'CANCELLED'}
    _restart_pending = True
    deadline = time.monotonic() + 120

    def wait_for_child():
        global _restart_pending
        if ready.exists():
            try:
                ready.unlink()
            except OSError:
                pass
            _restart_pending = False
            bpy.ops.wm.quit_blender('EXEC_DEFAULT')
            return None
        if child.poll() is not None or time.monotonic() > deadline:
            _restart_pending = False
            print(f"New Blender did not confirm startup; current session retained. Copy: {copy}")
            return None
        return 0.5

    bpy.app.timers.register(wait_for_child, first_interval=0.5)
    if copy is None:
        message = "Opening a new unsaved file. Waiting for new Blender"
    else:
        action = "Opening saved file" if use_saved_current else "Saved"
        message = f"{action}: {copy}. Waiting for new Blender"
    operator.report({'INFO'}, message)
    return {'FINISHED'}


class WM_OT_airetopo_dev_restart(bpy.types.Operator):
    bl_idname = "wm.airetopo_dev_restart"
    bl_label = "Restart Blender (Temp Copy)"
    bl_description = "Save the current state to a new temporary blend copy and restart Blender with that copy"
    save_current = False

    @classmethod
    def poll(cls, context):
        return _restart_poll()

    def execute(self, context):
        return _execute_restart(self, context, bool(getattr(self, "save_current", False)))


class WM_OT_airetopo_dev_restart_current(bpy.types.Operator):
    bl_idname = "wm.airetopo_dev_restart_current"
    bl_label = "Restart Blender — Save and Use This File"
    bl_description = "Save and restart Blender; new unsaved files are saved in the add-on temporary folder"

    @classmethod
    def poll(cls, context):
        return _restart_poll()

    def execute(self, context):
        return _execute_restart(self, context, True)


class WM_OT_airetopo_dev_restart_without_saving(bpy.types.Operator):
    bl_idname = "wm.airetopo_dev_restart_without_saving"
    bl_label = "Restart Without Saving — Use This File"
    bl_description = "Discard unsaved changes and restart with the last saved file, or a new file if it was never saved"

    @classmethod
    def poll(cls, context):
        return _restart_poll()

    def execute(self, context):
        return _execute_restart(self, context, False, use_saved_current=True)
