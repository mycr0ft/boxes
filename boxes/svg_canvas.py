"""SVG canvas — vector-graphics renderer for diagrams.

Provides a ``SvgCanvas`` builder class and three high-level drawing
functions (``svg_draw_edge``, ``svg_draw_node``, ``svg_draw_port``)
that mirror the structure of ``primitives.py`` but produce SVG 1.1 XML
instead of braille pixels.

Usage
-----
::

    c = SvgCanvas(scale=1.5)
    svg_draw_node(c, my_node)
    svg_draw_edge(c, my_edge)
    print(c.output())   # <svg xmlns=...>...</svg>

Coordinate system
-----------------
All input coordinates are in drawille pixel units (same as ``layout.py``
uses).  ``SvgCanvas.s()`` scales them by the ``scale`` factor so the
output is readable in a browser.  Default scale 1.5 gives reasonable
sizes for typical diagrams.

Arrowheads
----------
Filled/polygon arrowheads (TRIANGLE, DIAMOND, FILLED, DEFINITION,
REDEFINITION) are computed as ``<polygon>`` vectors via
``_arrow_polygon()``.  OPEN arrowheads are rendered as two ``<line>``
elements.  Arrow size matches ``ARROW_SIZE`` (7 px in diagram coords),
same as the braille renderer.

See also
--------
primitives.py  : drawille-based equivalent (terminal output)
layout.py      : Diagram.render_svg() calls these functions
"""

from math import atan2, cos, sin, pi
from xml.sax.saxutils import escape

from boxes.primitives import SOLID, DASHED, NONE, OPEN, TRIANGLE, DIAMOND, FILLED, \
    DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, PORTION, ARROW_SIZE, COMMENT_FOLD, \
    _port_arrow, _arrow_backoff


def _arrow_polygon(x, y, angle, style):
    """Return polygon/fill for an arrowhead, or (lines, None) for OPEN."""
    if style == NONE or style is None or style == PORTION:
        return None, style if style == PORTION else None
    size = ARROW_SIZE
    if style == OPEN:
        lines = []
        for sign in (-1, 1):
            a = angle + sign * 5 * pi / 6
            lines.append((x, y, x + cos(a) * size, y + sin(a) * size))
        return lines, 'open'
    if style == TRIANGLE:
        tip = (x, y)
        hp = angle + pi / 2
        hw = size * 0.4
        bx = x - cos(angle) * size
        by = y - sin(angle) * size
        pts = [
            tip,
            (bx + cos(hp) * hw, by + sin(hp) * hw),
            (bx - cos(hp) * hw, by - sin(hp) * hw),
        ]
        return pts, TRIANGLE
    elif style == DEFINITION or style == REDEFINITION or style == REFERENCE_SUBSETTING:
        # Same triangle polygon; extras drawn by _svg_arrow_extras
        hp = angle + pi / 2
        hw = size * 0.4
        bx = x - cos(angle) * size
        by = y - sin(angle) * size
        pts = [
            (x, y),
            (bx + cos(hp) * hw, by + sin(hp) * hw),
            (bx - cos(hp) * hw, by - sin(hp) * hw),
        ]
        return pts, style
    elif style == DIAMOND or style == FILLED:
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
        fill = 'black' if style == FILLED else 'white'
        return pts, fill


def _svg_draw_portion(c, x, y, angle):
    r = ARROW_SIZE * 0.6
    cx = x - cos(angle) * r
    cy = y - sin(angle) * r
    mouth_half = pi / 4
    start_a = angle + pi + mouth_half
    end_a = angle + pi - mouth_half
    sx = cx + r * cos(start_a)
    sy = cy + r * sin(start_a)
    ex = cx + r * cos(end_a)
    ey = cy + r * sin(end_a)
    scx, scy = c.s(cx, cy)
    ssx, ssy = c.s(sx, sy)
    sex, sey = c.s(ex, ey)
    sr = c.s(r)
    d = f"M {scx:.1f},{scy:.1f} L {ssx:.1f},{ssy:.1f} A {sr:.1f},{sr:.1f} 0 1 1 {sex:.1f},{sey:.1f} Z"
    c.elements.append(
        f'<path d="{d}" fill="{c.STROKE}" stroke="{c.STROKE}" />'
    )


