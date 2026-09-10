"""Parent group resolution — supports multiple rigs via unique group names."""

from __future__ import annotations

from typing import Optional, Tuple

import maya.cmds as cmds

from in_between.core.dag_targets import is_dag_node, resolve_transform_for_parent
from in_between.core.naming import unique_name


DEFAULT_LOCAL = "rig_group_local"
DEFAULT_WORLD = "rig_group_world"
DEFAULT_JOINT = "rig_group_joint"


def _resolve_parent(user_value: Optional[str], default_label: str) -> str:
    if user_value:
        resolved = resolve_transform_for_parent(user_value)
        if resolved:
            return resolved
    name = unique_name(default_label)
    if not cmds.objExists(name):
        cmds.group(empty=True, name=name)
    return name


def resolve_parents(
    local_parent: Optional[str],
    world_parent: Optional[str],
    joint_parent: Optional[str],
) -> Tuple[str, str, str]:
    """Return (local, world, joint) parent transforms, creating defaults when empty."""
    return (
        _resolve_parent(local_parent, DEFAULT_LOCAL),
        _resolve_parent(world_parent, DEFAULT_WORLD),
        _resolve_parent(joint_parent, DEFAULT_JOINT),
    )


def parent_under(child: str, parent: str) -> None:
    """
    Parent a DAG node under a transform. Skips dependency nodes (expressions,
    distanceBetween, etc.) — those cannot live in the DAG and trigger underworld warnings.
    """
    if not child or not parent:
        return
    if not is_dag_node(child):
        return
    parent_xform = resolve_transform_for_parent(parent)
    if not parent_xform:
        return
    if not cmds.objExists(child):
        return
    cmds.parent(child, parent_xform)
