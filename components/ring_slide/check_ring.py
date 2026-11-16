"""Draw two edge rings and assert the over joints slide along the under one.

Run::

    $env:MAYA_MODULE_PATH="C:\\Users\\andre\\Documents\\GitHub\\mgear\\release"
    & "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" components\\ring_slide\\check_ring.py
"""

import math
import os
import sys

import maya.standalone

maya.standalone.initialize()

import maya.api.OpenMaya as om
import maya.cmds as cmds

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from ring_slide import ring


def _dist(a, b):
    return ring.length(ring.sub(a, b))


def _deformed(mesh):
    shape = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True)[0]
    cmds.dgeval(shape + ".worldMesh[0]")
    selection = om.MSelectionList()
    selection.add(shape)
    fn = om.MFnMesh(selection.getDagPath(0))
    return [tuple(point)[:3] for point in fn.getPoints(om.MSpace.kWorld)]


def _loop_edges(mesh, height):
    flat = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
    chosen = set()
    for index in range(0, len(flat), 3):
        point = (flat[index], flat[index + 1], flat[index + 2])
        if abs(point[1] - height) > 0.05:
            continue
        if (point[0] ** 2 + point[2] ** 2) ** 0.5 < 0.2:
            continue
        chosen.add(index // 3)
    keep = []
    for edge in cmds.ls(mesh + ".e[*]", flatten=True):
        verts = cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)
        ids = [int(vert.split("[")[-1].rstrip("]")) for vert in verts]
        if len(ids) == 2 and ids[0] in chosen and ids[1] in chosen:
            keep.append(edge)
    return keep


def _local(joint):
    return tuple(cmds.getAttr(joint + ".translate")[0])


