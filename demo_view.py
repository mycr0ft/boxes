#!/usr/bin/env python3
"""Demo of view / package nodes with folder-tab label area."""

from boxes import Diagram, FILLED, DASHED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])
sensor = d.add_node('SensorCluster', ['block'])

pkg = d.add_view('Powertrain', ['package'],
    attributes=['+ read()', '+ calibrate()'])
vw = d.add_view('VehicleDynamics', ['view'])

d.add_edge(ecu, sensor, source_style=FILLED, target_style=None, label='reads')
d.contain(pkg, ecu, label='contains')
d.contain(vw, sensor)

print(d.render(routing='orthogonal', node_gap=20))
