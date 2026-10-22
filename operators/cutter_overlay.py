"""GPU previews for interactive cutter tools."""
from mathutils import Vector
from .cutter_screen import _axis_lock_mode, _screen_arc_points


def _draw_cutter_overlay(operator):
    if operator._start_pos is None:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    start = Vector(operator._start_pos)
    end = Vector(operator._mouse_pos or operator._start_pos)
    color = (0.1, 0.65, 1.0, 1.0)
    guide_color = (1.0, 0.78, 0.18, 0.55)
    label_color = (1.0, 1.0, 1.0, 1.0)

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    def draw_lines(points, line_color):
        batch = batch_for_shader(shader, "LINES", {"pos": points})
        shader.bind()
        shader.uniform_float("color", line_color)
        batch.draw(shader)

    cross_size = 7.0
    points = [
        (start.x - cross_size, start.y),
        (start.x + cross_size, start.y),
        (start.x, start.y - cross_size),
        (start.x, start.y + cross_size),
    ]

    if (end - start).length > 1.0:
        if getattr(operator, "_shift_locked", False) and operator._start_region is not None:
            if _axis_lock_mode(start, end) == "HORIZONTAL":
                guide = [(0.0, start.y), (operator._start_region.width, start.y)]
            else:
                guide = [(start.x, 0.0), (start.x, operator._start_region.height)]
            draw_lines(guide, guide_color)

        points.extend(
            [
                (start.x, start.y),
                (end.x, end.y),
                (end.x - cross_size, end.y),
                (end.x + cross_size, end.y),
                (end.x, end.y - cross_size),
                (end.x, end.y + cross_size),
            ]
        )

    draw_lines(points, color)

    font_id = 0
    try:
        blf.size(font_id, 14)
    except TypeError:
        blf.size(font_id, 14, 72)

    blf.color(font_id, *label_color)
    blf.position(font_id, start.x + 10.0, start.y + 10.0, 0)
    blf.draw(font_id, "A")

    if (end - start).length > 1.0:
        blf.position(font_id, end.x + 10.0, end.y + 10.0, 0)
        blf.draw(font_id, "B")


def _draw_cutter_arc_overlay(operator):
    if not operator._points:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    color = (0.1, 0.85, 1.0, 1.0)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    preview_points = list(operator._points)
    if operator._mouse_pos is not None and len(preview_points) < 3:
        preview_points.append(operator._mouse_pos)

    line_points = []
    if len(preview_points) == 3:
        arc_points = _screen_arc_points(
            preview_points[0],
            preview_points[1],
            preview_points[2],
            max(operator._preview_segments, 8),
        )
        if arc_points is not None:
            for start, end in zip(arc_points, arc_points[1:]):
                line_points.extend([start, end])

    if not line_points and len(preview_points) > 1:
        for start, end in zip(preview_points, preview_points[1:]):
            line_points.extend([start, end])

    cross_size = 7.0
    for point in preview_points:
        position = Vector(point)
        line_points.extend(
            [
                (position.x - cross_size, position.y),
                (position.x + cross_size, position.y),
                (position.x, position.y - cross_size),
                (position.x, position.y + cross_size),
            ]
        )

    if line_points:
        batch = batch_for_shader(shader, "LINES", {"pos": line_points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 14)
    except TypeError:
        blf.size(font_id, 14, 72)

    labels = ("A", "B", "C")
    blf.color(font_id, *label_color)
    for index, point in enumerate(preview_points[:3]):
        position = Vector(point)
        blf.position(font_id, position.x + 10.0, position.y + 10.0, 0)
        blf.draw(font_id, labels[index])


def _draw_cutter_path_overlay(operator):
    if not getattr(operator, "_surface_points", None) and not getattr(operator, "_points", None):
        return

    try:
        import blf
        import gpu
        from bpy_extras import view3d_utils
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    color = (0.15, 1.0, 0.55, 1.0)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    preview_points = []
    region = getattr(operator, "_start_region", None)
    rv3d = getattr(operator, "_start_rv3d", None)
    surface_points = getattr(operator, "_surface_points", None) or []
    mouse_surface_point = getattr(operator, "_mouse_surface_point", None)
    if region is not None and rv3d is not None and surface_points:
        world_points = [item["location"] for item in surface_points]
        if mouse_surface_point is not None:
            world_points.append(mouse_surface_point["location"])
        for location in world_points:
            point = view3d_utils.location_3d_to_region_2d(region, rv3d, location)
            if point is not None:
                preview_points.append(point)
    else:
        preview_points = list(operator._points)
        if operator._mouse_pos is not None:
            preview_points.append(operator._mouse_pos)

    if not preview_points:
        return

    line_points = []
    if len(preview_points) > 1:
        for start, end in zip(preview_points, preview_points[1:]):
            line_points.extend([start, end])

    cross_size = 6.0
    for point in preview_points:
        position = Vector(point)
        line_points.extend(
            [
                (position.x - cross_size, position.y),
                (position.x + cross_size, position.y),
                (position.x, position.y - cross_size),
                (position.x, position.y + cross_size),
            ]
        )

    if line_points:
        batch = batch_for_shader(shader, "LINES", {"pos": line_points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 13)
    except TypeError:
        blf.size(font_id, 13, 72)

    blf.color(font_id, *label_color)
    for index, point in enumerate(preview_points):
        if index >= 26:
            label = str(index + 1)
        else:
            label = chr(ord("A") + index)
        position = Vector(point)
        blf.position(font_id, position.x + 9.0, position.y + 9.0, 0)
        blf.draw(font_id, label)


def _draw_cutter_local_ring_overlay(operator):
    if operator._start_pos is None:
        return

    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    start = Vector(operator._start_pos)
    end = Vector(operator._mouse_pos or operator._start_pos)
    guide_color = (1.0, 0.78, 0.18, 0.85)
    label_color = (1.0, 1.0, 1.0, 1.0)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    guide_points = [(start.x, start.y), (end.x, end.y)]
    cross_size = 6.0
    for point in (start, end):
        guide_points.extend(
            [
                (point.x - cross_size, point.y),
                (point.x + cross_size, point.y),
                (point.x, point.y - cross_size),
                (point.x, point.y + cross_size),
            ],
        )
    batch = batch_for_shader(shader, "LINES", {"pos": guide_points})
    shader.bind()
    shader.uniform_float("color", guide_color)
    batch.draw(shader)

    font_id = 0
    try:
        blf.size(font_id, 13)
    except TypeError:
        blf.size(font_id, 13, 72)
    blf.color(font_id, *label_color)
    for label, point in (("A", start), ("B", end)):
        blf.position(font_id, point.x + 9.0, point.y + 9.0, 0)
        blf.draw(font_id, label)
