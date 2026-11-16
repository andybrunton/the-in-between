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


def _owned_curve(guide_root, suffix):
    """The loop curve under this guide.

    The stored name is the one used at draw time. Renaming the component
    renames the node and leaves that string behind, so both rings can claim
    ``ring_C0_over_crv`` while neither node is called that.
    """
    long_root = (cmds.ls(_name(guide_root), long=True) or [None])[0]
    if not long_root:
        return ""
    kids = cmds.listRelatives(long_root, children=True, fullPath=True, type="transform") or []
    matches = [kid for kid in kids if kid.split("|")[-1].endswith(suffix)]
    if len(matches) != 1:
        return ""
    return matches[0]


def _remember_curve(guide_root, suffix, attr):
    """Find this guide's curve and write its current name back on the guide."""
    curve = _owned_curve(guide_root, suffix)
    node = _name(guide_root)
    if curve and cmds.attributeQuery(attr, node=node, exists=True):
        cmds.setAttr(node + "." + attr, curve.split("|")[-1], type="string")
    return curve


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
    # setWeights walks the component in vertex-id order, whatever order we hand it.
    paired = sorted(zip(vert_ids, rows), key=lambda item: item[0])
    vert_ids = [vert for vert, _row in paired]
    rows = [_row for _vert, _row in paired]
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


def _ring_skin(skin):
    """True for a cluster this component made. A painted mesh skin is not ours."""
    if skin.split("|")[-1].endswith("_ringSlide_skin"):
        return True
    return cmds.attributeQuery(_ID, node=skin, exists=True)


def _live_skin(mesh):
    """Skin to add this ring to.

    A rebuild deletes the joints and leaves our cluster behind. Only that
    cluster is dropped. A skin already on the mesh is kept, weights and all,
    so the ring can add its joints without clearing the rest of the body.
    """
    found = cmds.ls(cmds.listHistory(mesh, pruneDagObjects=True) or [], type="skinCluster") or []
    dead = []
    live = None
    for skin in found:
        try:
            influences = cmds.skinCluster(skin, query=True, influence=True) or []
        except RuntimeError:
            influences = []
        alive = bool(influences) and all(cmds.objExists(joint) for joint in influences)
        if alive:
            live = skin
        elif _ring_skin(skin):
            dead.append(skin)
        elif live is None:
            live = skin
    if dead:
        cmds.delete(dead)
    return live


def _deform_root(rig):
    """The first joint under jnt_org. That is the skeleton the mesh should bind to."""
    org = getattr(rig, "jnt_org", None)
    if org is None:
        return None
    children = cmds.listRelatives(org.name(), children=True, type="joint", fullPath=True) or []
    return children[0] if children else None


def _deform_joints(root):
    if not root or not cmds.objExists(root):
        return []
    below = cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True) or []
    return [root] + below


def _closest_joint(point, joints):
    best = None
    best_distance = None
    for joint in joints:
        distance = ring.length(ring.sub(point, _world_pos(joint)))
        if best is None or distance < best_distance:
            best = joint
            best_distance = distance
    return best


def _skin(mesh, comp_id, influences, over_ids, under_ids, bind_root=None):
    """Ring verts weight 1. Everything else stays at 0 so the bind does not dent.

    A blend of the center and a rim joint cannot sit on the next vertex, so
    the rest of each shell is left unweighted. A second ring on the same mesh
    adds its joints to the skin that is already there and writes only its own
    vertices, so it does not clear the first seam.
    """
    count = cmds.polyEvaluate(mesh, vertex=True)
    slot = _weight_slots(over_ids, under_ids)
    # The ring joints, plus the skeleton they hang from, so painting can continue
    # on the same skin. A ring with no skeleton binds its own joints only.
    bind = _deform_joints(bind_root)
    have = {joint.split("|")[-1] for joint in bind}
    for joint in influences:
        if joint.split("|")[-1] not in have:
            bind.append(joint)
    if not bind:
        bind = list(influences)
    for joint in bind:
        cmds.getAttr(joint + ".worldMatrix[0]")

    skin = _live_skin(mesh)
    if skin is None:
        columns = {joint.split("|")[-1]: index for index, joint in enumerate(bind)}
        rows = [[0.0] * len(bind) for _ in range(count)]
        for index, influence in slot.items():
            if 0 <= index < count:
                rows[index][columns[influences[influence].split("|")[-1]]] = 1.0
        created = cmds.skinCluster(
            bind,
            mesh,
            toSelectedBones=True,
            maximumInfluences=2,
            obeyMaxInfluences=False,
            normalizeWeights=0,
            skinMethod=0,
            name="{}_ringSlide_skin".format(mesh.split("|")[-1]),
        )
        skin = created[0] if isinstance(created, (list, tuple)) else created
        _apply_weights(skin, mesh, bind, rows)
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
    for plug in cmds.listConnections(
        joint + ".inverseScale", source=True, destination=False, plugs=True
    ) or []:
        cmds.disconnectAttr(plug, joint + ".inverseScale")
    return joint


