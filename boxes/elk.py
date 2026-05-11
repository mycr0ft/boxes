"""ELKjs integration — spawns Node.js subprocess for production layouts.

Bridges to the Eclipse Layout Kernel (ELK) layered algorithm via elkjs.
The pipeline:

1. ``to_elk_json(diagram)`` — converts Diagram → ELK JSON
2. ``elk_layout(graph)`` — spawns ``node -e``, pipes JSON via stdin
3. ``apply_elk_result(diagram, result)`` — maps positions/waypoints back

Layout options configured (see layout_with_elk for defaults):
- elk.algorithm: layered, elk.direction: DOWN
- elk.edgeRouting: ORTHOGONAL
- Port constraints: FIXED_SIDE, alignment: CENTER

Requires
--------
npm install elkjs
node --version >= 16

See also
--------
sugiyama.py  : pure-Python alternative (~400 lines, no dependencies)
layout.py    : homegrown orthogonal router (used by default)
"""

import json
import subprocess
import os
from pathlib import Path

_ELK_BOOTSTRAP = """
const ELK = require('elkjs');
const elk = new ELK();
let data = '';
process.stdin.on('data', d => data += d);
process.stdin.on('end', () => {
  elk.layout(JSON.parse(data))
    .then(r => { process.stdout.write(JSON.stringify(r)); process.exit(0); })
    .catch(e => { process.stderr.write(e.message); process.exit(1); });
});
"""


def elk_layout(graph_dict, node_modules=None, timeout=30):
    """Send a graph JSON dict to elkjs, return the result dict.

    graph_dict should follow ELK input format:
      { "id": "root", "children": [...], "edges": [...], "layoutOptions": {...} }
    """
    if node_modules:
        env = os.environ.copy()
        env['NODE_PATH'] = str(Path(node_modules).resolve())
    else:
        env = os.environ.copy()

    proc = subprocess.run(
        ['node', '-e', _ELK_BOOTSTRAP],
        input=json.dumps(graph_dict),
        capture_output=True, text=True, timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'elkjs failed: {proc.stderr}')
    return json.loads(proc.stdout)


