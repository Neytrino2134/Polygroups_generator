# Phase 2 Manual Cleanup

Two manual buttons are available alongside lower-Retopo, Highpoly and backup cleanup:

- **Delete All Resculpting_ Meshes** removes local mesh objects whose names
  start with `Resculpting_`, including hidden objects. It follows the existing
  all-local-data cleanup scope. Names such as `Backup_Resculpting_01` and
  `Rock_Resculpting`, and non-mesh objects, are not matched. Mesh datablocks
  used by retained objects remain available.
- **Delete All Generated.N Collections** removes numbered Generated trees in
  the current scene, including owned nested collections and their exclusively
  owned objects. Objects linked to collections outside those trees and shared
  nested collections are preserved. Bare `Generated` and nonnumeric names are
  not matched. Linked Generated collections or ones shared with another scene
  are rejected before any deletion.

Both operators support Blender Undo and update the Phase 2 status with deletion
counts. Manual cleanup is unavailable during active Phase 2, ReBake queue,
finalization, import, bake or render work.

`tests/test_phase2_manual_cleanup_all_blender.py` verifies hidden meshes, prefix
matching, shared mesh data, nested collections, external object links,
other-scene guards, UI registration and processing locks. Existing completion
cleanup and visibility-control regressions also passed in Blender 5.2.
