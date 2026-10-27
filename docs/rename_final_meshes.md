# Phase 2 → Start Phase 2 → Rename Final Mesh

Start Phase 2 now has separate collapsible **ReBake** and **Rename Final Mesh**
groups. ReBake retains its existing repair, LOD creation, queue and export
options. Queue stop controls remain usable during an active rebake job.

Rename Final Mesh takes **Asset Name**, **Name Index** and starting **Version
Index**. It renames all prepared assets of the current scene in natural collection
order. Name Index is shared; Version Index increments once per asset.

For example, `Rock_00_01_Collection` → `Grave_Stone_02_05_Collection`, and
`SM_Rock_00_01_MID` → `SM_Grave_Stone_02_05_MID`. LOD numbers are preserved.
Existing Unity root/`.LODN` names and `_LODN_Collection` structure are preserved;
separate Unity LOD collections sharing the same base form one asset, not one
asset per LOD. The upper **Pipeline: Unreal (FAB) / Unity** selector chooses
export settings and directory; renaming does not rebuild geometry or convert
the existing mesh naming scheme between engines.

The operation updates mesh datablock names, associated material/image names,
known asset metadata, LOD source references and LOD label text. Images are written
under `Textures/<new asset identity>/` with new names, and their Blender paths
become relative. File extensions and original file bytes are retained for clean
file-backed images. Generated/edited images are saved from their current pixels.
Shared mesh data, materials, images and shader groups are isolated where needed,
so unrelated objects retain their resources. The working blend remains unsaved
until the user saves it through Blender.

All target names, source image files and destination texture paths are checked
before renaming. Unexpected mesh names, linked assets, ambiguous ownership,
unsupported image sources (such as UDIM/sequence/movie) and unrelated name/file
collisions stop the operation. Existing source textures and older exports are
retained. Texture files and datablock changes roll back if the rename itself
fails. All texture source bytes are staged before installation, supporting
overlapping index changes without reading a previously overwritten source.
Unused original shader groups are retained.

## Optional exports

- **Reexport FBX** uses the existing prepared-asset exporter with FBX only and
  the upper FAB/Unity selector. Unreal exports to `!Unreal`; Unity uses its
  configured export directory (default `//!Unity`). Export sorting follows the
  Phase 2 export setting. If an explicit LOW and LOD0 are both present, FBX uses
  LOD0 once; a standalone LOW is treated as LOD0.
- **Reexport Blend** writes one renamed asset file to `!Blend`, using the
  existing pack-textures and reset-Y options, including all its prepared meshes.
- **Export / Update JSON** defaults on. It creates current `MeshInfo.json`
  with the new identities and current triangle counts. With FBX enabled, the
  normal exporter also writes updated per-scope JSON and actual FBX paths.
  Without FBX, MeshInfo describes the scene and leaves its exported-files mapping
  empty rather than claiming that new FBX files exist.

If Section 11 has a valid generated TexFlow gallery result, its mesh filenames,
counts, ranges and asset headline are refreshed too. Matching old names in copy
are replaced; unrelated marketing copy and series fields remain intact. With
JSON export enabled, it saves to the last path recorded by **Save JSON…**;
otherwise to `texflow-fab-media.json` beside the working blend. A previously saved
JSON outside the addon is not discovered automatically. The gallery's result
document is updated even when JSON file export is disabled.

A follow-up export error leaves the successfully renamed scene intact and is
reported as **Renamed; follow-up export failed**. Some selected exports may
already have been written; the user can retry with the same identity. No source
texture or old export cleanup is performed.

Validation: actual Blender FBX/Blend/JSON tests cover FAB and Unity, index shifts,
shared resources, object-linked materials, generated images, visibility/selection,
name conflicts and injected filesystem/datablock failures. Native draw tests
cover the collapsed and expanded groups. External Unreal, Unity and Photoshop
import behavior is not established by these tests.
