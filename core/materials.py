import random


def clear_materials(obj):
    obj.data.materials.clear()


def create_material(name, color):
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True

    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color

    return material


def random_color():
    return (
        random.uniform(0.15, 0.9),
        random.uniform(0.15, 0.9),
        random.uniform(0.15, 0.9),
        1.0,
    )


def assign_materials(obj, groups, prefix="FaceSet"):
    clear_materials(obj)

    for index, group in enumerate(groups, start=1):
        material = create_material(f"{prefix}_{index:03d}", random_color())
        obj.data.materials.append(material)
        material_index = len(obj.data.materials) - 1

        for face in group:
            face.material_index = material_index


import bpy