def _place_joint(untwist, name, local, radius, spline_joints):
    """The joint, and the transform whose translate the slide drives.

    With no spline the joint itself lives under the control, so its translate
    is that space. With a spline the keys stay in the control's space, on a
    driver, and the joint is a child of the closest spline joint. A
    parentConstraint puts the joint on the driver. That bakes.
    """
    if not spline_joints:
        return _joint(untwist, name, local, radius), None
    driver = cmds.createNode(
        "transform", name=name.replace("_jnt", "_drv"), parent=untwist
    )
    cmds.setAttr(driver + ".translate", local[0], local[1], local[2])
    cmds.setAttr(driver + ".visibility", 0)
    parent = _closest_joint(_world_pos(driver), spline_joints)
    joint = _joint(parent, name, (0.0, 0.0, 0.0), radius)
    cmds.parentConstraint(driver, joint, maintainOffset=False)
    return joint, driver


def build_ring(
    comp_id, ctl, untwist, over_crv, under_crv, over_verts, under_verts, mesh,
    spline_joints=None, bind_root=None,
):
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

    parents = spline_joints or []
    center, _driver = _place_joint(
        untwist, comp_id + "_center_jnt", (0.0, 0.0, 0.0), radius * 1.6, parents
    )
    under_joints = []
    for index, local in enumerate(under):
        joint, _driver = _place_joint(
            untwist, "{}_under_{:03d}_jnt".format(comp_id, index), local, radius, parents
        )
        under_joints.append(joint)
    over_joints = []
    plug = ctl + ".ry"
    for index, local in enumerate(over):
        joint, driver = _place_joint(
            untwist, "{}_over_{:03d}_jnt".format(comp_id, index), local, radius, parents
        )
        keys = ring.slide_keys(local, under, normal, sign)
        target = driver or joint
        for channel, output in zip("xyz", _drive(comp_id, index, plug, keys)):
            cmds.connectAttr(output, target + "." + "t" + channel, force=True)
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
            bind_root,
        )
        if note:
            notes.append(note)
    else:
        notes.append("mesh is missing, so nothing was skinned")
    return notes, influences


def _centroid(points):
    if not points:
        return None
    count = float(len(points))
    return (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
        sum(point[2] for point in points) / count,
    )


