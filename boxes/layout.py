"""Diagram layout engine — Node, Edge, Port, Diagram classes with routing.

This module provides the core data model (``Node``, ``Edge``, ``Port``,
``Diagram``) and three routing strategies:

- **straight**    — ``_route_straight()`` center-to-center lines
- **orthogonal**  — ``_route_orthogonal()`` homegrown 3-segment Manhattan
                   with obstacle avoidance and edge-edge spacing
- **sugiyama**    — delegates to ``sugiyama.sugiyama_layout()``

Port sub-routing (``_port_route``) handles Z-shaped (3-segment) paths between
explicit ``source_port``/``target_port`` on edges.

After calling ``layout()``, the diagram is ready for rendering via
``render()`` (drawille terminal output) or ``render_svg()`` (SVG output).

See also
--------
sugiyama.py  : pure-Python Sugiyama pipeline
elk.py       : ELKjs subprocess integration
primitives.py: drawille-based terminal drawing
svg_canvas.py: SVG vector drawing
"""

from drawille import Canvas
from boxes.primitives import draw_polyline, draw_relation, draw_class_box, draw_port_box, \
    draw_comment_box, draw_view_box, \
    SOLID, DASHED, OPEN, NONE, FILLED, DIAMOND, TRIANGLE, CIRCLE, PORT_W, PORT_H
from boxes.svg_canvas import SvgCanvas, svg_draw_edge, svg_draw_node, svg_draw_port, svg_draw_comment, svg_draw_view

_MIN_PORT_SPACING = 8
from collections import defaultdict
from boxes.sugiyama import sugiyama_layout


class Port:
    """A small box on a node's boundary for structured connections.

    Ports are positioned along a node side using a proportional offset
    (0.0 = top/left, 1.0 = bottom/right).  They are rendered as 8×8 px
    boxes with an optional direction arrow inside and the label outside.

    Parameters
    ----------
    label : str
        Text shown outside the port box (away from the node).
    side : {'left', 'right', 'top', 'bottom'}
        Which edge of the parent node the port sits on.
    offset : float or None
        Proportional position along the side (0.0–1.0), or ``None`` for
        auto-distribution (evenly spaced with minimum gap).
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward node interior (input).
        ``'out'`` → arrow points away from node (output).
        ``'inout'`` → bidirectional double-headed arrow.
        ``None``  → no arrow drawn (default).

    See also
    --------
    Node.add_port : Attach a port to a node.
    Edge : source_port / target_port parameters use Port objects.
    """

    def __init__(self, label, side='left', offset=0.5, direction=None):
        self.label = label
        self.side = side
        self.offset = offset
        self.direction = direction
        self.parent = None
        self.x = self.y = 0

    @property
    def w(self):
        return PORT_W

    @property
    def h(self):
        return PORT_H

    @property
    def cx(self):
        return self.x + PORT_W // 2

    @property
    def cy(self):
        return self.y + PORT_H // 2

    def box(self):
        return (self.x, self.y, self.x + PORT_W, self.y + PORT_H)

    def update_pos(self):
        if not self.parent:
            return
        px, py, pw, ph = self.parent.x, self.parent.y, self.parent.w, self.parent.h
        if self.side == 'left':
            self.x = px - PORT_W
            self.y = py + int(ph * self.offset) - PORT_H // 2
        elif self.side == 'right':
            self.x = px + pw
            self.y = py + int(ph * self.offset) - PORT_H // 2
        elif self.side == 'top':
            self.x = px + int(pw * self.offset) - PORT_W // 2
            self.y = py - PORT_H
        elif self.side == 'bottom':
            self.x = px + int(pw * self.offset) - PORT_W // 2
            self.y = py + ph


