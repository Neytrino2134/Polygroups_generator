bl_info = {
    "name": "AI Retopo Toolkit",
    "author": "Meowmaster",
    "version": (0, 2, 59),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > AI Retopo",
    "description": "Semi-automatic retopology toolkit for generated AI meshes",
    "category": "Mesh",
}

from .custom_icons import register as register_icons
from .custom_icons import unregister as unregister_icons

from .preferences import register as register_preferences
from .preferences import unregister as unregister_preferences
from .custom_autosave import register as register_custom_autosave
from .custom_autosave import unregister as unregister_custom_autosave
from .core.remesh_defaults import register_remesh_defaults_timer
from .core.remesh_defaults import unregister_remesh_defaults_timer
from .hotkeys import register as register_hotkeys
from .hotkeys import unregister as unregister_hotkeys
from .operators import register as register_operators
from .operators import unregister as unregister_operators
from .properties import register as register_properties
from .properties import unregister as unregister_properties
from .tools import register as register_tools
from .tools import unregister as unregister_tools
from .ui import register as register_ui
from .ui import unregister as unregister_ui
from .pin_edges import register as register_pin_edges
from .pin_edges import unregister as unregister_pin_edges
from .seam_object_overlay import register as register_seam_object_overlay
from .seam_object_overlay import unregister as unregister_seam_object_overlay
from .uv_checker_overlay import register as register_uv_checker_overlay
from .uv_checker_overlay import unregister as unregister_uv_checker_overlay


def register():
    register_icons()
    register_preferences()
    register_custom_autosave()
    register_properties()
    register_operators()
    register_tools()
    register_ui()
    register_pin_edges()
    register_seam_object_overlay()
    register_uv_checker_overlay()
    register_hotkeys()
    register_remesh_defaults_timer()


def unregister():
    from .operators.import_queue import stop_import_queue

    stop_import_queue()
    unregister_custom_autosave()
    unregister_remesh_defaults_timer()
    unregister_hotkeys()
    unregister_ui()
    unregister_uv_checker_overlay()
    unregister_seam_object_overlay()
    unregister_pin_edges()
    unregister_tools()
    unregister_operators()
    unregister_properties()
    unregister_preferences()
    unregister_icons()
