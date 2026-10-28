"""Blender --background --factory-startup --python-exit-code 1 --python FILE."""
import math
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=False)
from polygroups_generator import ui
from polygroups_generator.core.chart_cuts import DEFAULT_OPTIONS, _quad_loops, kind_counts, topology_guard
from polygroups_generator.core.chart_topology import charts, classify, is_disk
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES

ZABROSHKA = Path(r"D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\47_Zabroshka\47_Zabroshka.blend")
scene = bpy.context.scene
settings = scene.polygroups_seam_finalization_settings


def all_disks(bm):
    return all(is_disk(classify(chart)) for chart in charts(bm))


def fresh(name, build):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    build()
    obj = bpy.context.active_object
    obj.name = name
    return obj


def guard_bm(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    result = topology_guard(bm, None, DEFAULT_OPTIONS)
    return bm, result


def collapsed_share(bm):
    """Area share of triangles squeezed to < 5% of their chart's mean UV scale."""
    uv = bm.loops.layers.uv.active
    total = bad = 0.0
    for chart in charts(bm):
        tris = [t for t in bm.calc_loop_triangles() if t[0].face in chart]
        ratios = []
        for a, b, c in tris:
            area = (b.vert.co - a.vert.co).cross(c.vert.co - a.vert.co).length * 0.5
            u, v = b[uv].uv - a[uv].uv, c[uv].uv - a[uv].uv
            ratios.append((area, abs(u.x * v.y - u.y * v.x) * 0.5))
        area_sum = sum(a for a, _ in ratios)
        uv_sum = sum(w for _, w in ratios)
        if area_sum <= 0.0 or uv_sum <= 0.0:
            continue
        scale = uv_sum / area_sum
        for area, uv_area in ratios:
            total += area
            if area > 0.0 and uv_area / area < 0.05 * scale:
                bad += area
    return bad / total if total else 0.0


# ---- panel and defaults
assert "topic_uv_4" in SECTION_SUBSECTION_PROPERTIES["show_uv_preparation_section"]
assert settings.topology_guard_fix_handles and settings.topology_guard_fix_necks
assert settings.topology_guard_create_edges and not settings.topology_guard_after_smart_seams
assert not settings.topology_guard_before_repair
assert math.isclose(settings.topology_guard_hole_ratio, 0.25, rel_tol=1e-6)


class Layout:
    def __init__(self, buttons):
        self.buttons = buttons
        self.operator_context = ""
        self.enabled = True

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), name
        if name.startswith("topology_guard_"):
            drawn.add(name)

    def label(self, *args, **kwargs):
        pass

    def separator(self, **kwargs):
        pass

    def operator(self, idname, **kwargs):
        button = type("Button", (), {})()
        if idname == "mesh.polygroups_topology_guard":
            self.buttons.append((button, self.operator_context))
        return button


visibility = scene.airetopo_panel_visibility_settings
visibility.show_uv_preparation_section = True
visibility.topic_uv_4 = True
buttons, drawn = [], set()
ui.draw_section_panel_content(ui.VIEW3D_PT_polygroups_uv_preparation, bpy.context,
                              Layout(buttons), "show_uv_preparation_section")
assert [b.action for b, _ in buttons] == ["SELECT", "APPLY"], buttons
# Every Topology Guard setting is reachable from the section.
assert drawn == {name for name in settings.bl_rna.properties.keys()
                 if name.startswith("topology_guard_")}, drawn
from polygroups_generator.localization import TEXT
assert all(name in TEXT["EN"] and name in TEXT["RU"] for name in drawn)
assert all(context == "EXEC_DEFAULT" for _, context in buttons)
search = ui._probe_panel(ui.VIEW3D_PT_polygroups_uv_preparation, bpy.context, "Topology Guard")
assert any("topic_uv_4" in key for key in search.groups)

# ---- torus without seams: closed handle -> ring + longitudinal
torus = fresh("GuardTorus", lambda: bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=12))
bm, result = guard_bm(torus.data)
assert all_disks(bm), kind_counts(result.after)
assert sum(e.seam for e in bm.edges) == 12 + 48, sum(e.seam for e in bm.edges)
bm.free()

# ---- torus with one ring seam: annulus -> one longitudinal
bm = bmesh.new()
bm.from_mesh(torus.data)
bm.edges.ensure_lookup_table()
ring = next(loop for loop in _quad_loops(classify(set(bm.faces))) if len(loop) == 12)
for edge in ring:
    edge.seam = True
result = topology_guard(bm, None, DEFAULT_OPTIONS)
assert all_disks(bm)
assert len(result.longitudinal) == 48 and not result.rings, (len(result.longitudinal), len(result.rings))
bm.free()

# ---- closed capped cylinder: genus 0 without boundary -> slit
cylinder = fresh("GuardCylinder", lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=16))
bm, result = guard_bm(cylinder.data)
assert all_disks(bm), kind_counts(result.after)
bm.free()

# ---- plane with an extruded spike: wall rings + longitudinal
plane = fresh("GuardSpike", lambda: bpy.ops.mesh.primitive_grid_add(x_subdivisions=9, y_subdivisions=9, size=9))
bpy.ops.object.mode_set(mode="EDIT")
live = bmesh.from_edit_mesh(plane.data)
for face in live.faces:
    face.select_set(False)
