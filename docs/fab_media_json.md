# Section 11 → JSON generation

Creates UTF-8 JSON for the TexFlow Photoshop plugin's FAB Media Gallery importer.
The output matches the supplied `texflow-fab-media-Temp.json`: `schemaVersion: 2`,
15 common fields and 80 per-mesh fields (20 aligned LOW/MID pairs).

1. Open the blend containing the prepared `Asset_Name_XX_NN_Collection` collections.
2. Click **Fill Fields**. This fills missing defaults, suggests the asset headline
   from the collection name and refreshes calculated statistics without replacing your hints.
3. Enter series, collection number, two headline lines and a description hint.
   Add confirmed pack facts (materials, texture maps/resolution, UVs, collision,
   intended uses) in **Pack facts / hints** or its multiline Text document.
   A linked multiline document takes precedence over the single-line notes field.
4. Review Nanite labels: these describe your intended Unreal configuration;
   Blender does not establish whether Nanite is enabled in Unreal.
5. Choose any built-in text model from the combined OpenAI / Google menu.
   Generation uses the existing provider key in addon preferences. Image models
   and the generic Custom Model ID placeholder are excluded from this text menu.
6. Optionally inspect **Prepare / View Prompt**, then **Generate JSON**.
   Each generation rescans the scene and sends the current hints and inventory.
   It runs in the background. A local cancel ignores the eventual response;
   it cannot cancel billing for a request already submitted to the provider.
7. Open/copy the result, or **Save JSON…** using Blender's file picker.
   Result documents remain editable in Blender and persist in the blend.
   Saving validates the JSON structure before writing the file.

## Counting rules

- Scan named asset collections in the current scene, including hidden/excluded
  collections. Temporarily enabled evaluation visibility is restored afterward.
- One prepared collection represents one unique asset. MID contributes one
  static mesh; the LOW/LOD chain contributes one more. An explicit `_LOW` mesh
  takes precedence over the lowest numbered LOD. Additional LOD levels do not
  increase mesh totals or contribute to the average/range.
- `_MID`, `_LOW`, `_LOD0`, `.LOD0`, `.LOD.0` and prepared Unity roots are recognized.
  `_HIGH`, collision meshes (`UCX_`, `UBX_`, `USP_`, `UCP_`) and non-mesh objects
  do not count. Unclassified meshes are listed in the prepared prompt as warnings.
- Polycounts mean evaluated **triangles**, including enabled viewport modifiers.
  These are Blender scene values, not verification of an exported FBX.
- LOW/MID entries use the same collection index, so a missing version leaves
  an empty slot. Filenames use the exact mesh name plus `.fbx`.
- Ambiguous collections with multiple candidate MID or LOW meshes are rejected.
  More than 20 unique assets is rejected, rather than silently truncating the template.
- Counts and filenames are calculated locally and restored after model output.
  General text is generated in English; unsupported technical claims are forbidden
  by the prompt. Review the generated copy before importing it into Photoshop.

**Clear** empties the input fields and detaches notes/prompt/result documents from
the panel; it does not delete existing Text documents. **Fill Fields** restores
missing defaults and refreshes the inventory.

Validation: `test_fab_media_blender.py` exercises the actual Blender mesh inventory,
modifiers, hidden/excluded objects, both mocked provider transports, malformed
responses, deterministic counts, export validation and registration lifecycle.
`test_fab_media_ui_blender.py` exercises the native panel in a separate GUI process.
Neither test makes paid API requests or verifies a live Photoshop import.
