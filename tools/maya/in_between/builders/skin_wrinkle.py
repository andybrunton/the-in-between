"""Skin Wrinkle — crease bulge between two driven transforms."""

from __future__ import annotations

import maya.cmds as cmds

from in_between.core.context import RigContext, RigResult
from in_between.core.drive import setup_drive
from in_between.core.naming import unique_name
from in_between.core.parents import parent_under, resolve_parents
from in_between.core.space_setup import (
    create_settings_locator,
    create_space_chain,
    rest_distance,
)
from in_between.joints.rmf_chain import create_joints_on_curve


def build(ctx: RigContext) -> RigResult:
    name = ctx.base_name
    start_obj = ctx.start
    end_obj = ctx.end
    rest_dist = rest_distance(start_obj, end_obj)

    local_p, world_p, joint_p = resolve_parents(
        ctx.local_parent, ctx.world_parent, ctx.joint_parent
    )

    root, _, orient_grp = create_space_chain(name, start_obj, end_obj)
    parent_under(root, local_p)

    settings = create_settings_locator(ctx.node("Settings"), root, start_obj, end_obj)
    parent_under(settings, world_p)

    for attr, dv, minv, maxv in [
        ("bulgeAmount", 1.2, 0, 3),
        ("creaseDepth", 0.9, 0, 2),
        ("creaseOffset", 0.5, 0, 1),
    ]:
        cmds.addAttr(settings, ln=attr, at="float", dv=dv, min=minv, max=maxv, k=True)

    peak = cmds.spaceLocator(name=unique_name(ctx.node("Peak")))[0]
    cmds.parent(peak, orient_grp)

    p_init = [(rest_dist * (i / 6.0), 0, 0) for i in range(7)]
    curve = cmds.curve(
        d=3,
        p=p_init,
        k=[0, 0, 0, 1, 1, 1, 2, 2, 2],
        name=unique_name(ctx.node("Crv")),
    )
    cmds.parent(curve, orient_grp)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr(f"{curve}.{attr}", 0)

    drive = setup_drive(
        name, ctx, settings, start_obj, end_obj, world_p, rest_dist, rest_dist * 0.5
    )

    expr = f"""
float $t = {drive.compression_plug};
float $span = max(0.001, {drive.span_plug});
float $compression = $t * max(0.001, {settings}.restLength - {settings}.minLength);
float $bulge = $compression * {settings}.bulgeAmount;
float $crease = $bulge * {settings}.creaseDepth;
float $peakY = $bulge - $crease;
float $peakX = $span * 0.5 + $span * {settings}.creaseOffset * 0.25;
{peak}.translateX = $peakX;
{peak}.translateY = $peakY;
{curve}.controlPoints[2].yValue = $bulge * 0.6;
{curve}.controlPoints[3].xValue = $peakX;
{curve}.controlPoints[3].yValue = $peakY;
{curve}.controlPoints[4].yValue = $bulge * 0.6;
"""
    expr_node = cmds.expression(s=expr, name=unique_name(ctx.node("WrinkleExpr")))
    parent_under(expr_node, world_p)

    joints = []
    if ctx.build_joints:
        joints = create_joints_on_curve(
            curve,
            ctx.node("chain"),
            num_joints=ctx.num_joints,
            joint_parent_group=joint_p,
            world_parent_group=world_p,
            rig_root=root,
            user_joint_parent=ctx.joint_parent,
        )

    cmds.select(settings)
    return RigResult(
        root=root,
        settings=settings,
        curve=curve,
        joint_chain=joints,
        local_root=local_p,
        world_root=world_p,
        joint_root=joint_p,
    )
