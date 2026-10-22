"""Seams workflow RNA property groups."""
from .callbacks import (
    _island_selector_tool_icon_update,
    _redraw_view3d,
    _seam_tool_icon_update,
    _small_islands_tool_icon_update,
    _sync_cutter_autoweld_distance,
    _sync_cutter_extrude,
    _sync_cutter_solidify_thickness,
    _sync_cutter_thickness,
    _sync_selected_cutter_path_settings,
    bpy,
    radians,
)


class POLYGROUPS_PG_knife_seam_settings(bpy.types.PropertyGroup):
    # Keep the stored boolean for compatibility with existing .blend files.
    cut_mode: bpy.props.EnumProperty(
        name="Knife Mode",
        items=(
            ("PLANE", "Plane Cut", "Continuous plane cut through the mesh", "MESH_PLANE", 0),
            ("POLYLINE", "Multi-Point Knife", "Standard Knife: click multiple points, then Space/Enter to apply seams", "IPO_LINEAR", 1),
        ),
        get=lambda self: 0 if self.stable_view_cut else 1,
        set=lambda self, value: setattr(self, "stable_view_cut", value == 0),
    )
    stable_view_cut: bpy.props.BoolProperty(
        name="Stable View Cut",
        description="Use a viewport-plane cut that stays continuous on dense meshes when zoomed out",
        default=False,
    )
    use_occlude_geometry: bpy.props.BoolProperty(
        name="Occlude Geometry",
        description="Limit the cut to visible geometry only",
        default=False,
    )
    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Only cut currently selected geometry",
        default=False,
    )
    xray: bpy.props.BoolProperty(
        name="X-Ray",
        description="Show the cut through the mesh while drawing",
        default=True,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark selected knife-cut edges as seams after confirming the cut",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after post-cut processing",
        default=False,
    )