min(live.faces, key=lambda f: f.calc_center_median().length).select_set(True)
bmesh.update_edit_mesh(plane.data)
for _ in range(3):
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0.0, 0.0, 1.0)})
bpy.ops.object.mode_set(mode="OBJECT")
bm = bmesh.new()
bm.from_mesh(plane.data)
bm.normal_update()
assert len(charts(bm)) == 1 and is_disk(classify(charts(bm)[0]))
result = topology_guard(bm, None, DEFAULT_OPTIONS)
counts = kind_counts(result.after)
assert len(charts(bm)) == 3, (len(charts(bm)), counts)
assert len(result.rings) == 8 and len(result.longitudinal) == 3, (len(result.rings), len(result.longitudinal))
bm.free()

# ---- operator in Edit Mode, plus the Generate Smart Seams hook
torus = fresh("GuardTorusOp", lambda: bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=12))
bpy.ops.object.mode_set(mode="EDIT")
assert bpy.ops.mesh.polygroups_topology_guard(action="SELECT") == {"FINISHED"}
assert sum(f.select for f in bmesh.from_edit_mesh(torus.data).faces) == len(torus.data.polygons)
assert bpy.ops.mesh.polygroups_topology_guard(action="APPLY") == {"FINISHED"}
live = bmesh.from_edit_mesh(torus.data)
assert all(is_disk(classify(chart)) for chart in charts(live))
assert collapsed_share(live) < 0.01, collapsed_share(live)
bpy.ops.object.mode_set(mode="OBJECT")

torus = fresh("GuardSmartSeams", lambda: bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=12))
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
# Topology Guard is a separate step by default: Smart Seams alone leaves the torus open.
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {"FINISHED"}
live = bmesh.from_edit_mesh(torus.data)
assert not all(is_disk(classify(chart)) for chart in charts(live))
bpy.ops.object.mode_set(mode="OBJECT")

torus = fresh("GuardSmartSeamsHook", lambda: bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=12))
settings.topology_guard_after_smart_seams = True
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
assert bpy.ops.mesh.polygroups_mark_smart_angle_seams() == {"FINISHED"}
live = bmesh.from_edit_mesh(torus.data)
assert all(is_disk(classify(chart)) for chart in charts(live)), [classify(c).chi for c in charts(live)]
bpy.ops.object.mode_set(mode="OBJECT")
settings.topology_guard_after_smart_seams = False

# ---- the user's reference meshes (broken / manually fixed pairs)
if ZABROSHKA.exists():
    names = ["Torus", "Torus.001", "Retopo_02", "Retopo_02.001", "Sphere", "Sphere.001", "Chair"]
    with bpy.data.libraries.load(str(ZABROSHKA)) as (source, target):
        target.objects = [n for n in names if n in source.objects]
    meshes = {obj.name: obj.data for obj in target.objects}

    def manual_seams(broken, fixed):
        a, b = bmesh.new(), bmesh.new()
        a.from_mesh(meshes[broken])
        b.from_mesh(meshes[fixed])
        a.edges.ensure_lookup_table()
        b.edges.ensure_lookup_table()
        added = {i for i in range(len(b.edges)) if b.edges[i].seam and not a.edges[i].seam}
        a.free()
        b.free()
        return added

    for fixed in ("Torus.001", "Retopo_02.001", "Sphere.001"):
        bm, result = guard_bm(meshes[fixed])
        assert not result.rings and not result.longitudinal, (fixed, len(result.rings), len(result.longitudinal))
        bm.free()

    bm, result = guard_bm(meshes["Torus"])
    assert {e.index for e in result.longitudinal} == manual_seams("Torus", "Torus.001")
    assert all_disks(bm)
    bm.free()

    bm, result = guard_bm(meshes["Sphere"])
    manual = manual_seams("Sphere", "Sphere.001")
    assert len(charts(bm)) == 26, len(charts(bm))
    assert {e.index for e in result.rings} <= manual and len(result.rings) == 192, len(result.rings)
    assert len(result.longitudinal) == 12
    bm.free()

    bm, result = guard_bm(meshes["Retopo_02"])
    manual = manual_seams("Retopo_02", "Retopo_02.001")
    assert len(charts(bm)) == 4, len(charts(bm))
    assert len(result.rings) == 38 and len({e.index for e in result.rings} & manual) >= 19
    assert set(kind_counts(result.after)) == {"DISK"}
    bm.free()

    bm, result = guard_bm(meshes["Chair"])
    assert set(kind_counts(result.after)) == {"DISK"}, kind_counts(result.after)
    bm.free()

    # Real unwrap: the tube in Retopo_02 must stop collapsing.
    obj = bpy.data.objects.new("GuardRetopo", meshes["Retopo_02"].copy())
    scene.collection.objects.link(obj)
    for other in list(scene.objects):
        other.select_set(other is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
    before = collapsed_share(bmesh.from_edit_mesh(obj.data))
    settings.topology_guard_unwrap = True
    assert bpy.ops.mesh.polygroups_topology_guard(action="APPLY") == {"FINISHED"}
    after = collapsed_share(bmesh.from_edit_mesh(obj.data))
    print(f"Retopo_02 collapsed UV share: before {before:.4f}, after {after:.4f}")
    assert after < before * 0.5 or after < 0.005, (before, after)
    bpy.ops.object.mode_set(mode="OBJECT")
else:
    print("Zabroshka reference file not found; reference-mesh checks skipped")

print("TOPOLOGY GUARD PASSED")
