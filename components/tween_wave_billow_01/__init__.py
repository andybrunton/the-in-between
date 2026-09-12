"""In-Between Wave Billow component.

A chain of joints riding a cubic bezier spine between a base and a tip control,
displaced by a stack of harmonic waves running along it. Capes, tails, cloth
strips: the animator winds the phase and the wave travels down the spine.

The spine bends because the controls turn: the bezier handles sit along each
control's own aim, which is the rig reading of the card's Start / End Angle.
Rolling a control twists its own end of the chain, blended along the span.

Nothing about the wave is a build-time setting. Amplitude starts at zero so the
rig binds on the guide pose, and the animator shapes the wave from there.

See Cards/Wave_Billow.html for the reference behaviour and wave_math.py for the
per point coefficients.
"""

from maya import cmds

import mgear.pymaya as pm

from mgear.shifter import component

from mgear.core import applyop, attribute, curve, node, primitive, transform
from mgear.core import vector

from . import wave_math

# Starting points for the anim attrs, straight off the card's own sliders.
DEFAULT_FREQUENCY = 1.75
DEFAULT_CIRCULARITY = 0.75
DEFAULT_COMPLEXITY = 0.5

# Complexity fades in four layers, so all four are always built.
HARMONIC_LAYERS = len(wave_math.HARMONICS)


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
        # axis the rigger wants the wave to oscillate along.
        self.normal = self.guide.blades["blade"].y
        self.rest_length = vector.getDistance(
            self.guide.apos[0], self.guide.apos[1]
        )
        self.u_params = wave_math.params(self.settings["div"])

        # +X down the chord, +Y the wave axis. wave_math assumes this frame.
        t = transform.getTransformLookingAt(
            self.guide.apos[0],
            self.guide.apos[1],
            self.normal,
            axis="xy",
            negate=False,
        )
        t_tip = transform.setMatrixPosition(t, self.guide.apos[1])

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

        # Spine -----------------------------------------
        # The two inner bezier points ride each control's own X, so turning a
        # control swings the spine out of it the way the card's angles do.
        self.tan_base = primitive.addTransform(
            self.ref_base, self.getName("tan_base"), t
        )
        self.tan_tip = primitive.addTransform(
            self.ref_tip, self.getName("tan_tip"), t_tip
        )
        self.spine_crv = curve.addCnsCurve(
            self.root,
            self.getName("spine_crv"),
            [self.ref_base, self.tan_base, self.tan_tip, self.ref_tip],
            3,
        )
        self.spine_crv.setAttr("visibility", False)

        # Roll: each end frame carries the Wave Twist offset, and every point
        # blends between them, so rolling either control twists its own end.
        self.up_base = primitive.addTransform(
            self.ref_base, self.getName("up_base"), t
        )
        self.up_tip = primitive.addTransform(
            self.ref_tip, self.getName("up_tip"), t_tip
        )

        # Points ----------------------------------------
        # spine_cns rides the spine, wave_loc carries the displacement in that
        # point's tangent / wave frame, and div_cns is respaced evenly along the
        # curve those wave points describe. Everything the DG drives in world
        # space has to stop inheriting its parent.
        self.spine_cns = []
        self.wave_loc = []
        self.twist_ref = []
        self.div_cns = []
        for i in range(len(self.u_params)):
            spine_cns = self._world_transform("spine%s_cns" % i, t)
            self.spine_cns.append(spine_cns)
            self.wave_loc.append(
                primitive.addTransform(
                    spine_cns, self.getName("wave%s_loc" % i), t
                )
            )
            self.twist_ref.append(self._world_transform("twist%s_ref" % i, t))

            div_cns = self._world_transform("div%s_loc" % i, t)
            self.div_cns.append(div_cns)
            self.jnt_pos.append([div_cns, i])

        # Displacing points off the spine stretches the gaps between them, worst
        # at a free end where the envelope peaks, so the joints are respaced
        # along the curve the wave points describe rather than sitting on them.
        #
        # Cubic, not linear. Circularity slides each point along the spine, so
        # once that swing passes the gap between points the wave curve folds
        # back on itself: neighbouring joints collapse together and any
        # orientation taken from the vector between them flips. Getting both
        # position and orientation off a smooth curve's tangent has no such
        # failure, and it holds however many joints the chain has.
        # ponytail: a cubic through the wave points as hulls damps the wave a
        # little at low joint counts, which the animator answers with amplitude.
        # Sampling the wave denser than the joints would remove even that.
        self.wave_crv = curve.addCnsCurve(
            self.root, self.getName("wave_crv"), self.wave_loc, 3
        )
        self.wave_crv.setAttr("visibility", False)

    def _world_transform(self, name, t):
        """A transform the DG drives in world space, so it must not inherit."""
        obj = primitive.addTransform(self.root, self.getName(name), t)
        obj.setAttr("inheritsTransform", False)
        return obj

    # =====================================================
    # ATTRIBUTES
    # =====================================================
    def addAttributes(self):
        """Create the anim and setup rig attributes for the component"""

        # Zero so the rig builds on the guide pose: the wave is the animator's
        # to dial in, and a bind pose wants the joints on the spine.
        self.amp_att = self.addAnimParam(
            "amplitude", "Amplitude", "double", 0, 0, None
        )
        self.freq_att = self.addAnimParam(
            "frequency", "Frequency", "double", DEFAULT_FREQUENCY, 0, None
        )
        # Deliberately unbounded: winding the phase past a cycle is how the
        # wave keeps travelling instead of snapping back at the end of one.
        self.phase_att = self.addAnimParam(
            "phase", "Wave Phase", "double", 0
        )
        self.circ_att = self.addAnimParam(
            "circularity", "Circularity", "double", DEFAULT_CIRCULARITY, 0, 1
        )
        self.complexity_att = self.addAnimParam(
            "complexity", "Complexity", "double", DEFAULT_COMPLEXITY, 0, 1
        )
        self.twist_att = self.addAnimParam(
            "wave_twist", "Wave Twist", "double", 0, -360, 360
        )

        # Spine tension: a TD retunes how hard the controls bend the bezier
        # without rebuilding.
        self.handle_att = self.addSetupParam(
            "handleRatio",
            "Handle Ratio",
            "double",
            self.settings["handleRatio"],
            0.0,
        )

        if self.settings["ikrefarray"]:
            ref_names = self.get_valid_alias_list(
                self.settings["ikrefarray"].split(",")
            )
            if len(ref_names) > 1:
                self.ikref_att = self.addAnimEnumParam(
                    "ikref", "Ik Ref", 0, ref_names
                )

    # =====================================================
    # OPERATORS
    # =====================================================
    def addOperators(self):
        """Create operators and set the relations for the component rig"""

        # eulerToQuat is the sin / cos source for the whole graph, and it lives
        # in a plugin: without this the build silently makes unknown nodes.
        cmds.loadPlugin("quatNodes", quiet=True)

        for up in (self.up_base, self.up_tip):
            pm.connectAttr(self.twist_att, up.attr("rotateX"))

        # Bezier handles -------------------------------
        handle = node.createMulNode(self._chord_length(), self.handle_att)
        pm.connectAttr(handle.attr("outputX"), self.tan_base.attr("tx"))
        node.createMulNode(
            handle.attr("outputX"), -1.0, self.tan_tip.attr("tx")
        )

        self._add_shared_wave_terms()

        # Points ---------------------------------------
        for i, u in enumerate(self.u_params):
            # Roll blended between the two control frames.
            roll = applyop.gear_intmatrix_op(
                self.up_base.attr("worldMatrix[0]"),
                self.up_tip.attr("worldMatrix[0]"),
                u,
            )
            pm.connectAttr(
                node.createDecomposeMatrixNode(roll.attr("output")).attr(
                    "outputRotate"
                ),
                self.twist_ref[i].attr("rotate"),
            )

            cns = applyop.pathCns(
                self.spine_cns[i], self.spine_crv, False, u, True
            )
            cns.setAttr("frontAxis", 0)  # +X down the spine
            cns.setAttr("upAxis", 1)  # +Y the wave axis
            cns.setAttr("worldUpType", 2)  # object rotation up
            cns.setAttr("worldUpVector", 0, 1, 0)
            pm.connectAttr(
                self.twist_ref[i].attr("worldMatrix[0]"),
                cns.attr("worldUpMatrix"),
            )

            self._add_wave_point(self.wave_loc[i], u)
            self._respace(self.div_cns[i], u, self.spine_cns[i])

        # inheritsTransform is off on everything the DG places, so the rig
        # scale has to be handed back or the wave keeps its build size.
        root_scale = node.createDecomposeMatrixNode(self.root.worldMatrix)
        for obj in self.spine_cns + self.div_cns:
            for axis in "xyz":
                pm.connectAttr(
                    root_scale.attr("outputScale%s" % axis.upper()),
                    obj.attr("s%s" % axis),
                )

    def _respace(self, div_cns, fraction, spine_cns):
        """Even arc length placement along the curve the wave points describe.

        Position from the wave curve, orientation from the spine frame under it.
        Orientation can't come from the wave: circularity slides each point
        along the spine, so once that swing passes the gap between points the
        wave curve folds back on itself and has a real cusp, where any tangent
        derived frame reverses. Aiming a joint at its neighbour has the same
        failure, and worse the more joints there are, because the gap it
        measures shrinks while the fold does not. The spine frame under the
        wave is smooth whatever the wave is doing, and it already carries the
        blended control roll.
        """
        mp = pm.createNode("motionPath")
        mp.attr("uValue").set(fraction)
        mp.attr("fractionMode").set(True)
        pm.connectAttr(
            self.wave_crv.attr("worldSpace"), mp.attr("geometryPath")
        )
        pm.connectAttr(mp.attr("allCoordinates"), div_cns.attr("translate"))
        pm.orientConstraint(spine_cns, div_cns, maintainOffset=False)

    def _chord_length(self):
        """Base to tip distance in base control space.

        Local rather than world so the rig global scale does not get squared
        into the handle length: the handles are local offsets on controls that
        already carry that scale.
        """
        rel = applyop.gear_mulmatrix_op(
            self.ref_tip.attr("worldMatrix[0]"),
            self.ref_base.attr("worldInverseMatrix[0]"),
        )
        dist = pm.createNode("distanceBetween")
        # point1 stays at the origin, so this is the length of rel's translate.
        pm.connectAttr(rel.attr("output"), dist.attr("inMatrix1"))
        return dist.attr("distance")

    def _add_shared_wave_terms(self):
        """Per harmonic terms that do not depend on the point: gain and phase."""

        # One setRange holds all three complexity windows and clamps them.
        weights = pm.createNode("setRange")
        for axis, h in zip("XYZ", (1, 2, 3)):
            start, span = wave_math.HARMONICS[h][3]
            pm.connectAttr(self.complexity_att, weights.attr("value" + axis))
            weights.attr("oldMin" + axis).set(start)
            weights.attr("oldMax" + axis).set(start + span)
            weights.attr("max" + axis).set(1)

        weighted = node.createMulNode(
            [self.amp_att] * 3,
            [weights.attr("outValue" + axis) for axis in "XYZ"],
        )
        # The base layer is always at full weight.
        self.harmonic_amp = [self.amp_att] + [
            weighted.attr("output" + axis) for axis in "XYZ"
        ]

        # -2 * phase is shared; each harmonic adds its complexity driven offset.
        # The gain is what makes the slider worth animating: see wave_math.
        base_phase = node.createMulNode(
            self.phase_att, -2.0 * wave_math.DEGREES_PER_PHASE_UNIT
        )
        offsets = node.createMulNode(
            [self.complexity_att] * 3,
            [wave_math.phase_gain(h) for h in (1, 2, 3)],
        )
        shifted = pm.createNode("plusMinusAverage")
        pm.connectAttr(offsets.attr("output"), shifted.attr("input3D[0]"))
        for axis in "xyz":
            pm.connectAttr(
                base_phase.attr("outputX"),
                shifted.attr("input3D[1].input3D%s" % axis),
            )
        self.phase_terms = [base_phase.attr("outputX")] + [
            shifted.attr("output3D%s" % axis) for axis in "xyz"
        ]

    def _add_wave_point(self, wave_loc, u):
        """Sum the harmonic layers into this point's tangent / wave offset."""
        mode = self.settings["pinMode"]
        total = pm.createNode("plusMinusAverage")

        for h in range(HARMONIC_LAYERS):
            two_theta = node.createAddNode(
                node.createMulNode(
                    self.freq_att, wave_math.theta_gain(u, h)
                ).attr("outputX"),
                self.phase_terms[h],
            )
            # quatX / quatW of a pure rotateX are the sin / cos of half the
            # angle, so feeding 2*theta gets both terms of the layer out of one
            # node. The plain double lands on a doubleAngle, which makes Maya
            # insert a unitConversion and read the number as degrees.
            # Kept as a name: pymaya has no wrapper class for a plugin node.
            quat = cmds.createNode("eulerToQuat")
            cmds.connectAttr(
                str(two_theta.attr("output")), quat + ".inputRotateX"
            )

            gain = node.createMulNode(
                self.harmonic_amp[h], wave_math.amp_gain(u, h, mode)
            )
            layer = node.createMulNode(
                [gain.attr("outputX"), gain.attr("outputX")],
                [quat + ".outputQuatX", quat + ".outputQuatW"],
            )
            pm.connectAttr(
                layer.attr("output"), total.attr("input3D[%s]" % h)
            )

        node.createMulNode(
            total.attr("output3Dx"), self.circ_att, wave_loc.attr("tx")
        )
        pm.connectAttr(total.attr("output3Dy"), wave_loc.attr("ty"))

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
