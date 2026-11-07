"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes

Qt-independent orthogonal pipe routing around rectangular obstacles.
"""

import heapq
import math

# Direction indices: right, left, down, up
_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_RIGHT = 0


def _inside(x, y, rects):
    """Return True if the point lies strictly inside any rectangle."""
    for left, top, right, bottom in rects:
        if left < x < right and top < y < bottom:
            return True
    return False


def route_orthogonal(start, end, obstacles, source_rect, target_rect, margin=20.0):
    """Find an orthogonal path between an output and an input port.

    The path leaves ``start`` to the right and enters ``end`` from the left,
    keeping ``margin`` distance from all obstacles. It minimizes length plus a
    penalty for each bend.

    Parameters
    ----------
    start, end : tuple of float
        Output and input port centers.
    obstacles : list of tuple
        Rectangles ``(left, top, right, bottom)`` to avoid, without the
        source and target node.
    source_rect, target_rect : tuple
        Rectangles of the source and target node.
    margin : float
        Clearance around obstacles.

    Returns
    -------
    list of tuple | None
        The path points including ``start`` and ``end`` or None, if no route
        could be found.
    """
    rects = [
        (left - margin, top - margin, right + margin, bottom + margin)
        for left, top, right, bottom in [*obstacles, source_rect, target_rect]
    ]
    exit_point = (max(start[0], source_rect[2]) + margin, start[1])
    entry_point = (min(end[0], target_rect[0]) - margin, end[1])
    if _inside(*exit_point, rects) or _inside(*entry_point, rects):
        return None

    xs = {exit_point[0], entry_point[0]}
    ys = {exit_point[1], entry_point[1]}
    for left, top, right, bottom in rects:
        xs.update((left, right))
        ys.update((top, bottom))
    # A frame around everything allows routes around the whole graph.
    xs.update((min(xs) - margin, max(xs) + margin))
    ys.update((min(ys) - margin, max(ys) + margin))
    xs, ys = sorted(xs), sorted(ys)
    x_index = {x: i for i, x in enumerate(xs)}
    y_index = {y: i for i, y in enumerate(ys)}
    source = (x_index[exit_point[0]], y_index[exit_point[1]])
    target = (x_index[entry_point[0]], y_index[entry_point[1]])
    bend_penalty = margin * 3

    def passable(a, b):
        # Neighboring grid lines can't enclose an obstacle edge,
        # so testing both endpoints and the midpoint is sufficient.
        ax, ay = xs[a[0]], ys[a[1]]
        bx, by = xs[b[0]], ys[b[1]]
        return not (
            _inside(bx, by, rects) or _inside((ax + bx) / 2, (ay + by) / 2, rects)
        )

    def heuristic(cell):
        return abs(xs[cell[0]] - entry_point[0]) + abs(ys[cell[1]] - entry_point[1])

    start_state = (source, _RIGHT)
    costs = {start_state: 0.0}
    previous = {}
    queue = [(heuristic(source), 0.0, source, _RIGHT)]
    goal_state = None
    while queue:
        _, cost, cell, direction = heapq.heappop(queue)
        if costs.get((cell, direction), math.inf) < cost:
            continue
        if cell == target:
            goal_state = (cell, direction)
            break
        for new_direction, (dx, dy) in enumerate(_DIRECTIONS):
            # No immediate reversals
            if new_direction == direction ^ 1:
                continue
            nxt = (cell[0] + dx, cell[1] + dy)
            if not (0 <= nxt[0] < len(xs) and 0 <= nxt[1] < len(ys)):
                continue
            if not passable(cell, nxt):
                continue
            new_cost = cost + abs(xs[nxt[0]] - xs[cell[0]])
            new_cost += abs(ys[nxt[1]] - ys[cell[1]])
            if new_direction != direction:
                new_cost += bend_penalty
            if nxt == target and new_direction != _RIGHT:
                new_cost += bend_penalty
            state = (nxt, new_direction)
            if new_cost < costs.get(state, math.inf):
                costs[state] = new_cost
                previous[state] = (cell, direction)
                heapq.heappush(
                    queue, (new_cost + heuristic(nxt), new_cost, nxt, new_direction)
                )
    if goal_state is None:
        return None

    cells = [goal_state[0]]
    state = goal_state
    while state in previous:
        state = previous[state]
        cells.append(state[0])
    cells.reverse()
    points = [start, *((xs[i], ys[j]) for i, j in cells), end]
    return simplify(points)


def simplify(points):
    """Remove duplicate and collinear points from an orthogonal path."""
    result = []
    for point in points:
        if (
            result
            and math.isclose(point[0], result[-1][0])
            and math.isclose(point[1], result[-1][1])
        ):
            continue
        if len(result) >= 2:
            a, b = result[-2], result[-1]
            if (math.isclose(a[0], b[0]) and math.isclose(b[0], point[0])) or (
                math.isclose(a[1], b[1]) and math.isclose(b[1], point[1])
            ):
                result[-1] = point
                continue
        result.append(point)
    return result


def _assign_lanes(segments, padding):
    """Assign lane indices to segments on one line so overlaps get own lanes.

    ``segments`` are ``(low, high, key)`` tuples. Returns a list of
    ``(key, lane, lane_count)`` per connected group of overlapping segments.
    """
    result = []
    segments = sorted(segments)
    group, group_end = [], -math.inf
    for segment in [*segments, None]:
        if segment is None or segment[0] >= group_end + padding:
            if len(group) > 1:
                # Greedy interval coloring
                lane_ends = []
                lanes = []
                for low, high, key in group:
                    for lane, end in enumerate(lane_ends):
                        if low >= end + padding:
                            lane_ends[lane] = high
                            break
                    else:
                        lane = len(lane_ends)
                        lane_ends.append(high)
                    lanes.append((key, lane))
                result.extend((key, lane, len(lane_ends)) for key, lane in lanes)
            if segment is None:
                break
            group, group_end = [], -math.inf
        group.append(segment)
        group_end = max(group_end, segment[1])
    return result


def separate_overlaps(paths, padding, max_offset=None, tol=0.5):
    """Spread overlapping collinear segments of different paths into lanes.

    Vertical segments sharing an x-coordinate are moved apart horizontally
    and inner horizontal segments sharing a y-coordinate are moved apart
    vertically, so that each pipe stays distinguishable and clickable.
    The first and last segment of each path (attached to the ports) keep
    their position.

    Parameters
    ----------
    paths : list of list of tuple
        Orthogonal paths as ``(x, y)`` points.
    padding : float
        Distance between neighboring lanes.
    max_offset : float | None
        Maximum distance of a lane from the original line. If the lanes
        would exceed it, the padding is reduced for this group.
    tol : float
        Tolerance to consider coordinates equal.

    Returns
    -------
    list of list of tuple
        The paths with separated segments.
    """
    paths = [[tuple(point) for point in path] for path in paths]
    if padding <= 0:
        return paths
    # axis 0: vertical segments (constant x), axis 1: horizontal (constant y)
    for axis in (0, 1):
        other = 1 - axis
        lines = []
        for path_index, path in enumerate(paths):
            for index in range(1, len(path) - 2):
                a, b = path[index], path[index + 1]
                if abs(a[axis] - b[axis]) > tol or abs(a[other] - b[other]) <= tol:
                    continue
                low, high = sorted((a[other], b[other]))
                lines.append((a[axis], low, high, (path_index, index)))
        lines.sort()
        start = 0
        while start < len(lines):
            stop = start + 1
            while stop < len(lines) and lines[stop][0] - lines[start][0] <= tol:
                stop += 1
            segments = [(low, high, key) for _, low, high, key in lines[start:stop]]
            for (path_index, index), lane, count in _assign_lanes(segments, padding):
                step = padding
                if max_offset is not None and count > 1:
                    step = min(padding, 2 * max_offset / (count - 1))
                offset = (lane - (count - 1) / 2) * step
                path = paths[path_index]
                for point_index in (index, index + 1):
                    point = list(path[point_index])
                    point[axis] += offset
                    path[point_index] = tuple(point)
            start = stop
    return paths