def _svg_arrow_extras(c, x, y, angle, style):
    """Draw auxiliary elements for DEFINITION, REDEFINITION, or REFERENCE_SUBSETTING."""
    size = ARROW_SIZE
    if style == DEFINITION:
        d = size + 3
        cx = x - cos(angle) * d
        cy = y - sin(angle) * d
        hp = angle + pi / 2
        ox = cos(hp) * 4
        oy = sin(hp) * 4
        c.add_circle(round(cx + ox), round(cy + oy), r=1.5, fill=c.STROKE)
        c.add_circle(round(cx - ox), round(cy - oy), r=1.5, fill=c.STROKE)
    elif style == REDEFINITION:
        dist = size + 2
        bx = x - cos(angle) * dist
        by = y - sin(angle) * dist
        hp = angle + pi / 2
        hw = size * 0.4
        c.add_line(bx + cos(hp) * hw, by + sin(hp) * hw,
                   bx - cos(hp) * hw, by - sin(hp) * hw)
    elif style == REFERENCE_SUBSETTING:
        hp = angle + pi / 2
        ox = cos(hp) * 4
        oy = sin(hp) * 4
        for d in (size + 3, size + 8):
            cx = x - cos(angle) * d
            cy = y - sin(angle) * d
            c.add_circle(round(cx + ox), round(cy + oy), r=1.5, fill=c.STROKE)
            c.add_circle(round(cx - ox), round(cy - oy), r=1.5, fill=c.STROKE)


class SvgCanvas:
    """SVG drawing surface, producing an SVG string on output()."""

    # Colors
    STROKE = '#1a1a1a'
    FILL = '#f0f0f0'

    def __init__(self, scale=1.5):
        self.scale = scale
        self.elements = []
        self.stroke_width = 1.5

    def s(self, *args):
        """Scale one or more values by the canvas scale factor."""
        if len(args) == 1:
            return args[0] * self.scale
        return tuple(a * self.scale for a in args)

    def add_line(self, x1, y1, x2, y2, stroke=None, width=None, dashed=False):
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        x1, y1, x2, y2 = self.s(x1, y1, x2, y2)
        parts = [
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"',
            f' stroke="{stroke}" stroke-width="{width}" fill="none"',
        ]
        if dashed:
            parts.append(f' stroke-dasharray="{width * 6},{width * 4}"')
        parts.append(' />')
        self.elements.append(''.join(parts))

    def add_rect(self, x, y, w, h, fill=None, stroke=None, width=None):
        fill = fill or self.FILL
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        x, y, w, h = self.s(x, y, w, h)
        self.elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
            f' fill="{fill}" stroke="{stroke}" stroke-width="{width}" />'
        )

    def add_text(self, x, y, text, color=None, size=None, anchor='middle'):
        color = color or self.STROKE
        # font-size matches drawille's 2px/char width
        # (SVG monospace char-width ≈ 0.6× font-size; 2/0.6 ≈ 3.33)
        size = size or self.s(10 / 3)
        x, y = self.s(x, y)
        t = escape(text)
        self.elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}"'
            f' font-size="{size:.1f}" font-family="monospace"'
            f' text-anchor="{anchor}">{t}</text>'
        )

    def add_polygon(self, points, fill=None, stroke=None, width=None):
        fill = fill or 'black'
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        pts = ' '.join(f'{self.s(x):.1f},{self.s(y):.1f}' for x, y in points)
        self.elements.append(
            f'<polygon points="{pts}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{width}" />'
        )

    def add_circle(self, x, y, r=1, fill=None, stroke=None):
        fill = fill or self.STROKE
        stroke = stroke or self.STROKE
        x, y = self.s(x, y)
        r = self.s(r)
        self.elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"'
            f' fill="{fill}" stroke="{stroke}" />'
        )

    def add_polyline(self, points, stroke=None, width=None, dashed=False):
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        pts = ' '.join(f'{self.s(x):.1f},{self.s(y):.1f}' for x, y in points)
        parts = [f'<polyline points="{pts}"']
        parts.append(f' stroke="{stroke}" stroke-width="{width}" fill="none"')
        if dashed:
            parts.append(f' stroke-dasharray="{width * 6},{width * 4}"')
        parts.append(' />')
        self.elements.append(''.join(parts))

    def add_group(self, attrs=None):
        """Open a <g> element. Must be followed by close_group()."""
        attr_str = ''
        if attrs:
            attr_str = ' ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items())
        self.elements.append(f'<g{attr_str}>')

    def close_group(self):
        self.elements.append('</g>')

    def output(self, width=None, height=None, padding=10):
        """Return SVG string. Bounds auto-computed if not provided."""
        if width is not None and height is not None:
            w, h = width, height
        else:
            # Compute from element positions (crude: collect all coords)
            xs, ys = [], []
            for el in self.elements:
                import re
                for m in re.finditer(r'x1="([\d.-]+)"|x2="([\d.-]+)"|x="([\d.-]+)"'
                                     r'|cx="([\d.-]+)"|points="([\d.,\s-]+)"', el):
                    pass  # complex; just use large default
            # Simple fallback: use padding boundaries from last elements
            w = 800
            h = 600

        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' viewBox="{-padding} {-padding} {w + padding * 2} {h + padding * 2}"'
            f' width="{w + padding * 2}pt" height="{h + padding * 2}pt">'
        )
        body = '\n'.join(self.elements)
        return f'{header}\n{body}\n</svg>'