def _world(node):
    cmds.getAttr(node + ".worldMatrix[0]")
    return tuple(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _in_space(node, space):
    """node's world position in space's local axes. Slide lives there, not in the joint's parent."""
    matrix = cmds.xform(space, query=True, worldSpace=True, matrix=True)
    origin = (matrix[12], matrix[13], matrix[14])
    axes = (
        (matrix[0], matrix[1], matrix[2]),
        (matrix[4], matrix[5], matrix[6]),
        (matrix[8], matrix[9], matrix[10]),
    )
    return ring.to_local(_world(node), origin, *axes)


def _check():
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import mgear.pymaya as pm
    import mgear.shifter as shifter
    import ring_guide

    # Vertex ids that do not go around the loop. A batch position query
    # returns them in index order and the guide draws chords.
    facet = cmds.polyCreateFacet(
        point=[(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        name="ord",
        constructionHistory=False,
    )[0]
    scrambled = [facet + ".vtx[0]", facet + ".vtx[2]", facet + ".vtx[1]", facet + ".vtx[3]"]
    got = ring_guide._positions(scrambled)
    if got[1] != (1.0, 0.0, 1.0) or got[2] != (1.0, 0.0, 0.0):
        raise AssertionError("positions came back in index order: {}".format(got))
    cmds.delete(facet)

    mesh = cmds.polyCylinder(
        name="ringGeo",
        radius=1.0,
        height=4.0,
        subdivisionsX=8,
        subdivisionsY=2,
        axis=(0, 1, 0),
        constructionHistory=False,
    )[0]
    cmds.xform(mesh, worldSpace=True, translation=(0, 2, 0))
    cmds.setAttr(mesh + ".scaleX", 1.8)
    cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)

    over_edges = _loop_edges(mesh, 4.0)
    under_edges = _loop_edges(mesh, 2.0)
    if len(over_edges) != 8 or len(under_edges) != 8:
        raise AssertionError("loops {} {}".format(len(over_edges), len(under_edges)))
    one = ring_guide._ordered_verts(over_edges[0])
    if one is None or len(one) != 8:
        raise AssertionError("one edge did not grow into the ring: {}".format(one))
    # Tilt it, so the control can only be square if it was really aligned.
    cmds.xform(mesh, worldSpace=True, rotation=(30, 0, 20), rotateAxis=(0, 0, 0))
    cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)

    shifter.clearComponentCache()
    root = ring_guide.create_guide(" ".join(over_edges), " ".join(under_edges))
    if not root:
        raise AssertionError("guide was not drawn")
    curves = cmds.ls("ring_*_over_crv", "ring_*_under_crv") or []
    if len(curves) != 2:
        raise AssertionError("guide loops missing: {}".format(curves))

    cmds.select("guide")
    shifter.Rig().buildFromSelection()

    ctl = cmds.ls("ring_C0_ctl", type="transform")
    over = cmds.ls("ring_C0_over_*_jnt", type="joint") or []
    under = cmds.ls("ring_C0_under_*_jnt", type="joint") or []
    center = cmds.ls("ring_C0_center_jnt", type="joint") or []
    if len(ctl) != 1 or len(over) != 8 or len(under) != 8 or len(center) != 1:
        raise AssertionError("rig counts ctl {} over {} under {} center {}".format(
            ctl, len(over), len(under), len(center)
        ))
    ctl = ctl[0]
    over = sorted(over)
    under = sorted(under)

    rest_over = [_world(joint) for joint in over]
    rest_under = [_world(joint) for joint in under]
    over_local = [_local(joint) for joint in over]
    under_local = [_local(joint) for joint in under]
    flat = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
    verts = [tuple(flat[index:index + 3]) for index in range(0, len(flat), 3)]

    def nearest(point):
        return min(range(len(verts)), key=lambda index: _dist(verts[index], point))

    over_ids = [nearest(point) for point in rest_over]
    for joint_at, index in zip(rest_over, over_ids):
        if _dist(joint_at, verts[index]) > 0.02:
            raise AssertionError("over joint off the vertex {} {}".format(joint_at, verts[index]))
    under_ids = [nearest(point) for point in rest_under]
    for joint_at, index in zip(rest_under, under_ids):
        if _dist(joint_at, verts[index]) > 0.02:
            raise AssertionError("under joint off the vertex")

    xs = [point[0] for point in rest_over]
    zs = [point[2] for point in rest_over]
    if max(xs) - min(xs) < 0.5 or max(zs) - min(zs) < 0.5:
        raise AssertionError("over joints collapsed onto one axis")

    matrix = cmds.xform(ctl, query=True, worldSpace=True, matrix=True)
    axis_up = ring.norm(ring.sub(ring.centroid(rest_over), ring.centroid(rest_under)))
    if ring.dot((matrix[4], matrix[5], matrix[6]), axis_up) < 0.999:
        raise AssertionError("control Y is off the line between the rings: {}".format(matrix[4:7]))
    if abs(matrix[0]) < 0.9 and abs(matrix[8]) < 0.9:
        raise AssertionError("control is rolled: {}".format(matrix[0:3]))
    sign = ring.twist_sign(
        max(over_local, key=lambda point: point[0] * point[0] + point[2] * point[2]),
        under_local,
        (0.0, 1.0, 0.0),
    )
    probe = cmds.spaceLocator(name="spinProbe")[0]
    cmds.parent(probe, ctl, relative=True)
    cmds.setAttr(probe + ".translate", 1, 0, 0)
    origin = _world(ctl)
    axis = (matrix[4], matrix[5], matrix[6])
    probe_rest = _world(probe)
    joint_rest = _world(over[0])
    cmds.setAttr(ctl + ".ry", 20)

    def _spin(rest, moved):
        radius = ring.sub(rest, origin)
        delta = ring.sub(moved, rest)
        return ring.dot(ring.cross(radius, delta), axis)

    if _spin(probe_rest, _world(probe)) * _spin(joint_rest, _world(over[0])) <= 0:
        raise AssertionError("over joints oppose the control")
    cmds.setAttr(ctl + ".ry", 0)
    cmds.delete(probe)

    cmds.setAttr(ctl + ".ry", 180)
    for joint in over + under:
        cmds.getAttr(joint + ".worldMatrix[0]")
    for joint, local, home in zip(under, under_local, rest_under):
        if _dist(_local(joint), local) > 1e-4 or _dist(_world(joint), home) > 0.02:
            raise AssertionError("under joint slid on twist {} {}".format(home, _world(joint)))
    for joint, local, home in zip(over, over_local, rest_over):
        got = _local(joint)
        want = ring.slide_position(local, under_local, (0.0, 1.0, 0.0), 0.5 * sign)
        if _dist(got, want) > 1e-3:
            raise AssertionError("over joint {} wanted {} got {}".format(joint, want, got))
        if _dist(_world(joint), home) < 0.2:
            raise AssertionError("over joint did not travel")

    cmds.setAttr(ctl + ".ry", 360)
    for joint, home in zip(over, rest_over):
        cmds.getAttr(joint + ".worldMatrix[0]")
        if _dist(_world(joint), home) > 0.02:
            raise AssertionError("full turn did not return")
    cmds.setAttr(ctl + ".ry", 40)
    at_40 = [_local(joint) for joint in over]
    cmds.setAttr(ctl + ".ry", 400)
    for joint, home in zip(over, at_40):
        if _dist(_local(joint), home) > 1e-3:
            raise AssertionError("twist did not wrap past 360")

    cmds.setAttr(ctl + ".ry", 0)
    cmds.setAttr(ctl + ".rx", 25)
    cmds.getAttr(under[0] + ".worldMatrix[0]")
    if _dist(_world(under[0]), rest_under[0]) < 0.05:
        raise AssertionError("pitch did not move the under ring")
    if _dist(_local(under[0]), under_local[0]) > 1e-4:
        raise AssertionError("pitch changed the under local position")
    if _dist(_local(over[0]), over_local[0]) > 1e-3:
        raise AssertionError("pitch changed the over slide")

    cmds.setAttr(ctl + ".rx", 0)
    cmds.setAttr(ctl + ".ry", 0)
    before = _deformed(mesh)
    cmds.setAttr(ctl + ".ry", 90)
    twisted = _deformed(mesh)
    cmds.setAttr(ctl + ".ry", 0)
    cmds.setAttr(ctl + ".rx", 25)
    pitched = _deformed(mesh)

    # The bottom loop is on neither ring, so it keeps no weight and stays put.
    seam = set(over_ids + under_ids)
    bottom = min(range(len(before)), key=lambda index: before[index][1])
    if bottom in seam:
        raise AssertionError("bottom vert is a seam vert")
    if _dist(twisted[over_ids[0]], before[over_ids[0]]) < 0.2:
        raise AssertionError("seam vert did not slide")
    if _dist(twisted[under_ids[0]], before[under_ids[0]]) > 0.02:
        raise AssertionError("under vert slid")
    if _dist(twisted[bottom], before[bottom]) > 0.02:
        raise AssertionError("bottom vert moved on twist")
    if _dist(pitched[bottom], before[bottom]) > 0.02:
        raise AssertionError("bottom vert moved on pitch")
    moved = sum(1 for a, b in zip(before, twisted) if _dist(a, b) > 0.02)
    if moved < 8:
        raise AssertionError("mesh did not slide ({})".format(moved))
    print("ring_slide check ok", "moved", moved)


def _check_parent():
    """The center control sits exactly on a tilted parent, and still slides."""
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import mgear.pymaya as pm
    import mgear.shifter as shifter
    import ring_guide

    mesh = cmds.polyCylinder(
        name="parentGeo", radius=1.0, height=4.0, subdivisionsX=8, subdivisionsY=2,
        axis=(0, 1, 0), constructionHistory=False,
    )[0]
    cmds.xform(mesh, worldSpace=True, translation=(0, 2, 0))
    cmds.setAttr(mesh + ".scaleX", 1.8)
    cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)
    over_edges = _loop_edges(mesh, 4.0)
    under_edges = _loop_edges(mesh, 2.0)

    shifter.clearComponentCache()
    guide_rig = shifter.guide.Rig()
    guide_rig.initialHierarchy()
    comp = guide_rig.getComponentGuide("control_01")
    comp.setParamDefValue("comp_name", "head")
    comp.setParamDefValue("neutralRotation", False)
    comp.draw(pm.PyNode("guide"))
    parent_root = comp.root.longName()
    cmds.xform(parent_root, worldSpace=True, translation=(0.3, 5.0, -0.2), rotation=(20, 35, 10))

    root = ring_guide.create_guide(
        " ".join(over_edges), " ".join(under_edges), parent_comp=parent_root
    )
    if not root:
        raise AssertionError("guide was not drawn")
    if cmds.getAttr(root + ".parentComp") != parent_root.split("|")[-1]:
        raise AssertionError("parent was not stored")
    cmds.select("guide")
    shifter.Rig().buildFromSelection()

    ctl = "ring_C0_ctl"
    want = cmds.xform("head_C0_ctl", query=True, worldSpace=True, matrix=True)
    if abs(want[0] - 1.0) < 0.05:
        raise AssertionError("the parent control is not tilted, so this proves nothing")
    got = cmds.xform(ctl, query=True, worldSpace=True, matrix=True)
    for index in (0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14):
        if abs(got[index] - want[index]) > 1e-3:
            roots = {
                node: cmds.listRelatives(node, parent=True, fullPath=True)
                for node in cmds.ls("ring_C0_root", long=True)
            }
            raise AssertionError("control is off the parent at {}: {} {} {}".format(
                index, got[index], want[index], roots
            ))

    over = sorted(cmds.ls("ring_C0_over_*_jnt", type="joint"))
    under = sorted(cmds.ls("ring_C0_under_*_jnt", type="joint"))
    if len(over) != 8 or len(under) != 8:
        raise AssertionError("joint counts {} {}".format(len(over), len(under)))
    flat = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)
    verts = [tuple(flat[index:index + 3]) for index in range(0, len(flat), 3)]
    rest_over = [_world(joint) for joint in over]
    rest_under = [_world(joint) for joint in under]
    for joint_at in rest_over + rest_under:
        if min(_dist(joint_at, vert) for vert in verts) > 0.02:
            raise AssertionError("joint off the mesh at {}".format(joint_at))

    under_local = [_local(joint) for joint in under]
    over_local = [_local(joint) for joint in over]
    normal = ring.newell(under_local)
    sign = ring.twist_sign(
        max(over_local, key=lambda point: point[0] * point[0] + point[2] * point[2]),
        under_local,
        normal,
    )
    cmds.setAttr(ctl + ".ry", 180)
    for joint in over + under:
        cmds.getAttr(joint + ".worldMatrix[0]")
    for joint, local, home in zip(under, under_local, rest_under):
        if _dist(_local(joint), local) > 1e-4 or _dist(_world(joint), home) > 0.02:
            raise AssertionError("under joint slid on twist")
    for joint, local, home in zip(over, over_local, rest_over):
        wanted = ring.slide_position(local, under_local, normal, 0.5 * sign)
        if _dist(_local(joint), wanted) > 1e-3:
            raise AssertionError("over joint wanted {} got {}".format(wanted, _local(joint)))
        if _dist(_world(joint), home) < 0.2:
            raise AssertionError("over joint did not travel")
    cmds.setAttr(ctl + ".ry", 360)
    for joint, home in zip(over, rest_over):
        cmds.getAttr(joint + ".worldMatrix[0]")
        if _dist(_world(joint), home) > 0.02:
            raise AssertionError("full turn did not return")
    print("ring_slide parent check ok")


