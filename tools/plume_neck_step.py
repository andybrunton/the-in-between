"""Shifter post step. The head drives the plume neck tip."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import plume_rig

plume_rig.drive_neck_from_head()
