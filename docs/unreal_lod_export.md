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

- All LODs in One GLTF: an embedded file containing the selected LODs of
  one asset.
- Separate LODs / Shared Textures: one GLTF/BIN pair per mesh, referencing
  the common GLTF/Textures directory.

GLB Mode is available whenever GLB is enabled:

- One File per Asset: embeds the selected LODs and their materials/textures.
- Separate LODs: one self-contained GLB per selected mesh, as before.

Follow Sort By is the default for both formats. LOD layouts combine the LOD
chain and export retained High separately. Sets and LOW / MID / HIGH export
separate files by default. With an explicit combined mode, those two layouts
package the selected variants or LODs together. Sets saves them under
`!Unreal/GLB/<asset>/` or `!Unreal/GLTF/<asset>/`. LOW / MID / HIGH saves
combined files directly in `!Unreal/GLB/` or `!Unreal/GLTF/`. Separate
files use quality subfolders inside those format folders.

JSON maps each LOD's GLB entry to the shared path in combined mode. Mesh totals
are unchanged. The regression test parses the GLB JSON chunk to verify that
multiple LOD nodes and embedded buffers/images are present in the same file.

Mesh Info defaults to JSON. FAB writes `MeshInfo_FBX.json`, `MeshInfo_GLB.json`
and `MeshInfo_GLTF.json` in the corresponding format folders for the formats
exported. Each report contains only its own format, with paths relative to
that report's folder. Sets and quality layouts place these reports under the
top-level format folders, referencing the geometry in its chosen layout.
The root `MeshInfo.json` still lists the complete export.

Each format report also contains `fab_technical_details` with Geometry,
Materials and Textures, and Rigging and Animation values for the Fab listing.
For packs, `ranges` gives the minimum and maximum per asset family across
its exported variants. Bounding box values are in scene meters along Blender
XYZ, using the maximum extent of the variants for each asset. GLB/GLTF mesh
counts and animation tracks come from the exported streams. FBX geometry
counts describe the evaluated Blender meshes. `null` marks information
that needs review, such as UV overlap or scan provenance.

Sort By = LODs / Format uses a format-first layout instead:

```text
!Unreal/FBX/SM_<asset>_LOD0.fbx
!Unreal/FBX/Textures/...
!Unreal/GLTF/<asset>.gltf
!Unreal/GLTF/Textures/...
!Unreal/GLB/<asset>.glb
!Unreal/GLB/Textures/...
```

All selected assets of a format are placed directly in that format folder.
Only enabled formats create folders, and each has one common Textures folder.
Combined GLTF/GLB files still embed textures; separate GLTF files use the
format's shared Textures directory. Each format gets MeshInfo.json for its
own files; the root report maps every selected format. Paths in each report
are relative to that report's directory. The original asset-first LODs layout
remains unchanged.

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

MeshInfo JSON also records `Path` (the absolute directory containing that JSON),
`AssetName`, and `NameIndex` (a string preserving leading zeroes). These fields
are shared by Unreal, Unity, Phase 2, rendering and ReLOD JSON exports.
Prepared mesh identities take precedence over unrelated current UI defaults;
unnumbered meshes use the relevant engine preparation settings. Each mesh and
asset record includes its identity too. In a mixed-pack document, a top-level
identity field is empty when the records do not share a single value.
ReLOD records the final output directory rather than its temporary staging folder.

**FBX Normal Maps** supports OpenGL, DirectX (default) and Both. Files end
in `_OpenGL` or `_DirectX`. Both references DirectX from the FBX and provides
OpenGL as an alternate. Untagged input is treated as OpenGL. A source ending
in `_DX` or `_DirectX` is recognized as DirectX. Conversion writes a separate
PNG with the green channel inverted. In a combined FBX and GLB/glTF export,
the GLB/glTF material keeps the OpenGL convention.

For automated Unreal import, read `meshes[].textures[]` from the MeshInfo
for an FBX export. Resolve each `path` relative to the JSON's `Path`.
`material_slot` is zero-based. Select the `role == "Normal"` record with
`preferred == true` for that slot. `fbx_reference` identifies files the
Blender FBX exporter links to a supported material socket. Apply the normal
record's `unreal.srgb`, `unreal.compression_settings` and
`unreal.flip_green_channel` to the imported texture. Avoid a second flip
in the import pipeline when using a DirectX variant.
