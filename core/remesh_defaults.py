DEFAULT_QUAD_COUNT = 3000
DEFAULT_USE_MATERIALS = True
DEFAULT_SYMMETRY_X = False
DEFAULTS_APPLIED_KEY = "_polygroups_qremesher_defaults_applied"


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