def _retitle(root, new_name):
    """Rename the guide the way the component editor does, and leave the curve strings stale.

    That is the scene that breaks: both rings still say ``ring_C0_over_crv``.
    """
    short = root.split("|")[-1]
    old_base = short[:-5] if short.endswith("_root") else short
    new_base = new_name + "_C0"
    nodes = cmds.listRelatives(root, allDescendents=True, fullPath=True) or []
    for node in sorted(nodes, key=len, reverse=True):
        name = node.split("|")[-1]
        if name.startswith(old_base):
            cmds.rename(node, new_base + name[len(old_base):])
    renamed = cmds.rename(root, new_base + "_root")
    cmds.setAttr(renamed + ".comp_name", new_name, type="string")
    return cmds.ls(renamed, long=True)[0]


def _heights(points, height):
    found = []
    for index, point in enumerate(points):
        if abs(point[1] - height) > 0.05:
            continue
        if point[0] ** 2 + point[2] ** 2 < 0.04:
            continue
        found.append(index)
    return found


def _check_two():
    """Two renamed rings on one mesh. Each slides its own seam and leaves the other."""
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import mgear.pymaya as pm
    import mgear.shifter as shifter
    import ring_guide

    mesh = cmds.polyCylinder(
        name="twoGeo", radius=1.0, height=4.0, subdivisionsX=8, subdivisionsY=4,
        axis=(0, 1, 0), constructionHistory=False,
    )[0]
    cmds.xform(mesh, worldSpace=True, translation=(0, 2, 0))
    shifter.clearComponentCache()
    guide_rig = shifter.guide.Rig()
    guide_rig.initialHierarchy()
    for name, height in (("chest", 0.0), ("head", 4.0)):
        comp = guide_rig.getComponentGuide("control_01")
        comp.setParamDefValue("comp_name", name)
        comp.draw(pm.PyNode("guide"))
        cmds.xform(comp.root.longName(), worldSpace=True, translation=(0, height, 0))

    cmds.select(clear=True)
    top = ring_guide.create_guide(
        " ".join(_loop_edges(mesh, 4.0)),
        " ".join(_loop_edges(mesh, 3.0)),
        parent_comp="head_C0_root",
    )
    top = _retitle(top, "neckRing_Top")
    cmds.select(clear=True)
    bot = ring_guide.create_guide(
        " ".join(_loop_edges(mesh, 1.0)),
        " ".join(_loop_edges(mesh, 0.0)),
        parent_comp="chest_C0_root",
    )
    bot = _retitle(bot, "neckRing_Bot")
    if cmds.objExists("ring_C0_over_crv"):
        raise AssertionError("the old curve name still exists, so this is not the broken scene")
    for root in (top, bot):
        if cmds.getAttr(root + ".overCrv") != "ring_C0_over_crv":
            raise AssertionError("curve string was updated before the build")
        if not cmds.objExists(root + "|" + root.split("|")[-1].replace("_root", "_over_crv")):
            raise AssertionError("renamed curve is missing under {}".format(root))

    cmds.select("guide")
    shifter.Rig().buildFromSelection()
    skins = cmds.ls(type="skinCluster") or []
    if len(skins) != 1:
        raise AssertionError("expected one shared skin, got {}".format(skins))

    rest = _deformed(mesh)
    top_over = _heights(rest, 4.0)
    bot_over = _heights(rest, 1.0)
    if len(top_over) != 8 or len(bot_over) != 8:
        raise AssertionError("seam counts {} {}".format(len(top_over), len(bot_over)))
    for comp in ("neckRing_Top_C0", "neckRing_Bot_C0"):
        joints = cmds.ls(comp + "_over_*_jnt", type="joint")
        if len(joints) != 8:
            raise AssertionError("{} built {} over joints".format(comp, len(joints)))
        for joint in joints:
            if min(_dist(_world(joint), rest[index]) for index in range(len(rest))) > 0.02:
                raise AssertionError("{} is off the mesh".format(joint))

    cmds.setAttr("neckRing_Top_C0_ctl.ry", 180)
    spun = _deformed(mesh)
    if max(_dist(spun[index], rest[index]) for index in top_over) < 0.2:
        raise AssertionError("top seam did not slide")
    if max(_dist(spun[index], rest[index]) for index in bot_over) > 0.02:
        raise AssertionError("top slide moved the bottom seam")
    cmds.setAttr("neckRing_Top_C0_ctl.ry", 0)
    cmds.setAttr("neckRing_Bot_C0_ctl.ry", 180)
    spun = _deformed(mesh)
    if max(_dist(spun[index], rest[index]) for index in bot_over) < 0.2:
        raise AssertionError("bottom seam did not slide")
    if max(_dist(spun[index], rest[index]) for index in top_over) > 0.02:
        raise AssertionError("bottom slide moved the top seam")
    print("ring_slide two check ok")


