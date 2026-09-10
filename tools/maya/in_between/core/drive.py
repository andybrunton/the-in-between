"""Universal distance / angle drive for all In-Between Maya behaviours."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

import maya.cmds as cmds

from in_between.core.context import RigContext
from in_between.core.naming import unique_name
from in_between.core.parents import parent_under
from in_between.core.space_setup import connect_world_distance

DriveMode = Literal["distance", "angle"]
DRIVE_DISTANCE: DriveMode = "distance"
DRIVE_ANGLE: DriveMode = "angle"
DEFAULT_MAX_BEND = 150.0


@dataclass
class DriveSetup:
    """Scalar compression t in [0, 1] plus chord span for layout."""

    mode: DriveMode
    compression_plug: str
    span_plug: str
    distance_node: Optional[str] = None
    distance_plug: Optional[str] = None
    angle_node: Optional[str] = None
    remap_node: Optional[str] = None


def _angle_between_vectors(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    len1 = math.sqrt(sum(a * a for a in v1))
    len2 = math.sqrt(sum(a * a for a in v2))
    if len1 < 1e-8 or len2 < 1e-8:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (len1 * len2)))))


def snapshot_bend_angle(start: str, end: str, reference: Optional[str]) -> float:
    p0 = cmds.xform(start, q=True, ws=True, t=True)
    p1 = cmds.xform(end, q=True, ws=True, t=True)
    if reference:
        p2 = cmds.xform(reference, q=True, ws=True, t=True)
        v1 = [p1[i] - p0[i] for i in range(3)]
        v2 = [p2[i] - p1[i] for i in range(3)]
    else:
        matrix = cmds.xform(start, q=True, ws=True, m=True)
        v1 = [matrix[0], matrix[1], matrix[2]]
        v2 = [p1[i] - p0[i] for i in range(3)]
    return _angle_between_vectors(v1, v2)


def add_drive_attrs(
    settings: str,
    rest_dist: float,
    min_length: float,
    rest_angle: float,
    max_bend_angle: float,
    drive_mode: DriveMode,
) -> None:
    cmds.addAttr(settings, ln="restLength", at="float", dv=rest_dist, min=0.001, k=True)
    cmds.addAttr(settings, ln="minLength", at="float", dv=min_length, min=0.001, k=True)
    cmds.addAttr(settings, ln="restAngle", at="float", dv=rest_angle, k=True)
    cmds.addAttr(settings, ln="maxBendAngle", at="float", dv=max_bend_angle, k=True)
    dv = 0 if drive_mode == DRIVE_DISTANCE else 1
    cmds.addAttr(
        settings,
        ln="driveMode",
        at="enum",
        en="distance:angle",
        dv=dv,
        k=True,
    )


def _connect_distance_compression(
    name: str,
    settings: str,
    dist_plug: str,
) -> str:
    remap = cmds.createNode("setRange", name=unique_name(f"{name}_DistRemap"))
    cmds.connectAttr(f"{settings}.minLength", f"{remap}.oldMinX")
    cmds.connectAttr(f"{settings}.restLength", f"{remap}.oldMaxX")
    cmds.setAttr(f"{remap}.minX", 1.0)
    cmds.setAttr(f"{remap}.maxX", 0.0)
    cmds.connectAttr(dist_plug, f"{remap}.valueX")
    return remap


def _connect_angle_compression(
    name: str,
    start: str,
    end: str,
    reference: Optional[str],
    settings: str,
    world_p: str,
) -> tuple[str, str]:
    decomp_s = cmds.createNode("decomposeMatrix", name=unique_name(f"{name}_StartDecomp"))
    decomp_e = cmds.createNode("decomposeMatrix", name=unique_name(f"{name}_EndDecomp"))
    parent_under(decomp_s, world_p)
    parent_under(decomp_e, world_p)
    cmds.connectAttr(f"{start}.worldMatrix[0]", f"{decomp_s}.inputMatrix")
    cmds.connectAttr(f"{end}.worldMatrix[0]", f"{decomp_e}.inputMatrix")

    pma_chord = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_ChordVec"))
    cmds.setAttr(f"{pma_chord}.operation", 2)
    cmds.connectAttr(f"{decomp_e}.outputTranslate", f"{pma_chord}.input3D[0]")
    cmds.connectAttr(f"{decomp_s}.outputTranslate", f"{pma_chord}.input3D[1]")

    angle = cmds.createNode("angleBetween", name=unique_name(f"{name}_BendAngle"))
    cmds.connectAttr(f"{pma_chord}.output3D", f"{angle}.vector1")

    if reference:
        decomp_ref = cmds.createNode("decomposeMatrix", name=unique_name(f"{name}_RefDecomp"))
        parent_under(decomp_ref, world_p)
        cmds.connectAttr(f"{reference}.worldMatrix[0]", f"{decomp_ref}.inputMatrix")
        pma_out = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_OutVec"))
        cmds.setAttr(f"{pma_out}.operation", 2)
        cmds.connectAttr(f"{decomp_ref}.outputTranslate", f"{pma_out}.input3D[0]")
        cmds.connectAttr(f"{decomp_e}.outputTranslate", f"{pma_out}.input3D[1]")
        cmds.connectAttr(f"{pma_out}.output3D", f"{angle}.vector2")
    else:
        compose = cmds.createNode("composeMatrix", name=unique_name(f"{name}_LocalX"))
        mult = cmds.createNode("multMatrix", name=unique_name(f"{name}_StartXWorld"))
        decomp_tip = cmds.createNode("decomposeMatrix", name=unique_name(f"{name}_StartXDecomp"))
        parent_under(compose, world_p)
        parent_under(mult, world_p)
        parent_under(decomp_tip, world_p)
        cmds.setAttr(f"{compose}.inputTranslate", 1.0, 0.0, 0.0)
        cmds.connectAttr(f"{start}.worldMatrix[0]", f"{mult}.matrixIn[0]")
        cmds.connectAttr(f"{compose}.outputMatrix", f"{mult}.matrixIn[1]")
        cmds.connectAttr(f"{mult}.matrixSum", f"{decomp_tip}.inputMatrix")
        pma_axis = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_StartAxis"))
        cmds.setAttr(f"{pma_axis}.operation", 2)
        cmds.connectAttr(f"{decomp_tip}.outputTranslate", f"{pma_axis}.input3D[0]")
        cmds.connectAttr(f"{decomp_s}.outputTranslate", f"{pma_axis}.input3D[1]")
        cmds.connectAttr(f"{pma_axis}.output3D", f"{angle}.vector2")

    remap = cmds.createNode("setRange", name=unique_name(f"{name}_AngleRemap"))
    cmds.connectAttr(f"{settings}.restAngle", f"{remap}.oldMinX")
    cmds.connectAttr(f"{settings}.maxBendAngle", f"{remap}.oldMaxX")
    cmds.setAttr(f"{remap}.minX", 0.0)
    cmds.setAttr(f"{remap}.maxX", 1.0)
    cmds.connectAttr(f"{angle}.angle", f"{remap}.valueX")
    return remap, angle


def setup_drive(
    name: str,
    ctx: RigContext,
    settings: str,
    start: str,
    end: str,
    world_p: str,
    rest_dist: float,
    min_length: float,
) -> DriveSetup:
    """Wire compression + span from ctx.drive_mode. Always snapshots angle attrs."""
    mode: DriveMode = ctx.drive_mode if ctx.drive_mode in (DRIVE_DISTANCE, DRIVE_ANGLE) else DRIVE_DISTANCE
    rest_angle = snapshot_bend_angle(start, end, ctx.reference)
    max_bend_angle = min(180.0, rest_angle + DEFAULT_MAX_BEND)

    add_drive_attrs(settings, rest_dist, min_length, rest_angle, max_bend_angle, mode)

    dist_node, dist_plug = connect_world_distance(name, start, end)
    parent_under(dist_node, world_p)

    if mode == DRIVE_ANGLE:
        remap, angle_node = _connect_angle_compression(
            name, start, end, ctx.reference, settings, world_p
        )
        return DriveSetup(
            mode=mode,
            compression_plug=f"{remap}.outValueX",
            span_plug=f"{settings}.restLength",
            distance_node=dist_node,
            distance_plug=dist_plug,
            angle_node=angle_node,
            remap_node=remap,
        )

    remap = _connect_distance_compression(name, settings, dist_plug)
    parent_under(remap, world_p)
    return DriveSetup(
        mode=mode,
        compression_plug=f"{remap}.outValueX",
        span_plug=dist_plug,
        distance_node=dist_node,
        distance_plug=dist_plug,
        remap_node=remap,
    )
