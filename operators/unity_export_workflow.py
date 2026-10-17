"""One-click asset preparation and global Unity export presets."""
import json
import os
import re
from pathlib import Path
import bpy

MESH_FIELDS = (
    'unity_skip_lods',
    'unity_export_directory', 'unity_export_overwrite', 'unity_export_clear_asset_folder',
    'unity_export_autosave', 'unity_export_fbx', 'unity_export_gltf', 'unity_gltf_mode',
    'unity_export_all_renders', 'unity_export_info_format', 'unity_use_auto_rig_pro',
    'unity_render_freestyle', 'unity_render_image_format', 'unity_render_mesh_info',
    'unity_render_separate', 'unity_render_mode', 'unity_render_text',
)
RENDER_FIELDS = (
    'freestyle_line_color', 'freestyle_line_thickness', 'freestyle_edges', 'freestyle_as_render_pass',
    'animation_views_image_format', 'animation_container', 'animation_frame_count', 'animation_fps',
    'transparent_background',
)
_PRESET_ITEMS = []


def unity_name_from_filepath(filepath):
    """Read Name_NameID_VersionID without treating underscores in Name as separators."""
    if not filepath:
        raise ValueError('Save the blend file before loading its name')
    stem = re.sub(r'\.LOD[0-9]+$', '', Path(filepath).stem, flags=re.IGNORECASE)
    match = re.fullmatch(r'(.+)_([0-9]{1,2})_(.+)', stem)
    return (match[1], match[2].zfill(2), match[3]) if match else (stem, '00', '01')


def step_naming_index(value, delta, name_index=False):
    match = re.fullmatch(r'(.*?)([0-9]+)', value.strip() or '00')
    if not match or (name_index and match[1]):
        return value
    prefix, digits = match.groups()
    number = max(0, int(digits) + delta)
    if name_index:
        number = min(99, number)
    return prefix + str(number).zfill(max(2, len(digits)))


def _load_dialog_name(self, context):
    if not self.load_from_file:
        return
    self.load_from_file = False
    if bpy.data.filepath:
        self.asset_name, self.name_index, self.version_index = unity_name_from_filepath(bpy.data.filepath)


def _index_button(field, delta):
    button = field + ('_decrease' if delta < 0 else '_increase')
    def update(self, context):
        if not getattr(self, button):
            return
        setattr(self, button, False)
        setattr(self, field, step_naming_index(getattr(self, field), delta, field == 'name_index'))
    return update


class OBJECT_OT_polygroups_unity_load_from_file(bpy.types.Operator):
    bl_idname = 'object.polygroups_unity_load_from_file'
    bl_label = 'Load from File'
    bl_description = 'Load the asset name, Name Index and Version Index from the current blend filename'
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        settings = context.scene.polygroups_mesh_finalization_settings
        settings.unity_asset_name, settings.unity_name_index, settings.unity_asset_index = unity_name_from_filepath(bpy.data.filepath)
        return {'FINISHED'}


def preset_path():
    return Path(bpy.utils.user_resource('CONFIG', path='airetopo', create=True)) / 'unity_export_presets.json'


def read_presets():
    path = preset_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid Unity export preset catalog')
    return data


def preset_items(self, context):
    global _PRESET_ITEMS
    try:
        names = sorted(read_presets(), key=str.casefold)
    except (OSError, ValueError):
        names = []
    _PRESET_ITEMS = [(name, name, '') for name in names] or [('__NONE__', 'No saved presets', '')]
    return _PRESET_ITEMS


def snapshot_preset(context):
    mesh = context.scene.polygroups_mesh_finalization_settings
    render = context.scene.polygroups_render_settings
    return {'mesh': {key: getattr(mesh, key) for key in MESH_FIELDS},
            'render': {key: list(getattr(render, key)) if key == 'freestyle_line_color' else getattr(render, key)
                       for key in RENDER_FIELDS}}


