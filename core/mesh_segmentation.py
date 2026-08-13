def get_seam_edges(bm):
    return {edge for edge in bm.edges if edge.seam}


def split_into_groups(bm, seam_edges=None):
    bm.faces.ensure_lookup_table()
    seam_edges = seam_edges if seam_edges is not None else get_seam_edges(bm)

    visited = set()
    groups = []

    for face in bm.faces:
        if face in visited:
            continue

        group = []
        stack = [face]

        while stack:
            current_face = stack.pop()
            if current_face in visited:
                continue

            visited.add(current_face)
            group.append(current_face)

            for edge in current_face.edges:
                if edge in seam_edges:
                    continue

                for linked_face in edge.link_faces:
                    if linked_face not in visited:
                        stack.append(linked_face)

        groups.append(group)

    return groups
