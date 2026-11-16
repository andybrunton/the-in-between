"""Component settings tab for ring_slide."""

from mgear.vendor.Qt import QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("ring_slide_settings")
        Form.resize(360, 280)
        layout = QtWidgets.QVBoxLayout(Form)

        drive = QtWidgets.QGroupBox("Parent", Form)
        drive_form = QtWidgets.QFormLayout(drive)
        self.spline_edit = QtWidgets.QLineEdit(drive)
        self.spline_edit.setToolTip(
            "Guide root of the spline this seam rides. Filled in by the tool."
        )
        self.joint_spin = QtWidgets.QSpinBox(drive)
        self.joint_spin.setRange(-1, 999)
        self.joint_spin.setSpecialValueText("Auto")
        self.joint_spin.setToolTip(
            "Numbered spline joint the seam is parented to. Auto blends the "
            "two joints nearest the seam. Filled in by the tool."
        )
        self.under_spin = QtWidgets.QSpinBox(drive)
        self.over_spin = QtWidgets.QSpinBox(drive)
        for spin, side in ((self.under_spin, "under"), (self.over_spin, "over")):
            spin.setRange(-1, 100)
            spin.setSuffix("%")
            spin.setSpecialValueText("Auto")
            spin.setToolTip(
                "How much of the head's turn the {} loop follows. 100 is the "
                "head, 0 is the chest. Auto looks at the mesh shell the loop "
                "belongs to: one that reaches the head turns with it, one that "
                "reaches the chest stays, the neck takes the seam's place on "
                "the neck.".format(side)
            )
        self.base_edit = QtWidgets.QLineEdit(drive)
        self.tip_edit = QtWidgets.QLineEdit(drive)
        drive_form.addRow("Parent Spline", self.spline_edit)
        drive_form.addRow("Parent Joint Index", self.joint_spin)
        drive_form.addRow("Under Turns", self.under_spin)
        drive_form.addRow("Over Turns", self.over_spin)
        drive_form.addRow("Base Control", self.base_edit)
        drive_form.addRow("Tip Control", self.tip_edit)
        layout.addWidget(drive)

        names = QtWidgets.QGroupBox("Captured", Form)
        form = QtWidgets.QFormLayout(names)
        self.mesh_label = QtWidgets.QLabel(names)
        self.over_label = QtWidgets.QLabel(names)
        self.under_label = QtWidgets.QLabel(names)
        for label in (self.mesh_label, self.over_label, self.under_label):
            label.setWordWrap(True)
        form.addRow("Mesh", self.mesh_label)
        form.addRow("Over", self.over_label)
        form.addRow("Under", self.under_label)
        layout.addWidget(names)