class POLYGROUPS_PG_seam_preparation_settings(bpy.types.PropertyGroup):
    show_seams_uv_editor: bpy.props.BoolProperty(
        name="Show Seams in UV Editor",
        description="Draw mesh seam edges on both sides of UV island cuts",
        default=False,
        update=_redraw_view3d,
    )
    uv_seam_path_auto_rip: bpy.props.BoolProperty(
        name="Auto Rip",
        description="Split UVs automatically after every UV Seam Path segment",
        default=True,
    )
    show_seams_object_mode: bpy.props.BoolProperty(
        name="Show Seams in Object Mode",
        description="Display seam edges on the active mesh while working in Object Mode",
        default=False,
        update=_redraw_view3d,
    )
    seam_overlay_max_polygons: bpy.props.IntProperty(
        name="Ignore Objects Above",
        description="Do not build the Object Mode seam overlay for meshes above this polygon count; zero disables the limit",
        default=500000,
        min=0,
        soft_max=5000000,
        subtype="UNSIGNED",
        update=_redraw_view3d,
    )
    seam_path_pin: bpy.props.BoolProperty(
        name="Mark As Pinned", description="Pin seams created by Vertex Seam Path and Edge Seam Path",
        default=False, update=_seam_tool_icon_update)
    seam_eraser_clear_mode: bpy.props.EnumProperty(
        name="Clear", description="Choose whether erasers clear seams together with pins or only pin marks",
        items=(("SEAMS", "Clear Seams and Pinned", "Clear both seam and pin marks from affected edges"),
               ("PINNED", "Clear Pinned Only", "Clear only pin marks while preserving seam marks")),
        default="SEAMS", update=_seam_tool_icon_update)
    smart_seam_angle_limit: bpy.props.FloatProperty(
        name="Surface Angle", default=0.7853981633974483,
        min=0.017453292519943295, max=1.5533430342749532, subtype="ANGLE",
        description="Maximum angle between average surface normals when merging regions",
    )
    smart_seam_filter_iterations: bpy.props.IntProperty(
        name="Noise Filtering", default=4, min=0, max=30,
        description="Neighborhood smoothing passes; increase to suppress larger surface bumps",
    )
    smart_seam_min_area: bpy.props.FloatProperty(
        name="Minimum Region Area", default=0.01, min=0.0, max=0.25, subtype="FACTOR",
        description="Merge regions smaller than this fraction of their connected component area",
    )
    smart_seam_smoothness: bpy.props.FloatProperty(
        name="Boundary Smoothing", default=0.35, min=0.0, max=2.0,
        description="Favor shorter region boundaries over small changes in surface orientation",
    )
    smart_seam_create_edges: bpy.props.BoolProperty(
        name="Create New Edges", default=True,
        description="Allow diagonal connections through faces when they improve the seam route; changes topology",
    )
    smart_seam_path_turn: bpy.props.FloatProperty(
        name="Avoid Sharp Turns", default=2.5, min=0.0, max=10.0,
        description="Direction-change penalty when finding seam paths; higher values favor smoother routes",
    )
    smart_seam_path_corridor: bpy.props.FloatProperty(
        name="Path Search Width", default=2.0, min=0.25, max=5.0,
        description="Maximum search distance from the surface boundary, in typical seam edge lengths",
    )
    smart_seam_edge_preference: bpy.props.FloatProperty(
        name="Prefer Existing Edges", default=0.6, min=0.0, max=5.0,
        description="Extra cost for diagonal cuts; higher values keep more of the route on existing edges",
    )
    smart_seam_replace: bpy.props.BoolProperty(
        name="Replace Existing Seams", default=True,
        description="Clear old seams inside the selected surface before applying the new boundaries",
    )
    smart_seam_pin_generated: bpy.props.BoolProperty(
        name="Mark Generated Seams As Pinned", description="Pin every seam generated by Smart Mark Seams",
        default=False, update=_seam_tool_icon_update)
    smart_seam_auto_relax: bpy.props.BoolProperty(
        name="Auto Smart Relax Seams",
        description="Run Smart Relax automatically after generating seams",
        default=True,
    )
    prefer_linked_seam: bpy.props.BoolProperty(
        name="Prefer Select Linked by Seam", default=True,
        description="Use seam boundaries for L and Ctrl+L in mesh Edit Mode; disable to use normal Blender shortcuts",
    )
    show_selection_group: bpy.props.BoolProperty(name="Selection", default=False)
    show_mesh_edit_group: bpy.props.BoolProperty(name="Mesh Editing", default=False)
    show_mark_clear_group: bpy.props.BoolProperty(name="Mark and Clear Seams", default=False)
    show_smart_mark_seams_group: bpy.props.BoolProperty(name="Smart Mark Seams", default=False)
    show_mark_clear_tools_group: bpy.props.BoolProperty(name="Mark and Clear Seam Tools", default=False)
    show_check_group: bpy.props.BoolProperty(name="Seam Checks", default=False)
    show_cut_group: bpy.props.BoolProperty(name="Cutting", default=False)
    selection_smooth_iterations: bpy.props.IntProperty(
        name="Smooth Iterations",
        description="Number of smoothing passes for the selected face region",
        default=2,
        min=1,
        max=25,
        soft_max=10,
    )
    seam_gap_max_edges: bpy.props.IntProperty(
        name="Max Gap Edges",
        description="Maximum number of non-seam edges allowed between two seam endpoints",
        default=6,
        min=1,
        max=20,
        soft_max=8,
    )
    seam_gap_max_distance: bpy.props.FloatProperty(
        name="Max Gap Distance",
        description="Maximum distance allowed when matching seam endpoints or short gap paths",
        default=0.2,
        min=0.1,
        max=1.0,
        precision=4,
        unit="LENGTH",
    )
    seam_gap_include_junctions: bpy.props.BoolProperty(
        name="Include Corners and T-Junctions", default=True,
        description="Also find gaps from an open seam end to an existing seam corner or junction ahead of it",
    )
    seam_gap_status: bpy.props.StringProperty(
        name="Seam Gap Status",
        default="Not checked",
    )
    seam_relax_mode: bpy.props.EnumProperty(
        name="Relax Mode",
        items=(
            ("RELAX", "Relax", "Relax all continuous seam chains"),
            ("SMART", "Smart Relax", "Protect junctions and sharp seam corners"),
        ),
        default="SMART",
    )
    seam_relax_iterations: bpy.props.IntProperty(
        name="Iterations", default=2, min=1, max=100, soft_max=20,
    )
    seam_relax_selected_area_only: bpy.props.BoolProperty(
        name="Selected Area Only",
        description="Relax only seam edges touching the selected face area",
        default=False,
    )
    seam_relax_corner_angle: bpy.props.FloatProperty(
        name="Corner Angle",
        description="Protect Smart Relax corners sharper than this angle",
        default=radians(90.0), min=0.0, max=radians(180.0), subtype="ANGLE",
    )
    seam_relax_use_corner_angle: bpy.props.BoolProperty(
        name="Protect Corners",
        description="Protect sharp seam corners from Smart Relax using Corner Angle",
        default=False,
    )
    seam_relax_protection_radius: bpy.props.IntProperty(
        name="Protection Radius",
        description="Number of seam edges protected around junctions and sharp corners",
        default=1, min=0, max=20, soft_max=5,
    )
    show_knife_seam_settings: bpy.props.BoolProperty(
        name="Knife Seam",
        default=False,
    )
    show_quick_knife_seam_settings: bpy.props.BoolProperty(
        name="Quick Knife Seam",
        default=False,
    )
    show_object_seam_cutter_settings: bpy.props.BoolProperty(
        name="Object Seam Cutter",
        default=False,
    )


