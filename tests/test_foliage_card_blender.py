"""Foliage Cards: highpoly leaf silhouette -> low-poly alpha card (07 Resculpting subsection)."""
import math
import sys
from pathlib import Path

import addon_utils
import bmesh
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
ctx = bpy.context
settings = ctx.scene.polygroups_resculpting_settings
core = sys.modules[f"{ROOT.name}.core.foliage_card"]
ui = sys.modules[f"{ROOT.name}.ui_panels.ai"]


def leaf(name, shift_x=0.0, res=120):
    """Fan leaf with slits and a hole, standing in XZ and bent in Y (like a scanned leaf)."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=res, y_segments=res, size=0.5)
    remove = []
    for face in bm.faces:
        c = face.calc_center_median()
        x, y = c.x, c.y + 0.45
        r, angle = math.hypot(x, y), math.atan2(x, y)
        inside = r < 0.85 and abs(angle) < 1.25 and y > 0
        slit = r > 0.35 and math.sin(angle * 9.0) > 0.85
        hole = math.hypot(x - 0.12, c.y + 0.05) < 0.04
        if not inside or slit or hole:
            remove.append(face)
    bmesh.ops.delete(bm, geom=remove, context="FACES")
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        v.co = (x + shift_x, 0.15 * x * x - 0.05 * (y + 0.5) ** 2, y + 0.5)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    ctx.scene.collection.objects.link(obj)
    return obj


def run_on(obj):
    for item in ctx.selected_objects:
        item.select_set(False)
    obj.select_set(True)
    ctx.view_layer.objects.active = obj
    return bpy.ops.object.polygroups_generate_foliage_card()


def check_card(card, source, limit):
    mesh = card.data
    tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
    assert 0 < tris <= limit, tris
    assert card["polygroups_foliage_card_source"] == source.name
    uv = np.empty(len(mesh.loops) * 2)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    assert uv.min() >= 0.0 and uv.max() <= 1.0, (uv.min(), uv.max())
    counts = {}
    for polygon in mesh.polygons:
        for key in polygon.edge_keys:
            counts[key] = counts.get(key, 0) + 1
    for edge in mesh.edges:
        assert edge.use_seam == (counts[edge.key] == 1), edge.key   # seams = card border only
    # Normals face the camera (Front view looks along +Y).
    assert all(p.normal.y < 0 for p in mesh.polygons), "card faces away from the front view"
    return tris


# --- One leaf, default Depth Map mode.
high = leaf("Leaf_High")
settings.foliage_card_resolution = "256"
settings.foliage_card_triangle_limit = 120
assert run_on(high) == {"FINISHED"}
card = bpy.data.objects["Leaf_High_Card"]
tris = check_card(card, high, 120)
assert "uncovered 0.00%" in settings.foliage_card_status, settings.foliage_card_status
# Vertices follow the bend (depth range > flat) and sit in front of the surface.
ys = [(card.matrix_world @ v.co).y for v in card.data.vertices]
assert max(ys) - min(ys) > 0.03, (min(ys), max(ys))
high_min_y = min(v.co.y for v in high.data.vertices)
assert min(ys) < high_min_y, (min(ys), high_min_y)

# --- AlphaMap: exact silhouette in card UV space (holes and slits transparent).
ops_module = sys.modules[f"{ROOT.name}.operators.foliage_card"]
alpha, coverage = ops_module.bake_alpha_map(ctx, card, high, 128)
assert tuple(alpha.size) == (128, 128) and 0.2 < coverage < 0.9, coverage
pixels = np.empty(128 * 128 * 4, dtype=np.float32)
alpha.pixels.foreach_get(pixels)
hit = pixels[0::4].reshape(128, 128) > 0.5
assert hit.sum() > 0 and card["polygroups_foliage_card_alpha_image"] == alpha.name

# --- Regenerate replaces the previous card instead of piling up copies.
assert run_on(high) == {"FINISHED"}
assert len([o for o in bpy.data.objects if o.get("polygroups_foliage_card_source") == high.name]) == 1

# --- Tighter budget is respected by raising the outline tolerance.
settings.foliage_card_triangle_limit = 40
assert run_on(high) == {"FINISHED"}
check_card(bpy.data.objects["Leaf_High_Card"], high, 40)

# --- Flat and Shrinkwrap modes.
settings.foliage_card_triangle_limit = 120
settings.foliage_card_depth_mode = "FLAT"
assert run_on(high) == {"FINISHED"}
flat = bpy.data.objects["Leaf_High_Card"]
ys = [(flat.matrix_world @ v.co).y for v in flat.data.vertices]
assert max(ys) - min(ys) < 1e-5
settings.foliage_card_depth_mode = "SHRINKWRAP"
assert run_on(high) == {"FINISHED"}
check_card(bpy.data.objects["Leaf_High_Card"], high, 120)
settings.foliage_card_depth_mode = "DEPTH_MAP"

# --- Two leaves in one highpoly: Separate gives one card per leaf.
pair = leaf("Pair_High", -0.55, res=100)
other = leaf("Pair_B", 0.55, res=100)
bpy.ops.object.select_all(action="DESELECT")
pair.select_set(True)
other.select_set(True)
ctx.view_layer.objects.active = pair
bpy.ops.object.join()
settings.foliage_card_islands = "SEPARATE"
assert run_on(pair) == {"FINISHED"}
cards = sorted(o.name for o in bpy.data.objects if o.get("polygroups_foliage_card_source") == "Pair_High")
assert cards == ["Pair_High_Card_01", "Pair_High_Card_02"], cards
settings.foliage_card_islands = "JOIN"

# --- A card cannot be used as a source, Bake Card needs a card.
ctx.view_layer.objects.active = bpy.data.objects["Leaf_High_Card"]
assert not bpy.ops.object.polygroups_generate_foliage_card.poll()
ctx.view_layer.objects.active = high
assert not bpy.ops.object.polygroups_bake_foliage_card.poll()

# --- Panel subsection references only real properties.
class Recorder:
    def __getattr__(self, name):
        if name == "prop":
            def prop(data, attr, **kwargs):
                assert hasattr(data, attr), attr
                return self
            return prop
        if name == "operator":
            def operator(idname, **kwargs):
                category, op = idname.split(".")
                getattr(getattr(bpy.ops, category), op).get_rna_type()   # KeyError if unknown
                return self
            return operator
        return lambda *args, **kwargs: self

ui.draw_foliage_cards(Recorder(), ctx, settings)
print("foliage card ok", tris)
