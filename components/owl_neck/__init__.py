"""Owl neck. An IK spline from spine_ik_02, without the hip joint or FK controls.

`division` is the number of neck joints, base through tip. Joint 0 sits on
the root. The tip joint is the head parent and gets no twist leaf. Every
other joint gets two leaf joints, A and B, whose rotateX is a 0-to-1 slice
of the head control's rotateY.

The head is whatever guide root is first in the tip reference array. Leave
that guide unparented from this neck. After every component's joints exist,
the tip IK is position- and aim-constrained to that control, both IK
controls are hidden, and that component's joint is reparented under the tip.
"""

import maya.cmds as cmds

import mgear.pymaya as pm
from mgear.pymaya import datatypes

from mgear.shifter import component

from mgear.core import applyop, attribute, curve, fcurve, node, primitive, transform, vector

# ponytail: fixed offset, not scaled to the guide. Raise it if the head
# control is much larger than the snow-owl test and the aim starts to flip.
AIM_UP_OFFSET = 10
TWIST_AXES = ("rx", "ry", "rz")


def twist_weights(count):
    """Slice of the head twist for each leaf. 0 on the first, 1 on the last."""
    if count < 1:
        return []
    if count == 1:
        return [0.0]
    last = float(count - 1)
    return [i / last for i in range(count)]


def _check_twist_weights():
    assert twist_weights(0) == []
    assert twist_weights(1) == [0.0]
    weights = twist_weights(6)
    assert len(weights) == 6
    assert weights[0] == 0.0 and weights[-1] == 1.0
    assert abs(weights[1] - 0.2) < 1e-9


_check_twist_weights()