class Node:
    """A diagram node (classifier) with optional stereotypes and attributes.

    Nodes are positioned by the layout engine and drawn as rectangular
    boxes with centered text.  Stereotypes appear above the name in
    guillemets (\\u00ab...\\u00bb).  Attributes appear below a separator
    line.

    Parameters
    ----------
    name : str
        Primary label shown inside the box.
    stereotypes : list of str, optional
        Stereotype labels shown above the name (e.g. ``['block']``).
    attributes : list of str, optional
        Attribute/method lines shown below a separator
        (e.g. ``['+ voltage : float', '# state : int']``).

    See also
    --------
    Diagram.add_node : Factory method for creating registered nodes.
    Port : Attachable boundary ports.
    """

    def __init__(self, name, stereotypes=None, attributes=None):
        self.name = name
        self.stereotypes = stereotypes or []
        self.attributes = attributes or []
        self.ports = []
        self.x = self.y = self.w = self.h = 0
        self._calc_size()

    def _calc_size(self):
        tw = []
        if self.stereotypes:
            tw.extend(len(f'\u00ab{s}\u00bb') for s in self.stereotypes)
        tw.append(len(self.name))
        if self.attributes:
            tw.extend(len(a) for a in self.attributes)
        max_tw = max(tw) if tw else 0
        self.w = max(max_tw * 2 + 6, 26)
        total_lines = len(self.stereotypes) + 1
        if self.attributes:
            total_lines += 1 + len(self.attributes)
        self.h = total_lines * 5 + 8

    def add_port(self, label, side='left', offset=None, direction=None):
        p = Port(label, side, offset, direction)
        p.parent = self
        self.ports.append(p)
        return p

    def add_attribute(self, text):
        self.attributes.append(text)
        self._calc_size()

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class Comment:
    """A comment/documentation node with a folded (dog-ear) corner.

    Comments are drawn as rectangles with the top-right corner folded
    over (dog-ear), distinguishing them from regular classifier boxes.

    Parameters
    ----------
    text : str
        The comment text shown inside the box.
    """

    def __init__(self, text):
        self.text = text
        self.x = self.y = 0
        self.w = max(len(text) * 2 + 6, 26)
        self.h = 21

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class View:
    """A view / package node with a folder-tab label area.

    Views are drawn as a rectangle with a "tab" at the top-left corner
    containing the name (and optional stereotypes).  Attributes appear
    in the main content area below a separator.  This matches the UML
    ``«package»`` and SysML ``«view»`` notation.

    Parameters
    ----------
    name : str
        Primary label shown in the tab.
    stereotypes : list of str, optional
        Stereotype labels (e.g. ``['view']``, ``['package']``).
    attributes : list of str, optional
        Attribute/method lines shown below a separator.
    """

    def __init__(self, name, stereotypes=None, attributes=None):
        self.name = name
        self.stereotypes = stereotypes or []
        self.attributes = attributes or []
        self.x = self.y = self.w = self.h = 0
        self._calc_size()

    def _calc_size(self):
        tw = []
        if self.stereotypes:
            tw.extend(len(f'\u00ab{s}\u00bb') for s in self.stereotypes)
        tw.append(len(self.name))
        if self.attributes:
            tw.extend(len(a) for a in self.attributes)
        max_tw = max(tw) if tw else 0
        self.w = max(max_tw * 2 + 6, 26)
        tab_lines = 1 + len(self.stereotypes)
        tab_h = tab_lines * 5 + 4
        attr_h = (1 + len(self.attributes)) * 5 if self.attributes else 0
        self.h = tab_h + attr_h + 6

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def add_attribute(self, text):
        self.attributes.append(text)
        self._calc_size()


class Edge:
    """A directed or undirected connection between two nodes (or ports).

    Edges can connect directly between nodes (using automatic boundary
    ports) or between explicit ``Port`` objects on each node.  The
    routing engine computes ``waypoints`` — a list of (x, y) waypoints
    that define the edge path.

    Parameters
    ----------
    source, target : Node
        The endpoints of the edge.
    line_style : {'solid', 'dashed'}, optional
        Line appearance.  Default ``SOLID``.
    source_style, target_style : str or None, optional
        Arrowhead at each end: ``NONE``, ``OPEN``, ``TRIANGLE``,
        ``DIAMOND``, ``FILLED``.  Default target_style is ``OPEN``.
    label : str, optional
        Text label placed at the Manhattan midpoint of the route.
    source_port, target_port : Port or None, optional
        Explicit port objects for structured (port-to-port) connections.
        When both are set, the routing uses L-shaped paths instead of
        the standard 3-segment boundary-port routing.

    See also
    --------
    Diagram.add_edge : Factory method.
    Port : Port objects used with source_port / target_port.
    """

    def __init__(self, source, target, *, line_style=SOLID, source_style=None,
                 target_style=OPEN, label=None, source_port=None, target_port=None):
        self.source = source
        self.target = target
        self.source_port = source_port
        self.target_port = target_port
        self.line_style = line_style
        self.source_style = source_style
        self.target_style = target_style
        self.label = label
        self.waypoints = []

    def route(self, *points):
        self.waypoints = list(points)