def to_elk_json(diagram):
    """Convert a drawille Diagram to ELK JSON.

    Maps:
      - Node → child node with label, port definitions
      - Edge → edge with port references
      - Arrow styles → passed through as custom properties
    """
    children = []
    edges = []
    # Track ports per node for edge routing
    port_index = {}
    port_side = {}  # node -> { edge_id -> side }

    for e in diagram.edges:
        ports_src = port_side.setdefault(e.source.name, {'out': [], 'in': []})
        ports_src['out'].append(e)
        ports_tgt = port_side.setdefault(e.target.name, {'out': [], 'in': []})
        ports_tgt['in'].append(e)

    for n in diagram.nodes:
        node_ports = []
        ps = port_side.get(n.name, {'out': [], 'in': []})

        for i, e in enumerate(ps['out']):
            pid = f'{n.name}_out_{i}'
            port_index[(n.name, e, 'source')] = pid
            node_ports.append({
                'id': pid, 'width': 8, 'height': 8,
                'properties': {'port.side': 'SOUTH', 'port.index': str(i)},
            })

        for i, e in enumerate(ps['in']):
            pid = f'{n.name}_in_{i}'
            port_index[(n.name, e, 'target')] = pid
            node_ports.append({
                'id': pid, 'width': 8, 'height': 8,
                'properties': {'port.side': 'NORTH', 'port.index': str(i)},
            })

        # Label as a node label (ELK supports nested labels)
        label_parts = []
        if n.stereotypes:
            for s in n.stereotypes:
                label_parts.append(f'\u00ab{s}\u00bb')
        label_parts.append(n.name)
        label_text = '\n'.join(label_parts)

        child = {
            'id': n.name,
            'width': n.w if n.w else 100,
            'height': n.h if n.h else 50,
            'labels': [{'text': label_text, 'properties': {'label.placement': 'INSIDE'}}],
        }
        if node_ports:
            child['ports'] = node_ports
        children.append(child)

    # Build edge entries
    for e in diagram.edges:
        src_pid = port_index.get((e.source.name, e, 'source'), e.source.name)
        tgt_pid = port_index.get((e.target.name, e, 'target'), e.target.name)

        edge = {
            'id': f'{e.source.name}__{e.target.name}__{id(e)}',
            'sources': [src_pid],
            'targets': [tgt_pid],
        }

        # Pass through our styling for post-processing
        props = {}
        if e.source_style:
            props['source_style'] = e.source_style
        if e.target_style:
            props['target_style'] = e.target_style
        if e.line_style:
            props['line_style'] = e.line_style
        if e.label:
            props['edge_label'] = e.label
            edge['labels'] = [{
                'text': e.label,
                'properties': {'label.placement': 'CENTER'}
            }]
        if props:
            edge['properties'] = props

        edges.append(edge)

    # Layout options for UML/SysML-style block diagrams
    layout_options = {
        'elk.algorithm': 'layered',
        'elk.direction': 'DOWN',
        'elk.edgeRouting': 'ORTHOGONAL',
        'elk.layered.spacing.nodeNodeBetweenLayers': '60',
        'elk.spacing.nodeNode': '20',
        'elk.spacing.edgeNode': '15',
        'elk.layered.nodePlacement.strategy': 'SIMPLE',
        'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
        'elk.portConstraints': 'FIXED_SIDE',
        'elk.portAlignment.default': 'CENTER',
        'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    }

    return {
        'id': 'root',
        'layoutOptions': layout_options,
        'children': children,
        'edges': edges,
    }


def _snap_to_node(wp, node):
    """Move a waypoint just outside *node* to the node's edge boundary.

    ELK places edge endpoints at the port center, which can be several
    pixels off the node boundary.  This projects the waypoint onto the
    nearest node edge so arrowheads sit flush.
    """
    x, y = wp
    nx1, ny1 = node.x, node.y
    nx2, ny2 = node.x + node.w, node.y + node.h

    if x < nx1:
        return (nx1, y)
    if x > nx2:
        return (nx2, y)
    if y < ny1:
        return (x, ny1)
    if y > ny2:
        return (x, ny2)
    return wp


def apply_elk_result(diagram, result):
    """Update Diagram node positions and edge waypoints from ELK result."""
    # Build lookup: node id → ELK result node
    elk_nodes = {}
    for child in result.get('children', []):
        elk_nodes[child['id']] = child

    for n in diagram.nodes:
        if n.name in elk_nodes:
            en = elk_nodes[n.name]
            n.x = int(en['x'])
            n.y = int(en['y'])
            n.w = int(en['width'])
            n.h = int(en['height'])

    elk_edges = {}
    for edge in result.get('edges', []):
        elk_edges[edge['id']] = edge

    edge_id_map = {}
    for e in diagram.edges:
        eid = f'{e.source.name}__{e.target.name}__{id(e)}'
        edge_id_map[eid] = e

    # Update edge waypoints
    for eid, ee in elk_edges.items():
        if eid not in edge_id_map:
            continue
        e = edge_id_map[eid]

        waypoints = []
        for section in ee.get('sections', []):
            sp = section.get('startPoint', {})
            waypoints.append((int(sp['x']), int(sp['y'])))
            for bp in section.get('bendPoints', []):
                waypoints.append((int(bp['x']), int(bp['y'])))
            ep = section.get('endPoint', {})
            waypoints.append((int(ep['x']), int(ep['y'])))

        if waypoints:
            # Clean consecutive duplicates
            cleaned = [waypoints[0]]
            for p in waypoints[1:]:
                if p != cleaned[-1]:
                    cleaned.append(p)

            # Snap first/last waypoint to node boundaries so arrowheads
            # sit flush instead of hovering off the port centre.
            if len(cleaned) >= 1:
                cleaned[0] = _snap_to_node(cleaned[0], e.source)
            if len(cleaned) >= 2:
                cleaned[-1] = _snap_to_node(cleaned[-1], e.target)

            e.waypoints = cleaned


def layout_with_elk(diagram, node_modules=None):
    """Full pipeline: convert Diagram → ELK JSON → run elkjs → apply results."""
    graph = to_elk_json(diagram)
    result = elk_layout(graph, node_modules=node_modules)
    apply_elk_result(diagram, result)
    return diagram