class POLYGROUPS_PG_object_seam_cutter_settings(bpy.types.PropertyGroup):
    cutter_apply_is_running: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    cutter_apply_stage: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    cutter_apply_message: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    cutter_apply_progress: bpy.props.FloatProperty(
        default=0.0, min=0.0, max=100.0, subtype="PERCENTAGE", options={"SKIP_SAVE"},
    )
    cutter_grid_auto_rotate: bpy.props.BoolProperty(
        name="Auto Rotate", description="Switch to a side view after the second base click to draw depth directly",
        default=True,
    )
    cutter_grid_axes: bpy.props.BoolVectorProperty(
        name="Grid Axes", description="Enable planes perpendicular to world X/Y/Z",
        size=3, default=(True, True, True), subtype="XYZ",
    )
    cutter_grid_counts: bpy.props.IntVectorProperty(
        name="Planes per Axis", description="Number of internal planes on each enabled axis",
        size=3, default=(3, 3, 3), min=0, max=64,
    )
    cutter_grid_apply_method: bpy.props.EnumProperty(
        name="Grid Apply Method", description="How Grid Volume planes cut the active mesh",
        items=(("BISECT", "Bisect", "Cut the whole active mesh with each plane"),
               ("KNIFE_INTERSECT", "Knife Intersect", "Intersect finite grid plane faces with the active mesh")),
        default="BISECT",
    )
    cutter_size_multiplier: bpy.props.FloatProperty(
        name="Cutter Size",
        description="Cutter plane size relative to the active object's bounding box diagonal",
        default=1.5,
        min=0.1,
        soft_max=5.0,
        precision=2,
    )
    cutter_alpha: bpy.props.FloatProperty(
        name="Cutter Alpha",
        description="Viewport opacity for newly created cutter planes",
        default=0.25,
        min=0.05,
        max=1.0,
        subtype="FACTOR",
    )
    cutter_solidify_thickness: bpy.props.FloatProperty(
        name="Plane Thickness",
        description="Visual Solidify thickness for cutter planes; seam calculation still uses the original center plane",
        default=0.001,
        min=0.0,
        soft_max=0.01,
        precision=5,
        update=_sync_cutter_solidify_thickness,
    )
    cutter_thickness: bpy.props.FloatProperty(
        name="Cutter Thickness",
        description="Solidify thickness for non-plane cutters; Boolean uses this thickness and Knife ignores it",
        default=0.0001,
        min=0.0001,
        max=0.001,
        precision=5,
        update=_sync_cutter_thickness,
    )
    cutter_extrude: bpy.props.FloatProperty(
        name="Curve Extrude",
        description="Height of the cutter curve surface, independent of Solidify thickness",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        precision=5,
        update=_sync_cutter_extrude,
    )
    cutter_arc_segments: bpy.props.IntProperty(
        name="Cylinder Segments",
        description="Number of segments used for the open arc cylinder cutter",
        default=16,
        min=3,
        max=96,
        soft_max=32,
    )
    cutter_contour_points: bpy.props.IntProperty(
        name="Contour Points",
        description="Number of vertices around the fitted local cutter outline",
        default=64,
        min=8,
        max=256,
    )
    cutter_contour_offset: bpy.props.FloatProperty(
        name="Contour Offset",
        description="Outward clearance beyond the mesh section; coarse contours also compensate for fitting error",
        default=0.002,
        min=0.0,
        soft_max=0.1,
        precision=5,
    )
    cutter_local_ring_segments: bpy.props.IntProperty(
        name="Local Ring Segments",
        description="Number of segments used for local ring cutter disks",
        default=64,
        min=8,
        max=192,
        soft_max=96,
    )
    cutter_local_ring_radius_offset: bpy.props.FloatProperty(
        name="Ring Radius Offset",
        description="Additional world-space radius added to local ring cutters",
        default=0.0,
        soft_min=-1.0,
        soft_max=1.0,
        precision=4,
    )
    cutter_local_ring_fit_mode: bpy.props.EnumProperty(
        name="Ring Fit Mode",
        description="How local ring cutters are oriented and centered",
        items=(
            ("VOLUME", "Snap To Volume", "Estimate a circular disk from local surface intersections, accepting incomplete sections"),
            ("SURFACE", "Surface Diameter", "Center on the actual section and use the drawn diameter, enlarged when needed to cover the section"),
        ),
        default="VOLUME",
    )
    cutter_local_ring_mark_pinned: bpy.props.BoolProperty(
        name="Mark As Pinned",
        description="Pin seams created by Local Ring cutters",
        default=False,
    )
    cutter_local_contour_mark_pinned: bpy.props.BoolProperty(
        name="Mark As Pinned",
        description="Pin seams created by Local Contour cutters",
        default=False,
    )
    cutter_apply_method: bpy.props.EnumProperty(
        name="Apply Method",
        description="Method used to apply arc, path, and draw cutter seams",
        items=(
            ("BOOLEAN", "Boolean - faster", "Use the faster boolean union workflow before deleting cutter faces"),
            ("KNIFE", "Knife Intersect - cleaner", "Use Intersect Knife for cleaner cuts before deleting cutter faces"),
        ),
        default="BOOLEAN",
    )
    cutter_boolean_solver: bpy.props.EnumProperty(
        name="Solver",
        description="Solver used by Boolean and Knife Intersect cutter application",
        items=(
            ("FLOAT", "Float", "Use the faster float boolean solver"),
            ("EXACT", "Exact", "Use the exact boolean solver for difficult or self-intersecting cutters"),
        ),
        default="FLOAT",
    )
    cutter_auto_fix_mesh: bpy.props.BoolProperty(
        name="Autofix",
        description="Run the enabled mesh repair stages around cutter application",
        default=True,
    )
    cutter_auto_fix_fin_faces: bpy.props.BoolProperty(
        name="Remove Fin Faces and Loose Geometry",
        description="Also remove dangling fin faces, wire edges, and loose vertices during cutter Autofix",
        default=True,
    )
    cutter_auto_fix_seam_check: bpy.props.BoolProperty(
        name="Check and Close Seam Gaps",
        description="After cutter Autofix, check and close seam gaps using the current N-panel settings",
        default=True,
    )
    cutter_auto_fix_small_islands: bpy.props.BoolProperty(
        name="Check and Merge Small Islands",
        description="After cutter Autofix, merge small seam islands using the dedicated threshold",
        default=True,
    )
    cutter_auto_fix_small_islands_threshold: bpy.props.FloatProperty(
        name="Small Islands Threshold (%)",
        description="Maximum relative island area merged after applying cutter seams",
        default=0.5,
        min=0.1,
        max=1.0,
        precision=2,
    )
    cutter_auto_fix_weld: bpy.props.BoolProperty(
        name="Weld",
        description="Weld vertices belonging to seam edges after all earlier Autofix operations",
        default=True,
    )
    cutter_auto_fix_weld_distance: bpy.props.FloatProperty(
        name="Weld Distance",
        description="Merge distance of the final seam-only AutoWeld operation",
        default=0.001,
        min=0.0001,
        max=0.05,
        # Blender's distance widget scales this to a visible 0.001 arrow step.
        step=0.01,
        precision=4,
        subtype="DISTANCE",
        update=_sync_cutter_autoweld_distance,
    )
    cutter_auto_fix_smart_relax_seams: bpy.props.BoolProperty(
        name="Smart Relax Seams",
        description="Smart Relax cutter seams once before triangulating; protect corners is disabled and protection radius is 1",
        default=True,
    )
    cutter_auto_fix_triangulate_ngons: bpy.props.BoolProperty(
        name="Triangulate N-gons",
        description="Triangulate faces with more than four sides after the final Weld stage",
        default=True,
    )
    cutter_mirror_axis: bpy.props.EnumProperty(
        name="Mirror Axis",
        description="Object-mode axis used when copying and mirroring selected cutters",
        items=(
            ("X", "X", "Mirror across the X axis"),
            ("Y", "Y", "Mirror across the Y axis"),
            ("Z", "Z", "Mirror across the Z axis"),
        ),
        default="X",
    )
    cutter_path_render_u: bpy.props.IntProperty(
        name="Path Render U",
        description="Render U resolution for newly created cutter path curves",
        default=4,
        min=1,
        max=128,
        soft_max=64,
        update=_sync_selected_cutter_path_settings,
    )
    continue_path_cutters: bpy.props.BoolProperty(
        name="Continue Path Cutters",
        description="Append new cutter paths to nearby existing cutter paths instead of creating separate objects",
        default=True,
    )
    cutter_path_mark_pinned: bpy.props.BoolProperty(
        name="Mark As Pinned",
        description="Pin seams created by Path curve cutters",
        default=False,
    )
    cutter_draw_mark_pinned: bpy.props.BoolProperty(
        name="Mark As Pinned",
        description="Pin seams created by Draw curve cutters",
        default=False,
    )
    cutter_path_join_distance: bpy.props.FloatProperty(
        name="Path Join Distance",
        description="Maximum distance used when continuing or joining cutter path curves",
        default=0.05,
        min=0.0,
        soft_max=0.5,
        precision=4,
    )
    cutter_draw_min_point_distance: bpy.props.FloatProperty(
        name="Draw Point Distance",
        description="Minimum surface distance between points while drawing cutter strokes",
        default=0.01,
        min=0.0,
        soft_max=0.2,
        precision=4,
    )
    cutter_draw_simplify_distance: bpy.props.FloatProperty(
        name="Draw Simplify",
        description="Optional distance-based simplification applied to cutter paths created with the draw tool",
        default=0.0,
        min=0.0,
        soft_max=0.2,
        precision=4,
    )
    cutter_draw_stabilize_stroke: bpy.props.BoolProperty(
        name="Stabilize Stroke",
        description="Draw from a delayed, smoothed cursor position",
        default=False,
    )
    cutter_draw_stabilize_radius: bpy.props.IntProperty(
        name="Stabilize Radius",
        description="Screen-space delay radius for stabilized cutter strokes",
        default=25,
        min=1,
        max=200,
        subtype="PIXEL",
    )
    cutter_draw_stabilize_factor: bpy.props.FloatProperty(
        name="Stabilize Factor",
        description="Smoothing applied while the stabilized point follows the cursor",
        default=0.75,
        min=0.0,
        max=0.99,
        subtype="FACTOR",
        precision=2,
    )
    continue_draw_strokes: bpy.props.BoolProperty(
        name="Continue Draw Strokes",
        description="Append new draw strokes to nearby existing draw strokes instead of creating separate objects",
        default=True,
    )
    cutter_draw_join_distance: bpy.props.FloatProperty(
        name="Draw Join Distance",
        description="Maximum distance used when continuing or joining cutter draw strokes",
        default=0.05,
        min=0.0,
        soft_max=0.5,
        precision=4,
    )
    auto_convert_draw_strokes: bpy.props.BoolProperty(
        name="Auto Convert Draw Strokes",
        description="Create a cutter path immediately after finishing a draw stroke",
        default=False,
    )
    delete_draw_strokes_after_convert: bpy.props.BoolProperty(
        name="Delete Draw Strokes After Convert",
        description="Delete source draw stroke objects after converting them to cutter paths",
        default=True,
    )
    auto_convert_draw_strokes_on_apply: bpy.props.BoolProperty(
        name="Auto Convert Draw On Apply",
        description="Convert cutter draw strokes to cutter paths before applying cutter seams",
        default=True,
    )
    hide_cutters_after_apply: bpy.props.BoolProperty(
        name="Hide Cutters After Apply",
        description="Hide cutter plane objects after applying seams",
        default=True,
    )
    fill_split_cutters: bpy.props.BoolProperty(
        name="Fill Cutter",
        description="Fill cut boundary openings after splitting an object with plane or arc cutters",
        default=False,
    )
    delete_cutters_after_apply: bpy.props.BoolProperty(
        name="Delete Cutters After Apply",
        description="Delete cutter plane objects after applying seams",
        default=False,
    )
    last_cutter_count: bpy.props.IntProperty(
        name="Last Cutters",
        default=0,
        min=0,
    )
    last_marked_edge_count: bpy.props.IntProperty(
        name="Last Seams",
        default=0,
        min=0,
    )


