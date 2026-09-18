"""Headless draw-and-build check for the In-Between Shifter components.

    set MAYA_MODULE_PATH=<mgear>\\release
    mayapy smoke_build.py

Builds each component from a freshly drawn guide and asserts the rig actually
moves the way it should. Fast enough to run after every code edit, which is the
point: Maya is the only place these components can really be tested.
"""

import os
import sys

import maya.standalone

maya.standalone.initialize()

from maya import cmds  # noqa: E402

_COMPONENTS = os.path.dirname(os.path.abspath(__file__))
_existing = os.environ.get("MGEAR_SHIFTER_COMPONENT_PATH", "")
_paths = [p for p in _existing.split(os.pathsep) if p]
if _COMPONENTS not in _paths:
    os.environ["MGEAR_SHIFTER_COMPONENT_PATH"] = os.pathsep.join(
        _paths + [_COMPONENTS]
    )

import mgear.pymaya as pm  # noqa: E402
from mgear import shifter  # noqa: E402
from mgear.shifter import guide_manager  # noqa: E402


def _one(pattern):
    found = cmds.ls(pattern, long=False)
    assert len(found) == 1, "expected exactly one {}, got {}".format(
        pattern, found
    )
    return found[0]


def _anim_plug(name):
    """Find an anim param by short name; Shifter prefixes it and moves it to
    the UI host, so its full path is not predictable from the component."""
    hits = [
        "{}.{}".format(transform, attr)
        for transform in cmds.ls(type="transform")
        for attr in (cmds.listAttr(transform, userDefined=True) or [])
        if attr.split("_", 1)[-1] == name
    ]
    assert len(hits) == 1, "expected exactly one '{}' attr, got {}".format(
        name, hits
    )
    return hits[0]


def _build(comp_type, settings=None):
    """Draw a guide, apply settings overrides, build, return the rig root."""
    cmds.file(new=True, force=True)
    shifter.clearComponentCache()

    pm.select(clear=True)
    guide_manager.draw_comp(comp_type, None, False)

    comp_root = _one("*_C0_root")
    for attr, value in (settings or {}).items():
        cmds.setAttr("{}.{}".format(comp_root, attr), value)

    _rebuild()
    return comp_root


def _rebuild():
    pm.select("guide")
    shifter.Rig().buildFromSelection()


def _joints_ride_the_bow(divisions):
    for i in range(divisions):
        jnt = cmds.xform(_one("*_C0_{}_jnt".format(i)), q=True, ws=True, t=True)
        loc = cmds.xform(
            _one("*_C0_div{}_loc".format(i)), q=True, ws=True, t=True
        )
        assert all(abs(a - b) < 1e-3 for a, b in zip(jnt, loc)), (i, jnt, loc)


def test_bounded_bow_distance_drive():
    divisions = 5
    _build("tween_bounded_bow_01", {"div": divisions, "driveMode": 0})

    locs = [_one("*_C0_div{}_loc".format(i)) for i in range(divisions)]
    joints = cmds.ls("*_C0_?_jnt", type="joint")
    assert len(joints) == divisions, joints

    for loc in locs:
        assert abs(cmds.getAttr(loc + ".ty")) < 1e-4, (loc, "not flat at rest")

    rest_x = cmds.getAttr(locs[-1] + ".tx")
    assert abs(rest_x - 4.0) < 1e-3, rest_x

    tip_ctl = _one("*_C0_tip_ctl")
    cmds.setAttr(tip_ctl + ".tx", -3.0)

    apex = cmds.getAttr(locs[2] + ".ty")
    bulge = cmds.getAttr(_anim_plug("bulge"))
    assert abs(apex - 0.75 * bulge) < 1e-3, (apex, bulge)

    assert abs(cmds.getAttr(locs[0] + ".ty")) < 1e-4
    assert abs(cmds.getAttr(locs[-1] + ".ty")) < 1e-4
    assert abs(cmds.getAttr(locs[-1] + ".tx") - 1.0) < 1e-3

    _joints_ride_the_bow(divisions)

    cmds.setAttr(_anim_plug("bulge_twist"), 90)
    x, y, z = cmds.xform(locs[2], q=True, ws=True, t=True)
    assert abs(y) < 1e-3, "twist should empty the Y bulge, got {}".format(y)
    assert abs(abs(z) - apex) < 1e-3, "twist changed bulge size: {}".format(z)
    cmds.setAttr(_anim_plug("bulge_twist"), 0)

    cmds.setAttr(tip_ctl + ".tx", 0.0)
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4

    cmds.setAttr(tip_ctl + ".tx", 2.0)
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4

    print("  distance drive OK")


def test_bounded_bow_angle_drive():
    divisions = 5
    _build(
        "tween_bounded_bow_01",
        {"div": divisions, "driveMode": 1, "maxBendAngle": 90.0},
    )

    locs = [_one("*_C0_div{}_loc".format(i)) for i in range(divisions)]
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4, "not flat at rest"

    tip_ctl = _one("*_C0_tip_ctl")
    cmds.setAttr(tip_ctl + ".tx", -4.0)
    cmds.setAttr(tip_ctl + ".tz", 4.0)

    apex = cmds.getAttr(locs[2] + ".ty")
    bulge = cmds.getAttr(_anim_plug("bulge"))
    assert abs(apex - 0.75 * bulge) < 1e-3, (apex, bulge)

    print("  angle drive OK")


def test_rebuild_after_moving_guide():
    divisions = 5
    _build("tween_bounded_bow_01", {"div": divisions})

    cmds.delete("rig")
    survivors = cmds.ls(type="joint")
    assert not survivors, "joints outlived the rig: {}".format(survivors)

    cmds.setAttr(_one("*_C0_tip") + ".translateX", 9.0)
    cmds.setAttr(_one("*_C0_root") + ".translateY", 6.0)
    _rebuild()

    _joints_ride_the_bow(divisions)
    tip = cmds.xform(_one("*_C0_4_jnt"), q=True, ws=True, t=True)
    assert abs(tip[0] - 9.0) < 1e-3 and abs(tip[1] - 6.0) < 1e-3, tip

    print("  rebuild after guide move OK")


def main():
    for test in (
        test_bounded_bow_distance_drive,
        test_bounded_bow_angle_drive,
        test_rebuild_after_moving_guide,
    ):
        print(test.__name__)
        test()
    print("smoke_build OK")


if __name__ == "__main__":
    main()
