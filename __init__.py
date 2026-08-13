bl_info = {
    "name": "PolyGroups Generator",
    "author": "OpenAI",
    "version": (0, 1, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > PolyGroups",
    "description": "Split a mesh into seam-bounded islands, assign materials, and build sculpt Face Sets",
    "category": "Mesh",
}

from .operators import register as register_operators
from .operators import unregister as unregister_operators
from .properties import register as register_properties
from .properties import unregister as unregister_properties
from .tools import register as register_tools
from .tools import unregister as unregister_tools
from .ui import register as register_ui
from .ui import unregister as unregister_ui


def register():
    register_properties()
    register_operators()
    register_tools()
    register_ui()


def unregister():
    unregister_ui()
    unregister_tools()
    unregister_operators()
    unregister_properties()
