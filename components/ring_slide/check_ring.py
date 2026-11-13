"""Draw two edge rings and assert the over joints slide along the under one.

Run::

    $env:MAYA_MODULE_PATH="C:\\Users\\andre\\Documents\\GitHub\\mgear\\release"
    & "C:\\Program Files\\Autodesk\\Maya2026\\bin\\mayapy.exe" components\\ring_slide\\check_ring.py
"""

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


def _check():
    cmds.file(new=True, force=True)
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = _root
    tools = os.path.normpath(os.path.join(_root, "..", "tools"))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import mgear.pymaya as pm
    import mgear.shifter as shifter
    import sheet_rig

    # Vertex ids that do not go around the loop. A batch position query
    # returns them in index order and the guide draws chords.
    facet = cmds.polyCreateFacet(
        point=[(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        name="ord",
        constructionHistory=False,
    )[0]
    scrambled = [facet + ".vtx[0]", facet + ".vtx[2]", facet + ".vtx[1]", facet + ".vtx[3]"]
    got = sheet_rig._positions(scrambled)
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
    one = sheet_rig._ordered_verts(over_edges[0])
    if one is None or len(one) != 8:
        raise AssertionError("one edge did not grow into the ring: {}".format(one))
    # Tilt it, so the control can only be square if it was really aligned.
    cmds.xform(mesh, worldSpace=True, rotation=(30, 0, 20), rotateAxis=(0, 0, 0))
    cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)

    shifter.clearComponentCache()
    root = sheet_rig.create_guide(" ".join(over_edges), " ".join(under_edges))
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
    import sheet_rig

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

    root = sheet_rig.create_guide(
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


if __name__ == "__main__":
    _check()
    _check_parent()
