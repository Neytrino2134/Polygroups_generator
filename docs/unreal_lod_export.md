# Unreal / FAB LOD export

Unreal/FAB Export exposes independent FBX, GLB and GLTF switches. Existing
HIGH/MID/LOW and Sets layouts remain available. A legacy mesh_export_format
saved in older blend files/scripts is honored until a new format switch is set.

Sort By = LODs recognizes `SM_<asset>_LODN` names and separately retained High
meshes from Unreal LOD Rename, including an edited High suffix via the stored
asset/index metadata. Only selected meshes are exported. Duplicate LOD/High
identities and normalized filename conflicts are rejected before writing.

Output:

```text
!Unreal/<asset>/FBX/SM_<asset>_LOD0.fbx
!Unreal/<asset>/GLB/SM_<asset>_LOD0.glb
!Unreal/<asset>/GLTF/<asset>.gltf
!Unreal/<asset>/Textures/...
!Unreal/<asset>/MeshInfo.json
!Unreal/MeshInfo.json
```

GLTF modes:

- All LODs in One GLTF: an embedded file containing all selected LOD meshes
  for the asset. High is exported as a separate file.
- Separate LODs / Shared Textures: one GLTF/BIN pair per mesh, referencing
  the common GLTF/Textures directory.

GLB Mode is available when GLB and Sort By = LODs are enabled:

- All LODs in One GLB (default): `<asset>/GLB/<asset>.glb` includes all
  selected LODs and embeds their materials/textures. Retained High is separate.
- Separate LODs: one self-contained GLB per selected mesh, as before.

JSON maps each LOD's GLB entry to the shared path in combined mode. Mesh totals
are unchanged. The regression test parses the GLB JSON chunk to verify that
multiple LOD nodes and embedded buffers/images are present in the same file.

JSON for LOD export has schema_version 2, preserves meshes and totals, and adds
asset groups. Each mesh includes asset, role, lod_index, lod, collections,
vertices, triangles and files mapped by format. Combined GLTF records share
the same file path. Totals count unique meshes, not one copy per format.
Paths are relative to the report containing them. TXT reports retain LOD labels.

Transforms, selection, image paths and temporarily disconnected bake masks
are restored on success and exporter failure. No folder deletion is added;
files no longer referenced after switching formats/modes are left on disk.

Blender 5.2 checks passed: test_unreal_lod_export_blender.py (all formats,
two assets, custom High, shared textures, JSON, legacy formats, no-format
validation and injected failure), test_unity_gltf_modes_blender.py and
test_selected_gltf_export.py. The Unity test fixture now saves its temporary
blend to meet the existing safe texture-refresh contract.
