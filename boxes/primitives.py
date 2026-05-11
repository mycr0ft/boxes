"""Terminal rendering primitives — drawille braille output.

All drawing functions in this module take a ``drawille.Canvas`` and draw
directly to its pixel grid using Bresenham line iteration.  Coordinate
system: drawille pixel units (1 braille char = 2×4 px).  Text is placed
via ``set_text(pixel_x, pixel_y, text)`` which converts to character
rows/columns via ``x // 2, y // 4``.

Arrowhead styles:  OPEN (>), TRIANGLE (triangle), DIAMOND (diamond),
FILLED (filled diamond).  Line styles: SOLID, DASHED.

Label collision avoidance in ``draw_polyline`` uses a spiral offset
search against a ``used_labels`` shared set.

See also
--------
svg_canvas.py : equivalent SVG vector renderer
layout.py     : Diagram / Node / Edge classes that call these primitives
"""

from math import atan2, cos, sin, pi
from drawille import Canvas, line

# ── constants ──
NONE = 'none'
OPEN = 'open'
TRIANGLE = 'triangle'
DIAMOND = 'diamond'
FILLED = 'filled'
SOLID = 'solid'
DASHED = 'dashed'

ARROW_SIZE = 7


# ── arrowhead drawing ──

def _draw_open(c, x, y, angle, size):
    for sign in (-1, 1):
        a = angle + sign * 5 * pi / 6
        for px, py in line(x, y, x + cos(a) * size, y + sin(a) * size):
            c.set(px, py)


def _draw_triangle(c, x, y, angle, size):
    hp = angle + pi / 2
    hw = size * 0.4
    bx = x - cos(angle) * size
    by = y - sin(angle) * size
    for px, py in line(x, y, bx + cos(hp) * hw, by + sin(hp) * hw): c.set(px, py)
    for px, py in line(x, y, bx - cos(hp) * hw, by - sin(hp) * hw): c.set(px, py)
    for px, py in line(bx + cos(hp) * hw, by + sin(hp) * hw, bx - cos(hp) * hw, by - sin(hp) * hw): c.set(px, py)