def apply_preset(context, preset):
    # Validate all fields before applying the catalog entry.
    plans = []
    for section, settings, fields in (
        ('mesh', context.scene.polygroups_mesh_finalization_settings, MESH_FIELDS),
        ('render', context.scene.polygroups_render_settings, RENDER_FIELDS),
    ):
        values = preset.get(section, {})
        if not isinstance(values, dict):
            raise ValueError('Invalid preset settings')
        for key in fields:
            if key not in values:
                continue
            value = values[key]
            prop = settings.bl_rna.properties[key]
            if prop.type == 'ENUM' and value not in prop.enum_items.keys():
                raise ValueError(f'Invalid preset value: {key}')
            if prop.type == 'BOOLEAN' and not isinstance(value, bool):
                raise ValueError(f'Invalid preset value: {key}')
            if prop.type == 'STRING' and not isinstance(value, str):
                raise ValueError(f'Invalid preset value: {key}')
            if key == 'freestyle_line_color' and (not isinstance(value, list) or len(value) != 4
                    or any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in value)):
                raise ValueError('Invalid preset line color')
            plans.append((settings, key, value))
    for settings, key, value in plans:
        setattr(settings, key, value)


class OBJECT_OT_polygroups_save_unity_export_preset(bpy.types.Operator):
    bl_idname = 'object.polygroups_save_unity_export_preset'
    bl_label = 'Save Unity Export Preset'
    bl_description = 'Save Unity export settings and line color in the global Blender user configuration'
    name: bpy.props.StringProperty(name='Preset Name', default='Unity Export')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        self.layout.prop(self, 'name')

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({'ERROR'}, 'Enter a preset name')
            return {'CANCELLED'}
        try:
            catalog = read_presets()
            catalog[name] = snapshot_preset(context)
            path = preset_path()
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, path)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Saved global preset: {name}')
        return {'FINISHED'}


