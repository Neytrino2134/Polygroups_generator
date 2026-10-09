"""Relocate the current project and only reachable mesh-material image assets."""
from pathlib import Path
from array import array
import re
import shutil
import tempfile
import bpy
from .dev_restart import _restart_poll, _execute_restart


def used_images():
    images, materials = {}, {}
    for scene in bpy.data.scenes:
        for obj in scene.objects:
            if obj.type != 'MESH':
                continue
            obj.update_from_editmode()
            for index in {p.material_index for p in obj.data.polygons}:
                if index < len(obj.material_slots):
                    material = obj.material_slots[index].material
                    if material:
                        if obj.library or material.library:
                            raise RuntimeError('Make linked meshes and materials local before relocating the project')
                        materials[material.as_pointer()] = material
    seen = set()
    def input_socket(socket, stack):
        for link in socket.links:
            if link.is_valid:
                output_socket(link.from_socket, stack)
    def output_socket(socket, stack):
        node = socket.node
        key = (socket.as_pointer(), tuple(n.as_pointer() for n in stack))
        if key in seen:
            return
        seen.add(key)
        if node.mute:
            for link in node.internal_links:
                if link.to_socket == socket:
                    input_socket(link.from_socket, stack)
            return
        if node.type in {'TEX_IMAGE', 'TEX_ENVIRONMENT'} and node.image:
            images[node.image.as_pointer()] = node.image
        if node.type == 'GROUP' and node.node_tree:
            for out in node.node_tree.nodes:
                if out.type == 'GROUP_OUTPUT' and out.is_active_output:
                    inner = out.inputs.get(socket.name)
                    if inner:
                        input_socket(inner, stack + (node,))
        elif node.type == 'GROUP_INPUT' and stack:
            outer = stack[-1].inputs.get(socket.name)
            if outer:
                input_socket(outer, stack[:-1])
        else:
            for inp in node.inputs:
                input_socket(inp, stack)
    for material in materials.values():
        if not material.use_nodes or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL' and node.is_active_output:
                for socket in node.inputs:
                    input_socket(socket, ())
    return list(images.values())


def _safe_name(name):
    return re.sub(r'[^\w. -]', '_', name).strip(' .') or 'Texture'


def _image_plan(image):
    if image.library:
        raise RuntimeError(f'Make linked image local first: {image.name}')
    source = image.source
    if source not in {'FILE', 'GENERATED', 'TILED', 'SEQUENCE', 'MOVIE'}:
        raise RuntimeError(f'Unsupported used image source: {image.name} ({source})')
    path = Path(bpy.path.abspath(image.filepath, library=image.library)) if image.filepath else None
    ext = {'JPEG': '.jpg', 'OPEN_EXR': '.exr', 'OPEN_EXR_MULTILAYER': '.exr', 'TIFF': '.tif', 'TARGA': '.tga'}.get(image.file_format, '.png')
    name = path.name if path else _safe_name(image.name) + ext
    if image.is_dirty or source == 'GENERATED':
        if source in {'TILED', 'SEQUENCE', 'MOVIE'}:
            raise RuntimeError(f'Save edits to tiled/animated image before relocation: {image.name}')
        if not image.has_data:
            raise RuntimeError(f'Image has no pixels: {image.name}')
        name = (path.stem if path else _safe_name(image.name)) + ext
        return name, [('pixels', image, name)]
    packed = list(image.packed_files)
    if packed:
        entries = [('packed', bytes(item.packed_file.data), Path(item.filepath).name or name) for item in packed]
        return name, entries
    if path is None:
        raise RuntimeError(f'Used image has no file: {image.name}')
    if source == 'TILED':
        pattern = str(path)
        if '<UDIM>' not in pattern and '<UVTILE>' not in pattern:
            raise RuntimeError(f'UDIM image needs a tile token: {image.name}')
        paths = []
        for tile in image.tiles:
            number = tile.number
            tile_path = Path(pattern.replace('<UDIM>', str(number)).replace('<UVTILE>', f'u{(number-1001)%10+1}_v{(number-1001)//10+1}'))
            paths.append(tile_path)
    elif source == 'SEQUENCE':
        match = re.match(r'^(.*?)(\d+)(\.[^.]+)$', path.name)
        if not match:
            raise RuntimeError(f'Cannot identify image sequence: {image.name}')
        prefix, digits, suffix = match.groups()
        expression = re.compile(re.escape(prefix) + r'\d{' + str(len(digits)) + '}' + re.escape(suffix) + '$')
        paths = sorted(p for p in path.parent.iterdir() if expression.fullmatch(p.name))
        if not paths:
            paths = [path]
    else:
        paths = [path]
    for item in paths:
        if not item.is_file():
            raise RuntimeError(f'Used texture is missing: {item}')
    return name, [('file', item, item.name) for item in paths]


