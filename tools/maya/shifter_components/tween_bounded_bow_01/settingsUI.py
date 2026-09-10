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
        ref_layout = QtWidgets.QHBoxLayout(ref_group)

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
        ref_layout.addWidget(self.refArray_listWidget)

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
        ref_layout.addLayout(button_column)

        main_layout.addWidget(ref_group)
        main_layout.addStretch()

        QtCore.QMetaObject.connectSlotsByName(Form)
