"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes

Qt-independent helpers for laying out node graphs in left-to-right layers.
"""

import itertools
from collections import deque
from dataclasses import dataclass, field

# Long pipes are split into chains of virtual nodes. A higher weight keeps such
# chains straight, so they pass through the reserved channels between nodes.
LONG_EDGE_WEIGHT = 4.0


@dataclass(eq=False)
class LayoutNode:
    """A node to be laid out; ``y`` is the top edge in scene coordinates."""

    key: object
    width: float
    height: float
    y: float = 0.0
    rank: int = 0
    dummy: bool = False
    edges: list = field(default_factory=list)


@dataclass(eq=False)
class LayoutEdge:
    """A pipe between two ports, offsets are measured from the node top."""

    source: LayoutNode
    target: LayoutNode
    source_offset: float
    target_offset: float
    weight: float = 1.0

    def other(self, node):
        """Return the opposite node and the port offsets (own, other)."""
        if node is self.source:
            return self.target, self.source_offset, self.target_offset
        return self.source, self.target_offset, self.source_offset


def _topological_ranks(nodes, edges, down_stream=True):
    successors = {node: [] for node in nodes}
    predecessors = {node: [] for node in nodes}
    for edge in edges:
        successors[edge.source].append(edge.target)
        predecessors[edge.target].append(edge.source)
    forward, backward = (
        (successors, predecessors) if down_stream else (predecessors, successors)
    )
    incoming = {node: len(set(backward[node])) for node in nodes}
    ready = deque(node for node in nodes if incoming[node] == 0)
    ranks = dict.fromkeys(nodes, 0)
    order = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for other in dict.fromkeys(forward[node]):
            ranks[other] = max(ranks[other], ranks[node] + 1)
            incoming[other] -= 1
            if incoming[other] == 0:
                ready.append(other)
    if len(order) != len(nodes):
        raise ValueError("Cannot auto-layout a graph containing a cycle.")
    if not down_stream:
        top = max(ranks.values(), default=0)
        ranks = {node: top - rank for node, rank in ranks.items()}
        order.reverse()
    return ranks, order, successors, predecessors


def assign_ranks(nodes, edges, down_stream=True):
    """Assign layers so that the total horizontal span of all pipes is small.

    A longest-path ranking is refined by moving each node towards the side with
    more connected pipes, which never violates the left-to-right pipe direction.
    """
    ranks, order, successors, predecessors = _topological_ranks(
        nodes, edges, down_stream
    )
    for _ in range(len(nodes)):
        changed = False
        for node in order:
            ins, outs = len(predecessors[node]), len(successors[node])
            if outs > ins:
                rank = min(ranks[other] for other in successors[node]) - 1
                if rank > ranks[node]:
                    ranks[node] = rank
                    changed = True
            elif ins > outs:
                rank = max(ranks[other] for other in predecessors[node]) + 1
                if rank < ranks[node]:
                    ranks[node] = rank
                    changed = True
        if not changed:
            break
    # Remove empty layers
    used = {rank: index for index, rank in enumerate(sorted(set(ranks.values())))}
    for node in nodes:
        node.rank = used[ranks[node]]


def _split_long_edges(nodes, edges):
    """Insert virtual nodes so every edge connects adjacent layers."""
    all_nodes = list(nodes)
    short_edges = []
    for edge in edges:
        span = edge.target.rank - edge.source.rank
        if span <= 1:
            short_edges.append(edge)
            continue
        previous, previous_offset = edge.source, edge.source_offset
        for rank in range(edge.source.rank + 1, edge.target.rank):
            dummy = LayoutNode(key=None, width=0.0, height=0.0, rank=rank, dummy=True)
            dummy.y = edge.source.y + edge.source_offset
            all_nodes.append(dummy)
            short_edges.append(
                LayoutEdge(previous, dummy, previous_offset, 0.0, LONG_EDGE_WEIGHT)
            )
            previous, previous_offset = dummy, 0.0
        short_edges.append(
            LayoutEdge(
                previous,
                edge.target,
                previous_offset,
                edge.target_offset,
                LONG_EDGE_WEIGHT,
            )
        )
    for node in all_nodes:
        node.edges = []
    for edge in short_edges:
        edge.source.edges.append(edge)
        edge.target.edges.append(edge)
    return all_nodes, short_edges


def _crossings(layers, edges):
    index = {node: i for layer in layers for i, node in enumerate(layer)}
    by_layer = {}
    for edge in edges:
        source = index[edge.source] + _port_fraction(edge.source, edge.source_offset)
        target = index[edge.target] + _port_fraction(edge.target, edge.target_offset)
        by_layer.setdefault(edge.source.rank, []).append((source, target))
    count = 0
    for pairs in by_layer.values():
        for i, (a1, b1) in enumerate(pairs):
            for a2, b2 in pairs[i + 1 :]:
                if (a1 - a2) * (b1 - b2) < 0:
                    count += 1
    return count


def _port_fraction(node, offset):
    if node.dummy or node.height <= 0:
        return 0.5
    return min(max(offset / node.height, 0.0), 0.999)


def _barycenter(node, ref_index, fallback):
    values = []
    for edge in node.edges:
        other, _, other_offset = edge.other(node)
        if other in ref_index:
            values.append(ref_index[other] + _port_fraction(other, other_offset))
    if not values:
        return fallback
    return sum(values) / len(values)


def order_layers(layers, edges, sweeps=12):
    """Reduce pipe crossings with alternating barycenter sweeps."""
    best = [layer[:] for layer in layers]
    best_crossings = _crossings(best, edges)
    for sweep in range(sweeps):
        if best_crossings == 0:
            break
        downward = sweep % 2 == 0
        indices = range(1, len(layers)) if downward else range(len(layers) - 2, -1, -1)
        for i in indices:
            reference = layers[i - 1] if downward else layers[i + 1]
            ref_index = {node: j for j, node in enumerate(reference)}
            current = {node: j for j, node in enumerate(layers[i])}
            keys = {
                node: _barycenter(node, ref_index, current[node]) for node in layers[i]
            }
            layers[i].sort(key=keys.__getitem__)
        crossings = _crossings(layers, edges)
        if crossings < best_crossings:
            best = [layer[:] for layer in layers]
            best_crossings = crossings
    return best


def _separation(upper, lower, y_gap):
    if upper.dummy and lower.dummy:
        gap = y_gap / 3
    elif upper.dummy or lower.dummy:
        gap = y_gap / 2
    else:
        gap = y_gap
    return upper.height + gap


def _place_layer(layer, y_gap):
    """Minimize weighted squared pipe slopes for one layer, keeping node order.

    This is a weighted isotonic regression (pool adjacent violators) on
    the desired positions shifted by the cumulative minimal separations.
    """
    connected = [node for node in layer if node.edges]
    if connected:
        shifts = [0.0]
        for upper, lower in itertools.pairwise(connected):
            shifts.append(shifts[-1] + _separation(upper, lower, y_gap))
        pools = []
        for node, shift in zip(connected, shifts):
            total = weight_sum = 0.0
            for edge in node.edges:
                other, own_offset, other_offset = edge.other(node)
                total += edge.weight * (other.y + other_offset - own_offset)
                weight_sum += edge.weight
            value, weight, count = total / weight_sum - shift, weight_sum, 1
            while pools and pools[-1][0] >= value:
                prev_value, prev_weight, prev_count = pools.pop()
                value = (prev_value * prev_weight + value * weight) / (
                    prev_weight + weight
                )
                weight += prev_weight
                count += prev_count
            pools.append((value, weight, count))
        index = 0
        for value, _, count in pools:
            for _ in range(count):
                connected[index].y = value + shifts[index]
                index += 1
    # Unconnected nodes are stacked below the connected ones.
    previous = connected[-1] if connected else None
    for node in layer:
        if node.edges:
            continue
        if previous is not None:
            node.y = previous.y + _separation(previous, node, y_gap)
        previous = node


def layered_layout(nodes, edges, x_gap, y_gap, down_stream=True, iterations=300):
    """Lay out nodes from left to right with short, straight pipes.

    Parameters
    ----------
    nodes : list of LayoutNode
        Nodes with their current ``y`` (used for the initial order).
    edges : list of LayoutEdge
        Directed pipes from output to input ports.
    x_gap, y_gap : float
        Minimal horizontal gap between layers and vertical gap between nodes.
    down_stream : bool
        Whether the initial ranking starts at source (True) or sink nodes.
    iterations : int
        Maximum number of vertical refinement sweeps.

    Returns
    -------
    dict
        Mapping of ``LayoutNode.key`` to ``(left, top)`` positions.
    """
    if not nodes:
        return {}
    assign_ranks(nodes, edges, down_stream)
    all_nodes, short_edges = _split_long_edges(nodes, edges)
    layer_count = max(node.rank for node in all_nodes) + 1
    layers = [[] for _ in range(layer_count)]
    for node in sorted(all_nodes, key=lambda n: n.y + n.height / 2):
        layers[node.rank].append(node)
    layers = order_layers(layers, short_edges)
    # Unconnected nodes go to the bottom of their layer.
    layers = [
        [node for node in layer if node.edges]
        + [node for node in layer if not node.edges]
        for layer in layers
    ]

    # Initial stacking, then block coordinate descent over the layers.
    for layer in layers:
        y = 0.0
        for upper, lower in zip([None, *layer], layer):
            if upper is not None:
                y += _separation(upper, lower, y_gap)
            lower.y = y
    for iteration in range(iterations):
        before = [node.y for node in all_nodes]
        order = layers if iteration % 2 == 0 else layers[::-1]
        for layer in order:
            _place_layer(layer, y_gap)
        if max(abs(a - node.y) for a, node in zip(before, all_nodes)) < 1e-6:
            break

    # Nodes that only feed later layers hug the right column edge, which keeps
    # their pipes short and clear of wider nodes in the same column.
    has_input = {id(edge.target) for edge in edges}
    has_output = {id(edge.source) for edge in edges}
    positions = {}
    x = 0.0
    for layer in layers:
        width = max((node.width for node in layer if not node.dummy), default=0.0)
        for node in layer:
            if node.dummy:
                continue
            left = x
            if id(node) in has_output and id(node) not in has_input:
                left = x + width - node.width
            positions[node.key] = (left, node.y)
        x += width + x_gap
    return positions
