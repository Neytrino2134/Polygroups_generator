"""Build a local filled cutter from one closed planar mesh cross-section."""
from collections import defaultdict
from itertools import product
from math import floor, cos, pi
from mathutils import Vector, Quaternion
from mathutils.geometry import intersect_line_line_2d, tessellate_polygon


class SectionNotFound(ValueError):
    """A nearby plane may resolve an open or ambiguous surface intersection."""


def _distance_to_segment(point, start, end):
    delta = end - start
    t = max(0.0, min(1.0, (point - start).dot(delta) / delta.length_squared)) if delta.length_squared else 0.0
    return (point - start - delta * t).length


def _segments(points):
    return zip(points, points[1:] + points[:1])


def _inside(point, polygon):
    inside = False
    for a, b in _segments(polygon):
        if (a.y > point.y) != (b.y > point.y):
            if point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x:
                inside = not inside
    return inside


def _resample(points, count):
    lengths = [(b - a).length for a, b in _segments(points)]
    perimeter = sum(lengths)
    if perimeter <= 1e-10:
        raise ValueError("The local section is too small")
    result, index, accumulated = [], 0, 0.0
    for step in range(count):
        distance = perimeter * step / count
        while index < len(points) - 1 and accumulated + lengths[index] < distance:
            accumulated += lengths[index]
            index += 1
        t = (distance - accumulated) / max(lengths[index], 1e-20)
        result.append(points[index].lerp(points[(index + 1) % len(points)], t))
    return result


def _offset(points, distance):
    result = []
    for index, point in enumerate(points):
        before = (point - points[index - 1]).normalized()
        after = (points[(index + 1) % len(points)] - point).normalized()
        n1, n2 = Vector((before.y, -before.x)), Vector((after.y, -after.x))
        bisector = n1 + n2
        divisor = bisector.dot(n1)
        if divisor < 1e-6:
            raise ValueError("The contour folds back on itself; increase Contour Points")
        result.append(point + bisector * (distance / divisor))
    return result


def _crosses(a, b):
    return any(intersect_line_line_2d(p, q, r, s) is not None
               for p, q in _segments(a) for r, s in _segments(b))


def _self_crosses(points):
    edges = list(_segments(points))
    for i, (a, b) in enumerate(edges):
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            if intersect_line_line_2d(a, b, *edges[j]) is not None:
                return True
    return False


def section_loops(target, depsgraph, origin, normal, include_open=False, as_segments=False):
    """Intersect evaluated triangles without rebuilding or altering source faces.

    Stitch only intersection endpoints, so duplicated faces and split vertices
    (common in imported meshes) do not break otherwise closed geometric loops.
    """
    evaluated = target.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if mesh is None or not mesh.vertices:
            raise ValueError("The target mesh is empty")
        mesh.calc_loop_triangles()
        normal = normal.normalized()
        matrix = evaluated.matrix_world
        vertices = [matrix @ v.co - origin for v in mesh.vertices]
        epsilon = max(max(v.length for v in vertices) * 1e-7, 1e-8)
        distances = [v.dot(normal) for v in vertices]
        points, cells = [], defaultdict(list)
        neighbors = tuple(product((-1, 0, 1), repeat=3))

        def node(point):
            # Project near-plane endpoints exactly onto the cut plane.
            point = point - normal * point.dot(normal)
            key = tuple(floor(value / epsilon) for value in point)
            for delta in neighbors:
                for index in cells.get(tuple(k + d for k, d in zip(key, delta)), ()):
                    if (points[index] - point).length <= epsilon:
                        return index
            index = len(points)
            points.append(point)
            cells[key].append(index)
            return index

        edges, coplanar = set(), defaultdict(int)
        crossings = {}
        seen_triangles = set()
        for triangle in mesh.loop_triangles:
            ids = tuple(triangle.vertices)
            triangle_key = tuple(sorted(ids))
            if triangle_key in seen_triangles:
                continue
            seen_triangles.add(triangle_key)
            ds = [distances[i] for i in ids]
            on = [abs(d) <= epsilon for d in ds]
            if all(on):
                ns = [node(vertices[i]) for i in ids]
                for i in range(3):
                    if ns[i] != ns[(i + 1) % 3]:
                        coplanar[tuple(sorted((ns[i], ns[(i + 1) % 3])))] += 1
                continue
            if min(ds) > epsilon or max(ds) < -epsilon:
                continue
            intersections = set()
            for i in range(3):
                j = (i + 1) % 3
                if on[i]:
                    intersections.add(node(vertices[ids[i]]))
                if not on[i] and not on[j] and (ds[i] < 0) != (ds[j] < 0):
                    key = tuple(sorted((ids[i], ids[j])))
                    if key not in crossings:
                        a, b = key
                        crossings[key] = node(vertices[a].lerp(
                            vertices[b], distances[a] / (distances[a] - distances[b])))
                    intersections.add(crossings[key])
            if len(intersections) == 2:
                edges.add(tuple(sorted(intersections)))
        # A coplanar cap contributes its outline, not triangulation diagonals.
        edges.update(edge for edge, uses in coplanar.items() if uses == 1)
        adjacency = defaultdict(set)
        for a, b in edges:
            adjacency[a].add(b)
            adjacency[b].add(a)
        loops, remaining = [], set(adjacency)
        while remaining:
            start = min(remaining, key=lambda i: tuple(points[i]))
            component, stack = {start}, [start]
            remaining.remove(start)
            while stack:
                for neighbor in adjacency[stack.pop()]:
                    if neighbor not in component:
                        component.add(neighbor)
                        remaining.discard(neighbor)
                        stack.append(neighbor)
            if as_segments:
                # Coarse rings need surface samples, not an ordered manifold loop.
                # Keep actual edge pairs for distance queries, including branches
                # and isolated segments; do not invent links across gaps.
                loops.append([points[v] + origin
                              for a in sorted(component) for b in sorted(adjacency[a]) if a < b
                              for v in (a, b)])
                continue
            endpoints = [v for v in component if len(adjacency[v]) == 1]
            closed = all(len(adjacency[v]) == 2 for v in component)
            if not closed:
                if not (include_open and len(endpoints) == 2
                        and all(len(adjacency[v]) <= 2 for v in component)):
                    continue
                start = min(endpoints, key=lambda i: tuple(points[i]))
            ordered, previous, current = [], None, start
            while True:
                ordered.append(points[current] + origin)
                following_nodes = adjacency[current] - {previous}
                if not following_nodes:
                    break
                following = min(following_nodes)
                previous, current = current, following
                if current == start:
                    break
            if len(ordered) >= 3:
                loops.append(ordered)
        return loops, epsilon
    finally:
        evaluated.to_mesh_clear()