def _check_spine():
    """Create Spine draws a spine_S_shape_01 with the neck defaults."""
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import ring_guide

    root = ring_guide.create_spine()
    if not root or cmds.getAttr(root + ".comp_type") != "spine_S_shape_01":
        raise AssertionError("spine guide was not drawn")
    expect = {
        "softness": 0.0,
        "position": 0.0,
        "lock_ori": 1.0,
        "maxstretch": 5.0,
        "maxsquash": 0.1,
        "division": 5,
        "autoBend": 0,
        "IKWorldOri": 1,
        "centralTangent": 0,
    }
    for name, value in expect.items():
        got = cmds.getAttr(root + "." + name)
        if abs(float(got) - value) > 1e-6:
            raise AssertionError("{} is {} wanted {}".format(name, got, value))
    base = root.split("|")[-1]
    if base.endswith("_root"):
        base = base[:-5]
    for suffix in ("tan0", "tan1", "eff"):
        if not cmds.objExists(base + "_" + suffix):
            raise AssertionError("spine is missing {}".format(suffix))
    base_pos, tip_pos = ring_guide.component_ends(root)
    base_ctl = ring_guide.create_control("base", base_pos)
    tip_ctl = ring_guide.create_control("tip", tip_pos)
    if cmds.getAttr(base_ctl + ".comp_type") != "control_01":
        raise AssertionError("base is not a control_01")
    if cmds.getAttr(base_ctl + ".comp_name") != "base" or cmds.getAttr(tip_ctl + ".comp_name") != "tip":
        raise AssertionError("controls were not named base and tip")
    got_base = cmds.xform(base_ctl, query=True, worldSpace=True, translation=True)
    got_tip = cmds.xform(tip_ctl, query=True, worldSpace=True, translation=True)
    if max(abs(a - b) for a, b in zip(got_base, base_pos)) > 1e-3:
        raise AssertionError("base control is off the spline root")
    if max(abs(a - b) for a, b in zip(got_tip, tip_pos)) > 1e-3:
        raise AssertionError("tip control is off the spline end")
    if abs(got_tip[1] - got_base[1]) < 1.0:
        raise AssertionError("tip control is not past the base")
    import maya.api.OpenMaya as om

    noticed = []
    picked = om.MSelectionList()
    picked.add(root)
    callback = om.MNodeMessage.addNameChangedCallback(
        picked.getDependNode(0),
        lambda _node, previous, _client: noticed.append(previous),
    )
    try:
        cmds.rename(root, "neck_C0_root")
    finally:
        om.MMessage.removeCallback(callback)
    if noticed != ["spine_C0_root"]:
        raise AssertionError("rename notice was {}".format(noticed))
    if not cmds.objExists("neck_C0_root"):
        raise AssertionError("renamed guide is missing")
    print("ring_slide spine check ok")