class Component(component.Main):
    """Shifter component Class"""

    # =====================================================
    # OBJECTS
    # =====================================================
    def addObjects(self):
        """Add all the objects needed to create the component."""

        t = transform.getTransformLookingAt(
            self.guide.apos[0],
            self.guide.apos[1],
            self.guide.blades["blade"].z * -1,
            "yx",
            self.negate)

        self.ik0_npo = primitive.addTransform(
            self.root, self.getName("ik0_npo"), t)
        self.ik0_ctl = self.addCtl(
            self.ik0_npo,
            "ik0_ctl",
            t,
            self.color_ik,
            "compas",
            w=self.size,
            tp=self.parentCtlTag)

        attribute.setKeyableAttributes(self.ik0_ctl, self.tr_params)
        attribute.setRotOrder(self.ik0_ctl, "ZXY")
        attribute.setInvertMirror(self.ik0_ctl, ["tx", "ry", "rz"])

        t = transform.setMatrixPosition(t, self.guide.apos[1])
        self.ik1_npo = primitive.addTransform(
            self.root, self.getName("ik1_npo"), t)
        self.ik1_ctl = self.addCtl(
            self.ik1_npo,
            "ik1_ctl",
            t,
            self.color_ik,
            "compas",
            w=self.size,
            tp=self.ik0_ctl)

        attribute.setKeyableAttributes(self.ik1_ctl, self.tr_params)
        attribute.setRotOrder(self.ik1_ctl, "ZXY")
        attribute.setInvertMirror(self.ik1_ctl, ["tx", "ry", "rz"])

        # Tangents. These stay available after ik0 and ik1 are hidden.
        vec_pos = vector.linearlyInterpolate(
            self.guide.apos[0], self.guide.apos[1], 0.33)
        t = transform.setMatrixPosition(t, vec_pos)
        self.tan0_npo = primitive.addTransform(
            self.ik0_ctl, self.getName("tan0_npo"), t)
        self.tan0_ctl = self.addCtl(
            self.tan0_npo,
            "tan0_ctl",
            t,
            self.color_ik,
            "sphere",
            w=self.size * 0.2,
            tp=self.ik0_ctl)
        attribute.setKeyableAttributes(self.tan0_ctl, self.t_params)

        vec_pos = vector.linearlyInterpolate(
            self.guide.apos[0], self.guide.apos[1], 0.66)
        t = transform.setMatrixPosition(t, vec_pos)
        self.tan1_npo = primitive.addTransform(
            self.ik1_ctl, self.getName("tan1_npo"), t)
        self.tan1_ctl = self.addCtl(
            self.tan1_npo,
            "tan1_ctl",
            t,
            self.color_ik,
            "sphere",
            w=self.size * 0.2,
            tp=self.ik1_ctl)
        attribute.setKeyableAttributes(self.tan1_ctl, self.t_params)
        attribute.setInvertMirror(self.tan0_ctl, ["tx"])
        attribute.setInvertMirror(self.tan1_ctl, ["tx"])

        self.mst_crv = curve.addCnsCurve(
            self.root,
            self.getName("mst_crv"),
            [self.ik0_ctl, self.tan0_ctl, self.tan1_ctl, self.ik1_ctl],
            3)
        self.slv_crv = curve.addCurve(
            self.root,
            self.getName("slv_crv"),
            [datatypes.Vector()] * 10,
            False,
            3)
        self.mst_crv.setAttr("visibility", False)
        self.slv_crv.setAttr("visibility", False)

        parentdiv = self.root
        parentctl = self.root
        self.div_cns = []
        self.neck_npo = []
        self.scl_transforms = []
        self.twister = []
        self.ref_twist = []

        t = transform.getTransformLookingAt(
            self.guide.apos[0],
            self.guide.apos[1],
            self.guide.blades["blade"].z * -1,
            "yx",
            self.negate)

        parent_twistRef = primitive.addTransform(
            self.root,
            self.getName("reference"),
            transform.getTransform(self.root))

        self.jointList = []
        division = self.settings["division"]
        for i in range(division):
            div_cns = primitive.addTransform(
                parentdiv, self.getName("%s_cns" % i))
            pm.setAttr(div_cns + ".inheritsTransform", False)
            self.div_cns.append(div_cns)
            parentdiv = div_cns

            # Hidden chain the joints hang from. No FK controls.
            neck_npo = primitive.addTransform(
                parentctl,
                self.getName("neck%s_npo" % i),
                transform.getTransform(parentctl))
            self.neck_npo.append(neck_npo)
            self.transform2Lock.append(neck_npo)
            parentctl = neck_npo

            scl_ref = primitive.addTransform(
                parentctl,
                self.getName("%s_scl_ref" % i),
                transform.getTransform(parentctl))
            self.scl_transforms.append(scl_ref)

            # The spline aims Y down the neck. Rotating 90 on Z puts the
            # joint's X there instead. Squash and stretch stay on scl_ref's Y.
            jnt_drv = primitive.addTransform(
                scl_ref,
                self.getName("%s_jnt_drv" % i),
                transform.getTransform(scl_ref))
            jnt_drv.rz.set(90)
            self.jnt_pos.append([jnt_drv, i])

            twister = primitive.addTransform(
                parent_twistRef, self.getName("%s_rot_ref" % i), t)
            ref_twist = primitive.addTransform(
                parent_twistRef, self.getName("%s_pos_ref" % i), t)
            ref_twist.setTranslation(
                datatypes.Vector(1.0, 0, 0), space="preTransform")
            self.twister.append(twister)
            self.ref_twist.append(ref_twist)

        self.cnx0 = primitive.addTransform(self.root, self.getName("0_cnx"))
        self.cnx1 = primitive.addTransform(self.root, self.getName("1_cnx"))

    def addAttributes(self):
        self.position_att = self.addAnimParam(
            "position", "Position", "double", self.settings["position"], 0, 1)
        self.maxstretch_att = self.addAnimParam(
            "maxstretch", "Max Stretch", "double",
            self.settings["maxstretch"], 1)
        self.maxsquash_att = self.addAnimParam(
            "maxsquash", "Max Squash", "double",
            self.settings["maxsquash"], 0, 1)
        self.softness_att = self.addAnimParam(
            "softness", "Softness", "double", self.settings["softness"], 0, 1)
        self.lock_ori0_att = self.addAnimParam(
            "lock_ori0", "Lock Ori 0", "double",
            self.settings["lock_ori"], 0, 1)
        self.lock_ori1_att = self.addAnimParam(
            "lock_ori1", "Lock Ori 1", "double",
            self.settings["lock_ori"], 0, 1)
        self.tan0_att = self.addAnimParam("tan0", "Tangent 0", "double", 1, 0)
        self.tan1_att = self.addAnimParam("tan1", "Tangent 1", "double", 1, 0)
        # The owl neck does not keep the spine's volume bulge.
        self.volume_att = self.addAnimParam(
            "volume", "Volume", "double", 0, 0, 1)

        division = self.settings["division"]
        if self.guide.paramDefs["st_profile"].value:
            self.st_value = self.guide.paramDefs["st_profile"].value
            self.sq_value = self.guide.paramDefs["sq_profile"].value
        else:
            self.st_value = fcurve.getFCurveValues(
                self.settings["st_profile"], division)
            self.sq_value = fcurve.getFCurveValues(
                self.settings["sq_profile"], division)

        self.st_att = [
            self.addSetupParam(
                "stretch_%s" % i, "Stretch %s" % i, "double",
                self.st_value[i], -1, 0)
            for i in range(division)]
        self.sq_att = [
            self.addSetupParam(
                "squash_%s" % i, "Squash %s" % i, "double",
                self.sq_value[i], 0, 1)
            for i in range(division)]

    # =====================================================
    # OPERATORS
    # =====================================================
    def addOperators(self):
        """Create operators and set the relations for the component rig."""

        d = vector.getDistance(self.guide.apos[0], self.guide.apos[1])
        dist_node = node.createDistNode(self.ik0_ctl, self.ik1_ctl)
        rootWorld_node = node.createDecomposeMatrixNode(
            self.root.attr("worldMatrix"))
        div_node = node.createDivNode(
            dist_node + ".distance", rootWorld_node + ".outputScaleX")
        div_node = node.createDivNode(div_node + ".outputX", d)

        mul_node = node.createMulNode(
            self.tan0_att, self.tan0_npo.getAttr("ty"))
        res_node = node.createMulNode(
            mul_node + ".outputX", div_node + ".outputX")
        pm.connectAttr(res_node + ".outputX", self.tan0_npo.attr("ty"))

        mul_node = node.createMulNode(
            self.tan1_att, self.tan1_npo.getAttr("ty"))
        res_node = node.createMulNode(
            mul_node + ".outputX", div_node + ".outputX")
        pm.connectAttr(res_node + ".outputX", self.tan1_npo.attr("ty"))

        op = applyop.gear_curveslide2_op(
            self.slv_crv, self.mst_crv, 0, 1.5, 0.5, 0.5)
        pm.connectAttr(self.position_att, op + ".position")
        pm.connectAttr(self.maxstretch_att, op + ".maxstretch")
        pm.connectAttr(self.maxsquash_att, op + ".maxsquash")
        pm.connectAttr(self.softness_att, op + ".softness")

        crv_node = node.createCurveInfoNode(self.slv_crv)

        division = self.settings["division"]
        for i in range(division):
            u = i / (division - 1.0)
            cns = applyop.pathCns(self.div_cns[i], self.slv_crv, False, u, True)
            cns.setAttr("frontAxis", 1)  # Y
            cns.setAttr("upAxis", 0)  # X

            intMatrix = applyop.gear_intmatrix_op(
                self.ik0_ctl + ".worldMatrix",
                self.ik1_ctl + ".worldMatrix",
                u)
            dm_node = node.createDecomposeMatrixNode(intMatrix + ".output")
            pm.connectAttr(dm_node + ".outputRotate", self.twister[i].attr("rotate"))
            pm.parentConstraint(
                self.twister[i], self.ref_twist[i], maintainOffset=True)
            pm.connectAttr(self.ref_twist[i] + ".translate", cns + ".worldUpVector")

            div_node = node.createDivNode(
                [1, 1, 1],
                [rootWorld_node + ".outputScaleX",
                 rootWorld_node + ".outputScaleY",
                 rootWorld_node + ".outputScaleZ"])

            op = applyop.gear_squashstretch2_op(
                self.scl_transforms[i],
                self.root,
                pm.arclen(self.slv_crv),
                "y",
                div_node + ".output")
            pm.connectAttr(self.volume_att, op + ".blend")
            pm.connectAttr(crv_node + ".arcLength", op + ".driver")
            pm.connectAttr(self.st_att[i], op + ".stretch")
            pm.connectAttr(self.sq_att[i], op + ".squash")

            if i == 0:
                mulmat_node = applyop.gear_mulmatrix_op(
                    self.div_cns[i].attr("worldMatrix"),
                    self.root.attr("worldInverseMatrix"))
                dm_node = node.createDecomposeMatrixNode(mulmat_node + ".output")
                pm.connectAttr(dm_node + ".outputTranslate", self.neck_npo[i].attr("t"))
            else:
                mulmat_node = applyop.gear_mulmatrix_op(
                    self.div_cns[i].attr("worldMatrix"),
                    self.div_cns[i - 1].attr("worldInverseMatrix"))
                dm_node = node.createDecomposeMatrixNode(mulmat_node + ".output")
                mul_node = node.createMulNode(
                    div_node + ".output", dm_node + ".outputTranslate")
                pm.connectAttr(mul_node + ".output", self.neck_npo[i].attr("t"))

            pm.connectAttr(dm_node + ".outputRotate", self.neck_npo[i].attr("r"))

            if i == 0:
                dm_node = node.createDecomposeMatrixNode(
                    self.ik0_ctl + ".worldMatrix")
                blend_node = node.createBlendNode(
                    [dm_node + ".outputRotate%s" % s for s in "XYZ"],
                    [cns + ".rotate%s" % s for s in "XYZ"],
                    self.lock_ori0_att)
                self.div_cns[i].attr("rotate").disconnect()
                pm.connectAttr(blend_node + ".output", self.div_cns[i] + ".rotate")
            elif i == division - 1:
                dm_node = node.createDecomposeMatrixNode(
                    self.ik1_ctl + ".worldMatrix")
                blend_node = node.createBlendNode(
                    [dm_node + ".outputRotate%s" % s for s in "XYZ"],
                    [cns + ".rotate%s" % s for s in "XYZ"],
                    self.lock_ori1_att)
                self.div_cns[i].attr("rotate").disconnect()
                pm.connectAttr(blend_node + ".output", self.div_cns[i] + ".rotate")

        pm.parentConstraint(self.ik0_ctl, self.cnx0)
        pm.scaleConstraint(self.ik0_ctl, self.cnx0)
        pm.parentConstraint(self.scl_transforms[-1], self.cnx1)
        pm.scaleConstraint(self.scl_transforms[-1], self.cnx1)

    # =====================================================
    # CONNECTOR
    # =====================================================
    def setRelation(self):
        """Set the relation beetween object from guide to rig"""
        self.relatives["root"] = self.cnx0
        self.relatives["eff"] = self.cnx1
        self.controlRelatives["root"] = self.ik0_ctl
        self.controlRelatives["eff"] = self.ik1_ctl
        self.jointRelatives["root"] = 0
        self.jointRelatives["eff"] = -1
        self.aliasRelatives["root"] = "base"
        self.aliasRelatives["eff"] = "tip"

    # =====================================================
    # POST
    # =====================================================
    def postScript(self):
        """Twist leaves, then connect the head once its joints exist.

        step_05 runs after every component has built its joints, so the
        head joint is already in the scene. A guide parent between this
        neck and the head would cycle with the constraint below.
        """
        mults = self._add_twist_leaves()
        driver = self._tip_driver()
        if driver is None:
            return
        ctl, joint = driver

        # Leaf rotateX is the axis down the neck. The guide picks which
        # channel on the tip reference supplies the twist.
        axis = TWIST_AXES[self.settings.get("twistAxis", 1)]
        for mult in mults:
            ctl.attr(axis) >> mult.input1
        self._constrain_ik_to_head(ctl)
        if joint is None:
            pm.displayWarning(
                "[owl_neck] Tip reference has no joint. Left the joint parent alone.")
            return
        self._reparent_head_joint(joint)

    def _tip_driver(self):
        """First tip-reference guide root, resolved like the bounded bow."""
        refs = [
            name.strip()
            for name in (self.settings.get("ikrefarray") or "").split(",")
            if name.strip()
        ]
        if not refs:
            pm.displayWarning(
                "[owl_neck] Tip reference is empty. IK controls left visible.")
            return None
        if len(refs) > 1:
            pm.displayWarning(
                "[owl_neck] Tip reference has several entries. Using {}.".format(refs[0]))

        ref = refs[0]
        comp = self.rig.findComponent(ref)
        if comp is None:
            pm.displayWarning(
                "[owl_neck] Tip reference '{}' was not in this build. "
                "IK controls left visible.".format(ref))
            return None

        ctl = self.rig.findControlRelative(ref)
        global_ctl = getattr(self.rig, "global_ctl", None)
        if not ctl or ctl == global_ctl:
            pm.displayWarning(
                "[owl_neck] '{}' did not resolve to a control. "
                "IK controls left visible.".format(ref))
            return None

        joint = comp.jointList[0] if comp.jointList else None
        return ctl, joint

    def _add_twist_leaves(self):
        """Two leaves per neck joint except the tip. Returns the multipliers."""
        if len(self.jointList) < 2:
            pm.displayWarning("[owl_neck] Not enough joints for twist leaves.")
            return []

        hosts = self.jointList[:-1]
        leaves = []
        for jnt in hosts:
            for sub_id in ("A", "B"):
                leaf_name = jnt.nodeName().replace("_jnt", "_twist%s_jnt" % sub_id)
                pm.select(clear=True)
                leaf = pm.createNode("joint", name=leaf_name)
                leaf.radius.set(1.5)
                pm.parent(leaf, jnt)
                leaf.t.set(0, 0, 0)
                leaf.r.set(0, 0, 0)
                leaf.jo.set(0, 0, 0)
                leaves.append(leaf)

        mults = []
        for leaf, weight in zip(leaves, twist_weights(len(leaves))):
            mult = pm.createNode("multDoubleLinear", name=leaf.name() + "_mult")
            mult.input2.set(weight)
            mult.output >> leaf.rx
            mults.append(mult)
        return mults

    def _constrain_ik_to_head(self, ctl):
        """Position and aim ik1 at the tip reference, then hide both IK controls."""
        head_ctl = ctl.name()
        ik0 = self.ik0_ctl.name()
        ik1 = self.ik1_ctl.name()

        cmds.parentConstraint(
            head_ctl, ik1, maintainOffset=True, skipRotate=["x", "y", "z"])

        aim_target = cmds.createNode(
            "transform", name="{}_aimTarget".format(ik1))
        cmds.parent(aim_target, head_ctl, relative=True)
        cmds.setAttr(aim_target + ".ty", AIM_UP_OFFSET)
        cmds.aimConstraint(
            aim_target,
            ik1,
            aimVector=(0, 1, 0),
            upVector=(0, 0, 1),
            worldUpType="objectrotation",
            worldUpVector=(0, 0, 1),
            worldUpObject=ik0,
            maintainOffset=True)
        cmds.setAttr(aim_target + ".visibility", 0)

        self._ghost_control(self.ik0_ctl)
        self._ghost_control(self.ik1_ctl)

    def _reparent_head_joint(self, target):
        """Hang the referenced joint off the tip, still driven by its control."""
        tip = self.jointList[-1]
        constraints = pm.listConnections(
            target,
            source=True,
            destination=False,
            type="mgear_matrixConstraint") or []
        if not constraints:
            pm.displayWarning(
                "[owl_neck] {} has no mgear_matrixConstraint. "
                "Left its parent alone.".format(target))
            return

        drivers = constraints[0].driverMatrix.inputs()
        if not drivers:
            pm.displayWarning(
                "[owl_neck] Head joint constraint on {} has no driver.".format(target))
            return

        driver = drivers[0]
        pm.delete(constraints[0])
        if target.getParent() != tip:
            pm.parent(target, tip)
        cmds.parentConstraint(driver.name(), target.name(), maintainOffset=True)
        cmds.scaleConstraint(driver.name(), target.name(), maintainOffset=True)

    def _ghost_control(self, ctl):
        """Hide shapes, lock channels, and keep it out of the anim control set."""
        ctl_name = ctl.name()
        for shape in cmds.listRelatives(ctl_name, shapes=True) or []:
            vis_attr = shape + ".visibility"
            cmds.setAttr(vis_attr, lock=False)
            incoming = cmds.listConnections(
                vis_attr, source=True, destination=False, plugs=True) or []
            for source_plug in incoming:
                cmds.disconnectAttr(source_plug, vis_attr)
            cmds.setAttr(vis_attr, 0)

        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(
                "{}.{}".format(ctl_name, attr),
                lock=True, keyable=False, channelBox=False)

        for grp_members in self.groups.values():
            if ctl in grp_members:
                grp_members.remove(ctl)
        if ctl in self.controlers:
            self.controlers.remove(ctl)

        for attr in cmds.listAttr(ctl_name, userDefined=True) or []:
            try:
                cmds.deleteAttr("{}.{}".format(ctl_name, attr))
            except Exception as exc:
                pm.displayWarning(
                    "[owl_neck] Could not delete {}.{}: {}".format(
                        ctl_name, attr, exc))
