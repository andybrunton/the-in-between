"""In-Between Bounded Bow component.

A chain of joints laid out on a cubic bezier bow between a base and a tip
control. The bulge height is driven either by the base/tip distance closing
(distance mode) or by the bow kinking at the tip, which covers the tip swinging
off the chord and the tip turning on the spot (angle mode).

See Cards/Bounded_Bow.html for the reference behaviour and bow_math.py for the
curve maths.
"""

from maya import cmds

import mgear.pymaya as pm

from mgear.shifter import component

from mgear.core import applyop, attribute, node, primitive, transform, vector

from . import bow_math

# easing setting -> remapValue ramp as (position, value, interpolation)
# interpolation: 1 = linear, 2 = smooth, 3 = spline
EASING_RAMPS = {
    0: [(0.0, 0.0, 2), (1.0, 1.0, 2)],  # smooth
    1: [(0.0, 0.0, 1), (1.0, 1.0, 1)],  # linear
    2: [(0.0, 0.0, 3), (0.5, 0.25, 3), (1.0, 1.0, 3)],  # ease in  (~t^2)
    3: [(0.0, 0.0, 3), (0.5, 0.75, 3), (1.0, 1.0, 3)],  # ease out (~1-(1-t)^2)
}

DRIVE_DISTANCE = 0
DRIVE_ANGLE = 1


##########################################################
# COMPONENT
##########################################################