class Diagram:
    """Top-level container for nodes, edges, and layout configuration.

    A Diagram holds a collection of Nodes and Edges and provides
    layout and rendering methods.  Layout is computed lazily on
    ``render()`` / ``render_svg()``.

    Usage
    -----
    ::

        d = Diagram()
        n1 = d.add_node('A', ['block'], attributes=['+ x'])
        n2 = d.add_node('B')
        p = n1.add_port('out', side='right', offset=0.5)
        d.add_edge(n1, n2, source_port=p, target_style=OPEN, label='conn')
        print(d.render(routing='orthogonal'))

    See also
    --------
    Node, Edge, Port : Element types.
    render, render_svg : Output methods.
    layout : Manual layout invocation.
    """

    def __init__(self):
        self.nodes = []
        self.comments = []
        self.views = []
        self.edges = []

    def add_node(self, name, stereotypes=None, attributes=None):
        """Create a new node and register it with the diagram.

        Parameters
        ----------
        name : str
            Node label shown inside the box.
        stereotypes : list of str, optional
            Stereotype labels (e.g. ``['block']``, ``['part']``).
        attributes : list of str, optional
            Attribute lines shown below a separator.

        Returns
        -------
        Node
            The newly created node.
        """
        n = Node(name, stereotypes, attributes)
        self.nodes.append(n)
        return n

    def add_comment(self, text):
        """Create a comment node and register it with the diagram.

        Comments are drawn as rectangles with a folded (dog-ear)
        top-right corner.  They are placed below regular nodes in
        the layout.

        Parameters
        ----------
        text : str
            The comment text shown inside the box.

        Returns
        -------
        Comment
        """
        c = Comment(text)
        self.comments.append(c)
        return c

    def add_view(self, name, stereotypes=None, attributes=None):
        """Create a view / package node and register it with the diagram.

        Views are drawn as rectangles with a folder-tab containing the
        name (and optional stereotypes).  They are placed below regular
        nodes in the layout.

        Parameters
        ----------
        name : str
            Primary label shown in the tab.
        stereotypes : list of str, optional
            Stereotype labels (e.g. ``['view']``, ``['package']``).
        attributes : list of str, optional
            Attribute/method lines shown below a separator.

        Returns
        -------
        View
        """
        v = View(name, stereotypes, attributes)
        self.views.append(v)
        return v

    def _update_port_positions(self):
        for n in self.nodes:
            if not n.ports:
                continue

            groups = defaultdict(list)
            for p in n.ports:
                groups[p.side].append(p)

            for side, ports in groups.items():
                n_ports = len(ports)

                if n_ports >= 1 and any(p.offset is None for p in ports):
                    # Auto-distribute all ports on this side with minimum spacing
                    if side in ('left', 'right'):
                        px = n.x - PORT_W if side == 'left' else n.x + n.w
                        total_h = n_ports * PORT_H + (n_ports - 1) * _MIN_PORT_SPACING
                        start_y = n.y + max(0, (n.h - total_h) // 2)
                        for i, p in enumerate(ports):
                            p.x = px
                            p.y = start_y + i * (PORT_H + _MIN_PORT_SPACING)
                    else:  # top / bottom
                        py = n.y - PORT_H if side == 'top' else n.y + n.h
                        total_w = n_ports * PORT_W + (n_ports - 1) * _MIN_PORT_SPACING
                        start_x = n.x + max(0, (n.w - total_w) // 2)
                        for i, p in enumerate(ports):
                            p.x = start_x + i * (PORT_W + _MIN_PORT_SPACING)
                            p.y = py
                else:
                    for p in ports:
                        p.update_pos()

    def add_edge(self, source, target, **kw):
        """Create a new edge and register it with the diagram.

        Parameters
        ----------
        source, target : Node
            Endpoint nodes.
        **kw
            Passed to ``Edge``: ``line_style``, ``source_style``,
            ``target_style``, ``label``, ``source_port``, ``target_port``.

        Returns
        -------
        Edge
            The newly created edge.
        """
        e = Edge(source, target, **kw)
        self.edges.append(e)
        return e

    def compose(self, whole, part, **kw):
        """Convenience: composition edge (filled diamond at whole, no arrow).

        Parameters
        ----------
        whole, part : Node
        **kw
            Passed through to ``add_edge``.  Overrides ``source_style``
            and ``target_style`` if provided.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', FILLED)
        kw.setdefault('target_style', NONE)
        return self.add_edge(whole, part, **kw)

    def aggregate(self, whole, part, **kw):
        """Convenience: aggregation edge (empty diamond at whole, no arrow)."""
        kw.setdefault('source_style', DIAMOND)
        kw.setdefault('target_style', NONE)
        return self.add_edge(whole, part, **kw)

    def depend(self, client, supplier, **kw):
        """Convenience: dependency edge (dashed, open arrow at supplier)."""
        kw.setdefault('line_style', DASHED)
        kw.setdefault('target_style', OPEN)
        kw.setdefault('source_style', NONE)
        return self.add_edge(client, supplier, **kw)

    def annotate(self, client, supplier, **kw):
        """Convenience: SysMLv2 annotation edge (same style as dependency).

        An annotation in SysMLv2 is a dashed line with an open arrow at the
        element being annotated — identical styling to ``depend()``.
        """
        return self.depend(client, supplier, **kw)

    def contain(self, container, element, **kw):
        """Convenience: containment edge (circle at container end).

        In UML/SysML, a containment relationship uses an open circle
        at the container end to indicate namespace membership.

        Parameters
        ----------
        container : Node or View
            The owning namespace / container.
        element : Node
            The contained element.
        **kw
            Passed through to ``add_edge``.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', CIRCLE)
        kw.setdefault('target_style', NONE)
        return self.add_edge(container, element, **kw)

    def generalize(self, child, parent, **kw):
        """Convenience: UML generalization / inheritance (open triangle at parent).

        Parameters
        ----------
        child, parent : Node
        **kw
            Passed through to ``add_edge``.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', NONE)
        kw.setdefault('target_style', TRIANGLE)
        return self.add_edge(child, parent, **kw)

    def _assign_layers(self):
        incoming = {n: set() for n in self.nodes}
        for e in self.edges:
            if isinstance(e.source, (Comment, View)) or isinstance(e.target, (Comment, View)):
                continue
            incoming[e.target].add(e.source)

        roots = [n for n in self.nodes if not incoming[n]]
        if not roots and self.nodes:
            roots = [self.nodes[0]]

        layer_of = {}
        queue = [(n, 0) for n in roots]
        for n, l in queue:
            if n in layer_of:
                continue
            layer_of[n] = l
            for e in self.edges:
                if isinstance(e.target, (Comment, View)):
                    continue
                if e.source == n:
                    queue.append((e.target, l + 1))

        for n in self.nodes:
            if n not in layer_of:
                layer_of[n] = 0

        layers = []
        for n, l in layer_of.items():
            while len(layers) <= l:
                layers.append([])
            layers[l].append(n)
        return layers, layer_of

    # ── straight-line routing ──

    def _route_straight(self, e, layer_of):
        if e.source_port and e.target_port:
            self._port_route(e)
            return
        sl = layer_of.get(e.source, 0)
        tl = layer_of.get(e.target, 0)
        if sl < tl and abs(sl - tl) == 1:
            same_src = [e2 for e2 in self.edges
                        if e2.source == e.source and layer_of.get(e2.target) == tl]
            same_tgt = [e2 for e2 in self.edges
                        if e2.target == e.target and layer_of.get(e2.source) == sl]
            try:
                src_i = same_src.index(e)
            except ValueError:
                src_i = 0
            try:
                tgt_i = same_tgt.index(e)
            except ValueError:
                tgt_i = 0
            n_src = max(len(same_src), 1)
            n_tgt = max(len(same_tgt), 1)
            src_ports = self._distribute_ports(n_src, e.source.w)
            tgt_ports = self._distribute_ports(n_tgt, e.target.w)
            sx = e.source.x + src_ports[min(src_i, len(src_ports) - 1)]
            sy = e.source.y + e.source.h
            tx = e.target.x + tgt_ports[min(tgt_i, len(tgt_ports) - 1)]
            ty = e.target.y
            e.route((sx, sy), (tx, ty))
        else:
            e.route((e.source.cx, e.source.cy), (e.target.cx, e.target.cy))

    # ── orthogonal (Manhattan) routing ──

    def _distribute_ports(self, n, w):
        """Distribute n ports across width w with minimum spacing."""
        if n <= 0:
            return []
        spacing = w / (n + 1)
        if spacing < _MIN_PORT_SPACING and n > 1:
            spacing = _MIN_PORT_SPACING
            total = (n - 1) * spacing
            start = max(0, (w - total) / 2)
            return [int(start + spacing * i + spacing / 2) for i in range(n)]
        return [int(w * (i + 1) / (n + 1)) for i in range(n)]

    def _get_port(self, node, edge, is_source, layer_of):
        """Compute a distributed port position for an edge on a node."""
        tl = layer_of.get(edge.target)
        sl = layer_of.get(edge.source)
        if is_source:
            peers = [e for e in self.edges if e.source == node and layer_of.get(e.target) == tl]
            try:
                i = peers.index(edge)
            except ValueError:
                i = 0
            n = max(len(peers), 1)
            ports = self._distribute_ports(n, node.w)
            x = node.x + ports[min(i, len(ports) - 1)]
            y = node.y + node.h
        else:
            peers = [e for e in self.edges if e.target == node and layer_of.get(e.source) == sl]
            try:
                i = peers.index(edge)
            except ValueError:
                i = 0
            n = max(len(peers), 1)
            ports = self._distribute_ports(n, node.w)
            x = node.x + ports[min(i, len(ports) - 1)]
            y = node.y
        return (x, y)

    def _segment_hits(self, x1, y1, x2, y2, obstacles):
        """Check if any obstacle box intersects the segment (x1,y1)-(x2,y2)."""
        for node in obstacles:
            nx1, ny1, nx2, ny2 = node.box()
            pad = 1
            if x1 == x2:  # vertical
                if not (nx1 - pad <= x1 <= nx2 + pad):
                    continue
                lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                if lo <= ny2 + pad and hi >= ny1 - pad:
                    return True, node
            else:  # horizontal
                if not (ny1 - pad <= y1 <= ny2 + pad):
                    continue
                lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                if lo <= nx2 + pad and hi >= nx1 - pad:
                    return True, node
        return False, None

    def _port_boundary(self, p):
        """Return (x, y) at the outer edge of a port box for edge connection."""
        if p.side == 'left':
            return (p.x, p.cy)
        elif p.side == 'right':
            return (p.x + PORT_W, p.cy)
        elif p.side == 'top':
            return (p.cx, p.y)
        else:  # bottom
            return (p.cx, p.y + PORT_H)

    def _port_route(self, e):
        sp, tp = e.source_port, e.target_port
        if not sp or not tp:
            return False
        sx, sy = self._port_boundary(sp)
        tx, ty = self._port_boundary(tp)
        gap = 4

        # Always make the final segment perpendicular to the target port face.
        # First determine the approach point (just before the port, on the
        # side the port faces), then route: source → (vertical leg) →
        # (horizontal leg) → approach → target in 3 segments.
        if tp.side == 'left':
            ax = tx - gap
            ay = ty
        elif tp.side == 'right':
            ax = tx + gap
            ay = ty
        elif tp.side == 'top':
            ax = tx
            ay = ty - gap
        else:  # bottom
            ax = tx
            ay = ty + gap

        # If source and approach are on opposite sides of the port,
        # a gap would create a hook — route directly instead.
        if tp.side in ('left', 'right') and (sx - tx) * (ax - tx) < 0:
            # Direct L-shaped route to port (no gap)
            if abs(ty - sy) > abs(tx - sx):
                e.route((sx, sy), (sx, ty), (tx, ty))
            else:
                e.route((sx, sy), (tx, sy), (tx, ty))
        elif tp.side in ('top', 'bottom') and (sy - ty) * (ay - ty) < 0:
            if abs(ty - sy) > abs(tx - sx):
                e.route((sx, sy), (sx, ty), (tx, ty))
            else:
                e.route((sx, sy), (tx, sy), (tx, ty))
        else:
            # 3-segment Z-shape with perpendicular final approach
            # First leg follows the non-port-face axis
            if tp.side in ('left', 'right'):
                e.route((sx, sy), (sx, ay), (ax, ay), (tx, ty))
            else:
                e.route((sx, sy), (ax, sy), (ax, ay), (tx, ty))
        return True

    def _route_orthogonal(self, e, layer_of, layers, gap_used=None):
        if e.source_port and e.target_port:
            self._port_route(e)
            return

        sl = layer_of.get(e.source, 0)
        tl = layer_of.get(e.target, 0)
        obstacles = [n for n in self.nodes if n not in (e.source, e.target)]

        if sl < tl:
            sx, sy = self._get_port(e.source, e, True, layer_of)
            tx, ty = self._get_port(e.target, e, False, layer_of)

            # Collect eligible gap y-levels between source and target layers
            gap_key = (sl, tl)
            if gap_used is not None and gap_key not in gap_used:
                gap_used[gap_key] = 0
            used = gap_used[gap_key] if gap_used is not None else 0

            candidates = []
            for l in range(sl, tl):
                gap_top = max(n.y + n.h for n in layers[l]) if layers[l] else 0
                gap_bot = min(n.y for n in layers[l + 1]) if layers[l + 1] else gap_top + 40
                if gap_top < gap_bot:
                    base = (gap_top + gap_bot) // 2
                    candidates.append(base)
            if not candidates:
                candidates.append((sy + ty) // 2)
            # Spread edges across the gap with per-edge offset
            base = candidates[0]
            offset = used * 3
            my = base + offset

            for my_candidate in [base + i * 3 for i in range(len(candidates) * 2 + 1)]:
                if my_candidate == base + offset:
                    my = my_candidate
                    break
                hits, _ = self._segment_hits(sx, my_candidate, tx, my_candidate, obstacles)
                if not hits:
                    my = my_candidate
                    break

            if gap_used is not None:
                gap_used[gap_key] = used + 1

            e.route((sx, sy), (sx, my), (tx, my), (tx, ty))
        elif sl > tl:
            # Reverse: source below target — route upward
            sx, sy = e.source.cx, e.source.y
            tx, ty = e.target.cx, e.target.y + e.target.h
            gap_key = (tl, sl)
            if gap_used is not None and gap_key not in gap_used:
                gap_used[gap_key] = 0
            used = gap_used[gap_key] if gap_used is not None else 0

            candidates = []
            for l in range(tl, sl):
                gap_top = max(n.y + n.h for n in layers[l]) if layers[l] else 0
                gap_bot = min(n.y for n in layers[l + 1]) if layers[l + 1] else gap_top + 40
                if gap_top < gap_bot:
                    candidates.append((gap_top + gap_bot) // 2)
            if not candidates:
                candidates.append((sy + ty) // 2)
            base = candidates[0]
            my = base + used * 3
            if gap_used is not None:
                gap_used[gap_key] = used + 1
            e.route((sx, sy), (sx, my), (tx, my), (tx, ty))
        else:
            self._route_straight(e, layer_of)

    # ── special-node edge routing (Comment / View) ──

    def _route_special_edge(self, e):
        special = e.source if isinstance(e.source, (Comment, View)) else e.target
        other = e.target if isinstance(e.source, (Comment, View)) else e.source
        is_source_special = isinstance(e.source, (Comment, View))

        dx = other.cx - special.cx
        dy = other.cy - special.cy

        if abs(dx) >= abs(dy):
            if dx >= 0:
                sx, sy = special.x + special.w, special.cy
            else:
                sx, sy = special.x, special.cy
        else:
            if dy >= 0:
                sx, sy = special.cx, special.y + special.h
            else:
                sx, sy = special.cx, special.y

        if abs(dx) >= abs(dy):
            if dx >= 0:
                nx, ny = other.x, other.cy
            else:
                nx, ny = other.x + other.w, other.cy
        else:
            if dy >= 0:
                nx, ny = other.cx, other.y
            else:
                nx, ny = other.cx, other.y + other.h

        if is_source_special:
            e.route((sx, sy), (nx, ny))
        else:
            e.route((nx, ny), (sx, sy))

    # ── Sugiyama routing ──

    def _route_sugiyama(self, node_gap, margin):
        edge_list = [(e.source.name, e.target.name) for e in self.edges]
        node_sizes = {n.name: (n.w, n.h) for n in self.nodes}
        # Use layer_gap from our own layout attrs or default
        layer_spacing = getattr(self, '_layer_gap', 50)

        positions, routes, _ = sugiyama_layout(
            edge_list, node_sizes,
            node_gap=node_gap, margin=margin,
            layer_spacing=layer_spacing,
        )

        # Update node positions
        for n in self.nodes:
            if n.name in positions:
                n.x, n.y, n.w, n.h = positions[n.name]

        # Map routes back to edges (preserving order)
        route_map = {}
        for src, tgt, pts in routes:
            route_map[(src, tgt)] = pts
        for e in self.edges:
            key = (e.source.name, e.target.name)
            if key in route_map:
                e.waypoints = route_map[key]
            else:
                e.waypoints = [(e.source.cx, e.source.cy), (e.target.cx, e.target.cy)]

    # ── layout entry point ──

    def layout(self, routing='orthogonal', layer_gap=50, node_gap=12, margin=8):
        """Compute node positions and edge waypoints.

        After calling ``layout()``, nodes have ``.x``, ``.y``, ``.w``,
        ``.h`` set and edges have ``.waypoints`` populated.  The method
        is called automatically by ``render()`` and ``render_svg()``.

        Parameters
        ----------
        routing : {'straight', 'orthogonal', 'sugiyama'}
            Routing engine to use.
        layer_gap : int
            Vertical gap between layers (pixels).
        node_gap : int
            Horizontal gap between nodes in the same layer (pixels).
        margin : int
            Left/top margin (pixels).
        """
        self._layer_gap = layer_gap

        if routing == 'sugiyama':
            self._route_sugiyama(node_gap, margin)
            self._update_port_positions()
            return

        layers, layer_of = self._assign_layers()
        y = margin
        for lyr in layers:
            x = margin
            max_h = 0
            for n in lyr:
                n.x = x
                n.y = y
                x += n.w + node_gap
                max_h = max(max_h, n.h)
            y += max_h + layer_gap

        self._update_port_positions()

        # Place comments and views below the last layer of nodes
        extras = self.comments + self.views
        if extras:
            max_y = max((n.y + n.h for n in self.nodes), default=y)
            gap = layer_gap
            x = margin
            for item in extras:
                item.x = x
                item.y = max_y + gap
                x += item.w + node_gap

        gap_used = {}
        for e in self.edges:
            if isinstance(e.source, (Comment, View)) or isinstance(e.target, (Comment, View)):
                self._route_special_edge(e)
            elif routing == 'orthogonal':
                self._route_orthogonal(e, layer_of, layers, gap_used)
            else:
                self._route_straight(e, layer_of)

    def render(self, c=None, routing='orthogonal', layer_gap=50, node_gap=12, margin=8):
        if c is None:
            c = Canvas()
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()
        used_labels = set()
        for e in self.edges:
            if len(e.waypoints) >= 2:
                draw_polyline(c, e.waypoints,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label,
                              used_labels=used_labels)
            else:
                draw_relation(c, e.source.cx, e.source.cy, e.target.cx, e.target.cy,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label)
        for n in self.nodes:
            draw_class_box(c, n.x, n.y, n.x + n.w, n.y + n.h, n.name, n.stereotypes, n.attributes)
            for p in n.ports:
                draw_port_box(c, p.x, p.y, p.label, side=p.side, direction=p.direction)
        for com in self.comments:
            draw_comment_box(c, com.x, com.y, com.x + com.w, com.y + com.h, com.text)
        for v in self.views:
            draw_view_box(c, v.x, v.y, v.x + v.w, v.y + v.h, v.name, v.stereotypes, v.attributes)
        return c.frame()

    def render_svg(self, routing='orthogonal', layer_gap=50, node_gap=12, margin=8, scale=1.5):
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()

        # Compute bounds
        xs = [margin]
        ys = [margin]
        for n in self.nodes:
            xs.extend([n.x, n.x + n.w])
            ys.extend([n.y, n.y + n.h])
            for p in n.ports:
                xs.extend([p.x, p.x + p.w])
                ys.extend([p.y, p.y + p.h])
        for com in self.comments:
            xs.extend([com.x, com.x + com.w])
            ys.extend([com.y, com.y + com.h])
        for v in self.views:
            xs.extend([v.x, v.x + v.w])
            ys.extend([v.y, v.y + v.h])
        for e in self.edges:
            for px, py in e.waypoints:
                xs.append(px)
                ys.append(py)

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad = 10
        w = int((max_x - min_x + pad * 2) * scale)
        h = int((max_y - min_y + pad * 2) * scale)

        c = SvgCanvas(scale=scale)
        for e in self.edges:
            svg_draw_edge(c, e)
        for n in self.nodes:
            svg_draw_node(c, n)
            for p in n.ports:
                svg_draw_port(c, p)
        for com in self.comments:
            svg_draw_comment(c, com)
        for v in self.views:
            svg_draw_view(c, v)
        return c.output(width=w, height=h, padding=pad * scale)
