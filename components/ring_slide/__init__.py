"""One seam. Over joints slide along the under edge ring.

The center control's translate, rotateX, and rotateZ are inherited by both
rings. rotateY is cancelled under the control and used only as the slide.
Each over joint is moved in 3D to a stored offset from the under loop, so
the ring does not have to be round, oval, or flat.

Bake the joint translates before exporting. The anim curves stay in Maya.
"""

import math

import maya.cmds as cmds

import mgear.pymaya as pm
from mgear.pymaya import datatypes
from mgear.shifter import component
from mgear.core import attribute, primitive, transform

from . import ring

_ID = "ringSlideId"
_NORMAL = (0.0, 1.0, 0.0)


def _name(node):
    if hasattr(node, "name"):
        node = node.name()
    return str(node)


def _curve_world(curve):
    """World CV positions. A repeated closing CV is dropped."""
    if not curve or not cmds.objExists(curve):
        return []
    shapes = cmds.listRelatives(curve, shapes=True, fullPath=True, noIntermediate=True) or []
    if not shapes:
        return []
    shape = shapes[0]
    count = cmds.getAttr(shape + ".degree") + cmds.getAttr(shape + ".spans")
    points = []
    for index in range(count):
        points.append(tuple(cmds.pointPosition(shape + ".cv[%d]" % index, world=True)))
    if len(points) > 1 and ring.length(ring.sub(points[0], points[-1])) < 1e-5:
        points = points[:-1]
    return points


def _root_basis(root):
    matrix = cmds.xform(root, query=True, worldSpace=True, matrix=True)
    origin = (matrix[12], matrix[13], matrix[14])
    x = (matrix[0], matrix[1], matrix[2])
    y = (matrix[4], matrix[5], matrix[6])
    z = (matrix[8], matrix[9], matrix[10])
    return origin, x, y, z


def _matrix_list(frame):
    origin, x, y, z = frame
    return [
        x[0], x[1], x[2], 0.0,
        y[0], y[1], y[2], 0.0,
        z[0], z[1], z[2], 0.0,
        origin[0], origin[1], origin[2], 1.0,
    ]


def _node_frame(node):
    """World (origin, x, y, z) of a transform. Scale is dropped. None if degenerate."""
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    x = ring.norm(tuple(matrix[0:3]))
    y = ring.norm(tuple(matrix[4:7]))
    z = ring.norm(tuple(matrix[8:11]))
    if x is None or y is None or z is None:
        return None
    return (matrix[12], matrix[13], matrix[14]), x, y, z


def _locals(curve, basis):
    return [ring.to_local(point, *basis) for point in _curve_world(curve)]


def _vert_index(token):
    left = token.rfind("[")
    right = token.rfind("]")
    if left < 0 or right < left:
        return None
    try:
        return int(token[left + 1:right])
    except ValueError:
        return None


def _vert_ids(spec):
    found = []
    for token in (spec or "").split():
        index = _vert_index(token)
        if index is not None:
            found.append(index)
    return found


