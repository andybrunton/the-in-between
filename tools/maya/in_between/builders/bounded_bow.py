"""Bounded Bow — compression bulge along a chord-aligned curve."""

from __future__ import annotations

import math
from typing import Optional

import maya.cmds as cmds

from in_between.core.context import RigContext, RigResult
from in_between.core.drive import setup_drive
from in_between.core.dag_targets import validate_dag_target
from in_between.core.naming import sanitize_name, unique_name
from in_between.core.parents import parent_under, resolve_parents
from in_between.core.space_setup import (
    create_settings_locator,
    create_space_chain,
    rest_distance,
)
from in_between.joints.rmf_chain import create_joints_on_curve

# Demo defaults aligned with Bounded_Bow.html (L_REST=420, L_MIN=150, MAX_HEIGHT=180).
_MIN_LENGTH_RATIO = 150.0 / 420.0
_MAX_HEIGHT_RATIO = 180.0 / 420.0  # ~0.43
_DEG_TO_RAD = math.pi / 180.0


def _make_pma(pma_name: str, inputs: list[str], op: int = 1) -> str:
    pma = cmds.createNode("plusMinusAverage", name=unique_name(pma_name))
    cmds.setAttr(f"{pma}.operation", op)
    for i, plug in enumerate(inputs):
        cmds.connectAttr(plug, f"{pma}.input1D[{i}]")
    return f"{pma}.output1D"


def _connect_easing(name: str, t_plug: str, settings: str, mult_h_eff: str) -> str:
    """Compression remap t -> eased weight via choice (smooth/linear/slow/fast)."""
    mult_slow = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_EaseSlow"))
    cmds.connectAttr(t_plug, f"{mult_slow}.input1X")
    cmds.connectAttr(t_plug, f"{mult_slow}.input2X")

    pma_1mt = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_Ease1mT"))
    cmds.setAttr(f"{pma_1mt}.operation", 2)
    cmds.setAttr(f"{pma_1mt}.input1D[0]", 1.0)
    cmds.connectAttr(t_plug, f"{pma_1mt}.input1D[1]")

    mult_1mt_sq = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_EaseFastSq"))
    cmds.connectAttr(f"{pma_1mt}.output1D", f"{mult_1mt_sq}.input1X")
    cmds.connectAttr(f"{pma_1mt}.output1D", f"{mult_1mt_sq}.input2X")

    pma_fast = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_EaseFast"))
    cmds.setAttr(f"{pma_fast}.operation", 2)
    cmds.setAttr(f"{pma_fast}.input1D[0]", 1.0)
    cmds.connectAttr(f"{mult_1mt_sq}.outputX", f"{pma_fast}.input1D[1]")

    mult_t2 = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_EaseT2"))
    cmds.connectAttr(t_plug, f"{mult_t2}.input1X")
    cmds.connectAttr(t_plug, f"{mult_t2}.input2X")

    mult_2t = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_Ease2T"))
    cmds.connectAttr(t_plug, f"{mult_2t}.input1X")
    cmds.setAttr(f"{mult_2t}.input2X", 2.0)

    pma_3m2t = cmds.createNode("plusMinusAverage", name=unique_name(f"{name}_Ease3m2T"))
    cmds.setAttr(f"{pma_3m2t}.operation", 2)
    cmds.setAttr(f"{pma_3m2t}.input1D[0]", 3.0)
    cmds.connectAttr(f"{mult_2t}.outputX", f"{pma_3m2t}.input1D[1]")

    mult_smooth = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_EaseSmooth"))
    cmds.connectAttr(f"{mult_t2}.outputX", f"{mult_smooth}.input1X")
    cmds.connectAttr(f"{pma_3m2t}.output1D", f"{mult_smooth}.input2X")

    choice = cmds.createNode("choice", name=unique_name(f"{name}_EaseChoice"))
    cmds.connectAttr(f"{settings}.easingMode", f"{choice}.selector")
    cmds.connectAttr(f"{mult_smooth}.outputX", f"{choice}.input[0]")
    cmds.connectAttr(t_plug, f"{choice}.input[1]")
    cmds.connectAttr(f"{mult_slow}.outputX", f"{choice}.input[2]")
    cmds.connectAttr(f"{pma_fast}.output1D", f"{choice}.input[3]")
    cmds.connectAttr(f"{choice}.output", f"{mult_h_eff}.input1X")
    return choice


def _connect_bend_cos(name: str, settings: str, mult_bend_cos: str) -> str:
    """bendAngle (deg) -> cos(rad) multiplier for bulge height."""
    rad_mult = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_BendRad"))
    cmds.connectAttr(f"{settings}.bendAngle", f"{rad_mult}.input1X")
    cmds.setAttr(f"{rad_mult}.input2X", _DEG_TO_RAD)

    cos_node = cmds.createNode("cos", name=unique_name(f"{name}_Cos"))
    cmds.connectAttr(f"{rad_mult}.outputX", f"{cos_node}.input")
    cmds.connectAttr(f"{cos_node}.output", f"{mult_bend_cos}.input2X")
    return cos_node


