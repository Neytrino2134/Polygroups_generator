"""Blender regression test for staged section and subsection controls."""

from pathlib import Path
import sys

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES
from polygroups_generator.properties import SECTION_VISIBILITY_PROPERTIES
from polygroups_generator.properties import SUBSECTION_VISIBILITY_PROPERTIES


settings = bpy.context.scene.airetopo_panel_visibility_settings
settings.single_section_mode = False

# Every section that draws collapsible groups must expose the header +/- controls.
for section_name in (
    "show_seam_preparation_section",
    "show_polygroups_section",
    "show_ai_generation_section",
):
    assert SECTION_SUBSECTION_PROPERTIES[section_name], f"Missing subsections for {section_name}"

for property_name in SECTION_VISIBILITY_PROPERTIES + SUBSECTION_VISIBILITY_PROPERTIES:
    setattr(settings, property_name, False)

# Expand All: main sections first, their subsections on the second click.
bpy.ops.object.airetopo_set_all_section_visibility(visible=True)
assert all(getattr(settings, name) for name in SECTION_VISIBILITY_PROPERTIES)
assert not any(getattr(settings, name) for name in SUBSECTION_VISIBILITY_PROPERTIES)

bpy.ops.object.airetopo_set_all_section_visibility(visible=True)
assert all(getattr(settings, name) for name in SUBSECTION_VISIBILITY_PROPERTIES)

# Collapse All reverses the order: subsections first, main sections second.
bpy.ops.object.airetopo_set_all_section_visibility(visible=False)
assert not any(getattr(settings, name) for name in SUBSECTION_VISIBILITY_PROPERTIES)
assert all(getattr(settings, name) for name in SECTION_VISIBILITY_PROPERTIES)

bpy.ops.object.airetopo_set_all_section_visibility(visible=False)
assert not any(getattr(settings, name) for name in SECTION_VISIBILITY_PROPERTIES)

# A section header +/- affects only that section's subsections.
bpy.ops.object.airetopo_set_section_subsection_visibility(
    section_property="show_import_section",
    visible=True,
)
assert all(getattr(settings, name) for name in SECTION_SUBSECTION_PROPERTIES["show_import_section"])
assert not any(
    getattr(settings, name)
    for section, names in SECTION_SUBSECTION_PROPERTIES.items()
    if section != "show_import_section"
    for name in names
)

bpy.ops.object.airetopo_set_section_subsection_visibility(
    section_property="show_import_section",
    visible=False,
)
assert not any(getattr(settings, name) for name in SUBSECTION_VISIBILITY_PROPERTIES)

addon_utils.disable(ROOT.name, default_set=True)
print("PANEL_VISIBILITY_STAGES_OK", flush=True)
