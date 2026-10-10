"""Frozen native-bake diagnostics, with reversible material and selection overrides."""
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import bpy
import numpy as np

from .bake_artifact_mask import canonical_z, classify, conservative_resize, pad_reasons

RUN_PROP = 'polygroups_projection_run'
META_PROP = 'polygroups_projection_metadata'
ARTIFACT_PROP = 'polygroups_bake_artifact_image'
BAKE_FIELDS = ('use_selected_to_active', 'use_cage', 'cage_object', 'cage_extrusion',
               'max_ray_distance', 'margin', 'margin_type', 'use_clear', 'normal_space',
               'normal_r', 'normal_g', 'normal_b')


def invalidate(target):
    target[RUN_PROP] = uuid.uuid4().hex
    # Keep the image slot for reuse: clearing it allocates another full-size image
    # on every bake. The new run token makes the previous contents unexportable.


def pixels(image):
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    return values.reshape(image.size[1], image.size[0], 4)


def geometry_signature(context, objects):
    digest = hashlib.sha256()
    graph = context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            digest.update(obj.name_full.encode())
            digest.update(np.asarray(obj.matrix_world, dtype=np.float64).tobytes())
            coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', coords)
            digest.update(coords.tobytes())
            loops = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get('vertex_index', loops)
            digest.update(loops.tobytes())
            normals = np.empty(len(mesh.corner_normals) * 3, dtype=np.float32)
            mesh.corner_normals.foreach_get('vector', normals)
            digest.update(normals.tobytes())
            digest.update(str([(p.loop_start, p.loop_total, p.use_smooth, p.material_index) for p in mesh.polygons]).encode())
            if mesh.uv_layers.active:
                uv = np.empty(len(mesh.loops) * 2, dtype=np.float32)
                mesh.uv_layers.active.data.foreach_get('uv', uv)
                digest.update(mesh.uv_layers.active.name.encode())
                digest.update(uv.tobytes())
        finally:
            evaluated.to_mesh_clear()
    return digest.hexdigest()