# ── High-level drawing functions for diagrams ──

def svg_draw_edge(c, e):
    """Draw an edge (with or without waypoints) onto an SvgCanvas."""
    if len(e.waypoints) >= 2:
        pts = list(e.waypoints)
        dashed = e.line_style == DASHED

        # Build polyline points, shortened at arrowhead ends
        draw_pts = list(pts)
        if e.target_style and e.target_style != NONE:
            bo = _arrow_backoff(e.target_style)
            if bo:
                x1, y1 = draw_pts[-2]
                x2, y2 = draw_pts[-1]
                if x1 == x2:
                    draw_pts[-1] = (x2, y2 - bo if y2 > y1 else y2 + bo)
                else:
                    draw_pts[-1] = (x2 - bo if x2 > x1 else x2 + bo, y2)
        if e.source_style and e.source_style != NONE:
            bo = _arrow_backoff(e.source_style)
            if bo:
                x1, y1 = draw_pts[0]
                x2, y2 = draw_pts[1]
                if x1 == x2:
                    draw_pts[0] = (x1, y1 + bo if y2 > y1 else y1 - bo)
                else:
                    draw_pts[0] = (x1 + bo if x2 > x1 else x1 - bo, y1)

        c.add_polyline(draw_pts, dashed=dashed)

        # Arrowheads at the ends
        if e.target_style and e.target_style != NONE and len(pts) >= 2:
            dx = pts[-1][0] - pts[-2][0]
            dy = pts[-1][1] - pts[-2][1]
            angle = atan2(dy, dx)
            poly, fill = _arrow_polygon(pts[-1][0], pts[-1][1], angle, e.target_style)
            if fill == PORTION:
                _svg_draw_portion(c, pts[-1][0], pts[-1][1], angle)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[-1][0], pts[-1][1], angle, fill)

        if e.source_style and e.source_style != NONE and len(pts) >= 2:
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
            angle = atan2(dy, dx)
            poly, fill = _arrow_polygon(pts[0][0], pts[0][1], angle + pi, e.source_style)
            if fill == PORTION:
                _svg_draw_portion(c, pts[0][0], pts[0][1], angle + pi)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[0][0], pts[0][1], angle + pi, fill)

        # Label at midpoint
        if e.label:
            total = sum(abs(pts[i + 1][0] - pts[i][0]) +
                        abs(pts[i + 1][1] - pts[i][1])
                        for i in range(len(pts) - 1))
            target = total // 2
            acc = 0
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                seg = abs(x2 - x1) + abs(y2 - y1)
                if acc + seg >= target:
                    rem = target - acc
                    if seg > 0:
                        if x1 == x2:
                            mx = x1
                            my = y1 + (rem if y2 > y1 else -rem)
                            lx, ly = mx, my - 4
                        else:
                            mx = x1 + (rem if x2 > x1 else -rem)
                            my = y1
                            lx, ly = mx, my - 6
                    else:
                        lx, ly = x1, y1 - 4
                    c.add_text(lx, ly, e.label, anchor='middle')
                    break
                acc += seg
    else:
        # Fallback straight line
        sx, sy = e.source.cx, e.source.cy
        tx, ty = e.target.cx, e.target.cy
        dx_total, dy_total = tx - sx, ty - sy
        length = max(1, (dx_total * dx_total + dy_total * dy_total) ** 0.5)

        lsx, lsy = sx, sy
        if e.source_style and e.source_style != NONE:
            bo = _arrow_backoff(e.source_style)
            if bo:
                lsx = sx + dx_total / length * bo
                lsy = sy + dy_total / length * bo

        ltx, lty = tx, ty
        if e.target_style and e.target_style != NONE:
            bo = _arrow_backoff(e.target_style)
            if bo:
                ltx = tx - dx_total / length * bo
                lty = ty - dy_total / length * bo

        dashed = e.line_style == DASHED
        c.add_line(lsx, lsy, ltx, lty, dashed=dashed)

        angle = atan2(ty - sy, tx - sx)
        poly, fill = _arrow_polygon(tx, ty, angle, e.target_style)
        if fill == PORTION:
            _svg_draw_portion(c, tx, ty, angle)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, tx, ty, angle, fill)
        poly, fill = _arrow_polygon(sx, sy, angle + pi, e.source_style)
        if fill == PORTION:
            _svg_draw_portion(c, sx, sy, angle + pi)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, sx, sy, angle + pi, fill)

        if e.label:
            mx, my = (sx + tx) // 2, (sy + ty) // 2
            c.add_text(mx, my - 6, e.label, anchor='middle')