def _bulge_arrow_curve(length: float) -> list:
    """Arrow along +Y — main bulge direction."""
    w = length * 0.18
    tip = length
    return [
        (0, 0, 0),
        (0, tip, 0),
        (-w, tip * 0.82, 0),
        (0, tip, 0),
        (w, tip * 0.82, 0),
    ]


def _lock_transform_channels(node: str, *, rotate_x: bool = False) -> None:
    """Channel box: all locked unless rotate_x (bulge twist around chord)."""
    for axis in ("X", "Y", "Z"):
        for kind in ("translate", "rotate", "scale"):
            attr = f"{kind}{axis}"
            if kind == "rotate" and axis == "X" and rotate_x:
                cmds.setAttr(f"{node}.{attr}", lock=False, keyable=True, channelBox=True)
            else:
                cmds.setAttr(f"{node}.{attr}", lock=True, keyable=False, channelBox=False)


def _read_bulge_twist_angle(bulge_twist: Optional[str]) -> float:
    if not bulge_twist or not cmds.objExists(bulge_twist):
        return 0.0
    return float(cmds.getAttr(f"{bulge_twist}.rotateX"))


def _delete_bulge_guide(base: str) -> None:
    for pattern in (f"{base}_Bulge*", f"{base}_Blade*"):
        for node in cmds.ls(pattern, transforms=True) or []:
            cmds.delete(node)


def place_bulge_arrow(start: str, end: str, rig_label: str) -> str:
    """
    Place a bulge-direction arrow at the chord midpoint.

    Chord = local +X. Arrow points +Y (main bulge). Only rotateX is unlocked —
    twist around the chord to aim the bulge. Build reads that angle.
    """
    start_obj = validate_dag_target(start, "Start")
    end_obj = validate_dag_target(end, "End")
    base = sanitize_name(rig_label) or "rig"
    _delete_bulge_guide(base)

    p1 = cmds.xform(start_obj, q=True, ws=True, t=True)
    p2 = cmds.xform(end_obj, q=True, ws=True, t=True)
    span = math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))
    mid = [(a + b) / 2.0 for a, b in zip(p1, p2)]

    grp = cmds.group(empty=True, name=unique_name(f"{base}_BulgeGrp"))
    twist = cmds.group(empty=True, name=unique_name(f"{base}_BulgeTwist"))
    cmds.parent(twist, grp)
    cmds.xform(grp, ws=True, translation=mid)
    cmds.aimConstraint(
        end_obj,
        grp,
        aimVector=(1, 0, 0),
        upVector=(0, 1, 0),
        worldUpType="objectrotation",
        worldUpObject=start_obj,
        worldUpVector=(0, 1, 0),
    )
    cmds.xform(grp, ws=True, translation=mid)

    length = max(span * 0.2, 2.0)
    arrow = cmds.curve(
        d=1,
        p=_bulge_arrow_curve(length),
        name=unique_name(f"{base}_BulgeArrow"),
    )
    cmds.parent(arrow, twist, relative=True)
    for shape in cmds.listRelatives(arrow, shapes=True) or []:
        cmds.setAttr(f"{shape}.overrideEnabled", 1)
        cmds.setAttr(f"{shape}.overrideColor", 20)

    _lock_transform_channels(grp)
    _lock_transform_channels(twist, rotate_x=True)
    _lock_transform_channels(arrow)
    cmds.select(twist, r=True)
    return twist


place_bow_blade = place_bulge_arrow


