"""Build a local filled cutter from one closed planar mesh cross-section."""
import bmesh
from mathutils import Vector
from mathutils.geometry import intersect_line_line_2d, tessellate_polygon


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


def section_loops(target, depsgraph, origin, normal):
    """Read evaluated geometry in world space, without changing the source mesh."""
    bm = bmesh.new()
    try:
        # Ray casting intersects Blender's evaluated loop triangles. Bisecting
        # the original non-planar quads/ngons instead creates straight chords
        # that need not pass through that hit, even on a closed mesh.
        evaluated = target.evaluated_get(depsgraph)
        mesh = evaluated.data
        mesh.calc_loop_triangles()
        matrix = evaluated.matrix_world
        vertices = [bm.verts.new(matrix @ v.co - origin) for v in mesh.vertices]
        for triangle in mesh.loop_triangles:
            bm.faces.new([vertices[i] for i in triangle.vertices])
        if not bm.verts:
            raise ValueError("The target mesh is empty")
        # Work near zero to reduce rounding error on translated objects.
        size = max(v.co.length for v in bm.verts)
        epsilon = max(size * 1e-8, 1e-8)
        result = bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            plane_co=Vector(), plane_no=normal, dist=epsilon,
            clear_inner=False, clear_outer=False,
        )
        edges = {e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)}
        adjacency = {}
        for edge in edges:
            a, b = edge.verts
            adjacency.setdefault(a, []).append(b)
            adjacency.setdefault(b, []).append(a)
        loops = []
        remaining = set(adjacency)
        while remaining:
            start = min(remaining, key=lambda v: tuple(v.co))
            remaining.remove(start)
            component, stack = {start}, [start]
            while stack:
                for neighbor in adjacency[stack.pop()]:
                    if neighbor not in component:
                        component.add(neighbor)
                        remaining.discard(neighbor)
                        stack.append(neighbor)
            if any(len(adjacency[v]) != 2 for v in component):
                continue
            ordered, previous, current = [], None, start
            while True:
                ordered.append(current.co + origin)
                following = min((v for v in adjacency[current] if v != previous), key=lambda v: tuple(v.co))
                previous, current = current, following
                if current == start:
                    break
            if len(ordered) >= 3:
                loops.append(ordered)
        return loops, epsilon
    finally:
        bm.free()


def fitted_section(target, depsgraph, origin, normal, seed, count, offset):
    normal = normal.normalized()
    loops, epsilon = section_loops(target, depsgraph, origin, normal)
    if not loops:
        raise ValueError("No closed local section found; place the line across a closed part of the mesh")
    distances = [min(_distance_to_segment(seed, a, b) for a, b in _segments(loop)) for loop in loops]
    index = min(range(len(loops)), key=lambda i: distances[i])
    if distances[index] > epsilon * 100:
        raise ValueError("The indicated section is open or ambiguous; move the two points slightly")
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
    fitted = _offset(sampled, max(0.0, offset) + error + epsilon * 4)
    if _self_crosses(fitted) or _crosses(outline, fitted) or not all(_inside(p, fitted) for p in outline):
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