class POLYGROUPS_PG_quick_knife_seam_settings(bpy.types.PropertyGroup):
    use_fill: bpy.props.BoolProperty(
        name="Fill",
        description="Fill the cut with a new face",
        default=False,
    )
    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Tolerance for the bisect cut",
        default=0.0001,
        min=0.0,
        soft_max=0.01,
        precision=5,
    )
    mark_seam: bpy.props.BoolProperty(
        name="Mark As Seam",
        description="Mark newly created cut edges as seams",
        default=True,
    )
    clear_selection_after_cutting: bpy.props.BoolProperty(
        name="Clear Selection After Cutting",
        description="Deselect vertices, edges, and faces after the cut",
        default=True,
    )


class POLYGROUPS_PG_polygroups_settings(bpy.types.PropertyGroup):
    show_small_islands: bpy.props.BoolProperty(name="Islands Analyzer", default=False)
    show_group_generation: bpy.props.BoolProperty(name="Generate PolyGroups", default=False)
    show_group_uv: bpy.props.BoolProperty(name="Seams and UV", default=False)
    show_group_materials: bpy.props.BoolProperty(name="Material Management", default=False)
    small_island_threshold: bpy.props.FloatProperty(name="Area Threshold (%)", default=3.0, min=1.0, max=49.0,
        description="Percentage of the largest seam island area in each connected mesh component")
    small_islands_merger_shape: bpy.props.EnumProperty(
        name="Selection Type",
        description="Gesture used by the Small Islands Merger tool",
        items=(
            ("BOX", "Box", "Select seam islands with a rectangular region", "MESH_PLANE", 0),
            ("LASSO", "Lasso", "Select seam islands with a freehand region", "GP_SELECT_STROKES", 1),
            ("CIRCLE", "Circle", "Paint over seam islands with a circular brush", "MESH_CIRCLE", 2),
        ),
        default="BOX",
        update=_small_islands_tool_icon_update,
    )
    island_selector_shape: bpy.props.EnumProperty(
        name="Selection Type",
        description="Gesture used by the Island Selector tool",
        items=(
            ("TWEAK", "Tweak", "Click a polygon or vertex to select its UV island", "RESTRICT_SELECT_OFF", 0),
            ("BOX", "Box", "Select UV islands with a rectangular region", "MESH_PLANE", 1),
            ("LASSO", "Lasso", "Select UV islands with a freehand region", "GP_SELECT_STROKES", 2),
            ("CIRCLE", "Circle", "Paint over UV islands with a circular brush", "MESH_CIRCLE", 3),
        ),
        default="TWEAK",
        update=_island_selector_tool_icon_update,
    )
    island_selector_selection_mode: bpy.props.EnumProperty(
        name="Selection Mode",
        description="Replace the current selection or add islands to it",
        items=(
            ("NEW", "New Select", "Clear the previous selection before selecting islands"),
            ("ADD", "Add", "Add newly touched islands to the current selection"),
        ),
        default="NEW",
    )
    face_selector_shift_shape: bpy.props.EnumProperty(
        name="Shift Selection",
        description="Selection gesture used while Shift is held in Face Selector",
        items=(
            ("BOX", "Box", "Shift-drag a box to add polygons", "MESH_PLANE", 0),
            ("CIRCLE", "Circle", "Shift-drag a circle brush to add polygons", "MESH_CIRCLE", 1),
            ("LASSO", "Lasso", "Shift-drag a lasso to add polygons", "GP_SELECT_STROKES", 2),
        ),
        default="BOX",
    )
    small_island_protect_sharp: bpy.props.BoolProperty(name="Protect Sharp Edges", default=True)
    small_island_protect_materials: bpy.props.BoolProperty(name="Protect Material Boundaries", default=False)
    small_island_selected_area: bpy.props.BoolProperty(
        name="Selected Area", description="Analyze only currently selected faces in Edit Mode", default=False)
    small_island_protect_pinned: bpy.props.BoolProperty(
        name="Protect Pinned Edges", description="Never select or remove pinned seams during analysis and merge", default=True)
    small_island_status: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    material_mode: bpy.props.EnumProperty(
        name="Material Mode",
        description="How generated PolyGroup materials use the source material textures",
        items=(
            ("TEXTURE_ONLY", "Source Texture", "Use the source material texture color"),
            ("TEXTURE_TINT", "Texture + Color", "Multiply source texture color by a random PolyGroup color"),
            ("COLOR_ONLY", "Random Color", "Use random PolyGroup colors without source textures"),
            ("CHECKER_TEXTURE", "Checker Texture", "Use a UV checker texture material"),
        ),
        default="TEXTURE_TINT",
    )
    checker_scale: bpy.props.FloatProperty(
        name="Checker Scale",
        description="Mapping scale for generated checker texture materials",
        default=80.0,
        min=0.01,
        soft_max=100.0,
        precision=2,
    )