def _owned_curve(guide_root, suffix):
    """The loop curve under this guide.

    The stored name is whatever the curve was called when the guide was drawn.
    Renaming the component renames the curve and leaves that string behind, so
    a second ring still says ``ring_C0_over_crv`` and both builds read nothing.
    """
    long_root = (cmds.ls(_name(guide_root), long=True) or [None])[0]
    if not long_root:
        return ""
    kids = cmds.listRelatives(long_root, children=True, fullPath=True, type="transform") or []
    matches = [kid for kid in kids if kid.split("|")[-1].endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    return ""


def _take_curve(guide_root, suffix, attr):
    """Return this guide's curve, and store its current short name."""
    curve = _owned_curve(guide_root, suffix)
    node = _name(guide_root)
    if curve and cmds.attributeQuery(attr, node=node, exists=True):
        cmds.setAttr(node + "." + attr, curve.split("|")[-1], type="string")
    return curve or ""


def _delete_previous(comp_id):
    doomed = []
    for node in cmds.ls("*." + _ID, objectsOnly=True, long=True) or []:
        if cmds.getAttr(node + "." + _ID) == comp_id:
            doomed.append(node)
    leftover = cmds.ls(comp_id + "_k*") or []
    if doomed or leftover:
        cmds.delete(doomed + leftover)


def _drive(comp_id, index, plug, keys):
    """Three cycled curves from degrees to the joint's local translate."""
    outputs = []
    for axis in range(3):
        curve = cmds.createNode("animCurveUA", name="{}_k{}{}".format(comp_id, index, "xyz"[axis]))
        for angle, pos in keys:
            cmds.setKeyframe(
                curve,
                float=angle,
                value=pos[axis],
                inTangentType="linear",
                outTangentType="linear",
            )
        cmds.setAttr(curve + ".preInfinity", 3)
        cmds.setAttr(curve + ".postInfinity", 3)
        cmds.connectAttr(plug, curve + ".input")
        outputs.append(curve + ".output")
    return outputs


def _apply_weights(skin, mesh, influences, rows, vert_ids=None):
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma

    if vert_ids is None:
        vert_ids = list(range(len(rows)))
    sel = om.MSelectionList()
    sel.add(mesh)
    sel.add(skin)
    dag = sel.getDagPath(0)
    if dag.apiType() != om.MFn.kMesh:
        dag.extendToShape()
    fn = oma.MFnSkinCluster(sel.getDependNode(1))
    indices = om.MIntArray()
    for joint in influences:
        chosen = om.MSelectionList()
        chosen.add(joint)
        indices.append(fn.indexForInfluenceObject(chosen.getDagPath(0)))
    comp_fn = om.MFnSingleIndexedComponent()
    comp = comp_fn.create(om.MFn.kMeshVertComponent)
    comp_fn.addElements(om.MIntArray(vert_ids))
    flat = []
    for row in rows:
        flat.extend(row)
    fn.setWeights(dag, comp, indices, om.MDoubleArray(flat), False)


def _weight_slots(over_ids, under_ids):
    """Vertex id to index in [center, *under, *over]. Center is slot 0 and unused."""
    slot = {}
    for index, influence in zip(under_ids, range(1, 1 + len(under_ids))):
        slot[index] = influence
    start = 1 + len(under_ids)
    for index, influence in zip(over_ids, range(start, start + len(over_ids))):
        slot[index] = influence
    return slot


def _live_skin(mesh):
    """Skin whose influences are all still in the scene, or None.

    A rebuild deletes the joints and leaves the cluster. That cluster is
    dropped. A live one is shared, so a second ring can add its joints.
    """
    found = cmds.ls(cmds.listHistory(mesh, pruneDagObjects=True) or [], type="skinCluster") or []
    dead = []
    live = None
    for skin in found:
        try:
            influences = cmds.skinCluster(skin, query=True, influence=True) or []
        except RuntimeError:
            influences = []
        if influences and all(cmds.objExists(joint) for joint in influences):
            live = skin
        else:
            dead.append(skin)
    if dead:
        cmds.delete(dead)
    return live


def _skin(mesh, comp_id, influences, over_ids, under_ids):
    """Ring verts weight 1. Everything else stays at 0 so the bind does not dent.

    A blend of the center and a rim joint cannot sit on the next vertex, so
    the rest of each shell is left unweighted. A second ring on the same mesh
    adds its joints to the skin that is already there and writes only its own
    vertices, so it does not clear the first seam.
    """
    count = cmds.polyEvaluate(mesh, vertex=True)
    slot = _weight_slots(over_ids, under_ids)
    for joint in influences:
        cmds.getAttr(joint + ".worldMatrix[0]")

    skin = _live_skin(mesh)
    if skin is None:
        rows = [[0.0] * len(influences) for _ in range(count)]
        for index, influence in slot.items():
            if 0 <= index < count:
                rows[index][influence] = 1.0
        created = cmds.skinCluster(
            influences,
            mesh,
            toSelectedBones=True,
            maximumInfluences=2,
            obeyMaxInfluences=False,
            normalizeWeights=0,
            skinMethod=0,
            name="{}_ringSlide_skin".format(mesh.split("|")[-1]),
        )
        skin = created[0] if isinstance(created, (list, tuple)) else created
        _apply_weights(skin, mesh, influences, rows)
        return None

    cmds.setAttr(skin + ".normalizeWeights", 0)
    have = cmds.skinCluster(skin, query=True, influence=True) or []
    have_short = {joint.split("|")[-1] for joint in have}
    for joint in influences:
        if joint.split("|")[-1] in have_short:
            continue
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0, lockWeights=False)
    all_inf = cmds.skinCluster(skin, query=True, influence=True) or []
    columns = {joint.split("|")[-1]: index for index, joint in enumerate(all_inf)}
    ours = [joint.split("|")[-1] for joint in influences]
    vert_ids = []
    rows = []
    for vert, local_index in slot.items():
        if not 0 <= vert < count:
            continue
        row = [0.0] * len(all_inf)
        row[columns[ours[local_index]]] = 1.0
        vert_ids.append(vert)
        rows.append(row)
    if vert_ids:
        _apply_weights(skin, mesh, all_inf, rows, vert_ids)
    return None


