"""Real Blender asset relocation: reachability, packed/generated/UDIM and reopen."""
from pathlib import Path
from types import SimpleNamespace
import bpy,addon_utils,sys,tempfile,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators.relocate_project import used_images,relocate_project
from polygroups_generator.custom_ui.schema import Layout,walk
from polygroups_generator import ui
prefs=bpy.context.preferences.addons[ROOT.name].preferences
with tempfile.TemporaryDirectory(prefix='airetopo-relocate-test-') as temp:
    root=Path(temp)
    src=root/'source'; src.mkdir()
    def texture(name):
        path=src/name
        im=bpy.data.images.new(name,width=4,height=4)
        im.generated_color=(.1,.2,.7,1)
        im.filepath_raw=str(path); im.file_format='PNG'; im.save()
        bpy.data.images.remove(im)
        return bpy.data.images.load(str(path),check_existing=False)
    file=texture('shared.png')
    packed=texture('packed.png'); packed.pack()
    unused=texture('unused.png')
    tile1=texture('tile.1001.png'); texture('tile.1002.png')
    tile1.filepath=str(src/'tile.<UDIM>.png'); tile1.source='TILED'; tile1.tiles.new(1002)
    generated=bpy.data.images.new('Generated',width=4,height=4)
    generated.pixels[:]=[.3,.6,.2,1]*16
    cube=bpy.data.objects['Cube']
    material=bpy.data.materials.new('Used'); material.use_nodes=True
    cube.data.materials.clear(); cube.data.materials.append(material)
    nodes=material.node_tree.nodes; links=material.node_tree.links
    shader=nodes.get('Principled BSDF')
    group=bpy.data.node_groups.new('Nested used images','ShaderNodeTree')
    group.interface.new_socket(name='Color',in_out='OUTPUT',socket_type='NodeSocketColor')
    output=group.nodes.new('NodeGroupOutput')
    p=group.nodes.new('ShaderNodeTexImage'); p.image=packed
    group.links.new(p.outputs['Color'],output.inputs['Color'])
    groupnode=nodes.new('ShaderNodeGroup'); groupnode.node_tree=group
    current=groupnode.outputs['Color']
    for image in (file,generated,tile1):
        node=nodes.new('ShaderNodeTexImage'); node.image=image
        mix=nodes.new('ShaderNodeMixRGB')
        links.new(current,mix.inputs[1]); links.new(node.outputs['Color'],mix.inputs[2])
        current=mix.outputs[0]
    links.new(current,shader.inputs['Base Color'])
    disconnected=nodes.new('ShaderNodeTexImage'); disconnected.image=unused
    other=bpy.data.materials.new('Unused slot'); other.use_nodes=True
    cube.data.materials.append(other)
    node=other.node_tree.nodes.new('ShaderNodeTexImage'); node.image=unused
    other.node_tree.links.new(node.outputs['Color'],other.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    old_blend=None
    if not os.environ.get('AIRETOPO_TEST_UNSAVED'):
        bpy.ops.wm.save_as_mainfile(filepath=str(src/'original.blend'))
        old_blend=hashlib.sha256((src/'original.blend').read_bytes()).hexdigest()
    assert set(im.name for im in used_images())=={file.name,packed.name,generated.name,tile1.name}
    missing=file.filepath; file.filepath=str(src/'missing.png')
    try:
        relocate_project(str(root/'failed'),'Project')
        raise AssertionError('Missing texture was not rejected')
    except RuntimeError as error:
        assert 'missing' in str(error).lower()
        assert not (root/'failed').exists()
    file.filepath=missing
    nested=bool(os.environ.get('AIRETOPO_TEST_NESTED'))
    destination=root/'destination'
    if nested:
        destination.mkdir()
        (destination/'keep.txt').write_text('Existing parent contents')
    stem='Relocated_16_01' if nested else 'Relocated'
    saved,count=relocate_project(str(destination),stem,put_in_subfolder=nested)
    expected=(destination/(stem+'_Main_Folder') if nested else destination)/(stem+'.blend')
    assert saved == expected
    if nested:
        assert (destination/'keep.txt').read_text()=='Existing parent contents'
    assert count==4 and saved.is_file()
    assert bpy.data.filepath==str(saved)
    if old_blend:
        assert hashlib.sha256((src/'original.blend').read_bytes()).hexdigest()==old_blend
    assets=list((saved.parent/'textures').rglob('*'))
    files=[p for p in assets if p.is_file()]
    assert len(files)==5,[p.name for p in files]
    assert not any('unused' in p.name for p in files)
    assert next(p for p in files if p.name=='shared.png').read_bytes()==(src/'shared.png').read_bytes()
    assert next(p for p in files if p.name=='packed.png').read_bytes()==(src/'packed.png').read_bytes()
    src.rename(root/'source_removed')
    bpy.ops.wm.open_mainfile(filepath=str(saved),load_ui=False)
    for image in used_images():
        assert image.filepath.replace('\\','/').startswith('//textures/'),(image.name,image.filepath,image.source)
        if image.source=='TILED':
            for tile in image.tiles:
                assert Path(bpy.path.abspath(image.filepath.replace('<UDIM>',str(tile.number)))).is_file()
        else:
            assert Path(bpy.path.abspath(image.filepath)).is_file(),image.name
            image.reload(); assert len(image.pixels)>0,image.name; assert image.has_data,image.name
    window=bpy.context.window_manager.windows[0]
    area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    region=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=window,area=area,region=region):
        for mode in ('CLASSIC','CUSTOM','UI_PANEL'):
            prefs.ui_mode=mode
            prefs.custom_ui_show_session=True
            prefs.show_panel_session_status=True
            model=Layout(key=mode)
            if mode=='UI_PANEL':
                from polygroups_generator.custom_ui.lifecycle import Session
                session=Session(bpy.context); session.select(0,True); session.refresh(bpy.context)
                model=session.model
            else:
                ui.VIEW3D_PT_polygroups_generator.draw(SimpleNamespace(layout=model),bpy.context)
            assert not model.errors,model.errors
            assert any(b[0]=='operator' and b[1]=='wm.airetopo_relocate_project' for b in model.bindings.values()),mode
            save_group=next(n for n in walk(model.node) if n['kind']=='group' and n['id'].endswith('.show_panel_save_restart'))
            auto_group=next(n for n in walk(model.node) if n['kind']=='group' and n['id'].endswith('.show_panel_autosave'))
            def operators(group):
                return {model.bindings[n['id']][1] for n in walk(group)
                        if n['id'] in model.bindings and model.bindings[n['id']][0]=='operator'}
            assert 'wm.airetopo_relocate_project' in operators(save_group),mode
            assert 'wm.airetopo_relocate_project' not in operators(auto_group),mode
            assert 'wm.airetopo_open_recent_autosave' in operators(auto_group),mode
            assert 'wm.airetopo_open_saved_file' in operators(save_group),mode
print('PROJECT_RELOCATION_TESTS_PASSED')
