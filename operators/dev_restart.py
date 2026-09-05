"""Restart Blender from an isolated recovery copy without overwriting the source."""
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import bpy


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


class WM_OT_airetopo_dev_restart(bpy.types.Operator):
    bl_idname = "wm.airetopo_dev_restart"
    bl_label = "Restart Blender (Temp Copy)"
    bl_description = "Save the current state to a new temporary blend copy and restart Blender with that copy"
    _pending = False

    @classmethod
    def poll(cls, context):
        return not cls._pending and not bpy.app.background

    def execute(self, context):
        if any(bpy.app.is_job_running(job) for job in ('RENDER', 'OBJECT_BAKE')):
            self.report({'ERROR'}, "Wait for rendering or baking to finish before restarting")
            return {'CANCELLED'}
        settings = context.scene.polygroups_model_preparation_settings
        if settings.batch_is_running or context.scene.polygroups_remesh_status.is_running:
            self.report({'ERROR'}, "Wait for import or remesh to finish before restarting")
            return {'CANCELLED'}
        root = restart_directory()
        token = 'restart_' + time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex
        copy = root / (token + '.blend')
        ready = root / (token + '.ready')
        try:
            root.mkdir(parents=True, exist_ok=True)
            if context.object and context.object.mode == 'EDIT':
                for obj in context.objects_in_mode:
                    obj.update_from_editmode()
            result = bpy.ops.wm.save_as_mainfile(
                filepath=str(copy), copy=True, relative_remap=True, check_existing=False)
            if 'FINISHED' not in result or not copy.is_file():
                raise RuntimeError("Could not save the temporary restart copy")
            # Only quit this process after the replacement has loaded this exact copy.
            expression = (
                "import bpy; from pathlib import Path; "
                f"bpy.app.timers.register(lambda: (Path({str(ready)!r}).write_text('ready') and None) "
                f"if Path(bpy.data.filepath).resolve() == Path({str(copy)!r}).resolve() else None, first_interval=2.0)"
            )
            child = subprocess.Popen([bpy.app.binary_path, str(copy), '--python-expr', expression])
        except (OSError, RuntimeError) as error:
            self.report({'ERROR'}, f"Restart failed; current Blender remains open: {error}")
            return {'CANCELLED'}
        cls = type(self)
        cls._pending = True
        deadline = time.monotonic() + 120
        def wait_for_child():
            if ready.exists():
                cls._pending = False
                bpy.ops.wm.quit_blender('EXEC_DEFAULT')
                return None
            if child.poll() is not None or time.monotonic() > deadline:
                cls._pending = False
                print(f"New Blender did not confirm startup; current session retained. Copy: {copy}")
                return None
            return 0.5
        bpy.app.timers.register(wait_for_child, first_interval=0.5)
        self.report({'INFO'}, f"Saved recovery copy: {copy}. Waiting for new Blender")
        return {'FINISHED'}