def _joint(parent, name, local, radius):
    cmds.select(parent)
    joint = cmds.joint(name=name)
    cmds.setAttr(joint + ".translate", local[0], local[1], local[2])
    cmds.setAttr(joint + ".jointOrient", 0, 0, 0)
    cmds.setAttr(joint + ".radius", radius)
    cmds.setAttr(joint + ".segmentScaleCompensate", 0)
    return joint


def build_ring(comp_id, ctl, untwist, over_crv, under_crv, over_verts, under_verts, mesh):
    """Joints, slide curves, and a skin. Returns warning strings."""
    notes = []
    _delete_previous(comp_id)
    if not cmds.objExists(untwist) or not cmds.objExists(ctl):
        return ["center control is missing"], []
    basis = _root_basis(ctl)
    over = _locals(over_crv, basis)
    under = _locals(under_crv, basis)
    if len(over) < 3 or len(under) < 3:
        return ["the guide is missing an over or under loop"], []
    # The control may be aligned to a parent, so its Y is not always the ring normal.
    normal = ring.newell(under) or _NORMAL
    widest = max(over, key=lambda point: point[0] * point[0] + point[2] * point[2])
    sign = ring.twist_sign(widest, under, normal)

    edges = [ring.length(ring.sub(b, a)) for a, b in zip(over, over[1:] + over[:1])]
    radius = max(sum(edges) / float(len(edges)) * 0.35, 0.02)

    center = _joint(untwist, comp_id + "_center_jnt", (0.0, 0.0, 0.0), radius * 1.6)
    under_joints = []
    for index, local in enumerate(under):
        under_joints.append(_joint(
            untwist, "{}_under_{:03d}_jnt".format(comp_id, index), local, radius
        ))
    over_joints = []
    plug = ctl + ".ry"
    for index, local in enumerate(over):
        joint = _joint(
            untwist, "{}_over_{:03d}_jnt".format(comp_id, index), local, radius
        )
        keys = ring.slide_keys(local, under, normal, sign)
        for channel, output in zip("xyz", _drive(comp_id, index, plug, keys)):
            cmds.connectAttr(output, joint + "." + "t" + channel, force=True)
        over_joints.append(joint)

    influences = [center] + under_joints + over_joints
    mesh_name = (mesh or "").split()[0].split(".")[0] if mesh else ""
    if mesh_name and cmds.objExists(mesh_name):
        note = _skin(
            mesh_name,
            comp_id,
            influences,
            _vert_ids(over_verts),
            _vert_ids(under_verts),
        )
        if note:
            notes.append(note)
    else:
        notes.append("mesh is missing, so nothing was skinned")
    return notes, influences


