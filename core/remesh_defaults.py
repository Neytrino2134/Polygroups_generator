import bpy


DEFAULT_QUAD_COUNT = 3000
DEFAULT_USE_MATERIALS = True
DEFAULT_SYMMETRY_X = False
DEFAULTS_APPLIED_KEY = "_polygroups_qremesher_defaults_applied"
MAX_TIMER_ATTEMPTS = 30

_timer_attempts = 0


def apply_quad_remesher_defaults_once(scene):
    if scene.get(DEFAULTS_APPLIED_KEY):
        return
    if not hasattr(scene, "qremesher"):
        return

    qremesher = scene.qremesher
    defaults = (
        ("target_count", DEFAULT_QUAD_COUNT),
        ("use_materials", DEFAULT_USE_MATERIALS),
        ("symmetry_x", DEFAULT_SYMMETRY_X),
    )
    for property_name, value in defaults:
        if hasattr(qremesher, property_name):
            setattr(qremesher, property_name, value)

    scene[DEFAULTS_APPLIED_KEY] = True


def _apply_quad_remesher_defaults_timer():
    global _timer_attempts
    _timer_attempts += 1

    waiting_for_qremesher = False
    for scene in bpy.data.scenes:
        if scene.get(DEFAULTS_APPLIED_KEY):
            continue
        if hasattr(scene, "qremesher"):
            apply_quad_remesher_defaults_once(scene)
        else:
            waiting_for_qremesher = True

    if waiting_for_qremesher and _timer_attempts < MAX_TIMER_ATTEMPTS:
        return 1.0

    return None


def register_remesh_defaults_timer():
    global _timer_attempts
    _timer_attempts = 0
    if not bpy.app.timers.is_registered(_apply_quad_remesher_defaults_timer):
        bpy.app.timers.register(_apply_quad_remesher_defaults_timer, first_interval=0.1)


def unregister_remesh_defaults_timer():
    if bpy.app.timers.is_registered(_apply_quad_remesher_defaults_timer):
        bpy.app.timers.unregister(_apply_quad_remesher_defaults_timer)