def _draw_diamond(c, x, y, angle, size, fill=False):
    s = size * 0.7
    hp = angle + pi / 2
    hw = s * 0.5
    pts = [
        (x, y),                                           # tip
        (x - cos(angle) * s + cos(hp) * hw,
         y - sin(angle) * s + sin(hp) * hw),             # right wing
        (x - 2 * cos(angle) * s,
         y - 2 * sin(angle) * s),                         # back
        (x - cos(angle) * s - cos(hp) * hw,
         y - sin(angle) * s - sin(hp) * hw),             # left wing
    ]
    for i in range(4):
        for px, py in line(*pts[i], *pts[(i + 1) % 4]): c.set(px, py)
    if fill:
        xs = [int(p[0]) for p in pts]
        ys = [int(p[1]) for p in pts]
        for fx in range(min(xs), max(xs) + 1):
            for fy in range(min(ys), max(ys) + 1):
                inside = False
                j = 3
                for i in range(4):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if ((yi > fy) != (yj > fy)) and fx < (xj - xi) * (fy - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
                if inside:
                    c.set(fx, fy)


_ARROW_DRAWERS = {
    OPEN: _draw_open,
    TRIANGLE: _draw_triangle,
    DIAMOND: lambda c, x, y, a, s: _draw_diamond(c, x, y, a, s, False),
    FILLED: lambda c, x, y, a, s: _draw_diamond(c, x, y, a, s, True),
}


# ── line drawing ──

def draw_line(c, x1, y1, x2, y2, style=SOLID):
    """Draw a single line segment on a drawille Canvas.

    Parameters
    ----------
    c : drawille.Canvas
        Target canvas.
    x1, y1, x2, y2 : int
        Endpoint coordinates (pixel units).
    style : {'solid', 'dashed'}
        ``SOLID`` draws every pixel.  ``DASHED`` draws 5 of every 8 pixels.
    """
    if style == DASHED:
        pts = list(line(x1, y1, x2, y2))
        for i, (px, py) in enumerate(pts):
            if i % 8 < 5:
                c.set(px, py)
    else:
        for px, py in line(x1, y1, x2, y2):
            c.set(px, py)


def draw_arrowhead(c, x, y, angle, style):
    """Draw an arrowhead at position (x, y) pointing in the given direction.

    Parameters
    ----------
    c : drawille.Canvas
    x, y : int
        Tip position (pixels).
    angle : float
        Direction angle in radians.
    style : str or None
        Arrowhead style: ``OPEN``, ``TRIANGLE``, ``DIAMOND``, ``FILLED``,
        ``NONE``, or ``None`` (no arrowhead drawn).
    """
    if style and style in _ARROW_DRAWERS:
        _ARROW_DRAWERS[style](c, x, y, angle, ARROW_SIZE)


# ── straight-line relation (one segment) ──

def draw_relation(c, x1, y1, x2, y2, line_style=SOLID, source=None, target=None, label=None):
    """Draw a straight-line relation with optional arrowheads and label.

    Parameters
    ----------
    c : drawille.Canvas
    x1, y1, x2, y2 : int
        Endpoint coordinates.
    line_style : {'solid', 'dashed'}
    source, target : str or None
        Arrowhead styles at each end.
    label : str or None
        Text placed perpendicular to the line at its midpoint.
    """
    draw_line(c, x1, y1, x2, y2, line_style)
    angle = atan2(y2 - y1, x2 - x1)
    draw_arrowhead(c, x2, y2, angle, target)
    draw_arrowhead(c, x1, y1, angle + pi, source)
    if label:
        mx = (x1 + x2) // 2
        my = (y1 + y2) // 2
        dx, dy = x2 - x1, y2 - y1
        length = max(abs(dx), abs(dy))
        if length > 0:
            perp_x = -dy / length
            perp_y = dx / length
            lx = int(mx + perp_x * 8)
            ly = int(my + perp_y * 8)
            c.set_text(lx, ly, label)


# ── multi-segment (orthogonal) polyline ──

def draw_polyline(c, points, line_style=SOLID, source=None, target=None, label=None,
                  used_labels=None):
    """Draw an orthogonal polyline through waypoints with arrowheads.

    used_labels : set of (x, y) tuples — occupied label positions to avoid.
    """
    for i in range(len(points) - 1):
        draw_line(c, *points[i], *points[i + 1], line_style)

    # target arrowhead on last segment
    if target and len(points) >= 2:
        dx = points[-1][0] - points[-2][0]
        dy = points[-1][1] - points[-2][1]
        draw_arrowhead(c, points[-1][0], points[-1][1], atan2(dy, dx), target)

    # source arrowhead on first segment
    if source and len(points) >= 2:
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
        draw_arrowhead(c, points[0][0], points[0][1], atan2(dy, dx) + pi, source)

    # label at Manhattan midpoint
    if label and len(points) >= 2:
        total = sum(abs(points[i + 1][0] - points[i][0]) +
                    abs(points[i + 1][1] - points[i][1])
                    for i in range(len(points) - 1))
        target_dist = total // 2
        acc = 0
        label_pos = None
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            seg_len = abs(x2 - x1) + abs(y2 - y1)
            if acc + seg_len >= target_dist:
                rem = target_dist - acc
                if seg_len > 0:
                    if x1 == x2:  # vertical → offset right
                        mx = x1
                        my = y1 + (rem if y2 > y1 else -rem)
                        lx, ly = mx + 6, my - 2
                    else:  # horizontal → offset below
                        mx = x1 + (rem if x2 > x1 else -rem)
                        my = y1
                        lx, ly = mx, my + 6
                else:
                    lx, ly = x1 + 6, y1
                label_pos = (lx, ly)
                break
            acc += seg_len

        if label_pos:
            lx, ly = label_pos
            # Collision avoidance: try offsets if position is taken
            if used_labels is not None:
                offsets = [(0, 0), (0, 12), (12, 0), (0, -8), (-12, 0),
                           (0, 20), (20, 0), (-20, 0), (0, -16)]
                for ox, oy in offsets:
                    pos = (lx + ox, ly + oy)
                    if not any(abs(pos[0] - p[0]) < 10 and abs(pos[1] - p[1]) < 5
                               for p in used_labels):
                        lx, ly = pos
                        used_labels.add(pos)
                        break
                else:
                    used_labels.add((lx, ly))
            c.set_text(lx, ly, label)


# ── port box ──

PORT_W = 8
PORT_H = 12

def _port_arrow(side, direction):
    """Return the Unicode arrow character for a port, or ``None`` for no arrow.

    Parameters
    ----------
    side : {'left', 'right', 'top', 'bottom'}
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward the node interior.
        ``'out'`` → arrow points away from the node.
        ``'inout'`` → double-headed arrow (bidirectional).
        ``None``  → no arrow drawn.
    """
    if direction is None:
        return None
    arrows = dict(
        in_left='\u2192', in_right='\u2190', in_top='\u2193', in_bottom='\u2191',
        out_left='\u2190', out_right='\u2192', out_top='\u2191', out_bottom='\u2193',
        inout_left='\u2194', inout_right='\u2194', inout_top='\u2195', inout_bottom='\u2195',
    )
    return arrows.get(f'{direction}_{side}')


def draw_port_box(c, x, y, label=None, side='left', direction=None):
    """Draw a small port box (8×12 px) with optional direction arrow inside and label outside.

    Parameters
    ----------
    c : drawille.Canvas
    x, y : int
        Top-left corner of the port box.
    label : str or None
        Text placed outside the port (away from the node).
    side : {'left', 'right', 'top', 'bottom'}
        Which side of the node the port is on — determines where the
        external label is placed.
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward the node interior (e.g. input port).
        ``'out'`` → arrow points away from the node (e.g. output port).
        ``'inout'`` → bidirectional (double-headed arrow).
        ``None``  → no arrow drawn (default).
    """
    x1, y1, x2, y2 = x, y, x + PORT_W, y + PORT_H
    for rx, ry in line(x1, y1, x2, y1): c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2): c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)

    arrow = _port_arrow(side, direction)
    if arrow:
        c.set_text(x + 3, y + 4, arrow)

    if label:
        ly = y + 4
        if side == 'left':
            c.set_text(x - len(label) * 2 - 2, ly, label)
        elif side == 'right':
            c.set_text(x + PORT_W + 2, ly, label)
        elif side == 'top':
            c.set_text(x + PORT_W // 2 - len(label), y - 4, label)
        elif side == 'bottom':
            c.set_text(x + PORT_W // 2 - len(label), y + PORT_H + 1, label)


# ── box ──

def draw_class_box(c, x1, y1, x2, y2, name, stereotypes=None, attributes=None):
    """Draw a rectangular classifier box with centered text.

    The box has four borders. Inside it renders (top to bottom):
    1. Stereotypes (if any), each in guillemets
    2. The node name
    3. A separator line (if attributes are present)
    4. Attribute/method lines (if any)

    Parameters
    ----------
    c : drawille.Canvas
    x1, y1, x2, y2 : int
        Bounding box corners (pixels).
    name : str
        Primary label.
    stereotypes : list of str, optional
    attributes : list of str, optional
    """
    for rx, ry in line(x1, y1, x2, y1): c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2): c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)
    box_cx = (x1 + x2) // 2
    lines = []
    if stereotypes:
        for s in stereotypes:
            lines.append(f'\u00ab{s}\u00bb')
    lines.append(name)
    if attributes:
        lines.append('')
        lines.extend(attributes)
    for i, txt in enumerate(lines):
        y = y1 + 4 + i * 5
        if txt == '' and attributes:
            for rx, ry in line(x1 + 2, y, x2 - 2, y): c.set(rx, ry)
        else:
            x = box_cx - len(txt)
            c.set_text(x, y, txt)