class Component(component.Main):
    """Shifter component. Joints are built after the control exists."""

    def setRelation(self):
        for name in self.guide.objectNames:
            self.relatives[name] = self.root
            self.controlRelatives[name] = self.root

    def addObjects(self):
        root = self.guide.root
        matrix = transform.getTransform(root)
        over_name = root.attr("overCrv").get() if root.hasAttr("overCrv") else ""
        under_name = root.attr("underCrv").get() if root.hasAttr("underCrv") else ""
        frame = ring.guide_frame(_curve_world(over_name), _curve_world(under_name))
        locals_ = [ring.to_local(point, *frame) for point in _curve_world(over_name)] if frame else []
        if frame:
            # The guide root aims at its first vertex, so it is not used. Stand
            # the control on the line between the rings, square to the world.
            # With a parent component, postScript lines it up with that instead.
            # Set here, not afterwards: addCtl locks the parent transform.
            matrix = datatypes.Matrix(_matrix_list(frame))
        self.ctl_npo = primitive.addTransform(self.root, self.getName("ctl_npo"), matrix)
        width = self.size
        if locals_:
            width = max(math.hypot(point[0], point[2]) for point in locals_) * 2.2
        self.ctl = self.addCtl(
            self.ctl_npo,
            "ctl",
            matrix,
            self.color_ik,
            "circle",
            w=width,
            tp=self.parentCtlTag,
        )
        attribute.setKeyableAttributes(
            self.ctl, ["tx", "ty", "tz", "rx", "ry", "rz"]
        )

        # A child that also receives the control's translate would move twice.
        # Cancel rotateY here so both rings inherit pitch, bank, and translate,
        # and the channel is free to drive the slide. Factor -1 stays on an
        # angle connection, so no unit conversion turns the twist into radians.
        self.untwist = primitive.addTransform(
            self.ctl, self.getName("untwist"), matrix
        )
        untwist = self.untwist.name()
        cmds.setAttr(untwist + ".translate", 0, 0, 0)
        cmds.setAttr(untwist + ".rotate", 0, 0, 0)
        cmds.setAttr(untwist + ".scale", 1, 1, 1)
        flip = cmds.createNode("unitConversion", name=self.getName("untwistMul"))
        cmds.setAttr(flip + ".conversionFactor", -1)
        cmds.connectAttr(self.ctl.name() + ".ry", flip + ".input")
        cmds.connectAttr(flip + ".output", untwist + ".ry")
        for channel in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
            cmds.setAttr(untwist + "." + channel, lock=True, keyable=False)

    def _align_to_parent(self):
        """Put the center control exactly on the control this component hangs from.

        Done after Connect, so the parent is the built control, which can
        differ from its guide (a control_01 ignores the guide's rotation
        unless World Space Orientation Align is off).
        """
        name = (self.settings.get("parentComp") or "").strip()
        if not name:
            return
        found = cmds.listRelatives(self.root.name(), parent=True, fullPath=True) or []
        frame = _node_frame(found[0]) if found else None
        if frame is None:
            pm.displayWarning("[ring_slide] Parent '{}' has no control to line up with.".format(name))
            return
        # addCtl locked this node. xform ignores locked channels without a word.
        npo = self.ctl_npo.name()
        channels = [npo + "." + name for name in ("tx", "ty", "tz", "rx", "ry", "rz")]
        locked = [plug for plug in channels if cmds.getAttr(plug, lock=True)]
        for plug in locked:
            cmds.setAttr(plug, lock=False)
        cmds.xform(npo, worldSpace=True, matrix=_matrix_list(frame))
        for plug in locked:
            cmds.setAttr(plug, lock=True)

    def postScript(self):
        if not hasattr(self, "untwist"):
            pm.displayWarning("[ring_slide] The center was not built.")
            return
        self._align_to_parent()
        notes, joints = build_ring(
            comp_id=self.fullName,
            ctl=_name(self.ctl),
            untwist=_name(self.untwist),
            over_crv=self.settings.get("overCrv") or "",
            under_crv=self.settings.get("underCrv") or "",
            over_verts=self.settings.get("overVerts") or "",
            under_verts=self.settings.get("underVerts") or "",
            mesh=self.settings.get("mesh") or "",
        )
        for joint in joints or []:
            self.jointList.append(pm.PyNode(joint))
        for note in notes:
            pm.displayWarning("[ring_slide] {}".format(note))