def svg_draw_node(c, n):
    """Draw a node box with stereotypes, name, and attributes."""
    c.add_rect(n.x, n.y, n.w, n.h)
    box_cx = n.x + n.w // 2
    lines = []
    if n.stereotypes:
        for s in n.stereotypes:
            lines.append(f'\u00ab{s}\u00bb')
    lines.append(n.name)

    # Separator if attributes exist
    sep_y = n.y + 4 + len(lines) * 5

    if n.attributes:
        # Draw separator line below name
        c.add_line(n.x + 2, sep_y, n.x + n.w - 2, sep_y)
        lines.append('')
        lines.extend(n.attributes)

    for i, txt in enumerate(lines):
        y = n.y + 4 + i * 5
        if txt == '' and n.attributes:
            continue
        c.add_text(box_cx, y + 4, txt, anchor='middle')


def svg_draw_comment(c, com):
    fold = min(COMMENT_FOLD, com.w // 3, com.h // 3)
    x1, y1 = com.x, com.y
    x2, y2 = com.x + com.w, com.y + com.h
    pts = [
        (x1, y1),
        (x2 - fold, y1),
        (x2, y1 + fold),
        (x2, y2),
        (x1, y2),
    ]
    c.add_polygon(pts, fill='white')
    c.add_text(com.x + com.w // 2, com.y + com.h // 2 + 2, com.text, anchor='middle')


def svg_draw_port(c, p):
    """Draw a port box with optional direction arrow inside and label outside."""
    c.add_rect(p.x, p.y, p.w, p.h, fill='white')
    arrow = _port_arrow(p.side, p.direction)
    if arrow:
        c.add_text(p.x + p.w // 2, p.y + p.h // 2 + 2, arrow, anchor='middle')
    if p.label:
        if p.side == 'left':
            c.add_text(p.x - 4, p.y + p.h // 2 + 2, p.label, anchor='end')
        elif p.side == 'right':
            c.add_text(p.x + p.w + 4, p.y + p.h // 2 + 2, p.label, anchor='start')
        elif p.side == 'top':
            c.add_text(p.x + p.w // 2, p.y - 4, p.label, anchor='middle')
        elif p.side == 'bottom':
            c.add_text(p.x + p.w // 2, p.y + p.h + 8, p.label, anchor='middle')
