import bpy


def assign_face_sets_from_materials(context, obj, randomize_colors=True):
    view_layer = context.view_layer
    if view_layer.objects.active is not obj:
        view_layer.objects.active = obj

    if obj.mode != "SCULPT":
        bpy.ops.object.mode_set(mode="SCULPT")

    bpy.ops.sculpt.face_sets_init(mode="MATERIALS")

    if randomize_colors:
        bpy.ops.sculpt.face_sets_randomize_colors()


def get_face_set_layer(bm):
    for layer_name in (".sculpt_face_set", "sculpt_face_set"):
        layer = bm.faces.layers.int.get(layer_name)
        if layer is not None:
            return layer
    return None


def split_faces_by_face_set(bm):
    bm.faces.ensure_lookup_table()
    layer = get_face_set_layer(bm)
    if layer is None:
        return None

    groups_by_id = {}
    for face in bm.faces:
        face_set_id = face[layer]
        groups_by_id.setdefault(face_set_id, []).append(face)

    return [
        groups_by_id[key]
        for key in sorted(groups_by_id.keys())
    ]
