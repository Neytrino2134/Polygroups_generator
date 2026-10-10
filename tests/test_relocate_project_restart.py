"""Actual restart handshake with a real replacement Blender process."""
from pathlib import Path
import bpy,addon_utils,sys,tempfile,os,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators import dev_restart
LOG=ROOT/'docs/custom_ui/relocate_restart_test.log'
LOG.write_text('Starting real restart test\n')
test_root=Path(tempfile.mkdtemp(prefix='airetopo-relocate-restart-'))
source=test_root/'source'; source.mkdir()
image=bpy.data.images.new('Used',width=4,height=4)
image.filepath_raw=str(source/'used.png'); image.file_format='PNG'; image.save()
bpy.data.images.remove(image)
image=bpy.data.images.load(str(source/'used.png'))
material=bpy.data.materials.new('Used'); material.use_nodes=True
cube=bpy.data.objects['Cube']; cube.data.materials.clear(); cube.data.materials.append(material)
node=material.node_tree.nodes.new('ShaderNodeTexImage'); node.image=image
material.node_tree.links.new(node.outputs['Color'],material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
bpy.ops.wm.save_as_mainfile(filepath=str(source/'original.blend'))
(test_root/'destination').mkdir()
child_script=test_root/'verify_child.py'
child_script.write_text("import bpy\nfrom pathlib import Path\n"+
    f"assert Path(bpy.data.filepath).resolve()==Path({str(test_root/'destination/Relocated_16_02_Main_Folder/Relocated_16_02.blend')!r}).resolve()\n"+
    "image=bpy.data.images['used.png']\nassert image.filepath.replace('\\\\','/').startswith('//textures/')\n"+
    "assert Path(bpy.path.abspath(image.filepath)).is_file()\nassert len(image.pixels)>0\n"+
    f"Path({str(LOG)!r}).write_text('PROJECT_RELOCATION_RESTART_TESTS_PASSED\\n')\n"+
    "bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=3.5)\n")
original_popen=dev_restart.subprocess.Popen
def spawn(command,*args,**kwargs):
    # Retain the real production ready expression and actual child process;
    # use factory GUI mode only to isolate this validation run.
    command=[command[0],'--factory-startup',command[1],
             '--python',str(child_script),*command[2:]]
    return original_popen(command,*args,**kwargs)
dev_restart.subprocess.Popen=spawn
def run():
    try:
        result=bpy.ops.wm.airetopo_relocate_project(directory=str(test_root/'destination'),project_name='Relocated',name_index='16',version_index='02',put_in_subfolder=True)
        assert 'FINISHED' in result
        assert dev_restart._restart_pending
    except Exception:
        LOG.write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
    finally:
        dev_restart.subprocess.Popen=original_popen
    return None
bpy.app.timers.register(run,first_interval=1)
