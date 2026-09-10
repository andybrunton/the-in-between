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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import register  # noqa: E402

register.register()

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

    # At the guide pose the bow is flat: every point sits on the chord.
    for loc in locs:
        assert abs(cmds.getAttr(loc + ".ty")) < 1e-4, (loc, "not flat at rest")

    rest_x = cmds.getAttr(locs[-1] + ".tx")
    assert abs(rest_x - 4.0) < 1e-3, rest_x

    # Compress the span past minLength: the bow should be at full height.
    tip_ctl = _one("*_C0_tip_ctl")
    cmds.setAttr(tip_ctl + ".tx", -3.0)

    apex = cmds.getAttr(locs[2] + ".ty")
    bulge = cmds.getAttr(_anim_plug("bulge"))
    assert abs(apex - 0.75 * bulge) < 1e-3, (apex, bulge)

    # Endpoints stay pinned to the chord no matter what.
    assert abs(cmds.getAttr(locs[0] + ".ty")) < 1e-4
    assert abs(cmds.getAttr(locs[-1] + ".ty")) < 1e-4
    assert abs(cmds.getAttr(locs[-1] + ".tx") - 1.0) < 1e-3

    # The skin joints ride the bow points.
    _joints_ride_the_bow(divisions)

    # Bulge twist rolls the bulge around the chord without changing its size.
    cmds.setAttr(_anim_plug("bulge_twist"), 90)
    x, y, z = cmds.xform(locs[2], q=True, ws=True, t=True)
    assert abs(y) < 1e-3, "twist should empty the Y bulge, got {}".format(y)
    assert abs(abs(z) - apex) < 1e-3, "twist changed bulge size: {}".format(z)
    cmds.setAttr(_anim_plug("bulge_twist"), 0)

    # Releasing the compression returns the bow to flat.
    cmds.setAttr(tip_ctl + ".tx", 0.0)
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4

    # Over-extending past rest must not invert the bulge.
    cmds.setAttr(tip_ctl + ".tx", 2.0)
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4

    print("  distance drive OK")


def test_bounded_bow_angle_drive():
    divisions = 5
    _build(
        "tween_bounded_bow_01",
        # rotateX lands on the guide root: an axis aligned guide would let a
        # frame mistake in the drive cancel itself out.
        {"div": divisions, "driveMode": 1, "maxBendAngle": 90.0, "rotateX": 90},
    )

    locs = [_one("*_C0_div{}_loc".format(i)) for i in range(divisions)]
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4, "not flat at rest"
    bulge = cmds.getAttr(_anim_plug("bulge"))

    # Swing the tip 90 degrees off the guide chord -> full bulge.
    tip_ctl = _one("*_C0_tip_ctl")
    cmds.setAttr(tip_ctl + ".tx", -4.0)
    cmds.setAttr(tip_ctl + ".tz", 4.0)

    apex = cmds.getAttr(locs[2] + ".ty")
    assert abs(apex - 0.75 * bulge) < 1e-3, (apex, bulge)

    # Turning the tip on the spot bends the bow just as much. This is the
    # arm case: the elbow closes, so the bicep's tip ctl rotates with the
    # forearm while staying exactly where it is.
    cmds.setAttr(tip_ctl + ".tx", 0.0)
    cmds.setAttr(tip_ctl + ".tz", 0.0)
    assert abs(cmds.getAttr(locs[2] + ".ty")) < 1e-4, "not flat again"

    cmds.setAttr(tip_ctl + ".rz", 90.0)
    apex = cmds.getAttr(locs[2] + ".ty")
    assert abs(apex - 0.75 * bulge) < 1e-3, (apex, bulge)

    print("  angle drive OK")


def test_rebuild_after_moving_guide():
    """Delete the rig, move the guide, rebuild: joints must follow.

    mGear's 'Connect Joints' guide option reuses any joint in the scene whose
    name matches and leaves it where it is. That is intentional (it protects
    skinned joints), but it means a joint that outlives its rig will silently
    pin the next build to the old pose. Assert nothing of ours survives.
    """
    divisions = 5
    _build("tween_bounded_bow_01", {"div": divisions})

    cmds.delete("rig")
    survivors = cmds.ls(type="joint")
    assert not survivors, "joints outlived the rig: {}".format(survivors)

    cmds.setAttr(_one("*_C0_tip") + ".translateX", 9.0)
    cmds.setAttr(_one("*_C0_root") + ".translateY", 6.0)
    # Rotate too: an axis aligned guide hides frame bugs, because the bow
    # matrix is then the identity and any missing one cancels out.
    cmds.setAttr(_one("*_C0_root") + ".rotateX", 90.0)
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
