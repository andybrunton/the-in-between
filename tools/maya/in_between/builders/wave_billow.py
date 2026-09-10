"""Wave Billow — harmonic displacement along the start/end chord."""

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
    num_joints = max(ctx.num_joints, 4)

    local_p, world_p, joint_p = resolve_parents(
        ctx.local_parent, ctx.world_parent, ctx.joint_parent
    )

    root, _, orient_grp = create_space_chain(name, start_obj, end_obj)
    parent_under(root, local_p)

    settings = create_settings_locator(ctx.node("Settings"), root, start_obj, end_obj)
    parent_under(settings, world_p)

    cmds.addAttr(settings, ln="amp", at="float", dv=48, min=0, max=75, k=True)
    cmds.addAttr(settings, ln="freq", at="float", dv=1.75, min=0.25, max=4.0, k=True)
    cmds.addAttr(settings, ln="steepness", at="float", dv=0.75, min=0, max=1, k=True)
    cmds.addAttr(settings, ln="complexity", at="float", dv=0.5, min=0, max=1, k=True)
    cmds.addAttr(settings, ln="phase", at="float", dv=0, min=0, max=360, k=True)
    cmds.addAttr(
        settings,
        ln="boundaryMode",
        at="enum",
        en="freestart:freeend:pinned",
        dv=1,
        k=True,
    )

    points = [(rest_dist * (i / (num_joints - 1)), 0, 0) for i in range(num_joints)]
    curve = cmds.curve(d=3, p=points, name=unique_name(ctx.node("WaveCrv")))
    cmds.parent(curve, orient_grp)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr(f"{curve}.{attr}", 0)

    drive = setup_drive(
        name, ctx, settings, start_obj, end_obj, world_p, rest_dist, rest_dist * 0.5
    )

    lines = [
        f"float $drive = {drive.compression_plug};",
        "float $phase = " + settings + ".phase * 3.14159 / 180;",
        "int $mode = " + settings + ".boundaryMode;",
        "float $amp = " + settings + ".amp * max(0.001, $drive);",
        "float $freq = " + settings + ".freq;",
        "float $steep = " + settings + ".steepness;",
        "float $complex = " + settings + ".complexity;",
        "float $L = " + f"{rest_dist:.4f};",
        "float $baseOffset = $complex * 2 * 3.14159;",
        "float $phaseOffsets[4];",
        "$phaseOffsets[0] = 0;",
        "$phaseOffsets[1] = $baseOffset * 0.5;",
        "$phaseOffsets[2] = $baseOffset * 0.8;",
        "$phaseOffsets[3] = $baseOffset * 1.2;",
        "float $weights[4];",
        "$weights[0] = 1.0;",
        "$weights[1] = clamp(($complex - 0.00) / 0.33, 0, 1);",
        "$weights[2] = clamp(($complex - 0.33) / 0.33, 0, 1);",
        "$weights[3] = clamp(($complex - 0.66) / 0.34, 0, 1);",
        "float $mult[4];",
        "$mult[0] = 1; $mult[1] = 2; $mult[2] = 3; $mult[3] = 4;",
        "float $ampMult[4];",
        "$ampMult[0] = 1; $ampMult[1] = 0.5; $ampMult[2] = 0.33; $ampMult[3] = 0.25;",
    ]

    for i in range(num_joints):
        lines.append(f"// CV {i}")
        lines.append(f"float $u{i} = {i} / float({num_joints - 1});")
        lines.append(f"float $x{i} = $u{i} * $L;")
        lines.append(
            f"float $amp_u{i} = ($mode == 0) ? (1 - $u{i}) : (($mode == 2) ? (4 * $u{i} * (1 - $u{i})) : $u{i});"
        )
        lines.append(f"float $dx{i} = 0; float $dy{i} = 0;")
        lines.append("for ($h = 0; $h < 4; $h++) {")
        lines.append("  float $k = (2 * 3.14159 * $freq * $mult[$h]) / max(0.001, $L);")
        lines.append(f"  float $theta = $k * ($u{i} * $L) - $phase + $phaseOffsets[$h];")
        lines.append("  float $hAmp = $amp * $ampMult[$h] * $weights[$h];")
        lines.append(f"  $dx{i} += -$steep * $hAmp * $amp_u{i} * sin($theta);")
        lines.append(f"  $dy{i} += -$hAmp * $amp_u{i} * cos($theta);")
        lines.append("}")
        lines.append(f"{curve}.controlPoints[{i}].xValue = $x{i} + $dx{i};")
        lines.append(f"{curve}.controlPoints[{i}].yValue = $dy{i};")

    expr_node = cmds.expression(s="\n".join(lines), name=unique_name(ctx.node("WaveExpr")))
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
