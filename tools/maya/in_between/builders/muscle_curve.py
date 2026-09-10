"""Muscle Curve — superellipse bulge driven by start/end distance."""

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
        ("maxHeight", 95.0, -80.0, 140.0),
        ("exponent", 2.0, 0.4, 4.0),
        ("apexSlide", 0.0, -0.85, 0.85),
    ]:
        cmds.addAttr(settings, ln=attr, at="float", dv=dv, min=minv, max=maxv, k=True)

    cvs = [((rest_dist * (i / 11.0)), 0, 0) for i in range(12)]
    muscle_crv = cmds.curve(d=3, p=cvs, name=unique_name(ctx.node("MuscleCrv")))
    cmds.parent(muscle_crv, orient_grp)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr(f"{muscle_crv}.{attr}", 0)

    drive = setup_drive(
        name, ctx, settings, start_obj, end_obj, world_p, rest_dist, rest_dist * 0.19
    )

    expr_lines = [
        f"float $t = {drive.compression_plug};",
        f"float $hFinal = {settings}.maxHeight * $t;",
        f"float $slide = {settings}.apexSlide;",
        f"float $n = {settings}.exponent;",
    ]

    for i in range(12):
        u = -1.0 + (i / 11.0) * 2.0
        expr_lines.extend([
            f"float $u{i} = {u:.4f};",
            f"float $w{i} = ($u{i} < $slide) ? ($u{i} - $slide)/(1.0 + $slide) : ($u{i} - $slide)/(1.0 - $slide);",
            f"float $p{i} = pow(max(0.0, 1.0 - pow(abs($w{i}), $n)), 1.0 / $n);",
            f"{muscle_crv}.controlPoints[{i}].yValue = $hFinal * $p{i};",
        ])

    expr = cmds.expression(s="\n".join(expr_lines), name=unique_name(ctx.node("DeformExpr")))
    parent_under(expr, world_p)

    joints = []
    if ctx.build_joints:
        joints = create_joints_on_curve(
            muscle_crv,
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
        curve=muscle_crv,
        joint_chain=joints,
        local_root=local_p,
        world_root=world_p,
        joint_root=joint_p,
    )
