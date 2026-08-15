bl_info = {
    "name": "AI Retopo Toolkit",
    "author": "OpenAI",
    "version": (0, 2, 8),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > AI Retopo",
    "description": "Semi-automatic retopology toolkit for generated AI meshes",
    "category": "Mesh",
}

from .preferences import register as register_preferences
from .preferences import unregister as unregister_preferences
from .operators import register as register_operators
from .operators import unregister as unregister_operators
from .properties import register as register_properties
from .properties import unregister as unregister_properties
from .tools import register as register_tools
from .tools import unregister as unregister_tools
from .ui import register as register_ui
from .ui import unregister as unregister_ui


def register():
    register_preferences()
    register_properties()
    register_operators()
    register_tools()
    register_ui()


def unregister():
    unregister_ui()
    unregister_tools()
    unregister_operators()
    unregister_properties()
    unregister_preferences()