class OBJECT_OT_polygroups_load_unity_export_preset(bpy.types.Operator):
    bl_idname = 'object.polygroups_load_unity_export_preset'
    bl_label = 'Load Unity Export Preset'
    bl_description = 'Load a globally saved Unity export preset including its Freestyle line color'
    bl_options = {'UNDO'}
    preset: bpy.props.EnumProperty(name='Preset', items=preset_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        self.layout.prop(self, 'preset')

    def execute(self, context):
        try:
            catalog = read_presets()
            if self.preset not in catalog:
                raise ValueError('No saved Unity export preset selected')
            apply_preset(context, catalog[self.preset])
        except (OSError, ValueError, TypeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Loaded global preset: {self.preset}')
        return {'FINISHED'}


def clear_prepare_asset_folder(context, folder, root):
    """Stage all selected material textures before replacing this asset's folders."""
    from .unity_reexport import refresh_asset_textures
    refresh_asset_textures(context.selected_objects, os.path.basename(folder), root)


class OBJECT_OT_polygroups_prepare_and_export_unity(bpy.types.Operator):
    bl_idname = 'object.polygroups_prepare_and_export_unity'
    bl_label = 'Prepare and Export'
    bl_description = 'Generate Smart LODs or use selected existing meshes, prepare meshes with Auto LODs for Unity, then export'
    skip_lods: bpy.props.BoolProperty(name='Skip LODs', default=False,
        description='Skip Generate LODs only; run Prepare Meshes (Auto LODs) on selected meshes, then export')
    asset_name: bpy.props.StringProperty(name='Asset Name')
    name_index: bpy.props.StringProperty(name='Name Index', default='00', maxlen=2)
    version_index: bpy.props.StringProperty(name='Version Index', default='01')
    load_from_file: bpy.props.BoolProperty(name='Load from File', options={'HIDDEN', 'SKIP_SAVE'},
        description='Load the name and indices from the current blend filename', update=_load_dialog_name)
    name_index_decrease: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
        description='Decrease Name Index', update=_index_button('name_index', -1))
    name_index_increase: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
        description='Increase Name Index', update=_index_button('name_index', 1))
    version_index_decrease: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
        description='Decrease Version Index', update=_index_button('version_index', -1))
    version_index_increase: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
        description='Increase Version Index', update=_index_button('version_index', 1))

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and context.active_object is not None
                and context.active_object.type == 'MESH'
                and not context.scene.polygroups_render_settings.is_running)

    def invoke(self, context, event):
        settings = context.scene.polygroups_mesh_finalization_settings
        self.asset_name = settings.unity_asset_name
        self.name_index = settings.unity_name_index
        self.version_index = settings.unity_asset_index
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text='Start')

    def draw(self, context):
        self.layout.prop(self, 'skip_lods')
        self.layout.prop(self, 'asset_name')
        for field in ('name_index', 'version_index'):
            row = self.layout.row(align=True)
            row.prop(self, field + '_decrease', text='', icon='TRIA_LEFT', toggle=True)
            row.prop(self, field)
            row.prop(self, field + '_increase', text='', icon='TRIA_RIGHT', toggle=True)
        row = self.layout.row()
        row.enabled = bool(bpy.data.filepath)
        row.prop(self, 'load_from_file', text='Load from File', icon='FILE_BLEND', toggle=True)

    def execute(self, context):
        from .unity_preparation import unity_name
        settings = context.scene.polygroups_mesh_finalization_settings
        if not self.asset_name.strip() or not self.name_index.isdigit() or not self.version_index.strip():
            self.report({'ERROR'}, 'Enter an asset name, numeric Name Index and Version Index')
            return {'CANCELLED'}
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Save the blend file before Prepare and Export')
            return {'CANCELLED'}
        if settings.unity_use_auto_rig_pro:
            self.report({'ERROR'}, 'Prepare and Export creates mesh LODs; disable Auto-Rig Pro Export for this operation')
            return {'CANCELLED'}
        if not settings.unity_export_fbx and not settings.unity_export_gltf:
            self.report({'ERROR'}, 'Enable FBX or GLTF export')
            return {'CANCELLED'}
        if settings.unity_export_all_renders and context.scene.camera is None:
            self.report({'ERROR'}, 'Set the scene camera before exporting renders')
            return {'CANCELLED'}
        settings.unity_asset_name = self.asset_name.strip()
        settings.unity_name_index = self.name_index.zfill(2)
        settings.unity_asset_index = self.version_index.strip()
        asset = unity_name(settings, '')
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        reuse_prepared = bool(selected_meshes) and all(
            obj.get('unity_prepared') and re.sub(r'\.LOD\d+$', '', obj.name, flags=re.IGNORECASE) == asset
            and obj.active_material is not None and obj.active_material.get('unity_asset_name') == asset
            for obj in selected_meshes)
        use_existing_lods = self.skip_lods or reuse_prepared
        for index in range(0 if use_existing_lods else settings.smart_lods_count):
            if bpy.data.objects.get(unity_name(settings, f'LOD{index}')):
                self.report({'ERROR'}, 'Prepared mesh names already exist; choose another index')
                return {'CANCELLED'}
        folder = os.path.join(bpy.path.abspath(settings.unity_export_directory), unity_name(settings, ''))
        if os.path.exists(folder) and not (settings.unity_export_clear_asset_folder or settings.unity_export_overwrite):
            self.report({'ERROR'}, 'Asset folder already exists; enable Clear Asset Folder or Overwrite')
            return {'CANCELLED'}
        if not settings.unity_export_directory.strip():
            self.report({'ERROR'}, 'Choose a Unity export directory')
            return {'CANCELLED'}
        if settings.unity_export_clear_asset_folder:
            try:
                if use_existing_lods:
                    meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
                    if not 1 <= len(meshes) <= 6:
                        raise ValueError('Select 1–6 meshes for LOD0–LOD5')
                    for index in range(len(meshes)):
                        existing = bpy.data.objects.get(unity_name(settings, f'LOD{index}'))
                        if existing is not None and existing not in meshes:
                            raise ValueError(f'An object named {existing.name} already exists; choose another index')
                clear_prepare_asset_folder(context, folder, bpy.path.abspath(settings.unity_export_directory))
            except (RuntimeError, ValueError, OSError) as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
        if reuse_prepared:
            pass  # Same-index reexport keeps material/image identities and existing LODs.
        elif use_existing_lods:
            try:
                prepared = bpy.ops.object.polygroups_prepare_unity(auto_lods=True)
            except RuntimeError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
            if 'FINISHED' not in prepared:
                return {'CANCELLED'}
        else:
            mode = settings.smart_lods_prepare_mode
            try:
                settings.smart_lods_prepare_mode = 'UNITY'
                if 'FINISHED' not in bpy.ops.object.polygroups_smart_lods_prepare():
                    return {'CANCELLED'}
            finally:
                settings.smart_lods_prepare_mode = mode
        result = bpy.ops.object.polygroups_export_unity('EXEC_DEFAULT' if bpy.app.background else 'INVOKE_DEFAULT')
        return {'FINISHED'} if 'RUNNING_MODAL' in result else result