def nearest_section(target, depsgraph, origin, normal, seed, include_open=False):
    loops, epsilon = section_loops(target, depsgraph, origin, normal, include_open=include_open)
    if not loops:
        raise SectionNotFound("No closed local section found; place the line across a closed part of the mesh")
    distances = [min(_distance_to_segment(seed, a, b) for a, b in _segments(loop)) for loop in loops]
    index = min(range(len(loops)), key=lambda i: distances[i])
    # World-space ray hits lose precision on meshes far from the world origin.
    # Keep this tolerance tied to numeric precision, not a fraction of the limb.
    tolerance = max(epsilon * 100, max(abs(value) for value in seed) * 1e-6)
    if distances[index] > tolerance:
        raise SectionNotFound("The indicated section is open or ambiguous; move the two points slightly")
    return loops, index, epsilon


def fitted_ring_section(target, depsgraph, origin, normal, seed, count, offset,
                        radius_from_center=None, radius_hint=0.0):
    """Coarse circular fit; tolerate broken, branched and imperfect sections."""
    normal = normal.normalized()
    components, epsilon = section_loops(target, depsgraph, origin, normal, as_segments=True)
    if components:
        def distance(component):
            return min(_distance_to_segment(seed, a, b)
                       for a, b in zip(component[::2], component[1::2]))
        index = min(range(len(components)), key=lambda i: distance(components[i]))
        loop = list(components[index])
        # Include nearby disconnected fragments within the scale of the stroke.
        # Larger components farther away belong to other parts of the object.
        reach = max(radius_hint * 2, epsilon * 100)
        for i, component in enumerate(components):
            if i != index and all((p - seed).length <= reach for p in component):
                loop.extend(component)
        if distance(components[index]) > reach:
            loop = [seed]  # Do not relocate the ring onto an unrelated section.
    else:
        loop = [seed]
    # The hit is a valid surface sample even if triangle stitching is ambiguous.
    loop.append(seed)
    axis_x = normal.orthogonal().normalized()
    axis_y = normal.cross(axis_x).normalized()
    outline = [Vector(((p - origin).dot(axis_x), (p - origin).dot(axis_y))) for p in loop]
    center_2d = Vector(((min(p.x for p in outline) + max(p.x for p in outline)) * .5,
                        (min(p.y for p in outline) + max(p.y for p in outline)) * .5))
    center = origin + axis_x * center_2d.x + axis_y * center_2d.y
    # The polygon's inradius must enclose the section even at low segment counts.
    extent = max((p - center_2d).length for p in outline)
    fitted_radius = extent / cos(pi / max(3, count))
    if extent < radius_hint * .25:
        fitted_radius = max(fitted_radius, radius_hint)
    radius = fitted_radius + offset + epsilon * 4
    if radius_from_center is not None:
        radius = max(radius, radius_from_center(center))
    if radius <= epsilon:
        raise ValueError("Ring Radius Offset makes the ring too small")
    return center, axis_x, axis_y, radius


