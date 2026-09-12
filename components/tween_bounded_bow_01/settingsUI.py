"""Component settings tab for tween_bounded_bow_01.

Hand written rather than generated from a .ui file so there is no Designer /
pyside-uic round trip on every parameter change.
"""

from mgear.vendor.Qt import QtCore, QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("tween_bounded_bow_01_settings")
        Form.resize(350, 460)

        main_layout = QtWidgets.QVBoxLayout(Form)

        drive_group = QtWidgets.QGroupBox("Drive", Form)
        drive_form = QtWidgets.QFormLayout(drive_group)

        self.driveMode_comboBox = QtWidgets.QComboBox(drive_group)
        self.driveMode_comboBox.addItems(["Distance", "Angle"])
        drive_form.addRow("Drive Mode", self.driveMode_comboBox)

        self.minLength_doubleSpinBox = QtWidgets.QDoubleSpinBox(drive_group)
        self.minLength_doubleSpinBox.setRange(0.01, 1.0)
        self.minLength_doubleSpinBox.setSingleStep(0.01)
        self.minLength_doubleSpinBox.setDecimals(3)
        self.minLength_doubleSpinBox.setToolTip(
            "Distance mode: fraction of the guide length at which the bulge is "
            "at full height."
        )
        drive_form.addRow("Min Length Ratio", self.minLength_doubleSpinBox)

        self.maxBendAngle_doubleSpinBox = QtWidgets.QDoubleSpinBox(drive_group)
        self.maxBendAngle_doubleSpinBox.setRange(1.0, 180.0)
        self.maxBendAngle_doubleSpinBox.setDecimals(1)
        self.maxBendAngle_doubleSpinBox.setToolTip(
            "Angle mode: bend between the chord and the tip control's own "
            "aim, in degrees, at which the bulge is at full height."
        )
        drive_form.addRow("Max Bend Angle", self.maxBendAngle_doubleSpinBox)

        self.easing_comboBox = QtWidgets.QComboBox(drive_group)
        self.easing_comboBox.addItems(["Smooth", "Linear", "Ease In", "Ease Out"])
        drive_form.addRow("Easing", self.easing_comboBox)

        self.angleDriver_group = QtWidgets.QGroupBox("Angle Driver", drive_group)
        angle_form = QtWidgets.QFormLayout(self.angleDriver_group)

        angle_ref_row = QtWidgets.QHBoxLayout()
        self.angleRef_lineEdit = QtWidgets.QLineEdit(self.angleDriver_group)
        self.angleRef_lineEdit.setToolTip(
            "mGear guide name of the control or locator whose rotation "
            "drives the bow (e.g. arm_L0_elbow). Leave empty to infer bend "
            "from the tip control pose."
        )
        self.angleRef_pick_pushButton = QtWidgets.QPushButton(
            "<<", self.angleDriver_group
        )
        self.angleRef_pick_pushButton.setToolTip(
            "Use the selected guide component root or locator"
        )
        angle_ref_row.addWidget(self.angleRef_lineEdit)
        angle_ref_row.addWidget(self.angleRef_pick_pushButton)
        angle_form.addRow("Driver", angle_ref_row)

        self.angleAxis_comboBox = QtWidgets.QComboBox(self.angleDriver_group)
        self.angleAxis_comboBox.addItems(["Rotate X", "Rotate Y", "Rotate Z"])
        self.angleAxis_comboBox.setToolTip(
            "Which rotation channel on the driver opens the bow."
        )
        angle_form.addRow("Axis", self.angleAxis_comboBox)

        self.angleReverse_checkBox = QtWidgets.QCheckBox(
            "Reverse", self.angleDriver_group
        )
        self.angleReverse_checkBox.setToolTip(
            "Flip the driver sign so negative rotation drives the bulge."
        )
        angle_form.addRow("", self.angleReverse_checkBox)

        self.angleJointDriver_checkBox = QtWidgets.QCheckBox(
            "Joint driver", self.angleDriver_group
        )
        self.angleJointDriver_checkBox.setToolTip(
            "Drive from a joint index on the referenced component instead of "
            "a control or locator. Use this for neck IK, spine chains, etc."
        )
        angle_form.addRow("", self.angleJointDriver_checkBox)

        self.angleJointIndex_spinBox = QtWidgets.QSpinBox(self.angleDriver_group)
        self.angleJointIndex_spinBox.setRange(0, 999)
        self.angleJointIndex_spinBox.setToolTip(
            "0-based index into the driver component's joint list."
        )
        angle_form.addRow("Joint index", self.angleJointIndex_spinBox)

        drive_form.addRow(self.angleDriver_group)

        main_layout.addWidget(drive_group)

        shape_group = QtWidgets.QGroupBox("Shape", Form)
        shape_form = QtWidgets.QFormLayout(shape_group)

        self.div_spinBox = QtWidgets.QSpinBox(shape_group)
        self.div_spinBox.setRange(2, 64)
        shape_form.addRow("Joints", self.div_spinBox)

        self.bulge_doubleSpinBox = QtWidgets.QDoubleSpinBox(shape_group)
        self.bulge_doubleSpinBox.setRange(0.0, 10.0)
        self.bulge_doubleSpinBox.setSingleStep(0.01)
        self.bulge_doubleSpinBox.setDecimals(3)
        self.bulge_doubleSpinBox.setToolTip(
            "Peak bulge height as a fraction of the guide length. Sets the "
            "default of the animatable 'bulge' attribute."
        )
        shape_form.addRow("Bulge Ratio", self.bulge_doubleSpinBox)

        self.tangent_doubleSpinBox = QtWidgets.QDoubleSpinBox(shape_group)
        self.tangent_doubleSpinBox.setRange(0.0, 1.0)
        self.tangent_doubleSpinBox.setSingleStep(0.05)
        self.tangent_doubleSpinBox.setDecimals(3)
        self.tangent_doubleSpinBox.setToolTip(
            "Bezier handle span. Low is peaky, high is flat topped."
        )
        shape_form.addRow("Tangent Weight", self.tangent_doubleSpinBox)

        main_layout.addWidget(shape_group)

        # Same layout as the stock IK Reference Array: list on the left, add /
        # remove stacked on the right, drag to reorder.
        ref_group = QtWidgets.QGroupBox("Tip Ctl Reference Array", Form)
        ref_layout = QtWidgets.QVBoxLayout(ref_group)
        ref_row = QtWidgets.QHBoxLayout()

        self.refArray_listWidget = QtWidgets.QListWidget(ref_group)
        self.refArray_listWidget.setDragDropOverwriteMode(True)
        self.refArray_listWidget.setDragDropMode(
            QtWidgets.QAbstractItemView.InternalMove
        )
        self.refArray_listWidget.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.refArray_listWidget.setAlternatingRowColors(True)
        self.refArray_listWidget.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.refArray_listWidget.setSelectionRectVisible(False)
        ref_row.addWidget(self.refArray_listWidget)

        button_column = QtWidgets.QVBoxLayout()
        self.refArrayAdd_pushButton = QtWidgets.QPushButton("<<", ref_group)
        self.refArrayAdd_pushButton.setToolTip(
            "Add the selected objects as space references for the tip control"
        )
        self.refArrayRemove_pushButton = QtWidgets.QPushButton(">>", ref_group)
        self.refArrayRemove_pushButton.setToolTip(
            "Remove the highlighted references from the list"
        )
        button_column.addWidget(self.refArrayAdd_pushButton)
        button_column.addWidget(self.refArrayRemove_pushButton)
        button_column.addStretch()
        ref_row.addLayout(button_column)
        ref_layout.addLayout(ref_row)

        self.ikrefJointDriver_checkBox = QtWidgets.QCheckBox(
            "Joint reference", ref_group
        )
        self.ikrefJointDriver_checkBox.setToolTip(
            "Follow a joint index on each listed component instead of a "
            "control or locator. Use this for neck IK, spine chains, etc."
        )
        ref_layout.addWidget(self.ikrefJointDriver_checkBox)

        ikref_joint_row = QtWidgets.QHBoxLayout()
        ikref_joint_row.addWidget(QtWidgets.QLabel("Joint index", ref_group))
        self.ikrefJointIndex_spinBox = QtWidgets.QSpinBox(ref_group)
        self.ikrefJointIndex_spinBox.setRange(0, 999)
        self.ikrefJointIndex_spinBox.setToolTip(
            "0-based index into each referenced component's joint list."
        )
        ikref_joint_row.addWidget(self.ikrefJointIndex_spinBox)
        ikref_joint_row.addStretch()
        ref_layout.addLayout(ikref_joint_row)

        main_layout.addWidget(ref_group)
        main_layout.addStretch()

        QtCore.QMetaObject.connectSlotsByName(Form)