def _world_pos(node):
    cmds.dgeval(node + ".worldMatrix[0]")
    return tuple(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _blend_index(point, positions):
    """(index, next index, weight of next) along an open chain."""
    if len(positions) < 2:
        return 0, 0, 0.0
    spans = []
    total = 0.0
    for index in range(len(positions) - 1):
        span = ring.length(ring.sub(positions[index + 1], positions[index]))
        spans.append(span)
        total += span
    if total < 1e-8:
        return 0, 0, 0.0
    distance = ring.chain_fraction(point, positions) * total
    walked = 0.0
    for index, span in enumerate(spans):
        if distance <= walked + span + 1e-6 or index == len(spans) - 1:
            weight = 0.0 if span < 1e-8 else min(1.0, max(0.0, (distance - walked) / span))
            return index, index + 1, weight
        walked += span
    return 0, 1, 0.0


def _numbered_joints(spine):
    joints = []
    for index in range(int(spine.settings["division"])):
        name = str(spine.getName("{}_jnt".format(index)))
        if cmds.objExists(name):
            joints.append(name)
    return joints


def _drop_control(comp, ctl):
    """Hide a control and keep it out of the anim set. Incoming drivers stay."""
    name = ctl.name() if hasattr(ctl, "name") else str(ctl)
    for shape in cmds.listRelatives(name, shapes=True, fullPath=True) or []:
        plug = shape + ".visibility"
        try:
            cmds.setAttr(plug, lock=False)
        except RuntimeError:
            pass
        for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(source, plug)
        cmds.setAttr(plug, 0)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
        plug = name + "." + attr
        try:
            cmds.setAttr(plug, lock=True, keyable=False, channelBox=False)
        except RuntimeError:
            cmds.setAttr(plug, keyable=False, channelBox=False)
    for members in comp.groups.values():
        if ctl in members:
            members.remove(ctl)
    if ctl in comp.controlers:
        comp.controlers.remove(ctl)


def _segment_u(point, origin, end):
    """Fraction of point along the segment from origin to end, clamped to 0-1."""
    span = ring.sub(end, origin)
    length = ring.length(span)
    if length < 1e-8:
        return 0.0
    return min(1.0, max(0.0, ring.dot(ring.sub(point, origin), span) / (length * length)))


def _mesh_shape(mesh):
    """The mesh before any deformer, so a stale skin cannot move the points."""
    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or []
    shown = [s for s in shapes if not cmds.getAttr(s + ".intermediateObject")]
    if not shown:
        return None
    count = cmds.polyEvaluate(shown[0], vertex=True)
    # A scene can hold stale intermediates from old binds. Only a same-sized one is this mesh.
    for shape in shapes:
        if cmds.getAttr(shape + ".intermediateObject") and cmds.polyEvaluate(shape, vertex=True) == count:
            return shape
    return shown[0]


def _shell_turn(mesh, vert, other, origin, end, seam):
    """Share of the head's turn for the shell holding `vert`, see ring.shell_turn.

    The mesh is separate shells that meet at the seams. Two loops on one
    connected shell have nothing to match, so both take the seam's own share.
    """
    import maya.api.OpenMaya as om

    shape = _mesh_shape(mesh)
    if shape is None:
        return seam
    selection = om.MSelectionList()
    selection.add(shape)
    dag = selection.getDagPath(0)
    walker = om.MItMeshVertex(dag)
    def flood(start):
        found = {start}
        todo = [start]
        while todo:
            walker.setIndex(todo.pop())
            for neighbour in walker.getConnectedVertices():
                if neighbour not in found:
                    found.add(neighbour)
                    todo.append(neighbour)
        return found

    shell = flood(vert)
    if other in shell:
        return seam
    far = len(flood(other))
    span = ring.sub(end, origin)
    length2 = ring.dot(span, span)
    if length2 < 1e-12:
        return seam
    points = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
    fractions = [
        ring.dot(ring.sub((points[i].x, points[i].y, points[i].z), origin), span) / length2
        for i in shell
    ]
    return ring.shell_turn(len(shell), far, sum(fractions) / len(fractions), seam)


def _follow_ring(npo, joints, positions, point, index=-1, lean=None):
    """Parent the seam to a spline joint so it rides the bend and keeps its place.

    index is the numbered joint to use. Below zero it blends the two joints
    either side of the seam. The joint carries the seam's place, pitch, bank,
    and the chest's own turn. The head's spin is not in it: that is added
    from the tip's rotateY, so it can run past 180.

    lean is (end joint, fraction): tilt the seam part way to the neck's end
    joint, which has the full pitch and bank and none of the head's spin. A
    spline barely tilts a joint a quarter of the way down the neck, so
    without this a seam would hardly follow the head.
    """
    for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
        try:
            cmds.setAttr(npo + "." + channel, lock=False)
        except RuntimeError:
            pass
    if 0 <= index < len(joints):
        picks = [(joints[index], 1.0)]
    else:
        low, high, weight = _blend_index(point, positions)
        if low == high or weight < 1e-4:
            picks = [(joints[low], 1.0)]
        elif weight > 1.0 - 1e-4:
            picks = [(joints[high], 1.0)]
        else:
            picks = [(joints[low], 1.0 - weight), (joints[high], weight)]
    names = [joint for joint, _ in picks]
    skip = ["x", "y", "z"] if lean else []
    cns = cmds.parentConstraint(*names, npo, maintainOffset=True, skipRotate=skip)[0]
    aliases = cmds.parentConstraint(cns, query=True, weightAliasList=True)
    for alias, (_, weight) in zip(aliases, picks):
        cmds.setAttr(cns + "." + alias, weight)
    if lean:
        end, fraction = lean
        # Blend on a helper, then hold the seam to it. Weights set after a
        # maintained offset would leave the seam off its rest pose.
        mix = cmds.createNode("transform", name=npo + "_lean")
        cmds.parent(mix, cmds.listRelatives(npo, parent=True, fullPath=True)[0])
        cmds.xform(mix, worldSpace=True, translation=cmds.xform(npo, query=True, worldSpace=True, translation=True))
        turn = cmds.orientConstraint(*names, end, mix)[0]
        aliases = cmds.orientConstraint(turn, query=True, weightAliasList=True)
        weights = [(1.0 - fraction) * weight for _, weight in picks] + [fraction]
        for alias, weight in zip(aliases, weights):
            cmds.setAttr(turn + "." + alias, weight)
        cmds.setAttr(mix + ".visibility", 0)
        cmds.orientConstraint(mix, npo, maintainOffset=True)
    cmds.dgeval(npo + ".worldMatrix[0]")


class Component(component.Main):
    """Shifter component. Joints are built after the control exists."""

    def setRelation(self):
        for name in self.guide.objectNames:
            self.relatives[name] = self.root
            self.controlRelatives[name] = self.root

    def addObjects(self):
        root = self.guide.root
        matrix = transform.getTransform(root)
        over_name = _remember_curve(root, "_over_crv", "overCrv")
        under_name = _remember_curve(root, "_under_crv", "underCrv")
        frame = ring.guide_frame(_curve_world(over_name), _curve_world(under_name))
        locals_ = [ring.to_local(point, *frame) for point in _curve_world(over_name)] if frame else []
        if frame:
            # The guide root aims at its first vertex, so it is not used. Stand
            # the control on the line between the rings, square to the world.
            # With a parent component, postScript lines it up with that instead.
            # Set here, not afterwards: addCtl locks the parent transform.
            matrix = datatypes.Matrix(_matrix_list(frame))
        self.ctl_npo = primitive.addTransform(self.root, self.getName("ctl_npo"), matrix)
        # Above the control, so a neck twist turns both loops. The control's
        # own rotateY is cancelled and only slides the over loop ahead.
        self.spin = primitive.addTransform(self.ctl_npo, self.getName("spin"), matrix)
        width = self.size
        if locals_:
            width = max(math.hypot(point[0], point[2]) for point in locals_) * 2.2
        self.ctl = self.addCtl(
            self.spin,
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

    def _built_control(self, guide_name):
        guide_name = (guide_name or "").strip()
        if not guide_name:
            return None
        found = self.rig.findControlRelative(guide_name)
        if found is None or found == self.rig.global_ctl:
            return None
        return found.name()

    def _hook_spline(self, spine, base, tip):
        """Drive the spline from the base and tip, once, and hide its controls.

        Same as owl_neck: ik1 follows the tip by position and is aimed at a
        point beyond it, so pitch and bank bend the neck. A spin about the
        aim cannot show up in that, so the seams read the tip's rotateY.
        """
        root = spine.root.name()
        if cmds.attributeQuery("ringSlideHook", node=root, exists=True):
            return True
        ik0 = spine.ik0_ctl.name()
        ik1 = spine.ik1_ctl.name()
        base_at = _world_pos(base)
        tip_at = _world_pos(tip)
        gap = ring.sub(tip_at, base_at)
        reach = ring.length(gap)
        if reach < 1e-6:
            pm.displayWarning("[ring_slide] Base and tip sit on the same spot.")
            return False
        cmds.parentConstraint(base, ik0, maintainOffset=True)
        # ik1 sits a little off the tip's pivot. Following the tip directly
        # would swing it round the pivot when the head twists. So ik1 follows
        # a pivot that sits at the tip and is aimed without the twist.
        pivot = cmds.createNode("transform", name=ik1 + "_pivot")
        cmds.parent(pivot, cmds.listRelatives(tip, parent=True, fullPath=True)[0])
        cmds.xform(pivot, worldSpace=True, translation=tip_at)
        cmds.pointConstraint(tip, pivot)
        cmds.setAttr(pivot + ".visibility", 0)
        # ponytail: a point one neck-length past the tip, with Z as the up hint.
        # It sits on the tip's own Y, the axis the head twists about, so a
        # spin leaves it where it is and only pitch and bank swing it. A
        # chain that runs along world Z flips; point the up vector elsewhere.
        target = cmds.createNode("transform", name=ik1 + "_aimTarget")
        cmds.parent(target, tip, relative=True)
        tip_y = cmds.xform(tip, query=True, worldSpace=True, matrix=True)[4:7]
        if ring.dot(tip_y, gap) < 0.0:
            tip_y = ring.mul(tip_y, -1.0)
        beyond = ring.add(tip_at, ring.mul(ring.norm(tip_y), reach))
        cmds.xform(target, worldSpace=True, translation=beyond)
        cmds.setAttr(target + ".visibility", 0)
        cmds.aimConstraint(
            target,
            pivot,
            aimVector=(0, 1, 0),
            upVector=(0, 0, 1),
            worldUpType="objectrotation",
            worldUpVector=(0, 0, 1),
            worldUpObject=ik0,
            maintainOffset=True,
        )
        cmds.parentConstraint(pivot, ik1, maintainOffset=True)
        for ctl in list(spine.controlers):
            _drop_control(spine, ctl)
        cmds.addAttr(root, ln="ringSlideHook", at="bool")
        cmds.setAttr(root + ".ringSlideHook", True)
        return True

    def _prepare_spline(self, over_crv, under_crv):
        """Orient this seam to the chain. Returns (twist plug, under %, over %)."""
        spine = self.rig.findComponent((self.settings.get("baseSpline") or "").strip())
        if spine is None:
            pm.displayWarning("[ring_slide] Base spline was not built.")
            return None, 0.0, 0.0
        joints = _numbered_joints(spine)
        base = self._built_control(self.settings.get("baseCtl"))
        tip = self._built_control(self.settings.get("tipCtl"))
        under = _centroid(_curve_world(under_crv))
        over = _centroid(_curve_world(over_crv))
        if not base or not tip or len(joints) < 2 or under is None or over is None:
            pm.displayWarning(
                "[ring_slide] Not built: Base Control '{}' -> {}, Tip Control '{}' -> {}, "
                "{} spline joints.".format(
                    self.settings.get("baseCtl"), base,
                    self.settings.get("tipCtl"), tip, len(joints),
                )
            )
            return None, 0.0, 0.0
        if not self._hook_spline(spine, base, tip):
            return None, 0.0, 0.0
        origin = _world_pos(base)
        end = _world_pos(tip)
        center = tuple((over[i] + under[i]) * 0.5 for i in range(3))
        index = int(self.settings.get("splineJoint", -1))
        if index >= len(joints):
            pm.displayWarning(
                "[ring_slide] Parent joint index {} is past the last joint ({}). "
                "Using the nearest joints.".format(index, len(joints) - 1)
            )
            index = -1
        self._spline_joints = joints
        _follow_ring(
            self.ctl_npo.name(),
            joints,
            [_world_pos(joint) for joint in joints],
            center,
            index,
            lean=(joints[-1], _segment_u(center, origin, end)),
        )
        # Each loop has to turn like the mesh shell it is stitched to, or the
        # edges between them stretch. Both loops spin by the under share; the
        # over loop slides on round the under loop by the difference. The
        # slide keys wrap at 360, so a factor of 1 is one lap per head turn.
        seam = _segment_u(under, origin, end)
        mesh = (self.settings.get("mesh") or "").split()[0].split(".")[0]
        over_ids = _vert_ids(self.settings.get("overVerts") or "")
        under_ids = _vert_ids(self.settings.get("underVerts") or "")

        def turn(name, mine, theirs):
            pct = int(self.settings.get(name, -1))
            if pct >= 0:
                return pct / 100.0
            if not mine or not theirs or not mesh or not cmds.objExists(mesh):
                return seam
            return _shell_turn(mesh, mine[0], theirs[0], origin, end, seam)

        under_turn = turn("underTurn", under_ids, over_ids)
        over_turn = turn("overTurn", over_ids, under_ids)
        # The seam's Y may point down the neck or back up it. The head's
        # turn is about its own Y, so flip both when the two disagree.
        seam_y = cmds.xform(self.spin.name(), query=True, worldSpace=True, matrix=True)[4:7]
        head_y = cmds.xform(tip, query=True, worldSpace=True, matrix=True)[4:7]
        self._twist_way = -1.0 if ring.dot(seam_y, head_y) < 0.0 else 1.0
        return tip + ".ry", under_turn, over_turn

    def _drive_twist(self, plug, under_pct, over_pct):
        """Spin both loops by the under share, slide the over loop by the difference.

        under_pct and over_pct are host attrs in percent. The sign from the
        seam's Y is a build constant, so the attrs read as the amount the user set.
        """
        scale = self._twist_way / 100.0
        spin = cmds.createNode("multDoubleLinear", name=self.getName("spinScale"))
        cmds.setAttr(spin + ".input2", scale)
        pm.connectAttr(under_pct, spin + ".input1")
        diff = cmds.createNode("plusMinusAverage", name=self.getName("slideDiff"))
        cmds.setAttr(diff + ".operation", 2)
        pm.connectAttr(over_pct, diff + ".input1D[0]")
        pm.connectAttr(under_pct, diff + ".input1D[1]")
        slide = cmds.createNode("multDoubleLinear", name=self.getName("slideScale"))
        cmds.setAttr(slide + ".input2", scale)
        cmds.connectAttr(diff + ".output1D", slide + ".input1")
        self._drive_angle(plug, spin + ".output", self.spin.name() + ".ry", "spinMul")
        self._drive_angle(plug, slide + ".output", self.ctl.name() + ".ry", "slideMul")

    def _drive_angle(self, plug, factor, target, node_name):
        cmds.setAttr(target, lock=False)
        conv = cmds.createNode("unitConversion", name=self.getName(node_name))
        cmds.addAttr(conv, ln=_ID, dataType="string")
        cmds.setAttr(conv + "." + _ID, self.fullName, type="string")
        cmds.connectAttr(factor, conv + ".conversionFactor")
        cmds.connectAttr(plug, conv + ".input")
        cmds.connectAttr(conv + ".output", target, force=True)

    def postScript(self):
        if not hasattr(self, "untwist"):
            pm.displayWarning("[ring_slide] The center was not built.")
            return
        over_crv = _remember_curve(self.guide.root, "_over_crv", "overCrv")
        under_crv = _remember_curve(self.guide.root, "_under_crv", "underCrv")
        twist = None
        under_turn = over_turn = 0.0
        self._spline_joints = []
        if (self.settings.get("baseSpline") or "").strip():
            twist, under_turn, over_turn = self._prepare_spline(over_crv, under_crv)
        else:
            self._align_to_parent()
        notes, joints = build_ring(
            comp_id=self.fullName,
            ctl=_name(self.ctl),
            untwist=_name(self.untwist),
            over_crv=over_crv,
            under_crv=under_crv,
            over_verts=self.settings.get("overVerts") or "",
            under_verts=self.settings.get("underVerts") or "",
            mesh=self.settings.get("mesh") or "",
            spline_joints=self._spline_joints,
            bind_root=_deform_root(self.rig),
        )
        if twist:
            # Host attrs, seeded from the build. Animate these to change the twist.
            # Full name, not the short prefix: two rings both called "ring" share one attr otherwise.
            under = self.addAnimParam(
                self.fullName + "_underTurn", "Under Turn", "double", under_turn * 100.0, exactName=True
            )
            over = self.addAnimParam(
                self.fullName + "_overTurn", "Over Turn", "double", over_turn * 100.0, exactName=True
            )
            self._drive_twist(twist, under, over)
            _drop_control(self, self.ctl)
        for joint in joints or []:
            self.jointList.append(pm.PyNode(joint))
        for note in notes:
            pm.displayWarning("[ring_slide] {}".format(note))