class Component(component.Main):
    """Shifter component Class"""

    # =====================================================
    # OBJECTS
    # =====================================================
    def addObjects(self):
        """Add all the objects needed to create the component."""

        # The blade icon is drawn with its flag toward +Y, so blade.y is the
        # direction the rigger pointed the bulge.
        self.normal = self.guide.blades["blade"].y
        self.rest_length = vector.getDistance(
            self.guide.apos[0], self.guide.apos[1]
        )
        self.is_angle_drive = self.settings["driveMode"] == DRIVE_ANGLE

        # +X down the chord, +Y is the bulge plane. bow_math assumes this frame.
        t = transform.getTransformLookingAt(
            self.guide.apos[0],
            self.guide.apos[1],
            self.normal,
            axis="xy",
            negate=False,
        )

        # Base ------------------------------------------
        self.ctl_npo = primitive.addTransform(
            self.root, self.getName("ctl_npo"), t
        )
        self.ctl = self.addCtl(
            self.ctl_npo,
            "base_ctl",
            t,
            self.color_ik,
            "square",
            w=self.rest_length * 0.2,
            tp=self.parentCtlTag,
        )
        attribute.setKeyableAttributes(self.ctl, self.tr_params)
        self.ref_base = primitive.addTransform(
            self.ctl, self.getName("ref_base"), t
        )

        # Tip -------------------------------------------
        t_tip = transform.setMatrixPosition(t, self.guide.apos[1])
        self.ik_cns = primitive.addTransform(
            self.root, self.getName("ik_cns"), t_tip
        )
        self.tip_npo = primitive.addTransform(
            self.ik_cns, self.getName("tip_npo"), t_tip
        )
        self.tip_ctl = self.addCtl(
            self.tip_npo,
            "tip_ctl",
            t_tip,
            self.color_ik,
            "square",
            w=self.rest_length * 0.2,
            tp=self.ctl,
        )
        attribute.setKeyableAttributes(self.tip_ctl, self.tr_params)
        self.ref_tip = primitive.addTransform(
            self.tip_ctl, self.getName("ref_tip"), t_tip
        )

        # Bow space -------------------------------------
        # bow_root is re-aimed at runtime, bow_twist rolls the bulge plane
        # around the chord.
        self.bow_root = primitive.addTransform(
            self.root, self.getName("bow_root"), t
        )
        self.bow_twist = primitive.addTransform(
            self.bow_root, self.getName("bow_twist"), t
        )

        self.u_params = bow_math.params(self.settings["div"])
        self.div_cns = []
        for i in range(len(self.u_params)):
            # addTransform re-parents world-preserving, so it needs the bow
            # matrix: without it the loc keeps world identity and its untouched
            # tz holds the leftover offset back to the origin.
            div_cns = primitive.addTransform(
                self.bow_twist, self.getName("div%s_loc" % i), t
            )
            self.div_cns.append(div_cns)
            self.jnt_pos.append([div_cns, i])

    # =====================================================
    # ATTRIBUTES
    # =====================================================
    def addAttributes(self):
        """Create the anim and setup rig attributes for the component"""

        self.bulge_att = self.addAnimParam(
            "bulge",
            "Bulge",
            "double",
            self.rest_length * self.settings["bulgeRatio"],
            0,
            None,
        )
        self.tangent_att = self.addAnimParam(
            "tangent",
            "Tangent Weight",
            "double",
            self.settings["tangentWeight"],
            0,
            1,
        )
        self.twist_att = self.addAnimParam(
            "bulge_twist", "Bulge Twist", "double", 0, -360, 360
        )

        if self.settings["ikrefarray"]:
            ref_names = self.get_valid_alias_list(
                self.settings["ikrefarray"].split(",")
            )
            if len(ref_names) > 1:
                self.ikref_att = self.addAnimEnumParam(
                    "ikref", "Ik Ref", 0, ref_names
                )

        # Drive thresholds stay on the setup host so a TD can retune the falloff
        # after the build without editing the DG.
        if self.is_angle_drive:
            # doubleAngle on both sides of the comparison keeps Maya's implicit
            # unit conversion consistent with angleBetween.angle.
            self.threshold_att = self.addSetupParam(
                "maxBendAngle",
                "Max Bend Angle",
                "doubleAngle",
                self.settings["maxBendAngle"],
            )
        else:
            self.rest_length_att = self.addSetupParam(
                "restLength", "Rest Length", "double", self.rest_length, 0.001
            )
            self.threshold_att = self.addSetupParam(
                "minLength",
                "Min Length",
                "double",
                self.rest_length * self.settings["minLengthRatio"],
                0.001,
            )

    # =====================================================
    # OPERATORS
    # =====================================================
    def addOperators(self):
        """Create operators and set the relations for the component rig"""

        # Bow space -------------------------------------
        pm.pointConstraint(self.ref_base, self.bow_root, maintainOffset=False)
        applyop.aimCns(
            self.bow_root,
            self.ref_tip,
            axis="xy",
            wupType="objectrotation",
            wupVector=[0, 1, 0],
            wupObject=self.ctl,
            maintainOffset=False,
        )
        pm.connectAttr(self.twist_att, self.bow_twist.attr("rotateX"))

        # Chord length, measured in component local space so the rig global
        # scale does not leak into the drive.
        length_att = self._local_distance()

        # Compression / bend -> 0..1, eased, in a single remapValue.
        remap = pm.createNode("remapValue")
        self._set_easing_ramp(remap)
        if self.is_angle_drive:
            pm.connectAttr(self._bend_angle(), remap.attr("inputValue"))
            remap.attr("inputMin").set(0)
            pm.connectAttr(self.threshold_att, remap.attr("inputMax"))
        else:
            pm.connectAttr(length_att, remap.attr("inputValue"))
            pm.connectAttr(self.rest_length_att, remap.attr("inputMin"))
            pm.connectAttr(self.threshold_att, remap.attr("inputMax"))

        height_att = node.createMulNode(
            remap.attr("outValue"), self.bulge_att
        ).attr("outputX")

        # Bow points ------------------------------------
        for div_cns, u in zip(self.div_cns, self.u_params):
            kx_tangent, kx_base, ky = bow_math.bezier_coefficients(u)

            tangent_term = node.createMulNode(self.tangent_att, kx_tangent)
            x_norm = pm.createNode("plusMinusAverage")
            pm.connectAttr(
                tangent_term.attr("outputX"), x_norm.attr("input1D[0]")
            )
            cmds.setAttr("{}.input1D[1]".format(x_norm), kx_base)
            node.createMulNode(
                [x_norm.attr("output1D"), height_att],
                [length_att, ky],
                [div_cns.attr("tx"), div_cns.attr("ty")],
            )

        # Orient each point down the bow by aiming at its neighbour.
        for i, div_cns in enumerate(self.div_cns):
            if i < len(self.div_cns) - 1:
                target, axis = self.div_cns[i + 1], "xy"
            else:
                target, axis = self.div_cns[i - 1], "-xy"
            applyop.aimCns(
                div_cns,
                target,
                axis=axis,
                wupType="objectrotation",
                wupVector=[0, 1, 0],
                wupObject=self.bow_twist,
                maintainOffset=False,
            )

    def _local_distance(self):
        """distanceBetween base and tip, expressed in component root space."""
        dist = pm.createNode("distanceBetween")
        for ref, point in ((self.ref_base, "point1"), (self.ref_tip, "point2")):
            mul_m = applyop.gear_mulmatrix_op(
                ref.attr("worldMatrix[0]"),
                self.root.attr("worldInverseMatrix[0]"),
            )
            decomp = pm.createNode("decomposeMatrix")
            pm.connectAttr(mul_m.attr("output"), decomp.attr("inputMatrix"))
            pm.connectAttr(
                decomp.attr("outputTranslate"), dist.attr(point)
            )
        return dist.attr("distance")

    def _bend_angle(self):
        """The kink at the tip: chord direction against the tip ctl's own aim.

        Both ways a bow bends have to count. The tip can swing off the chord,
        and it can turn on the spot without moving at all, which is what an
        elbow closing under a bicep does. Measuring the chord against a fixed
        rest direction only catches the first.
        """
        mul_m = applyop.gear_mulmatrix_op(
            self.ref_tip.attr("worldMatrix[0]"),
            self.ref_base.attr("worldInverseMatrix[0]"),
        )
        decomp = pm.createNode("decomposeMatrix")
        pm.connectAttr(mul_m.attr("output"), decomp.attr("inputMatrix"))

        aim = pm.createNode("vectorProduct")
        aim.attr("operation").set(3)  # vector x matrix, ignores translation
        aim.attr("input1").set(1, 0, 0)
        pm.connectAttr(mul_m.attr("output"), aim.attr("matrix"))

        angle = pm.createNode("angleBetween")
        pm.connectAttr(decomp.attr("outputTranslate"), angle.attr("vector1"))
        # Both refs come off the same guide matrix, so at rest the tip's +X
        # lies along the chord and the angle is zero.
        pm.connectAttr(aim.attr("output"), angle.attr("vector2"))
        return angle.attr("angle")

    def _set_easing_ramp(self, remap):
        ramp = EASING_RAMPS[self.settings["easing"]]
        # Clear the default two entries so a 3 point ramp does not inherit them.
        for i in cmds.getAttr("{}.value".format(remap), multiIndices=True) or []:
            cmds.removeMultiInstance("{}.value[{}]".format(remap, i), b=True)
        for i, (position, value, interp) in enumerate(ramp):
            entry = "{}.value[{}]".format(remap, i)
            cmds.setAttr("{}.value_Position".format(entry), position)
            cmds.setAttr("{}.value_FloatValue".format(entry), value)
            cmds.setAttr("{}.value_Interp".format(entry), interp)

    # =====================================================
    # CONNECTOR
    # =====================================================
    def setRelation(self):
        """Set the relation between object from guide to rig"""
        self.relatives["root"] = self.div_cns[0]
        self.relatives["tip"] = self.div_cns[-1]

        self.jointRelatives["root"] = 0
        self.jointRelatives["tip"] = len(self.div_cns) - 1

        self.controlRelatives["root"] = self.ctl
        self.controlRelatives["tip"] = self.tip_ctl

    def connect_standard(self):
        """standard connection definition for the component"""
        self.connect_standardWithSimpleIkRef()
