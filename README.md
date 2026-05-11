# boxes — UML/SysML block diagrams in your terminal (and SVG)

**boxes** is a pure-Python library for rendering UML/SysML-like block diagrams
using Unicode braille characters (via [drawille](https://github.com/asciimoo/drawille))
or as SVG. It supports four routing engines, ports as small boundary boxes, node
attributes, multiple arrowhead styles, and label collision avoidance.

## Installation

```bash
git clone <this-repo>
cd boxes
poetry install
```

This creates a virtualenv and installs `drawille` (the only Python dependency).
Run scripts with `poetry run` (no `PYTHONPATH` needed):

```bash
poetry run python demo.py
poetry run python stress_test.py
```

**Note:** `boxes` is installed in editable mode, so any changes to the source
are picked up automatically.

### Optional: ELKjs integration

For professional-quality orthogonal routing via the Eclipse Layout Kernel:

```bash
npm install elkjs
```

Then use `routing='elk'` (see §Routing Engines below).

## Tutorial

### 1. Your first diagram

```python
from boxes import Diagram, OPEN, FILLED

d = Diagram()
vehicle = d.add_node('Vehicle', ['block'])
engine  = d.add_node('Engine',  ['part'])
wheel   = d.add_node('Wheel',   ['part'])

d.add_edge(vehicle, engine, source_style=FILLED, target_style=OPEN,
           label='composed of')
d.add_edge(vehicle, wheel,  source_style=FILLED, target_style=OPEN,
           label='composed of')

print(d.render())  # terminal output
```

The `render()` method layouts the diagram and returns a string of Unicode braille
characters. Print it to see the diagram in your terminal.

### 2. Nodes

A `Node` has a **name**, optional **stereotypes** (shown as «stereotype» above the
name), and optional **attributes** (shown below a separator line).

```python
from boxes import Diagram

d = Diagram()

sensor = d.add_node('TemperatureSensor', ['block'],
    attributes=['+ id : int', '+ value : float', '- threshold : float'])
```

The node width auto-sizes to the longest text. Stereotypes are wrapped in
guillemets (`\u00ab...\u00bb`).

### 3. Edges

An `Edge` connects two nodes, with optional arrowheads at each end and an
optional label.

```python
from boxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

d.add_edge(source, target)                                # default: open arrow at target
d.add_edge(source, target, source_style=FILLED,            # filled diamond at source
            target_style=TRIANGLE, label='generalizes')    # triangle at target
d.add_edge(source, target, line_style=DASHED)              # dashed line
```

#### Available arrowhead styles

| Constant | Shape | Usage |
|----------|-------|-------|
| `NONE` | (none) | Plain line end |
| `OPEN` | `>` | Default target arrow, composition |
| `TRIANGLE` | `△` | Generalization / inheritance |
| `DIAMOND` | `◇` | Aggregation (unfilled) |
| `FILLED` | `◆` | Composition (filled) |

#### Line styles

| Constant | Appearance |
|----------|-----------|
| `SOLID` | ─── continuous line |
| `DASHED` | ╌╌ dashed line |

### 4. Ports

Ports are small boxes on a node's boundary, used in UML/SysML for structured
connectors and proxy ports.

```python
sensor = d.add_node('SensorCluster', ['block'])
actuator = d.add_node('ActuatorDriver', ['block'])

out_port = sensor.add_port('out', side='right')   # auto-distributed
in_port  = actuator.add_port('in', side='left')

d.add_edge(sensor, actuator, source_port=out_port, target_port=in_port,
           target_style=OPEN, label='data')
```

**Auto-distribution:** when `offset=None` (the default), ports on the same side
are automatically spaced evenly with a minimum gap of 8 px. This makes it easy
to add multiple ports:

```python
hub = d.add_node('Hub')
# 3 ports on the left, 2 on the right — all evenly spaced
hub.add_port('L1', side='left')
hub.add_port('L2', side='left')
hub.add_port('L3', side='left')
hub.add_port('R1', side='right')
hub.add_port('R2', side='right')
```

For precise positioning, pass an explicit `offset` (0.0–1.0, proportion along
the side):

```python
port = node.add_port('out', side='right', offset=0.25)  # 25% from top
```

Port-to-port edges use L-shaped (2-segment) routing.

### 5. Rendering to SVG

```python
svg = d.render_svg(routing='orthogonal', node_gap=60)
with open('/tmp/diagram.svg', 'w') as f:
    f.write(svg)
```

The SVG uses vector lines, polygons for arrowheads, and `<text>` elements.
Open the result in any browser or vector-editing tool. The `scale` parameter
(default 1.5) controls the output size.

### 6. Full workflow example

```python
from boxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

d = Diagram()

# Layer 0
ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])

# Layer 1
sensor   = d.add_node('SensorCluster', ['block'])
actuator = d.add_node('ActuatorDriver', ['block'],
    attributes=['+ apply()'])
display  = d.add_node('DisplayUnit', ['block'])

# Ports
sns_out  = sensor.add_port('out', side='right', offset=0.3)
act_in   = actuator.add_port('in', side='left', offset=0.3)
act_out  = actuator.add_port('out', side='right', offset=0.5)
disp_in  = display.add_port('in', side='left', offset=0.5)

# Traditional top-down edges
d.add_edge(ecu, sensor,   source_style=FILLED, target_style=OPEN, label='reads')
d.add_edge(ecu, actuator, source_style=FILLED, target_style=OPEN, label='commands')
d.add_edge(ecu, display,  source_style=FILLED, target_style=OPEN, label='updates')

# Lateral port-to-port edges
d.add_edge(sensor, actuator, source_port=sns_out, target_port=act_in,
           target_style=OPEN, label='data')
d.add_edge(actuator, display, source_port=act_out, target_port=disp_in,
           target_style=OPEN, label='output')

# Terminal output
print(d.render(routing='orthogonal', node_gap=60))

# SVG output
svg = d.render_svg(routing='orthogonal', node_gap=60)
with open('/tmp/diagram.svg', 'w') as f:
    f.write(svg)
```

---

## Routing Engines

boxes provides four routing engines, selectable via the `routing` parameter:

```python
d.render(routing='orthogonal')    # or 'straight', 'sugiyama', 'elk'
d.render_svg(routing='sugiyama')
```

### `straight`

**File:** `layout.py:Drawing._route_straight()` (line 99)

Center-to-center straight lines. For adjacent layers, ports are distributed
evenly along the node boundary using `_distribute_ports()`. For non-adjacent
layers or same-layer edges, falls back to direct center-to-center diagonals.

Best for: quick sketches, small diagrams (≤10 edges).

### `orthogonal` (homegrown)

**File:** `layout.py:Drawing._route_orthogonal()` (line 191)

Three-segment Manhattan paths (down → across → down) with:
- **Distributed boundary ports** via `_get_port()` / `_distribute_ports()`
- **Gap y-level candidates** between layers, tested for obstacle intersection
  via `_segment_hits()`
- **Edge-edge avoidance** via `gap_used` counter — each edge sharing a gap
  gets a 3 px vertical offset
- **Reverse-edge handling** (source below target) — routes upward from the
  source's top port to the target's bottom port
- **Port-to-port routing** via `_port_route()` — L-shaped (2-segment) paths
  for edges with explicit `source_port`/`target_port`

Best for: medium diagrams (10–30 edges), SysML block diagrams, UML
composite structure.

### `sugiyama` (pure-Python)

**File:** `sugiyama.py` (410 lines)

Full 5-stage Sugiyama framework:

| Stage | Function | Lines | Description |
|-------|----------|-------|-------------|
| 1. Cycle removal | `remove_cycles()` | ~40 | Greedy DFS: reverses back-edges |
| 2. Layer assignment | `assign_layers()` | ~50 | Longest-path from roots to sinks |
| 3. Crossing minimization | `minimize_crossings()` | ~120 | Barycenter layer sweep (forward + backward, up to 24 passes) |
| 4. Node positioning | `position_nodes()` | ~80 | X/Y assignment within layers, centered |
| 5. Edge routing | `route_edges()` | ~200 | Orthogonal with obstacle avoidance |

**Key properties:**
- Correctly handles non-adjacent edges (unlike the homegrown `orthogonal`
  which uses BFS-shortest-path layering)
- Crossing minimization can get stuck in local minima
- Does not support ports (they are ignored in Sugiyama mode)

Best for: directed graphs, flow charts, diagrams with non-adjacent
edges.

### `elk` (ELKjs subprocess)

**File:** `elk.py` (211 lines)

Bridges to the [Eclipse Layout Kernel](https://www.eclipse.org/elk/) via a
Node.js subprocess. The pipeline:

1. `to_elk_json()` — converts Diagram → ELK JSON graph format with
   `elk.algorithm: layered`, `elk.edgeRouting: ORTHOGONAL`, port constraints,
   and label placement options
2. `elk_layout()` — spawns `node -e`, pipes JSON via stdin, reads result
   from stdout (30-second timeout)
3. `apply_elk_result()` — maps ELK positions/waypoints back to Diagram nodes
   and edges

**Requirements:**
```bash
npm install elkjs
node --version  # v16+
```

**Layout options configured** (`elk.py` lines 136–148):

| Option | Value | Effect |
|--------|-------|--------|
| `elk.algorithm` | `layered` | Layered (Sugiyama-based) |
| `elk.direction` | `DOWN` | Top-to-bottom |
| `elk.edgeRouting` | `ORTHOGONAL` | Right-angle bends |
| `elk.layered.spacing.nodeNodeBetweenLayers` | `60` | Vertical layer gap |
| `elk.spacing.nodeNode` | `20` | Horizontal node gap |
| `elk.portConstraints` | `FIXED_SIDE` | Ports stay on assigned side |
| `elk.layered.nodePlacement.strategy` | `SIMPLE` | Basic node positioning |

Best for: production-quality layouts, large diagrams (30+ nodes),
when visual polish matters more than startup time (~500 ms subprocess
spawn overhead).

---

## Renderers

### Terminal renderer (drawille)

**File:** `primitives.py` (219 lines)

The terminal renderer uses the [drawille](https://github.com/asciimoo/drawille)
library to convert vector primitives to Unicode braille characters
(U+2800–U+28FF). Each braille character represents a 2×4 pixel grid.

**Architecture:**

1. `drawille.Canvas.set(x, y)` — sets a pixel at (x, y)
2. `drawille.line(x1, y1, x2, y2)` — Bresenham line iterator returning
   pixel coordinates
3. `drawille.Canvas.set_text(x, y, text)` — writes ASCII text at a pixel
   position (converted to character row/col via `x//2, y//4`)
4. `drawille.Canvas.frame()` — produces the output string

**Drawing functions** (all in `primitives.py`):

| Function | Lines | What it draws |
|----------|-------|---------------|
| `draw_line()` | 74–82 | Single line segment (solid or dashed) |
| `draw_arrowhead()` | 85–87 | Dispatches to `_draw_open`, `_draw_triangle`, `_draw_diamond` |
| `draw_relation()` | 92–107 | Straight line + arrowheads + perpendicular label |
| `draw_polyline()` | 112–177 | Multi-segment polyline + arrowheads + Manhattan-midpoint label with collision avoidance |
| `draw_class_box()` | 199–219 | Rectangular box + centered text + optional separator + attributes |
| `draw_port_box()` | 186–194 | Small rectangle (14×10 px) with label |

**Label collision avoidance** (`draw_polyline()` lines 162–176):
Uses a shared `used_labels` set. When a label position is already occupied
(within a 10×5 px window), it tries a spiral of offsets:

```
(0,0) → (0,12) → (12,0) → (0,-8) → (-12,0) → (0,20) → ...
```

### SVG renderer

**File:** `svg_canvas.py` (252 lines)

The SVG renderer produces W3C-standard SVG 1.1 output. It mirrors the structure
of the terminal renderer but operates at the vector level.

**`SvgCanvas` class** (`svg_canvas.py` lines 41–146):

| Method | SVG element |
|--------|-------------|
| `add_line()` | `<line>` with optional `stroke-dasharray` |
| `add_rect()` | `<rect>` with fill and stroke |
| `add_text()` | `<text>` with `text-anchor`, `font-family="monospace"` |
| `add_polygon()` | `<polygon>` for arrowheads |
| `add_polyline()` | `<polyline>` for multi-segment edges |
| `add_group()` / `close_group()` | `<g>` for grouping |
| `output()` | Wraps all elements in `<svg>` with computed viewBox |

All coordinates are scaled by a configurable `scale` factor (default 1.5)
via `SvgCanvas.s()`. Text labels use `text-anchor="middle"` for automatic
centering.

**SVG drawing functions:**

| Function | What it draws |
|----------|---------------|
| `svg_draw_edge()` | Edge polylines with arrowhead polygons at endpoints and label text |
| `svg_draw_node()` | Rect + centered text lines + optional separator line |
| `svg_draw_port()` | Small rect + centered label |

Arrowheads are computed as `(<polygon> ...)` vectors via `_arrow_polygon()`
(lines 10–38), scaled to `ARROW_SIZE * 2` for better SVG visibility.

---

## API Reference

### Package exports (`__init__.py`)

```python
from boxes import (
    # Arrowhead styles
    NONE, OPEN, TRIANGLE, DIAMOND, FILLED,
    # Line styles
    SOLID, DASHED,
    # Drawing primitives
    draw_line, draw_arrowhead, draw_relation, draw_polyline,
    draw_class_box, draw_port_box, PORT_W, PORT_H, ARROW_SIZE,
    # Core classes
    Diagram, Node, Edge, Port,
    # Routing engines
    sugiyama_layout, layout_with_elk,
    # SVG renderer
    SvgCanvas, svg_draw_edge, svg_draw_node, svg_draw_port,
)
```

### `class Node`

| Method / Attribute | Description |
|-------------------|-------------|
| `Node(name, stereotypes=None, attributes=None)` | Create a node |
| `.add_port(label, side='left', offset=None)` | Add a port; `None` = auto-distribute; returns `Port` |
| `.add_attribute(text)` | Add an attribute line |
| `.x, .y, .w, .h` | Position and size (set by layout) |
| `.cx, .cy` | Center coordinates (properties) |
| `.box()` | Returns `(x1, y1, x2, y2)` |
| `.contains(px, py)` | Point-in-rect test |

### `class Port`

| Attribute | Description |
|-----------|-------------|
| `.label` | Port label text |
| `.side` | One of `'left'`, `'right'`, `'top'`, `'bottom'` |
| `.offset` | Proportional position along side (0.0–1.0) or `None` for auto-distribution |
| `.parent` | The owning `Node` |
| `.x, .y, .w, .h` | Position and size (14×10 px) |
| `.cx, .cy` | Center coordinates |
| `.box()` | Returns `(x1, y1, x2, y2)` |
| `.update_pos()` | Recompute position from parent's current bounds |

### `class Edge`

| Parameter | Description |
|-----------|-------------|
| `Edge(source, target, ...)` | `source`/`target` are `Node` objects |
| `source_style` | Arrowhead at source: `NONE`, `OPEN`, `TRIANGLE`, `DIAMOND`, `FILLED` |
| `target_style` | Arrowhead at target (default: `OPEN`) |
| `line_style` | `SOLID` or `DASHED` |
| `label` | Text label at midpoint (optional) |
| `source_port` | `Port` object for source connection (optional) |
| `target_port` | `Port` object for target connection (optional) |
| `.waypoints` | List of `(x, y)` tuples set by routing |
| `.route(*points)` | Set waypoints |

### `class Diagram`

| Method | Description |
|--------|-------------|
| `add_node(name, stereotypes=None, attributes=None)` | Create and register a `Node` |
| `add_edge(source, target, **kw)` | Create and register an `Edge` |
| `layout(routing='orthogonal', layer_gap=50, node_gap=12, margin=8)` | Compute positions and waypoints |
| `render(routing='orthogonal', ...)` | Layout + return terminal braille string |
| `render_svg(routing='orthogonal', ..., scale=1.5)` | Layout + return SVG string |

---

## Architecture overview

```
                    ┌──────────────────────────┐
                    │     Diagram (layout.py)   │
                    │  Node, Edge, Port classes  │
                    │  Layer assignment, routing │
                    └──────┬──────────┬─────────┘
                           │          │
              ┌────────────┘          └────────────┐
              ↓                                    ↓
     ┌─────────────────┐                 ┌──────────────────┐
     │   primitives.py  │                 │   svg_canvas.py   │
     │  drawille-based   │                 │  SVG 1.1 output   │
     │  raster drawing   │                 │  vector drawing   │
     └────────┬─────────┘                 └────────┬─────────┘
              ↓                                    ↓
     ┌─────────────────┐                 ┌──────────────────┐
     │ drawille.Canvas  │                 │   <svg> string   │
     │ braille chars    │                 │   XML elements   │
     └─────────────────┘                 └──────────────────┘

     Routing engines (all feed into Diagram):
       layout._route_orthogonal()   — homegrown 3-segment
       layout._route_straight()     — center-to-center
       sugiyama.sugiyama_layout()   — 5-stage Sugiyama
       elk.layout_with_elk()        — ELKjs subprocess
```

---

## Known limitations

- **Label-over-line overwrite:** drawille's `set_text()` replaces braille
  characters with ASCII text at the target position. Labels falling on bus
  lines break the line visually. The SVG renderer does not have this issue.
- **Sugiyama crossing minimization** can get stuck in local minima on
  complex graphs.
- **Ports are not supported in Sugiyama mode** (ports are ignored).
- **ELKjs subprocess overhead** (~500 ms per layout). Not suitable for
  interactive use.
- **ELKjs produces wider diagrams** with different spacing than our Python
  routers — may exceed terminal width.
# boxes
