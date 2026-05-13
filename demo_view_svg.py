#!/usr/bin/env python3
"""SVG version of view / package demo."""

from boxes import Diagram, FILLED, DASHED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])
sensor = d.add_node('SensorCluster', ['block'])

pkg = d.add_view('Powertrain', ['package'],
    attributes=['+ read()', '+ calibrate()'])
vw = d.add_view('VehicleDynamics', ['view'])

d.add_edge(ecu, sensor, source_style=FILLED, target_style=None, label='reads')
d.add_edge(ecu, pkg, line_style=DASHED, target_style=None, label='in')
d.add_edge(vw, sensor, line_style=DASHED, target_style=None, label='uses')

svg = d.render_svg(routing='orthogonal', node_gap=20)
path = '/tmp/boxes_view.svg'
with open(path, 'w') as f:
    f.write(svg)
print(f'Saved SVG ({len(svg)} chars) to {path}')
