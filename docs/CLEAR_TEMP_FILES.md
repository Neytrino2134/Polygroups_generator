# Clear Temp Files

`Scan and Check` / `Clear All Temp Files` (`core/final_cleanup.py`, `operators/final_cleanup.py`) work on the
folder of the open blend (the final asset folder).

Deleted: backup saves (`.blend1`, `.blendN`, `.BlendAutosaveN`, also inside `!` folders), other `.blend` files
beside the working blend or in other folders (for example `blender`), the `Bakes` and `batch_reports` folders,
and unused materials, images and textures of the open blend (zero users, no fake user, not linked).

Never touched: the working blend, `!Blend` / `!Renders` / `!Unity` / `!Unreal` / `!ZBrush` (except backup
saves), `01_` ... `20_` source folders and `Textures` folders.

Check: number of files in `!Blend`, and for every `Generated.N.blend` the object names found without loading
data: `Highpoly_Generated.N` plus `Resculpting_NN_Highpoly_Generated.N` or `Retopo_NN_Highpoly_Generated.N`.
The check box is set when every Generated.N file has both.

Shown in Save and Cleanup, Phase 1 - Start Import and Phase 2 (replacing Blend File Manager). Clear asks for
confirmation and deletes permanently; each file is re-checked (size, time, path) just before deletion.
