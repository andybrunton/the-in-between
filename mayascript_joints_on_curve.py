import maya.cmds as cmds
import maya.api.OpenMaya as om2


def _sample_curve(crv, u_val):
    """Get world-space point + normalized tangent at a 0-1 arc-length fraction,
    independent of any pathAnimation / world-up guessing."""
    pos = cmds.pointOnCurve(crv, top=True, pr=u_val, position=True)
    tan = cmds.pointOnCurve(crv, top=True, pr=u_val, normalizedTangent=True)
    p = om2.MVector(pos)
    t = om2.MVector(tan).normal()
    return p, t


def _build_rmf(points, tangents):
    """Double Reflection Method (Wang/Juttler/Zheng/Liu 2008).
    Propagates a reference (up) vector along the curve with NO flips -
    each new frame is derived only from the previous one + local geometry,
    never from a fixed world axis after the seed."""
    world_up = om2.MVector(0, 1, 0)
    t0 = tangents[0]
    # seed reference: world up, projected perpendicular to first tangent.
    # fall back to world Z if the curve starts parallel to world Y.
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


def create_evenly_spaced_joints(name="curve_jnt", num_joints=5, front_axis='x', up_axis='y', up_offset=10.0):
    sel = cmds.ls(sl=True)
    if not sel:
        cmds.warning("Please select a valid curve.")
        return

    crv = sel[0]
    shapes = cmds.listRelatives(crv, shapes=True)
    if not shapes or cmds.nodeType(shapes[0]) != 'nurbsCurve':
        cmds.warning("Selected object is not a valid NURBS curve.")
        return

    if num_joints < 1:
        cmds.warning("Number of joints must be at least 1.")
        return

    cmds.undoInfo(openChunk=True)

    main_group = cmds.group(empty=True, name=f"{name}_setup_GRP")
    jnt_group = cmds.group(empty=True, name=f"{name}_jnt_GRP")
    up_group = cmds.group(empty=True, name=f"{name}_UpLoc_GRP")
    cmds.parent([jnt_group, up_group], main_group)

    created_joints = []

    try:
        form = cmds.getAttr(f"{shapes[0]}.form")
        if isinstance(form, (list, tuple)):
            form = form[0]
        is_closed = (int(form) > 0)

        u_vals = []
        for i in range(num_joints):
            if is_closed:
                u_vals.append(i / float(num_joints))
            else:
                u_vals.append(0.0 if num_joints == 1 else i / float(num_joints - 1))

        # Sample real curve geometry directly - no pathAnimation involved yet,
        # so there's nothing here that can flip.
        points, tangents = [], []
        for u in u_vals:
            p, t = _sample_curve(crv, u)
            points.append(p)
            tangents.append(t)

        up_vectors = _build_rmf(points, tangents)

        # Build the up-curve from RMF-derived offset points (guaranteed flip-free)
        up_curve_points = [list(p + up_offset * up) for p, up in zip(points, up_vectors)]
        curve_kwargs = {"point": up_curve_points, "name": f"{name}_upCrv", "degree": 3}
        if is_closed:
            curve_kwargs["periodic"] = True
        up_crv = cmds.curve(**curve_kwargs)
        cmds.parent(up_crv, main_group)

        # Now create the joints, drive them with pathAnimation, and feed each
        # one an Object-Up locator riding the clean up-curve.
        for i, u_val in enumerate(u_vals):
            cmds.select(clear=True)
            jnt = cmds.joint(name=f"{name}_{i:02d}")
            cmds.parent(jnt, jnt_group)
            created_joints.append(jnt)

            m_path = cmds.pathAnimation(
                jnt, curve=crv, fractionMode=True,
                follow=True, followAxis=front_axis, upAxis=up_axis
            )
            cmds.cutKey(m_path, time=(None, None), attribute='uValue')
            cmds.setAttr(f"{m_path}.uValue", u_val)

            up_loc = cmds.spaceLocator(name=f"{name}_upLoc_{i:02d}")[0]
            cmds.parent(up_loc, up_group)

            up_path = cmds.pathAnimation(up_loc, curve=up_crv, fractionMode=True)
            cmds.cutKey(up_path, time=(None, None), attribute='uValue')
            cmds.setAttr(f"{up_path}.uValue", u_val)

            cmds.setAttr(f"{m_path}.worldUpType", 1)  # Object Up
            cmds.connectAttr(f"{up_loc}.worldMatrix[0]", f"{m_path}.worldUpMatrix")

    except Exception as e:
        cmds.warning(f"Error generating joints: {e}")
    finally:
        cmds.undoInfo(closeChunk=True)

    return created_joints


# Example usage
if __name__ == "__main__":
    create_evenly_spaced_joints(name="my_curve_joint", num_joints=10, front_axis='x', up_axis='y')