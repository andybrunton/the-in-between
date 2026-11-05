"""Shifter post step. The head drives the plume neck tip."""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plume_rig

importlib.reload(plume_rig)
plume_rig.drive_neck_from_head()
