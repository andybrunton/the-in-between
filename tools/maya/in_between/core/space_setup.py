"""Shared start/end space alignment for chord-aligned rigs."""

from __future__ import annotations

import math
from typing import Optional, Tuple

import maya.cmds as cmds

from in_between.core.naming import unique_name
from in_between.core.parents import parent_under


def rest_distance(start: str, end: str) -> float:
    p1 = cmds.xform(start, q=True, ws=True, t=True)
    p2 = cmds.xform(end, q=True, ws=True, t=True)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def create_space_chain(
    name_prefix: str,
    start: str,
    end: str,
    aim_vector=(1, 0, 0),
    up_vector=(0, 1, 0),
    up_object: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Create root → space → orient empty groups aimed from start toward end.
    Returns (root, space_grp, orient_grp).

    up_object sets the aimConstraint worldUpObject (blade / start local axes).
    """
    root = cmds.group(empty=True, name=unique_name(f"{name_prefix}_Grp"))
    space_grp = cmds.group(empty=True, name=unique_name(f"{name_prefix}_Space"))
    orient_grp = cmds.group(empty=True, name=unique_name(f"{name_prefix}_Orient"))

    cmds.parent(orient_grp, space_grp)
    cmds.parent(space_grp, root)

    cmds.matchTransform(space_grp, start, pos=True, rot=False)
    cmds.pointConstraint(start, space_grp, maintainOffset=False)
    cmds.aimConstraint(
        end,
        space_grp,
        aimVector=aim_vector,
        upVector=up_vector,
        worldUpType="objectrotation",
        worldUpObject=up_object or start,
        worldUpVector=up_vector,
    )
    return root, space_grp, orient_grp


def hide_transform(node: str) -> None:
    if cmds.objExists(node):
        cmds.setAttr(f"{node}.visibility", 0)


def create_settings_locator(
    name: str,
    parent: str,
    start: str,
    end: str,
) -> str:
    settings = cmds.spaceLocator(name=unique_name(name))[0]
    parent_under(settings, parent)
    p1 = cmds.xform(start, q=True, ws=True, t=True)
    p2 = cmds.xform(end, q=True, ws=True, t=True)
    cmds.xform(
        settings,
        ws=True,
        t=((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2),
    )
    hide_transform(settings)
    return settings


def connect_world_distance(name_prefix: str, start: str, end: str) -> Tuple[str, str]:
    """distanceBetween driven by world matrices of start/end."""
    dist_node = cmds.createNode("distanceBetween", name=unique_name(f"{name_prefix}_Dist"))
    decomp1 = cmds.createNode("decomposeMatrix", name=unique_name(f"{name_prefix}_StartDecomp"))
    decomp2 = cmds.createNode("decomposeMatrix", name=unique_name(f"{name_prefix}_EndDecomp"))
    cmds.connectAttr(f"{start}.worldMatrix[0]", f"{decomp1}.inputMatrix")
    cmds.connectAttr(f"{end}.worldMatrix[0]", f"{decomp2}.inputMatrix")
    cmds.connectAttr(f"{decomp1}.outputTranslate", f"{dist_node}.point1")
    cmds.connectAttr(f"{decomp2}.outputTranslate", f"{dist_node}.point2")
    return dist_node, f"{dist_node}.distance"