def relocate_project(directory, project_name):
    """Preflight/copy first, then save; do not overwrite an existing project."""
    root = Path(directory).expanduser().resolve()
    if not project_name or project_name != _safe_name(project_name) or '/' in project_name or '\\' in project_name:
        raise RuntimeError('Choose a valid project filename')
    name = project_name if project_name.lower().endswith('.blend') else project_name + '.blend'
    if not root.parent.is_dir() or (root.exists() and (not root.is_dir() or any(root.iterdir()))):
        raise RuntimeError('Choose a new or empty destination folder')
    if bpy.data.filepath and root == Path(bpy.data.filepath).resolve().parent:
        raise RuntimeError('Choose a different project folder')
    images = used_images()
    plans = [(image, *_image_plan(image)) for image in images]
    old_paths = [(image, image.filepath, image.source,
                  [(item, item.filepath) for item in image.packed_files]) for image in images]
    # TemporaryDirectory cleanup is confined to this verified destination parent.
    with tempfile.TemporaryDirectory(prefix='.airetopo-relocate-', dir=str(root.parent)) as temp:
        staging = Path(temp).resolve()
        assert staging.parent == root.parent
        for index, (image, filename, entries) in enumerate(plans):
            folder = staging / 'textures' / f'{index:03d}_{_safe_name(image.name)}'
            folder.mkdir(parents=True)
            for kind, data, asset_name in entries:
                target = folder / asset_name
                if kind == 'file':
                    shutil.copy2(data, target)
                elif kind == 'packed':
                    target.write_bytes(data)
                else:
                    copy = image.copy()
                    try:
                        pixels = array('f', [0.0]) * len(image.pixels)
                        image.pixels.foreach_get(pixels)
                        copy.pixels.foreach_set(pixels)
                        copy.filepath_raw = str(target)
                        copy.save()
                    finally:
                        bpy.data.images.remove(copy)
        root.mkdir(exist_ok=True)
        if plans:
            shutil.move(str(staging/'textures'), str(root/'textures'))
    try:
        for index, (image, filename, entries) in enumerate(plans):
            destination = root / 'textures' / f'{index:03d}_{_safe_name(image.name)}' / filename
            # save_as remaps paths from the OLD blend directory to the new one.
            image.filepath = bpy.path.relpath(str(destination)) if bpy.data.filepath else str(destination)
            for item in image.packed_files:
                packed_destination = destination.parent / Path(item.filepath).name
                item.filepath = bpy.path.relpath(str(packed_destination)) if bpy.data.filepath else str(packed_destination)
            if image.source == 'GENERATED':
                image.source = 'FILE'
        result = bpy.ops.wm.save_as_mainfile(filepath=str(root/name), copy=False,
            relative_remap=True, check_existing=False)
        if 'FINISHED' not in result:
            raise RuntimeError('Blender could not save the relocated project')
        if any(not image.filepath.replace('\\','/').startswith('//textures/') for image in images):
            # Unsaved projects have no old relative-path base. Normalize now
            # that Blender knows the destination, then persist without backups.
            for index, (image, filename, entries) in enumerate(plans):
                image.filepath = '//textures/' + f'{index:03d}_{_safe_name(image.name)}/' + filename
                for item in image.packed_files:
                    item.filepath = '//textures/' + f'{index:03d}_{_safe_name(image.name)}/' + Path(item.filepath).name
            versions = bpy.context.preferences.filepaths.save_version
            try:
                bpy.context.preferences.filepaths.save_version = 0
                if 'FINISHED' not in bpy.ops.wm.save_mainfile(check_existing=False):
                    raise RuntimeError('Could not save relative texture paths')
            finally:
                bpy.context.preferences.filepaths.save_version = versions
    except Exception:
        for image, path, source, packed_paths in old_paths:
            image.filepath = path
            image.source = source
            for item, packed_path in packed_paths:
                item.filepath = packed_path
        raise
    return root/name, len(images)


class WM_OT_airetopo_relocate_project(bpy.types.Operator):
    bl_idname = 'wm.airetopo_relocate_project'
    bl_label = 'Save Project to New Folder and Restart'
    bl_description = 'Copy only textures connected to used mesh materials, save in a new/empty folder and restart from that file'
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    project_name: bpy.props.StringProperty(name='Project Name', default='Project')
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return _restart_poll()

    def invoke(self, context, event):
        self.project_name = Path(bpy.data.filepath).stem if bpy.data.filepath else 'Project'
        self.directory = str(Path(bpy.data.filepath).parent) if bpy.data.filepath else ''
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, 'project_name')
        self.layout.label(text='Choose a new or empty folder', icon='INFO')

    def execute(self, context):
        if any(bpy.app.is_job_running(job) for job in ('RENDER','OBJECT_BAKE')):
            self.report({'ERROR'}, 'Wait for rendering or baking to finish')
            return {'CANCELLED'}
        settings = context.scene.polygroups_model_preparation_settings
        if settings.batch_is_running or context.scene.polygroups_remesh_status.is_running:
            self.report({'ERROR'}, 'Wait for import or remesh to finish')
            return {'CANCELLED'}
        try:
            path, count = relocate_project(self.directory, self.project_name)
        except Exception as exc:
            self.report({'ERROR'}, f'Project relocation failed; Blender remains open: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Saved {path} with {count} used texture(s)')
        return _execute_restart(self, context, False, use_saved_current=True)
