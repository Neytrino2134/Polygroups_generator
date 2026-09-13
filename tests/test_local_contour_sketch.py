"""Blender --background --factory-startup --python-exit-code 1 --python tests/test_local_contour_sketch.py"""
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from math import pi

import addon_utils
import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.operators import local_contour_sketch as sketch
from polygroups_generator.operators import object_seam_cutter as cutter
from polygroups_generator import tools

bindings = tools.VIEW3D_WST_polygroups_draw_cutter_local_contour.bl_keymap
assert len(bindings) == 2
assert all(item[0] == sketch.OBJECT_OT_polygroups_local_contour_gesture.bl_idname
           for item in bindings)
assert {(item[1]["ctrl"], item[1]["shift"]) for item in bindings} == {
    (True, False), (True, True),
}

assert len(sketch._simplify_screen_points([Vector((x, 0)) for x in range(20)])) == 2
assert len(sketch._simplify_screen_points([
    Vector((-10, 0)), Vector((0, 8)), Vector((10, 0))
])) == 3

bpy.ops.mesh.primitive_cube_add()
target = bpy.context.active_object
target.name = "Sketch Target"

# Exercise the three gestures without a GPU viewport or modal handler.
gesture = sketch.OBJECT_OT_polygroups_local_contour_gesture
fake_area = SimpleNamespace(tag_redraw=lambda: None)
fake_region = SimpleNamespace(width=1000, height=1000)
fake_rv3d = SimpleNamespace(view_matrix=Matrix.Identity(4))
fake_context = SimpleNamespace(workspace=SimpleNamespace(status_text_set=lambda _message: None))
original_view_lookup = cutter._view3d_under_mouse
cutter._view3d_under_mouse = lambda _context, event: (
    fake_area, fake_region, fake_rv3d, (event.mouse_x, event.mouse_y)
)

def make_event(event_type, value="PRESS", x=100, y=100, ctrl=False, shift=False):
    return SimpleNamespace(type=event_type, value=value, mouse_x=x, mouse_y=y,
                           ctrl=ctrl, shift=shift, alt=False)

def make_gesture():
    state = SimpleNamespace(
        _mode="WAIT", _points=[], _mouse_pos=None, _drawing=False,
        _button_down=False, _press_pos=None, _press_shift=False, _start_pos=None,
        _start_area=None, _area=None, _start_region=None, _region=None,
        _start_rv3d=None, _rv3d=None, _view_matrix=None,
        _drag_threshold=6.0, _target_name=target.name,
        _tag_redraw=lambda: None, _set_status=lambda _context: None,
        report=lambda *_args: None,
    )
    for name in ("_handle_press", "_finish_click", "_append_point"):
        setattr(state, name, MethodType(getattr(gesture, name), state))
    state._finish_sketch = lambda _context, source: setattr(state, "finished_source", source) or {"FINISHED"}
    return state

try:
    click = make_gesture()
    assert gesture.modal(click, fake_context, make_event("LEFTMOUSE", ctrl=True)) == {"RUNNING_MODAL"}
    assert gesture.modal(click, fake_context, make_event("LEFTMOUSE", "RELEASE")) == {"RUNNING_MODAL"}
    assert click._mode == "PLANE" and tuple(click._start_pos) == (100, 100)
    gesture.modal(click, fake_context, make_event("LEFTMOUSE", x=140))
    assert click._button_down and tuple(click._press_pos) == (140, 100)

    shifted = make_gesture()
    gesture.modal(shifted, fake_context, make_event("LEFTMOUSE", ctrl=True))
    gesture.modal(shifted, fake_context, make_event("LEFTMOUSE", "RELEASE"))
    gesture.modal(shifted, fake_context, make_event("LEFTMOUSE", x=140, shift=True))
    assert shifted._mode == "PLANE" and shifted._press_shift

    draw = make_gesture()
    gesture.modal(draw, fake_context, make_event("LEFTMOUSE", ctrl=True))
    gesture.modal(draw, fake_context, make_event("MOUSEMOVE", "NOTHING", x=120, ctrl=True))
    assert draw._mode == "DRAW" and len(draw._points) == 2
    assert gesture.modal(draw, fake_context, make_event("LEFTMOUSE", "RELEASE", x=120)) == {"FINISHED"}
    assert draw.finished_source == "DRAW"

    path = make_gesture()
    gesture.modal(path, fake_context, make_event("LEFTMOUSE", ctrl=True, shift=True))
    gesture.modal(path, fake_context, make_event("LEFTMOUSE", ctrl=True, shift=True, x=140))
    assert path._mode == "PATH" and len(path._points) == 2
    assert gesture.modal(path, fake_context, make_event("SPACE")) == {"FINISHED"}
    assert path.finished_source == "PATH"
finally:
    cutter._view3d_under_mouse = original_view_lookup

camera = bpy.data.objects.new("Sketch Camera", bpy.data.cameras.new("Sketch Camera"))
bpy.context.collection.objects.link(camera)
camera.matrix_world = Matrix.Translation((0, -8, 0)) @ Quaternion((1, 0, 0), pi / 2).to_matrix().to_4x4()
region = SimpleNamespace(width=1000, height=1000)