def fitted_section_with_retries(target, depsgraph, seed, normal, count, offset, search_scale):
    """Try the exact stroke first, then nine small, deterministic adjustments.

    Every candidate still requires a closed loop at a nearby surface hit and
    passes the usual clearance and neighboring-section checks. Geometry errors
    caused by an excessive offset are not hidden by searching a different part.
    """
    normal = normal.normalized()
    try:
        return fitted_section(target, depsgraph, seed, normal, seed, count, offset)
    except SectionNotFound:
        pass
    scale = max(float(search_scale), 1e-6)
    axis_x = normal.orthogonal().normalized()
    axis_y = normal.cross(axis_x).normalized()
    # Ascending positional/angle adjustments; at most 0.5% of the stroke length
    # in translation and 1.5 degrees in tilt.
    candidates = [(normal, scale * .001), (normal, -scale * .001)]
    for axis in (axis_x, axis_y):
        for angle in (.75, -.75):
            candidates.append((Quaternion(axis, angle * pi / 180) @ normal, 0.0))
    candidates.extend([(normal, scale * .005), (normal, -scale * .005),
                       (Quaternion((axis_x + axis_y).normalized(), 1.5 * pi / 180) @ normal, 0.0)])
    evaluated = target.evaluated_get(depsgraph)
    inverse = evaluated.matrix_world.inverted_safe()
    for candidate_normal, shift in candidates:
        candidate_seed = seed
        if shift:
            desired = seed + normal * shift
            hit, location, _, _ = evaluated.closest_point_on_mesh(inverse @ desired)
            if not hit:
                continue
            candidate_seed = evaluated.matrix_world @ location
            # Never let nearest-surface projection jump to another distant part.
            if (candidate_seed - seed).length > abs(shift) * 2 + scale * 1e-6:
                continue
        try:
            return fitted_section(target, depsgraph, candidate_seed, candidate_normal,
                                  candidate_seed, count, offset)
        except SectionNotFound:
            continue
    raise SectionNotFound("No closed local contour found after 10 nearby attempts; move the line or repair the local opening")


def fitted_section(target, depsgraph, origin, normal, seed, count, offset):
    normal = normal.normalized()
    loops, index, epsilon = nearest_section(target, depsgraph, origin, normal, seed)
    loop = loops[index]
    axis_x = (loop[1] - loop[0]).normalized()
    axis_y = normal.cross(axis_x).normalized()
    def project(points):
        return [Vector(((p - origin).dot(axis_x), (p - origin).dot(axis_y))) for p in points]
    outline = project(loop)
    if sum(a.x * b.y - b.x * a.y for a, b in _segments(outline)) < 0:
        outline.reverse()
    sampled = _resample(outline, max(8, int(count)))
    # Chords of a coarse contour can sit inside the surface. Compensate for
    # that error before adding the requested outward clearance.
    error = max(min(_distance_to_segment(p, a, b) for a, b in _segments(sampled)) for p in outline)
    fitted = sampled if offset <= 0 else _offset(sampled, offset + error + epsilon * 4)
    if _self_crosses(fitted) or (offset > 0 and (
            _crosses(outline, fitted) or not all(_inside(p, fitted) for p in outline))):
        raise ValueError("Cannot fit this contour at the current resolution; increase Contour Points or reduce Contour Offset")
    for other_index, other in enumerate(loops):
        if other_index == index:
            continue
        other = project(other)
        if _crosses(fitted, other) or _inside(other[0], fitted) or _inside(fitted[0], other):
            raise ValueError("The cutter would touch another section; reduce Contour Offset or increase Contour Points")
    vertices = [origin + axis_x * p.x + axis_y * p.y for p in fitted]
    triangles = tessellate_polygon([vertices])
    if len(triangles) != len(vertices) - 2:
        raise ValueError("Could not fill the local contour")
    # A filled n-gon avoids introducing triangulation diagonals into the seam.
    return vertices, [tuple(range(len(vertices)))]
