"""Check format defaults, encoder settings and actual four-view output bytes."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy
import addon_utils

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import render_queue as rq, turnaround_animation as ta
scene=bpy.context.scene
settings=scene.polygroups_render_settings
assert settings.image_format=='PNG'
assert settings.animation_views_image_format=='WEBP'
assert scene.polygroups_mesh_finalization_settings.unity_render_image_format=='WEBP'
assert rq._transparent_output_path('Image.jpg')=='Image_transparent.png'
bpy.ops.mesh.primitive_cube_add()
assert bpy.ops.object.polygroups_prepare_turnaround_animation()=={'FINISHED'}
settings.resolution_x=settings.resolution_y=32
settings.render_engine='EEVEE'
with TemporaryDirectory() as directory:
    settings.output_directory=directory
    for file_format, extension in (('PNG','.png'),('JPEG','.jpg'),('WEBP','.webp')):
        settings.image_format=file_format
        scene.render.film_transparent=False
        rq._configure_render(scene,settings,{'output_path':str(Path(directory)/('Image'+extension))})
        assert scene.render.image_settings.file_format==file_format
        assert rq._current_state_render_path().endswith(extension)
        settings.animation_views_image_format=file_format
        assert bpy.ops.object.polygroups_render_turnaround_views()=={'FINISHED'}
        folder=Path(ta._turnaround_output_directory(settings))
        files=list(folder.glob('*'+extension))
        assert len(files)==4
        for path in files:
            data=path.read_bytes()
            if file_format=='PNG':
                assert data.startswith(b'\x89PNG\r\n\x1a\n')
            elif file_format=='JPEG':
                assert data.startswith(b'\xff\xd8')
            else:
                assert data[:4]==b'RIFF' and data[8:12]==b'WEBP'
print('RENDER_IMAGE_FORMATS_TEST_PASSED')