for perspective in ("ORTHO", "PERSP"):
    camera.data.type = perspective
    camera.data.ortho_scale = 5
    bpy.context.view_layer.update()
    view = camera.matrix_world.inverted()
    projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(), x=1000, y=1000)
    rv3d = SimpleNamespace(
        view_matrix=view, perspective_matrix=projection @ view,
        is_perspective=perspective == "PERSP", view_perspective=perspective,
    )
    screen_points = [view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(p))
                     for p in ((-1.5, 0, -.2), (0, 0, .3), (1.5, 0, -.2))]
    vertices, faces = sketch._projected_sheet(region, rv3d, screen_points, target)
    assert len(vertices) > 6 and len(faces) == len(vertices) // 2 - 1
    projected = []
    for index in range(len(vertices) // 2):
        front = view3d_utils.location_3d_to_region_2d(region, rv3d, vertices[index * 2])
        back = view3d_utils.location_3d_to_region_2d(region, rv3d, vertices[index * 2 + 1])
        assert (front - back).length < .01
        projected.append(front)
    # Drawing well outside the cube trims its end tails near the silhouette.
    assert (projected[0] - screen_points[0]).length > 10
    assert (projected[-1] - screen_points[-1]).length > 10
    # The old 10%-of-bounds extrusion was over 2.6 units deep for this cube.
    assert max((vertices[index] - vertices[index + 1]).length
               for index in range(0, len(vertices), 2)) < 2.2

    temp = sketch._make_sketch(bpy.context, target, region, rv3d, screen_points, "PATH")
    assert temp.get(sketch.TEMP_PROP) == "PATH"
    assert not temp.get(cutter.CUTTER_PROP)
    temp.data.vertices[1].co.z += .1  # A back-view edit must survive conversion.
    edited_back_z = temp.data.vertices[1].co.z
    assert bpy.ops.object.polygroups_finalize_local_contour() == {"FINISHED"}
    assert temp.get(cutter.CUTTER_PROP)
    assert temp.get(cutter.CUTTER_TYPE_PROP) == "LOCAL_CONTOUR"
    assert cutter.CUTTER_SOLIDIFY_MODIFIER_NAME in temp.modifiers
    assert abs(temp.data.vertices[1].co.z - edited_back_z) < 1e-6
    assert bpy.context.active_object == target
    bpy.data.objects.remove(temp, do_unlink=True)

# Both Path and Draw use this projection. Contour Offset must extend both
# front and back rails by the chosen amount, independent of the bounding box.
settings = bpy.context.scene.polygroups_object_seam_cutter_settings
original_offset = settings.cutter_contour_offset
try:
    settings.cutter_contour_offset = 0.0
    tight_verts, _ = sketch._projected_sheet(region, rv3d, screen_points, target)
    settings.cutter_contour_offset = 0.05
    offset_verts, _ = sketch._projected_sheet(region, rv3d, screen_points, target)
finally:
    settings.cutter_contour_offset = original_offset
assert len(tight_verts) == len(offset_verts)
middle = (len(tight_verts) // 4) * 2
tight_depth = (tight_verts[middle] - tight_verts[middle + 1]).length
offset_depth = (offset_verts[middle] - offset_verts[middle + 1]).length
assert 0.09 < offset_depth - tight_depth < 0.11

# Front/back depth must follow a curved surface rather than the object's box.
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
sphere = bpy.context.active_object
camera.data.type = "ORTHO"
bpy.context.view_layer.update()
view = camera.matrix_world.inverted()
projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(), x=1000, y=1000)
rv3d = SimpleNamespace(view_matrix=view, perspective_matrix=projection @ view,
                       is_perspective=False, view_perspective="ORTHO")
sphere_path = [view3d_utils.location_3d_to_region_2d(region, rv3d, Vector((x, 0, 0)))
               for x in (-1.3, 0, 1.3)]
sphere_verts, _ = sketch._projected_sheet(region, rv3d, sphere_path, sphere)
spans = []
for index in range(0, len(sphere_verts), 2):
    pixel = view3d_utils.location_3d_to_region_2d(region, rv3d, sphere_verts[index])
    spans.append((pixel, (sphere_verts[index] - sphere_verts[index + 1]).length))
center_span = min(spans, key=lambda item: (item[0] - sphere_path[1]).length)[1]
outer_pixel = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector((.7, 0, 0)))
outer_span = min(spans, key=lambda item: (item[0] - outer_pixel).length)[1]
assert center_span > outer_span + .3

# A second disconnected part behind the visible one must not deepen the sheet.
cube_corners = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
cube_faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
              (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
stack_verts = [(x, y + center_y, z) for center_y in (-2, 2)
               for x, y, z in cube_corners]
stack_faces = [tuple(index + offset for index in face)
               for offset in (0, 8) for face in cube_faces]
stack_mesh = bpy.data.meshes.new("Stacked contour target")
stack_mesh.from_pydata(stack_verts, [], stack_faces)
stack_target = bpy.data.objects.new("Stacked contour target", stack_mesh)
bpy.context.collection.objects.link(stack_target)
bpy.context.view_layer.update()
stack_verts, _ = sketch._projected_sheet(region, rv3d, sphere_path, stack_target)
assert max((stack_verts[index] - stack_verts[index + 1]).length
           for index in range(0, len(stack_verts), 2)) < 2.3

# The tightened sheet still works with the existing cutter application modes.
settings.cutter_auto_fix_mesh = False
settings.hide_cutters_after_apply = False
settings.cutter_boolean_solver = "EXACT"
for method in ("BOOLEAN", "KNIFE"):
    bpy.ops.mesh.primitive_cube_add()
    apply_target = bpy.context.active_object
    apply_path = [view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(p))
                  for p in ((-1.3, 0, -.15), (0, 0, .2), (1.3, 0, -.15))]
    temporary = sketch._make_sketch(bpy.context, apply_target, region, rv3d, apply_path, "PATH")
    assert bpy.ops.object.polygroups_finalize_local_contour() == {"FINISHED"}
    settings.cutter_apply_method = method
    assert bpy.ops.object.polygroups_apply_cutter_seams() == {"FINISHED"}
    assert any(edge.use_seam for edge in apply_target.data.edges), method
    bpy.data.objects.remove(temporary, do_unlink=True)

print("Local contour sketch tests passed", flush=True)
addon_utils.disable(ROOT.name)
