"""DAG nodes valid as start/end rig anchors and UI selection targets."""

from __future__ import annotations

from typing import List, Optional, Tuple

import maya.cmds as cmds

# Explicit allowlist — HIK controls use their own nodeTypes, not plain "transform".
SELECTABLE_DAG_TYPES: Tuple[str, ...] = (
    "transform",
    "joint",
    # Human IK (Maya 2011+)
    "hikIKEffector",
    "hikEffector",
    "hikFKJoint",
    "hikHandle",
    # Classic IK
    "ikEffector",
    "ikHandle",
)

_SELECTABLE_SET = frozenset(SELECTABLE_DAG_TYPES)


def _short_name(name: str) -> str:
    return name.split("|")[-1].strip()


def node_type(name: str) -> Optional[str]:
    short = _short_name(name)
    if not short or not cmds.objExists(short):
        return None
    return cmds.nodeType(short)


def is_selectable_dag(name: str) -> bool:
    """True if name is an allowed rig-control DAG node."""
    short = _short_name(name)
    if not short or not cmds.objExists(short):
        return False
    ntype = cmds.nodeType(short)
    if ntype in _SELECTABLE_SET:
        return True
    # Future HIK node types: transform-derived, hik* prefix
    if ntype.startswith("hik") and cmds.objectType(short, isAType="transform"):
        return True
    return False


def resolve_dag_target(name: str) -> Optional[str]:
    """
  Return a usable DAG short name, or None.
  If a shape is passed, walks up to its transform parent.
    """
    if not name:
        return None
    short = _short_name(name)
    if not cmds.objExists(short):
        return None

    if is_selectable_dag(short):
        return short

    parent = cmds.listRelatives(short, parent=True, fullPath=False)
    if parent and is_selectable_dag(parent[0]):
        return parent[0]

    return None


def list_selected_targets() -> List[str]:
    """Current selection filtered to allowed DAG control types."""
    found: List[str] = []
    for obj in cmds.ls(sl=True, long=False) or []:
        resolved = resolve_dag_target(obj)
        if resolved and resolved not in found:
            found.append(resolved)
    return found


def resolve_transform_for_parent(name: str) -> Optional[str]:
    """
    Return a transform suitable as a DAG parent (never a shape).
    Accepts any transform type — broader than rig-anchor allowlist.
    """
    if not name:
        return None
    short = _short_name(name)
    if not cmds.objExists(short):
        return None

    if cmds.objectType(short, isAType="transform"):
        return short

    parents = cmds.listRelatives(short, parent=True, type="transform", fullPath=False)
    if parents:
        return parents[0]

    return None


def is_dag_node(name: str) -> bool:
    """True if the node exists in the DAG (can be parented under a transform)."""
    short = _short_name(name)
    if not short or not cmds.objExists(short):
        return False
    return bool(cmds.ls(short, dagObjects=True))


def selectable_type_label() -> str:
    return ", ".join(SELECTABLE_DAG_TYPES)


def validate_dag_target(name: str, label: str) -> str:
    resolved = resolve_dag_target(name)
    if not resolved:
        ntype = node_type(name) or "unknown"
        raise ValueError(
            f"{label} must be a rig control ({selectable_type_label()}), "
            f"got '{name}' ({ntype})"
        )
    return resolved