def _rig(name):
    found = [node for node in cmds.ls(name, long=True) or [] if "|guide|" not in node]
    if not found:
        raise AssertionError("rig node {} is missing".format(name))
    return found[0]


def _y_axis(node):
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return ring.norm((matrix[4], matrix[5], matrix[6]))


def _check_drive():
    """Base and tip drive a hidden spline. Rings twist between them."""
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import mgear.shifter as shifter
    import ring_guide

    mesh = cmds.polyCylinder(
        radius=1,
        height=4,
        subdivisionsAxis=8,
        subdivisionsHeight=4,
        constructionHistory=False,
    )[0]
    cmds.xform(mesh, worldSpace=True, translation=(0, 2, 0))
    cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)

    root = ring_guide.create_control("root")
    base = ring_guide.create_control("base", (0.0, 0.0, 0.0), parent=root)
    spine = ring_guide.create_spine(parent=base)
    # Off to one side, so the tip's own Y is not along base to tip, as on the owl.
    tip = ring_guide.create_control(
        "tip", (1.0, 4.0, 0.0), parent=ring_guide.sibling_parent(base)
    )
    if "|root_C0_root|" not in cmds.ls(tip, long=True)[0].replace(tip, ""):
        # The tip guide hangs under the same parent as the base.
        tip_parent = cmds.listRelatives(tip, parent=True, fullPath=True)[0]
        root_long = cmds.ls(root, long=True)[0]
        if tip_parent != root_long:
            raise AssertionError("tip guide parent is {}".format(tip_parent))
    spine_parent = cmds.listRelatives(spine, parent=True, fullPath=True)[0]
    if spine_parent != cmds.ls(base, long=True)[0]:
        raise AssertionError("spline guide parent is {}".format(spine_parent))

    over = _loop_edges(mesh, 3.0)
    under = _loop_edges(mesh, 2.0)
    if len(over) < 8 or len(under) < 8:
        raise AssertionError("loops {} {}".format(len(over), len(under)))
    top_ring = ring_guide.create_guide(
        " ".join(over),
        " ".join(under),
        base_spline=spine,
        base_ctl=base,
        tip_ctl=tip,
    )
    if cmds.getAttr(top_ring + ".baseSpline") != spine.split("|")[-1]:
        raise AssertionError("spline was not stored on the ring")
    cmds.select(clear=True)
    low_over = _loop_edges(mesh, 1.0)
    low_under = _loop_edges(mesh, 0.0)
    low_ring = ring_guide.create_guide(
        " ".join(low_over),
        " ".join(low_under),
        base_spline=spine,
        base_ctl=base,
        tip_ctl=tip,
    )

    # One connected mesh, so there is no shell to read: set the turns outright.
    cmds.setAttr(top_ring + ".underTurn", 40)
    cmds.setAttr(top_ring + ".overTurn", 100)
    cmds.setAttr(low_ring + ".underTurn", 50)
    cmds.setAttr(low_ring + ".overTurn", 100)
    cmds.select("guide")
    shifter.Rig().buildFromSelection()

    for ctl in (
        "spine_C0_ik0_ctl",
        "spine_C0_ik1_ctl",
        "spine_C0_tan0_ctl",
        "spine_C0_tan1_ctl",
        "spine_C0_fk0_ctl",
        "spine_C0_fk4_ctl",
        "ring_C0_ctl",
        "ring_C1_ctl",
    ):
        shapes = cmds.listRelatives(ctl, shapes=True, fullPath=True) or []
        if not shapes or cmds.getAttr(shapes[0] + ".visibility") != 0:
            raise AssertionError("{} is still visible".format(ctl))
        if cmds.getAttr(ctl + ".ry", keyable=True):
            raise AssertionError("{} rotateY is still keyable".format(ctl))
    for ctl in ("base_C0_ctl", "tip_C0_ctl"):
        if not cmds.getAttr(ctl + ".ry", keyable=True):
            raise AssertionError("{} is not keyable".format(ctl))

    tip_root = _rig("tip_C0_root")
    if "|root_C0_ctl|" not in tip_root or "spine_C0" in tip_root:
        raise AssertionError("built tip is {}".format(tip_root))
    if "|base_C0_ctl|" not in _rig("spine_C0_root"):
        raise AssertionError("built spline is not under the base")

    hooked = cmds.listConnections(
        "spine_C0_ik1_ctl", source=True, destination=False, type="parentConstraint"
    ) or []
    if len(set(hooked)) != 1:
        raise AssertionError("ik1 constraints {}".format(set(hooked)))

    npo = "ring_C0_ctl_npo"
    targets = cmds.parentConstraint(npo, query=True, targetList=True) or []
    if not any(name.startswith("spine_C0_") and name.endswith("_jnt") for name in targets):
        raise AssertionError("ring is not riding the spline joints: {}".format(targets))
    neck_y = _y_axis(targets[0])
    ring_y = _y_axis(npo)
    if abs(ring.dot(neck_y, ring_y)) < 0.95:
        raise AssertionError("ring Y {} is off the joint Y {}".format(ring_y, neck_y))

    over_joint = sorted(cmds.ls("ring_C0_over_*_jnt", type="joint") or [])[0]
    under_joint = sorted(cmds.ls("ring_C0_under_*_jnt", type="joint") or [])[0]
    low_over_joint = sorted(cmds.ls("ring_C1_over_*_jnt", type="joint") or [])[0]
    rest_over = _in_space(over_joint, "ring_C0_untwist")
    rest_under = _in_space(under_joint, "ring_C0_untwist")
    rest_low = _in_space(low_over_joint, "ring_C1_untwist")
    mesh_pts = _deformed(mesh)
    if min(_dist(_world(over_joint), point) for point in mesh_pts) > 0.05:
        raise AssertionError("over joint is off the mesh at bind")

    numbered = [
        joint for joint in cmds.ls("spine_C0_*_jnt", type="joint") or []
        if joint.split("_")[-2].isdigit()
    ]
    for joint in cmds.ls("ring_C*_jnt", type="joint") or []:
        parent = (cmds.listRelatives(joint, parent=True) or [""])[0]
        if parent not in numbered:
            raise AssertionError("{} is under {}, not a spline joint".format(joint, parent))
        here = _world(joint)
        nearest = min(numbered, key=lambda item: _dist(_world(item), here))
        if _dist(_world(parent), here) > _dist(_world(nearest), here) + 1e-3:
            raise AssertionError("{} closest spline joint is {}, parent is {}".format(
                joint, nearest, parent
            ))
    skin = (cmds.ls(type="skinCluster") or [None])[0]
    influences = {
        name.split("|")[-1]
        for name in (cmds.skinCluster(skin, query=True, influence=True) or [])
    }
    root = (cmds.listRelatives("jnt_org", children=True, type="joint") or [""])[0]
    for name in [root] + numbered:
        if name.split("|")[-1] not in influences:
            raise AssertionError("{} is not a skin influence".format(name))

    cmds.setAttr("tip_C0_ctl.ry", 40)
    slid = _dist(_in_space(over_joint, "ring_C0_untwist"), rest_over)
    if slid < 0.05:
        raise AssertionError("tip twist did not slide the over joint ({})".format(slid))
    if _dist(_in_space(under_joint, "ring_C0_untwist"), rest_under) > 0.001:
        raise AssertionError("tip twist moved an under joint")
    if _dist(_in_space(low_over_joint, "ring_C1_untwist"), rest_low) < 0.02:
        raise AssertionError("second ring did not slide")

    # The head's own channel runs past 180, so the spin must not wrap there.
    # Each seam takes its distance-along-the-neck share, and the top takes more.
    spin_top = cmds.getAttr("ring_C0_spinMul.conversionFactor")
    slide_top = cmds.getAttr("ring_C0_slideMul.conversionFactor")
    # Under turns 40, over turns 100: both spin by 0.4, the over loop slides on by 0.6.
    if abs(abs(spin_top) - 0.4) > 1e-6 or abs(abs(slide_top) - 0.6) > 1e-6 or spin_top * slide_top < 0:
        raise AssertionError("top ring shares {} {}".format(spin_top, slide_top))
    if abs(abs(cmds.getAttr("ring_C1_spinMul.conversionFactor")) - 0.5) > 1e-6:
        raise AssertionError("bottom ring Under Turns of 50 was not used")
    if abs(abs(cmds.getAttr("ring_C1_slideMul.conversionFactor")) - 0.5) > 1e-6:
        raise AssertionError("bottom ring slide is not over minus under")
    for turn in (90.0, 270.0, 540.0, -400.0):
        cmds.setAttr("tip_C0_ctl.ry", turn)
        got = cmds.getAttr("ring_C0_spin.ry")
        if abs(got - spin_top * turn) > 1e-3:
            raise AssertionError("spin at {} is {}, wanted {}".format(turn, got, spin_top * turn))
        got = cmds.getAttr("ring_C0_ctl.ry")
        if abs(got - slide_top * turn) > 1e-3:
            raise AssertionError("slide at {} is {}, wanted {}".format(turn, got, slide_top * turn))
    # The slide is 0.6 of the head, so 360 degrees of it is 600 of the head: one lap.
    cmds.setAttr("tip_C0_ctl.ry", 300.0)
    if _dist(_in_space(over_joint, "ring_C0_untwist"), rest_over) < 0.05:
        raise AssertionError("half a lap did not move the seam")
    cmds.setAttr("tip_C0_ctl.ry", 600.0)
    if _dist(_in_space(over_joint, "ring_C0_untwist"), rest_over) > 0.02:
        raise AssertionError("a full lap did not bring the seam back to its start")
    # A pure twist must not bend the neck, even when the tip's Y is off the neck axis.
    cmds.setAttr("tip_C0_ctl.ry", 0)
    aim_rest = _y_axis("spine_C0_ik1_ctl")
    cmds.setAttr("tip_C0_ctl.ry", 180.0)
    if ring.dot(_y_axis("spine_C0_ik1_ctl"), aim_rest) < 0.999:
        raise AssertionError("twisting the head bent the neck")
    low_joint_index = cmds.getAttr(low_ring + ".splineJoint")
    top_joint_index = cmds.getAttr(top_ring + ".splineJoint")
    if not 0 <= low_joint_index < top_joint_index <= 4:
        raise AssertionError("joint indices {} {}".format(low_joint_index, top_joint_index))
    pinned = cmds.parentConstraint(npo, query=True, targetList=True) or []
    if pinned != ["spine_C0_{}_jnt".format(top_joint_index)]:
        raise AssertionError("top ring is on {}, wanted joint {}".format(pinned, top_joint_index))

    cmds.setAttr("tip_C0_ctl.ry", 0)
    flat_y = _y_axis(npo)
    cmds.setAttr("tip_C0_ctl.rx", 40)
    pitched = _dist(_in_space(over_joint, "ring_C0_untwist"), rest_over)
    if pitched > 0.05:
        raise AssertionError("tip pitch slid the seam ({})".format(pitched))
    # The seam leans toward the head's pitch by its place on the neck.
    leaned = math.degrees(math.acos(min(1.0, ring.dot(flat_y, _y_axis(npo)))))
    if leaned < 0.5 * 0.3 * 40.0:
        raise AssertionError("seam leaned {} degrees for a 40 degree pitch".format(leaned))

    cmds.setAttr("tip_C0_ctl.rx", 0)
    rest_pos = _world(npo)
    cmds.setAttr("tip_C0_ctl.tx", 2)
    cmds.dgeval("spine_C0_4_jnt.worldMatrix[0]")
    if abs(_world("spine_C0_4_jnt")[0]) < 0.4:
        raise AssertionError("tip translate did not move the neck")
    if _dist(_world(npo), rest_pos) < 0.05:
        raise AssertionError("tip translate did not carry the ring")
    bent = cmds.getAttr(npo + ".rotate")[0]
    if max(abs(channel) for channel in bent) < 1.0:
        raise AssertionError("bending the tip did not reorient the ring")
    bent_y = _y_axis(npo)
    target_y = _y_axis(targets[0])
    # The seam leans part way to the neck's end, so it sits near its joint's Y, not on it.
    if abs(ring.dot(bent_y, target_y)) < 0.85:
        raise AssertionError("bent ring Y {} left the joint Y {}".format(bent_y, target_y))

    cmds.setAttr("tip_C0_ctl.tx", 0)
    low_rest = _world("ring_C1_ctl_npo")
    cmds.setAttr("base_C0_ctl.rz", 25)
    cmds.dgeval("spine_C0_2_jnt.worldMatrix[0]")
    mid = _world("spine_C0_2_jnt")
    if abs(mid[0]) < 0.05 and abs(mid[2]) < 0.05:
        raise AssertionError("base control did not bend the neck {}".format(mid))
    if _dist(_world("ring_C1_ctl_npo"), low_rest) < 0.05:
        raise AssertionError("base bend did not carry the lower ring")
    print("ring_slide drive check ok")


