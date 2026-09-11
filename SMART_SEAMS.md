# Generate Smart Seams

## Surface detection

Before surface detection, any selected vertex, edge or face seeds a Select Linked operation delimited by existing seams. The operator expands the selection through visible faces without crossing a seam, then works on the resulting complete islands. Multiple selected seeds may select multiple islands. Area-weighted bilateral normal filtering suppresses small bumps. Adjacent regions merge according to their average orientation and Surface Angle; small regions are absorbed and a boundary-length optimization reduces fragmentation. Selection borders and mesh borders become seams.

The Edit Mesh toolbar also contains Smart Seams Generator. Each left click clears the previous selection, uses Blender's native visible-vertex picking at the cursor, selects the picked vertex's seam-bounded island, and immediately runs Generate Smart Seams. A click that does not hit exactly one visible vertex restores the previous selection. Right click returns to Blender's Select tool. The active tool header starts with Surface Angle and exposes the same generation and routing settings.

## Direction-aware path search

Internal boundaries are split into chains at junctions and selection-border contacts. Closed loops are routed as two anchored halves. Endpoints stay fixed.

For each chain, build a local corridor of selected faces. Measure distance from the original boundary along mesh edges, limited by Path Search Width times the median edge length of that chain. Search states contain both the previous and current vertex, allowing the cost to penalize sharp direction changes. Cost includes length, squared direction change, deviation from the original boundary, and a preference for local normal changes relative to Surface Angle.

Existing edges are the default graph connections. With Create New Edges enabled, also consider diagonals of convex polygons with at most 32 vertices. A pair of adjacent triangles can be crossed by connecting their opposite vertices through a new point on their common edge. Diagonal connections have an additional cost controlled by Prefer Existing Edges. This lets a path follow edges, take a diagonal to avoid a detour, and resume following edges.

Only an improving path is applied. The search cannot pass through another seam or cross the selection border. It rejects repeated vertices and multiple cuts through the same face within a route. Replaced seam segments are cleared; their geometry stays in the mesh. Junctions and protected existing seams stay fixed.

## Controls

- Surface Angle (45 degrees): maximum angle between region mean normals for merging; also normalizes the path's preference for local bends.
- Noise Filtering (4): bilateral neighborhood passes. Increase for bumps spanning more edges.
- Minimum Region Area (0.01): cleanup threshold relative to each connected selected component.
- Boundary Smoothing (0.35): surface-label boundary optimization before path search.
- Avoid Sharp Turns (2.5): path direction penalty. Increase to reduce staircase turns.
- Path Search Width (2.0): corridor radius in typical seam-edge lengths. Reduce to keep the path closer to the original detected transition.
- Create New Edges (off): allow diagonal connections during path search.
- Prefer Existing Edges (0.6): extra diagonal cost. Higher values favor existing edges; lower values allow more cuts. Visible when Create New Edges is enabled.
- Replace Existing Seams (on): replace seams inside the selected surface. Turn off to preserve manual seams, which also protects them from rerouting.

Corner Cut Strength has been replaced by path controls. There is no longer a fixed 35-degree crease rejection or a planar-face-only restriction.

## Geometry and limits

Original vertex coordinates are never moved. Native BMesh operations copy face attributes and preserve/interpolate UVs. Splitting a warped polygon can change its implicit triangulation, as with native vertex connections. For triangle-pair cuts, the inserted point lies on the original shared edge, preserving the piecewise-planar surface.

This is bounded graph optimization, not a globally optimal surface curve solver. It does not relocate junctions or guarantee UV distortion, disk-shaped islands or a particular region count after rerouting. Concave polygons are excluded from diagonal candidates. Search width is mesh-density dependent; segmentation and lengths use object-local coordinates. Long cuts are assembled from local graph connections rather than a single unrestricted Connect Vertex Path call. No new edge is created when the existing route has lower cost or no safe alternative exists.

## Verification

Blender 5.2 background integration tests cover noisy-cube surface detection (six connected regions), UV preservation, partial selections, seam replacement, flat and warped staircase routes, actual operator on/off behavior, triangle-pair cuts, UV interpolation and face attributes, junction anchors, hidden/unselected boundaries and strong existing-edge preference.

On the staircase fixture the internal seam length falls from 8 to approximately 6.83 with two quad diagonals. The triangular variant creates four seam segments through two new crossing vertices. These are synthetic regression fixtures; the user's screenshots illustrate the target but do not supply editable geometry for an exact reproduction.
