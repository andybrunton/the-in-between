"""Shifter post step. Adds one Splay channel per feather row on the rig host."""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plume_rig

importlib.reload(plume_rig)
plume_rig.add_splay()
