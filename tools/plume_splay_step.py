"""Shifter post step. Adds one Splay channel per feather row on the rig host."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import plume_rig

plume_rig.add_splay()
