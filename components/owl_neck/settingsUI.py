"""Component settings tab for owl_neck.

Hand written rather than generated from a .ui file.
"""

from mgear.vendor.Qt import QtCore, QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("owl_neck_settings")
        Form.resize(350, 380)

        main_layout = QtWidgets.QVBoxLayout(Form)
        group = QtWidgets.QGroupBox(Form)
        form = QtWidgets.QFormLayout(group)

        self.division_spinBox = QtWidgets.QSpinBox(group)
        self.division_spinBox.setMinimum(3)
        self.division_spinBox.setMaximum(100)
        self.division_spinBox.setToolTip(
            "Neck joints from base to tip. Twist leaves go on every joint except the tip."
        )
        form.addRow("Divisions", self.division_spinBox)

        self.position_slider, self.position_spinBox = self._percent_row(group, form, "Position")
        self.lockOri_slider, self.lockOri_spinBox = self._percent_row(group, form, "Lock Orient")
        self.softness_slider, self.softness_spinBox = self._percent_row(group, form, "Softness")

        self.maxStretch_spinBox = QtWidgets.QDoubleSpinBox(group)
        self.maxStretch_spinBox.setMinimum(1.0)
        self.maxStretch_spinBox.setSingleStep(0.1)
        self.maxStretch_spinBox.setValue(3.0)
        form.addRow("Max Stretch", self.maxStretch_spinBox)

        self.maxSquash_spinBox = QtWidgets.QDoubleSpinBox(group)
        self.maxSquash_spinBox.setMinimum(0.1)
        self.maxSquash_spinBox.setMaximum(1.0)
        self.maxSquash_spinBox.setSingleStep(0.1)
        self.maxSquash_spinBox.setValue(0.1)
        form.addRow("Max Squash", self.maxSquash_spinBox)

        self.squashStretchProfile_pushButton = QtWidgets.QPushButton(
            "Squash and Stretch Profile", group
        )

        main_layout.addWidget(group)

        # Same list as the bounded bow tip reference: pick a guide root, no typed name.
        ref_group = QtWidgets.QGroupBox("Tip Reference", Form)
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
        self.refArray_listWidget.setToolTip(
            "Guide root the neck tip follows, usually the head. "
            "The first entry is used."
        )
        ref_row.addWidget(self.refArray_listWidget)

        button_column = QtWidgets.QVBoxLayout()
        self.refArrayAdd_pushButton = QtWidgets.QPushButton("<<", ref_group)
        self.refArrayAdd_pushButton.setToolTip(
            "Add the selected guide root. Do not parent it under this neck."
        )
        self.refArrayRemove_pushButton = QtWidgets.QPushButton(">>", ref_group)
        self.refArrayRemove_pushButton.setToolTip(
            "Remove the highlighted reference"
        )
        button_column.addWidget(self.refArrayAdd_pushButton)
        button_column.addWidget(self.refArrayRemove_pushButton)
        button_column.addStretch()
        ref_row.addLayout(button_column)
        ref_layout.addLayout(ref_row)

        axis_row = QtWidgets.QHBoxLayout()
        axis_row.addWidget(QtWidgets.QLabel("Twist Driver Axis", ref_group))
        self.twistAxis_comboBox = QtWidgets.QComboBox(ref_group)
        self.twistAxis_comboBox.addItems(["Rotate X", "Rotate Y", "Rotate Z"])
        self.twistAxis_comboBox.setCurrentIndex(1)
        self.twistAxis_comboBox.setToolTip(
            "Which rotation on the tip reference drives the neck twist."
        )
        axis_row.addWidget(self.twistAxis_comboBox)
        axis_row.addStretch()
        ref_layout.addLayout(axis_row)
        main_layout.addWidget(ref_group)

        main_layout.addStretch(1)
        main_layout.addWidget(self.squashStretchProfile_pushButton)

        self._sync(self.position_slider, self.position_spinBox)
        self._sync(self.lockOri_slider, self.lockOri_spinBox)
        self._sync(self.softness_slider, self.softness_spinBox)

    def _percent_row(self, parent, form, label):
        row = QtWidgets.QHBoxLayout()
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, parent)
        slider.setMaximum(100)
        spin = QtWidgets.QSpinBox(parent)
        spin.setMaximum(100)
        row.addWidget(slider)
        row.addWidget(spin)
        form.addRow(label, row)
        return slider, spin

    def _sync(self, slider, spin):
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