def build(ctx: RigContext) -> RigResult:
    name = ctx.base_name
    start_obj = ctx.start
    end_obj = ctx.end
    rest_dist = rest_distance(start_obj, end_obj)
    min_length = rest_dist * _MIN_LENGTH_RATIO
    max_height = rest_dist * _MAX_HEIGHT_RATIO

    local_p, world_p, joint_p = resolve_parents(
        ctx.local_parent, ctx.world_parent, ctx.joint_parent
    )

    bulge_angle = _read_bulge_twist_angle(ctx.bulge_twist)

    root, space_grp, orient_grp = create_space_chain(name, start_obj, end_obj)
    parent_under(root, local_p)

    settings = create_settings_locator(ctx.node("Settings"), root, start_obj, end_obj)
    parent_under(settings, world_p)

    cmds.addAttr(settings, ln="weight", at="float", dv=1.0, min=0.0, max=2.0, k=True)
    cmds.addAttr(settings, ln="tangentWeight", at="float", dv=0.55, min=0.0, max=1.0, k=True)
    cmds.addAttr(settings, ln="maxHeight", at="float", dv=max_height, min=0.0, k=True)
    cmds.addAttr(settings, ln="bendAngle", at="float", dv=bulge_angle, k=True)
    cmds.addAttr(
        settings,
        ln="easingMode",
        at="enum",
        en="smooth:linear:slow:fast",
        dv=0,
        k=True,
    )

    cmds.connectAttr(f"{settings}.bendAngle", f"{orient_grp}.rotateX")

    p_init = [(rest_dist * (i / 6.0), 0, 0) for i in range(7)]
    curve = cmds.curve(
        d=3,
        p=p_init,
        k=[0, 0, 0, 1, 1, 1, 2, 2, 2],
        name=unique_name(ctx.node("Crv")),
    )
    parent_under(curve, orient_grp)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        cmds.setAttr(f"{curve}.{attr}", 0)

    drive = setup_drive(name, ctx, settings, start_obj, end_obj, world_p, rest_dist, min_length)

    mult_L = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_L_Fracs"))
    cmds.connectAttr(drive.span_plug, f"{mult_L}.input1X")
    cmds.connectAttr(drive.span_plug, f"{mult_L}.input1Y")
    cmds.connectAttr(drive.span_plug, f"{mult_L}.input1Z")
    cmds.setAttr(f"{mult_L}.input2X", 0.5)
    cmds.setAttr(f"{mult_L}.input2Y", 0.25)
    cmds.setAttr(f"{mult_L}.input2Z", 0.75)

    mult_params = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_TangentScale"))
    cmds.connectAttr(f"{settings}.tangentWeight", f"{mult_params}.input1X")
    cmds.connectAttr(f"{mult_L}.outputX", f"{mult_params}.input2X")

    mult_T = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_T_Fracs"))
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1X")
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1Y")
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1Z")
    cmds.setAttr(f"{mult_T}.input2X", 0.5)
    cmds.setAttr(f"{mult_T}.input2Y", 0.25)
    cmds.setAttr(f"{mult_T}.input2Z", -0.25)

    mult_hEff = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_hEff_Base"))
    cmds.connectAttr(f"{settings}.weight", f"{mult_hEff}.input2X")

    mult_hEff_final = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_hEff_Final"))
    cmds.connectAttr(f"{settings}.maxHeight", f"{mult_hEff_final}.input2X")
    cmds.connectAttr(f"{mult_hEff}.outputX", f"{mult_hEff_final}.input1X")

    mult_bend_cos = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_BendCos"))
    cmds.connectAttr(f"{mult_hEff_final}.outputX", f"{mult_bend_cos}.input1X")

    mult_hEff_fracs = cmds.createNode("multiplyDivide", name=unique_name(f"{name}_hEff_Fracs"))
    cmds.connectAttr(f"{mult_bend_cos}.outputX", f"{mult_hEff_fracs}.input1X")
    cmds.connectAttr(f"{mult_bend_cos}.outputX", f"{mult_hEff_fracs}.input1Y")
    cmds.setAttr(f"{mult_hEff_fracs}.input2X", 0.5)
    cmds.setAttr(f"{mult_hEff_fracs}.input2Y", 0.75)

    # Compression remap -> easing -> bulge weight (matches card math).
    easing_choice = _connect_easing(name, drive.compression_plug, settings, mult_hEff)
    cos_node = _connect_bend_cos(name, settings, mult_bend_cos)

    cv2_x = _make_pma(f"{name}_CV2_X", [f"{mult_L}.outputY", f"{mult_T}.outputY"])
    cv4_x = _make_pma(f"{name}_CV4_X", [f"{mult_L}.outputZ", f"{mult_T}.outputZ"])
    span_end = drive.distance_plug or f"{settings}.restLength"
    cv5_x = _make_pma(f"{name}_CV5_X", [span_end, f"{mult_T}.outputX"], op=2)

    cvs = f"{curve}.controlPoints"
    cmds.connectAttr(f"{mult_T}.outputX", f"{cvs}[1].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputX", f"{cvs}[1].yValue")
    cmds.connectAttr(cv2_x, f"{cvs}[2].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[2].yValue")
    cmds.connectAttr(f"{mult_L}.outputX", f"{cvs}[3].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[3].yValue")
    cmds.connectAttr(cv4_x, f"{cvs}[4].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[4].yValue")
    cmds.connectAttr(cv5_x, f"{cvs}[5].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputX", f"{cvs}[5].yValue")
    cmds.connectAttr(drive.span_plug, f"{cvs}[6].xValue")

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

    if ctx.bulge_twist:
        _delete_bulge_guide(name)

    cmds.select(settings)
    return RigResult(
        root=root,
        settings=settings,
        curve=curve,
        joint_chain=joints,
        local_root=local_p,
        world_root=world_p,
        joint_root=joint_p,
        meta={
            "easing": easing_choice,
            "bend_cos": cos_node,
            "drive": drive,
        },
    )