def material_signature(objects):
    visited = set()
    data = []
    def value(socket):
        item = getattr(socket, 'default_value', None)
        if isinstance(item, (str, float, int, bool)) or item is None:
            return item
        try:
            return list(item)
        except TypeError:
            return getattr(item, 'name_full', str(item))
    def tree_data(tree):
        if tree is None or tree in visited:
            return
        visited.add(tree)
        data.append((tree.name_full, [(link.from_node.name, link.from_socket.identifier,
            link.to_node.name, link.to_socket.identifier) for link in tree.links]))
        for node in tree.nodes:
            data.append((node.name, node.bl_idname, [value(socket) for socket in node.inputs],
                [(name, str(getattr(node, name))) for name in ('operation', 'blend_type', 'uv_map', 'attribute_name', 'space') if hasattr(node, name)]))
            image = getattr(node, 'image', None)
            if image:
                data.append((image.name_full, image.colorspace_settings.name))
            tree_data(getattr(node, 'node_tree', None))
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            data.append((obj.name_full, slot.link, mat.name_full if mat else None))
            if mat:
                tree_data(mat.node_tree)
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def uv_ownership(context, target, width, height):
    """UV-connected island IDs; ambiguous overlap has ID -1 (no edge growth)."""
    evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        if mesh.uv_layers.active is None:
            raise ValueError('Target has no active UV map')
        mesh.calc_loop_triangles()
        uv = mesh.uv_layers.active.data
        parents = list(range(len(mesh.polygons)))
        def root(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return i
        edges = {}
        for polygon in mesh.polygons:
            loops = list(polygon.loop_indices)
            for a, b in zip(loops, loops[1:] + loops[:1]):
                ends = sorted(((mesh.loops[a].vertex_index, tuple(uv[a].uv)),
                               (mesh.loops[b].vertex_index, tuple(uv[b].uv))))
                key = tuple(ends)
                if key in edges:
                    parents[root(polygon.index)] = root(edges[key])
                else:
                    edges[key] = polygon.index
        owners = np.zeros((height, width), dtype=np.int32)
        strict_coverage = np.zeros((height, width), dtype=bool)
        for tri in mesh.loop_triangles:
            points = np.asarray([uv[i].uv[:] for i in tri.loops], dtype=np.float64)
            if np.any(points < -1e-6) or np.any(points > 1 + 1e-6):
                raise ValueError('UDIM/out-of-tile UVs are not supported by projection masks')
            points *= (width, height)
            x0, y0 = np.maximum(np.floor(points.min(axis=0)).astype(int), 0)
            x1, y1 = np.minimum(np.ceil(points.max(axis=0)).astype(int), (width, height))
            if x0 >= x1 or y0 >= y1:
                continue
            a, b, c = points
            denominator = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
            if abs(denominator) < 1e-12:
                continue
            owner = root(tri.polygon_index) + 1
            xx = np.arange(x0, x1)[None, :] + .5
            for start in range(y0, y1, 64):
                end = min(start + 64, y1)
                yy = np.arange(start, end)[:, None] + .5
                u = ((xx-a[0])*(c[1]-a[1]) - (yy-a[1])*(c[0]-a[0])) / denominator
                v = ((b[0]-a[0])*(yy-a[1]) - (b[1]-a[1])*(xx-a[0])) / denominator
                inside = (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8)
                region = owners[start:end, x0:x1]
                seen = strict_coverage[start:end, x0:x1]
                strict = (u > 1e-8) & (v > 1e-8) & (u+v < 1-1e-8)
                conflict = inside & (((region != 0) & (region != owner)) | (strict & seen))
                region[inside & (region == 0)] = owner
                region[conflict] = -1
                seen |= strict
        return owners
    finally:
        evaluated.to_mesh_clear()


@dataclass(frozen=True)
class BakeProjectionContext:
    run: str
    frame: int
    signature: str
    materials: str
    width: int
    height: int
    normal_name: str
    bake: tuple
    source_names: tuple


class ProjectionSession:
    """Prepare/launch/complete is shared by synchronous and modal operators."""
    def __init__(self, context, target, sources, settings, normal, read_normal=True):
        self.context, self.target, self.sources = context, target, tuple(sources)
        self.settings = SimpleNamespace(**{name: getattr(settings, name) for name in (
            'bake_artifact_mode', 'bake_artifact_radius', 'bake_artifact_inherit_margin', 'bake_artifact_geometry', 'bake_artifact_self_intersections',
            'bake_artifact_match_normal', 'bake_artifact_resolution', 'bake_artifact_mask', 'bake_resolution',
            'autogenerate_smart_cage', 'smart_cage_object', 'use_selected_to_active', 'cage_extrusion', 'image_prefix')})
        self.scene = context.scene
        self.original_engine = self.scene.render.engine
        self.original_type = self.scene.cycles.bake_type
        self.bake_snapshot = {key: getattr(self.scene.render.bake, key) for key in BAKE_FIELDS}
        self.selection = tuple(context.selected_objects)
        self.active = context.view_layer.objects.active
        self.material_backups, self.temp_materials, self.temp_images = [], [], []
        self.handlers = []
        self.native_cancelled = False
        self.closed = False
        self.normal = normal if settings.bake_normal else None
        self.z_epsilon = .001 if not self.normal or self.normal.is_float else .004
        if normal is None:
            raise ValueError('Missing normal bake target image')
        width, height = tuple(normal.size)
        if normal.source == 'TILED':
            raise ValueError('UDIM projection masks are not supported')
        cage = self.bake_snapshot['cage_object'] if self.bake_snapshot['use_cage'] else None
        self.objects = (target, *self.sources, *((cage,) if cage else ()))
        # Selected-to-active samples source shaders; target bake image nodes are
        # outputs and may legitimately be reinitialized by Blender during NORMAL.
        self.material_objects = self.sources if self.bake_snapshot['use_selected_to_active'] else (target,)
        self.frozen = BakeProjectionContext(target[RUN_PROP], self.scene.frame_current,
            geometry_signature(context, self.objects), material_signature(self.material_objects), width, height, self.normal.name if self.normal else '',
            tuple(self.bake_snapshot.items()), tuple(o.name_full for o in sources))
        self.ownership = uv_ownership(context, target, width, height)
        self.z = None
        if self.normal and read_normal:
            self.capture_normal()
        self.hit = self.domain = None

    @property
    def swizzle(self):
        return tuple(self.bake_snapshot[k] for k in ('normal_r', 'normal_g', 'normal_b'))

    def validate(self):
        if self.target.get(RUN_PROP) != self.frozen.run or self.scene.frame_current != self.frozen.frame:
            raise ValueError('Bake run/frame changed during diagnostics')
        if geometry_signature(self.context, self.objects) != self.frozen.signature:
            raise ValueError('Evaluated geometry/UVs changed during diagnostics')
        if material_signature(self.material_objects) != self.frozen.materials:
            raise ValueError('Materials changed during diagnostics')

    def capture_normal(self):
        if self.native_cancelled:
            raise RuntimeError('Native normal bake was cancelled')
        self.validate()
        if tuple(self.normal.size) != (self.frozen.width, self.frozen.height):
            raise ValueError('Normal image resolution changed during bake')
        self.z = canonical_z(pixels(self.normal), self.swizzle)
        self.unwatch()

    def watch(self):
        self.unwatch()
        self.native_cancelled = False
        def cancelled(obj, *unused):
            if obj == self.target:
                self.native_cancelled = True
        bpy.app.handlers.object_bake_cancel.append(cancelled)
        self.handlers.append(cancelled)

    def unwatch(self):
        for handler in self.handlers:
            if handler in bpy.app.handlers.object_bake_cancel:
                bpy.app.handlers.object_bake_cancel.remove(handler)
        self.handlers.clear()

    def _override_materials(self, obj, image=None, white=False):
        backup = (obj, obj.active_material_index, [(s.link, s.material) for s in obj.material_slots])
        self.material_backups.append(backup)
        if not obj.material_slots:
            obj.data.materials.append(None)
        for slot in obj.material_slots:
            mat = slot.material.copy() if slot.material else bpy.data.materials.new('Projection diagnostic')
            self.temp_materials.append(mat)
            slot.link = 'OBJECT'
            slot.material = mat
            mat.use_nodes = True
            tree = mat.node_tree
            if white:
                for out in [n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL']:
                    emit = tree.nodes.new('ShaderNodeEmission')
                    emit.inputs['Color'].default_value = (1, 1, 1, 1)
                    # Surface replacement preserves displacement and its linked graph.
                    tree.links.new(emit.outputs[0], out.inputs['Surface'])
            if image:
                node = tree.nodes.new('ShaderNodeTexImage')
                node.image = image
                tree.nodes.active = node

    def restore_materials(self):
        for obj, index, slots in reversed(self.material_backups):
            if not slots:
                obj.data.materials.clear()
            else:
                for slot, (link, material) in zip(obj.material_slots, slots):
                    slot.link = link
                    slot.material = material
            obj.active_material_index = index
        self.material_backups.clear()
        for material in self.temp_materials:
            bpy.data.materials.remove(material)
        self.temp_materials.clear()

    def prepare(self, kind):
        if bpy.app.is_job_running('OBJECT_BAKE'):
            raise RuntimeError('Another bake job is still running')
        self.validate()
        self.restore_materials()
        image = bpy.data.images.new('Projection private '+kind, width=self.frozen.width,
            height=self.frozen.height, alpha=True, float_buffer=True)
        self.temp_images.append(image)
        image.colorspace_settings.name = 'Non-Color'
        image.generated_color = (0, 0, 0, 0)
        for key, value in self.bake_snapshot.items():
            setattr(self.scene.render.bake, key, value)
        bake = self.scene.render.bake
        self.scene.render.engine = 'CYCLES'
        bake.margin = 0
        bake.use_clear = True
        if kind == 'UV':
            bake.use_selected_to_active = False
            bake.use_cage = False
            bake.cage_object = None
        self._override_materials(self.target, image, white=kind == 'UV')
        if kind == 'HIT':
            for source in self.sources:
                self._override_materials(source, white=True)
            if not bake.use_selected_to_active:
                # Self bake: target surface is the emission source as well.
                self.restore_materials()
                self._override_materials(self.target, image, white=True)
        for obj in self.context.selected_objects:
            obj.select_set(False)
        for obj in ((self.target,) if kind == 'UV' or not bake.use_selected_to_active else (self.target, *self.sources)):
            obj.select_set(True)
        self.context.view_layer.objects.active = self.target
        self.current_image, self.kind = image, kind
        self.watch()
        return 'NORMAL' if kind == 'NORMAL' else 'EMIT'

    def complete(self):
        if bpy.app.is_job_running('OBJECT_BAKE'):
            raise RuntimeError('Cannot read a running diagnostic bake')
        if self.native_cancelled:
            raise RuntimeError('Native diagnostic bake was cancelled')
        values = pixels(self.current_image)
        if self.kind == 'NORMAL':
            self.z = canonical_z(values, self.swizzle)
        elif self.kind == 'HIT':
            self.hit = values[..., 0] > .5
        else:
            self.domain = values[..., 0] > .5
        del values
        self.restore_materials()
        self.temp_images.remove(self.current_image)
        bpy.data.images.remove(self.current_image)
        self.current_image = None
        self.unwatch()

    def result(self):
        from ..operators.baking import _ensure_target_image, _write_pixels, _generate_legacy_geometric_artifact_mask
        self.validate()
        inherited_margin = self.bake_snapshot['margin'] if self.settings.bake_artifact_inherit_margin else 0
        radius = inherited_margin + self.settings.bake_artifact_radius
        reasons = classify(self.z, self.domain if self.hit is None else self.hit, self.domain, self.ownership,
            radius=0, epsilon=self.z_epsilon)
        if self.settings.bake_artifact_geometry or self.settings.bake_artifact_self_intersections:
            # Explicit supplementary geometry diagnostics; never replace native core.
            legacy, _ = _generate_legacy_geometric_artifact_mask(self.context, self.target, self.sources, self.settings,
                resolution_override=self.frozen.width, include_source=self.settings.bake_artifact_geometry, radius_override=0)
            geometric = pixels(legacy)[..., 0] > .5
            if geometric.shape != reasons.shape:
                # Legacy resolution remains independent; supplementary output must match.
                raise ValueError('Optional geometric diagnostics require matching mask resolution')
            reasons[geometric] |= 16
        reasons = pad_reasons(reasons, self.domain, self.ownership, radius)
        mask = reasons != 0
        size = self.frozen.width if self.settings.bake_artifact_match_normal else self.settings.bake_artifact_resolution
        if self.frozen.width != self.frozen.height:
            raise ValueError('Non-square normal maps are not supported by artifact output')
        mask = conservative_resize(mask, size)
        image = _ensure_target_image(self.target, self.settings, ARTIFACT_PROP, 'ArtifactMask', 'Non-Color', resolution=size)
        # A real datablock reference survives blend copies and follows existing
        # Batch AutoBake material/image ownership and cleanup. The node is unlinked.
        tree = self.target.active_material.node_tree
        node = tree.nodes.get('PolyGroups Bake Artifact Mask')
        if node is None:
            node = tree.nodes.new('ShaderNodeTexImage')
            node.name = 'PolyGroups Bake Artifact Mask'
            node.label = 'Projection Artifact Mask (diagnostic)'
            node.location = (-560, -560)
        node.image = image
        image.use_fake_user = False
        rgba = np.ones((size, size, 4), dtype=np.float32)
        rgba[..., :3] = mask[..., None]
        _write_pixels(image, rgba.ravel())
        metadata = dict(version=1, producer='native-cycles-projection', run=self.frozen.run,
            analysis=self.settings.bake_artifact_mode,
            target=self.target.name_full, sources=list(self.frozen.source_names), frame=self.frozen.frame,
            geometry=self.frozen.signature, normal=self.frozen.normal_name, normal_size=[self.frozen.width, self.frozen.height],
            materials=self.frozen.materials,
            size=[size, size], swizzle=list(self.swizzle), epsilon=self.z_epsilon, edge_z=.08,
            radius=radius, extra_padding=self.settings.bake_artifact_radius,
            inherit_margin=self.settings.bake_artifact_inherit_margin, inherited_margin=inherited_margin,
            padding='8-neighbor dilation inside same island and nearest-island gutter; ambiguous ties blocked',
            reversed=int(np.count_nonzero(reasons & 1)), misses=int(np.count_nonzero(reasons & 2)),
            edges=int(np.count_nonzero(reasons & 4)), overlaps=int(np.count_nonzero(self.ownership == -1)),
            caveat='Positive-Z wrong hits are not detected; overlapping UVs are ambiguous',
            cage=self.bake_snapshot['cage_object'].name if self.bake_snapshot['cage_object'] else '',
            extrusion=self.bake_snapshot['cage_extrusion'], ray_distance=self.bake_snapshot['max_ray_distance'],
            selected_to_active=self.bake_snapshot['use_selected_to_active'], margin=self.bake_snapshot['margin'])
        image[META_PROP] = json.dumps(metadata, sort_keys=True)
        image[RUN_PROP] = self.frozen.run
        return image, metadata

    def passes(self):
        return (('NORMAL',) if self.z is None else ()) + (('HIT',) if self.settings.bake_artifact_mode == 'FULL' else ()) + ('UV',)

    def close(self):
        if self.closed:
            return
        if bpy.app.is_job_running('OBJECT_BAKE'):
            raise RuntimeError('Wait for the native bake job before restoring diagnostics')
        self.restore_materials()
        self.unwatch()
        for image in self.temp_images:
            bpy.data.images.remove(image)
        self.temp_images.clear()
        for key, value in self.bake_snapshot.items():
            setattr(self.scene.render.bake, key, value)
        self.scene.cycles.bake_type = self.original_type
        self.scene.render.engine = self.original_engine
        for obj in self.context.selected_objects:
            obj.select_set(False)
        for obj in self.selection:
            obj.select_set(True)
        self.context.view_layer.objects.active = self.active
        self.closed = True


def current_mask(target, normal):
    image = bpy.data.images.get(target.get(ARTIFACT_PROP, ''))
    if image is None:
        return None
    if not target.get(RUN_PROP):
        raise ValueError('Artifact mask belongs to an older bake; bake again')
    if image.get(RUN_PROP) != target.get(RUN_PROP):
        return None
    meta = json.loads(image.get(META_PROP, '{}'))
    if meta.get('normal') and (normal is None or normal.name != meta['normal'] or list(normal.size) != meta['normal_size']):
        raise ValueError('Artifact mask normal association changed; bake again')
    if list(image.size) != meta.get('size'):
        raise ValueError('Artifact mask dimensions changed')
    if meta.get('normal_hash') and hashlib.sha256(pixels(normal).tobytes()).hexdigest() != meta['normal_hash']:
        raise ValueError('Normal pixels changed since artifact analysis; bake again')
    return image


def seal_mask(target):
    """Associate the finished, background-filled normal image with its raw-bake mask."""
    image = bpy.data.images.get(target.get(ARTIFACT_PROP, ''))
    if image is None or image.get(RUN_PROP) != target.get(RUN_PROP):
        return
    meta = json.loads(image.get(META_PROP, '{}'))
    normal = bpy.data.images.get(meta.get('normal', ''))
    if normal is not None:
        meta['normal_hash'] = hashlib.sha256(pixels(normal).tobytes()).hexdigest()
    image[META_PROP] = json.dumps(meta, sort_keys=True)


def save_mask_png(image, filepath):
    """Verify a temporary PNG against the binary image before atomic replacement."""
    original_path, original_format = image.filepath_raw, image.file_format
    fd, temporary = tempfile.mkstemp(prefix='.artifact-', suffix='.png', dir=os.path.dirname(filepath))
    os.close(fd)
    check = None
    try:
        expected = pixels(image)
        if not np.all((expected[..., :3] == 0) | (expected[..., :3] == 1)) or not np.all(expected[..., 3] == 1):
            raise ValueError('Artifact mask is not opaque binary RGB')
        image.filepath_raw, image.file_format = temporary, 'PNG'
        image.save()
        check = bpy.data.images.load(temporary, check_existing=False)
        check.colorspace_settings.name = 'Non-Color'
        if tuple(check.size) != tuple(image.size) or not np.array_equal(pixels(check), expected):
            raise ValueError('Saved artifact PNG failed pixel verification')
        bpy.data.images.remove(check)
        check = None
        os.replace(temporary, filepath)
        image.filepath_raw = bpy.path.relpath(filepath)
        # Persistent provenance accompanies exported PNGs (image custom properties are blend-only).
        sidecar = filepath + '.json'
        fd, meta_temp = tempfile.mkstemp(prefix='.artifact-meta-', dir=os.path.dirname(filepath))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(image[META_PROP])
            os.replace(meta_temp, sidecar)
        finally:
            if os.path.exists(meta_temp):
                os.remove(meta_temp)
    except Exception:
        image.filepath_raw, image.file_format = original_path, original_format
        raise
    finally:
        if check:
            bpy.data.images.remove(check)
        if os.path.exists(temporary):
            os.remove(temporary)
