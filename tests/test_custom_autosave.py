"""Blender smoke test for the versioned custom autosave lifecycle."""

from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

import bpy


ADDONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDONS))
from polygroups_generator import custom_autosave


# Add-on registration runs while Blender exposes _RestrictData without filepath.
real_bpy = custom_autosave.bpy
custom_autosave.bpy = SimpleNamespace(
    data=SimpleNamespace(),
    context=SimpleNamespace(window_manager=None),
)
try:
    custom_autosave._read_status_from_disk()
    assert custom_autosave._initialize_status_timer() == 0.1
finally:
    custom_autosave.bpy = real_bpy


test_dir = Path(tempfile.mkdtemp(prefix="airetopo-autosave-test-"))
try:
    preferences = SimpleNamespace(
        autosave_mode="CUSTOM",
        autosave_versions=2,
        autosave_interval_minutes=2.0,
    )
    custom_autosave._preferences = lambda: preferences
    custom_autosave.register()
    assert not bpy.context.preferences.filepaths.use_auto_save_temporary_files

    bpy.ops.mesh.primitive_cube_add()
    saved, _status = custom_autosave.save_now(force=True)
    assert saved
    assert custom_autosave.status_snapshot()["event"] == "CUSTOM"
    assert custom_autosave.status_snapshot()["autosave_time"] != "—"
    assert custom_autosave.status_snapshot()["regular_save_time"] == "—"
    session_dir = custom_autosave.current_autosave_directory()
    assert (session_dir / "Unsaved.blendAutosave1").exists()

    project = test_dir / "project.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(project)) == {"FINISHED"}
    assert bpy.data.filepath == str(project)
    assert not session_dir.exists()
    assert custom_autosave.status_snapshot()["event"] == "REGULAR"
    assert custom_autosave.status_snapshot()["regular_save_time"] != "—"
    assert custom_autosave.status_snapshot()["autosave_time"] != "—"

    bpy.ops.mesh.primitive_uv_sphere_add()
    assert custom_autosave.save_now(force=True)[0]
    bpy.ops.mesh.primitive_cone_add()
    assert custom_autosave.save_now(force=True)[0]
    assert (test_dir / "project.blendAutosave1").exists()
    assert (test_dir / "project.blendAutosave2").exists()
    assert bpy.data.filepath == str(project)

    preferences.autosave_versions = 1
    bpy.ops.mesh.primitive_torus_add()
    assert custom_autosave.save_now(force=True)[0]
    assert (test_dir / "project.blendAutosave1").exists()
    assert not (test_dir / "project.blendAutosave2").exists()
    autosave = test_dir / "project.blendAutosave1"

    recovery_root = test_dir / "recovery"
    recovery_session = recovery_root / "old-session"
    recovery_session.mkdir(parents=True)
    unsaved_recovery = recovery_session / "Unsaved.blendAutosave1"
    shutil.copy2(autosave, unsaved_recovery)
    (recovery_session / "not-an-autosave.txt").write_text("ignored", encoding="utf-8")
    recoveries = custom_autosave.collect_recent_autosaves(
        recovery_root,
        [project, autosave],
        limit=8,
    )
    recovery_paths = {entry["filepath"] for entry in recoveries}
    assert str(autosave.resolve()) in recovery_paths
    assert str(unsaved_recovery.resolve()) in recovery_paths
    assert len(recoveries) == 2

    assert bpy.ops.wm.airetopo_open_recent_autosave(filepath=str(autosave)) == {"FINISHED"}
    assert "Torus" in bpy.data.objects
    recovery = custom_autosave.recovery_snapshot()
    restored = Path(recovery["restored"])
    assert recovery["active"]
    assert Path(recovery["original"]) == project
    assert restored.exists()
    assert restored.parent == project.parent
    assert restored.name.startswith("project_restored_")
    assert restored.suffix == ".blend"
    assert bpy.data.filepath == str(restored)

    assert bpy.ops.wm.airetopo_save_recovery_to_original() == {"FINISHED"}
    assert bpy.data.filepath == str(project)
    assert not restored.exists()
    assert not custom_autosave.recovery_snapshot()["active"]
    assert "Torus" in bpy.data.objects

    preferences.autosave_mode = "NATIVE"
    custom_autosave.configure()
    assert bpy.context.preferences.filepaths.use_auto_save_temporary_files
    print("CUSTOM_AUTOSAVE_OK", flush=True)
finally:
    try:
        custom_autosave.unregister()
    except Exception:
        pass
    shutil.rmtree(test_dir, ignore_errors=True)
