"""RMF joint chain on a NURBS curve — driver + skin split for clean hierarchy."""

from __future__ import annotations

from typing import List, Optional, Tuple

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from in_between.core.naming import unique_name
from in_between.core.parents import parent_under


def _sample_curve(crv: str, u_val: float) -> Tuple[om2.MVector, om2.MVector]:
    """World-space sample — driver joints live outside the local rig chain."""
    pos = cmds.pointOnCurve(
        crv, turnOnPercentage=True, parameter=u_val, position=True
    )
    tan = cmds.pointOnCurve(
        crv, turnOnPercentage=True, parameter=u_val, normalizedTangent=True
    )
    return om2.MVector(pos), om2.MVector(tan).normal()


def _build_rmf(points, tangents):
    world_up = om2.MVector(0, 1, 0)
    t0 = tangents[0]
    if abs(t0 * world_up) > 0.999:
        world_up = om2.MVector(0, 0, 1)
    r0 = (world_up - (t0 * world_up) * t0).normal()

    refs = [r0]
    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        t_i, t_ip1 = tangents[i], tangents[i + 1]
        r_i = refs[i]

        v1 = p1 - p0
        c1 = v1 * v1
        if c1 < 1e-10:
            refs.append(r_i)
            continue
        r_iL = r_i - (2.0 / c1) * (v1 * r_i) * v1
        t_iL = t_i - (2.0 / c1) * (v1 * t_i) * v1

        v2 = t_ip1 - t_iL
        c2 = v2 * v2
        if c2 < 1e-10:
            r_ip1 = r_iL
        else:
            r_ip1 = r_iL - (2.0 / c2) * (v2 * r_iL) * v2

        refs.append(r_ip1.normal())

    return refs


def _align_skin_joint(skin: str, driver: str) -> None:
    """
    Snap skin joint to driver, bake rotation into jointOrient, keep translate.
    Rotate attrs stay zero — ready for game-engine export.
    """
    cmds.dgeval(driver)
    cmds.matchTransform(skin, driver, pos=True, rot=True)
    cmds.makeIdentity(
        skin, apply=True, translate=False, rotate=True, scale=False, jointOrient=True
    )
    cmds.setAttr(f"{skin}.segmentScaleCompensate", 0)


def _force_dag_eval(nodes: List[str]) -> None:
    """Flush DG so world matrices match the current frame before binding offsets."""
    t = cmds.currentTime(query=True)
    cmds.currentTime(t, edit=True)
    if nodes:
        cmds.dgeval(nodes)


def _rebind_skin_constraints(pairs: List[Tuple[str, str]], eval_nodes: List[str]) -> None:
    """Re-snap skin joints once the hierarchy has fully evaluated."""
    _force_dag_eval(eval_nodes)
    for skin, driver in pairs:
        for con in cmds.listRelatives(skin, type="parentConstraint") or []:
            cmds.delete(con)
        _align_skin_joint(skin, driver)
        cmds.parentConstraint(driver, skin, maintainOffset=True)
    cmds.refresh(force=True)


def create_joints_on_curve(
    curve: str,
    name_prefix: str,
    num_joints: int = 8,
    joint_parent_group: Optional[str] = None,
    world_parent_group: Optional[str] = None,
    rig_root: Optional[str] = None,
    user_joint_parent: Optional[str] = None,
    front_axis: str = "x",
    up_axis: str = "y",
    up_offset: float = 10.0,
) -> List[str]:
    """
    Build an RMF joint chain on a curve.

    Driver joints sit under world_parent_group (motion path only). Skin joints
    are direct children of joint_parent_group (nested under rig_root when
    auto-created), oriented via jointOrient, then parent-constrained to drivers.
    """
    shapes = cmds.listRelatives(curve, shapes=True) or []
    if not shapes or cmds.nodeType(shapes[0]) != "nurbsCurve":
        cmds.warning("Curve has no nurbsCurve shape.")
        return []

    if num_joints < 1:
        return []

    if rig_root and joint_parent_group and not user_joint_parent:
        parent_under(joint_parent_group, rig_root)

    base = unique_name(name_prefix)
    drv_group = cmds.group(empty=True, name=unique_name(f"{base}_drv_GRP"))
    up_group = cmds.group(empty=True, name=unique_name(f"{base}_UpLoc_GRP"))

    if world_parent_group:
        parent_under(drv_group, world_parent_group)
        parent_under(up_group, world_parent_group)

    skin_joints: List[str] = []
    driver_joints: List[str] = []
    form = cmds.getAttr(f"{shapes[0]}.form")
    if isinstance(form, (list, tuple)):
        form = form[0]
    is_closed = int(form) > 0

    u_vals = []
    for i in range(num_joints):
        if is_closed:
            u_vals.append(i / float(num_joints))
        else:
            u_vals.append(0.0 if num_joints == 1 else i / float(num_joints - 1))

    points, tangents = [], []
    for u in u_vals:
        p, t = _sample_curve(curve, u)
        points.append(p)
        tangents.append(t)

    up_vectors = _build_rmf(points, tangents)
    up_curve_points = [list(p + up_offset * up) for p, up in zip(points, up_vectors)]
    curve_kwargs = {"point": up_curve_points, "name": unique_name(f"{base}_upCrv"), "degree": 3}
    if is_closed:
        curve_kwargs["periodic"] = True
    up_crv = cmds.curve(**curve_kwargs)
    parent_under(up_crv, up_group)

    for i, u_val in enumerate(u_vals):
        cmds.select(clear=True)
        drv = cmds.joint(name=unique_name(f"{base}_drv_jnt_{i:02d}"))
        parent_under(drv, drv_group)
        cmds.setAttr(f"{drv}.visibility", 0)

        m_path = cmds.pathAnimation(
            drv,
            curve=curve,
            fractionMode=True,
            follow=True,
            followAxis=front_axis,
            upAxis=up_axis,
        )
        cmds.cutKey(m_path, time=(None, None), attribute="uValue")
        cmds.setAttr(f"{m_path}.uValue", u_val)

        up_loc = cmds.spaceLocator(name=unique_name(f"{base}_upLoc_{i:02d}"))[0]
        parent_under(up_loc, up_group)
        cmds.setAttr(f"{up_loc}.visibility", 0)

        up_path = cmds.pathAnimation(up_loc, curve=up_crv, fractionMode=True)
        cmds.cutKey(up_path, time=(None, None), attribute="uValue")
        cmds.setAttr(f"{up_path}.uValue", u_val)

        cmds.setAttr(f"{m_path}.worldUpType", 1)
        cmds.connectAttr(f"{up_loc}.worldMatrix[0]", f"{m_path}.worldUpMatrix")

        cmds.select(clear=True)
        skin = cmds.joint(name=unique_name(f"{base}_jnt_{i:02d}"))
        if joint_parent_group:
            parent_under(skin, joint_parent_group)

        _align_skin_joint(skin, drv)
        cmds.parentConstraint(drv, skin, maintainOffset=True)
        driver_joints.append(drv)
        skin_joints.append(skin)

    pairs = list(zip(skin_joints, driver_joints))
    eval_nodes = [drv_group, up_group, curve]
    if rig_root:
        eval_nodes.append(rig_root)
    if joint_parent_group:
        eval_nodes.append(joint_parent_group)
    eval_nodes.extend(driver_joints)
    eval_nodes.extend(skin_joints)

    _rebind_skin_constraints(pairs, eval_nodes)
    cmds.evalDeferred(
        lambda p=pairs, n=eval_nodes: _rebind_skin_constraints(p, n),
        lowestPriority=True,
    )

    return skin_joints