def _check_shells():
    """Auto reads head, neck and chest from the mesh shells a loop belongs to."""
    import ring_slide

    cmds.file(new=True, force=True)
    pieces = []
    # Chest and head are bigger meshes than the thin neck between them.
    for low, high, around in ((0.0, 3.0, 8), (3.5, 7.0, 4), (7.5, 10.0, 8)):
        piece = cmds.polyCylinder(
            radius=1, height=high - low, subdivisionsAxis=around, subdivisionsHeight=1,
            constructionHistory=False,
        )[0]
        cmds.xform(piece, worldSpace=True, translation=(0, (low + high) / 2.0, 0))
        cmds.makeIdentity(piece, apply=True, translate=True)
        pieces.append(piece)
    mesh = cmds.polyUnite(*pieces, constructionHistory=False)[0]
    flat = cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)

    def vert(height):
        for index in range(0, len(flat), 3):
            if abs(flat[index + 1] - height) < 1e-3 and flat[index] ** 2 + flat[index + 2] ** 2 > 0.5:
                return index // 3
        raise AssertionError("no vertex at {}".format(height))

    base = (0.0, 2.0, 0.0)
    tip = (0.0, 8.0, 0.0)
    head = ring_slide._shell_turn(mesh, vert(7.5), vert(7.0), base, tip, 0.875)
    neck_top = ring_slide._shell_turn(mesh, vert(7.0), vert(7.5), base, tip, 0.875)
    neck_bottom = ring_slide._shell_turn(mesh, vert(3.5), vert(3.0), base, tip, 0.208)
    chest = ring_slide._shell_turn(mesh, vert(3.0), vert(3.5), base, tip, 0.208)
    same = ring_slide._shell_turn(mesh, vert(3.5), vert(7.0), base, tip, 0.5)
    got = (head, neck_top, neck_bottom, chest, same)
    want = (1.0, 0.875, 0.208, 0.0, 0.5)
    if max(abs(a - b) for a, b in zip(got, want)) > 1e-6:
        raise AssertionError("shell turns {} wanted {}".format(got, want))
    print("ring_slide shell check ok")


def _check_weight_order():
    """Weights handed over in loop order still land on those vertices."""
    import ring_slide

    cmds.file(new=True, force=True)
    mesh = cmds.polyPlane(subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
    joints = []
    for index in range(4):
        cmds.select(clear=True)
        joints.append(cmds.joint(name="w{}_jnt".format(index), position=(index, 0, 0)))
    skin = cmds.skinCluster(joints, mesh, toSelectedBones=True, normalizeWeights=0)[0]
    vert_ids = [3, 2, 1, 0]
    rows = []
    for index in range(4):
        row = [0.0] * 4
        row[index] = 1.0
        rows.append(row)
    ring_slide._apply_weights(skin, mesh, joints, rows, vert_ids)
    for vert, row in zip(vert_ids, rows):
        want = joints[row.index(1.0)]
        got = cmds.skinPercent(skin, "{}.vtx[{}]".format(mesh, vert), query=True, transform=want)
        if abs(got - 1.0) > 1e-4:
            raise AssertionError("vert {} weight on {} is {}".format(vert, want, got))
    print("ring_slide weight order check ok")


if __name__ == "__main__":
    _check_weight_order()
    _check_shells()
    _check_spine()
    _check()
    _check_parent()
    _check_two()
    _check_drive()
