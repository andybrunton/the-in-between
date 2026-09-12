"""Component settings tab for tween_wave_billow_01.

Hand written rather than generated from a .ui file so there is no Designer /
pyside-uic round trip on every parameter change.
"""

from mgear.vendor.Qt import QtCore, QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("tween_wave_billow_01_settings")
        Form.resize(350, 340)

        main_layout = QtWidgets.QVBoxLayout(Form)

        spine_group = QtWidgets.QGroupBox("Spine", Form)
        spine_form = QtWidgets.QFormLayout(spine_group)

        self.div_spinBox = QtWidgets.QSpinBox(spine_group)
        self.div_spinBox.setRange(2, 64)
        spine_form.addRow("Joints", self.div_spinBox)

        self.handle_doubleSpinBox = QtWidgets.QDoubleSpinBox(spine_group)
        self.handle_doubleSpinBox.setRange(0.0, 1.0)
        self.handle_doubleSpinBox.setSingleStep(0.01)
        self.handle_doubleSpinBox.setDecimals(3)
        self.handle_doubleSpinBox.setToolTip(
            "Bezier handle length as a fraction of the base to tip distance. "
            "Low keeps the spine straight until close to the controls, high "
            "lets them swing it wide."
        )
        spine_form.addRow("Handle Ratio", self.handle_doubleSpinBox)

        self.pinMode_comboBox = QtWidgets.QComboBox(spine_group)
        self.pinMode_comboBox.addItems(["Free Start", "Free End", "Pinned"])
        self.pinMode_comboBox.setToolTip(
            "Which end of the spine the wave is allowed to move. Free End is "
            "a cape off a shoulder, Pinned is a rope tied at both ends."
        )
        spine_form.addRow("Pin Mode", self.pinMode_comboBox)

        main_layout.addWidget(spine_group)

        note = QtWidgets.QLabel(
            "Amplitude, frequency, circularity, complexity, phase and twist "
            "are anim attrs on the rig UI host. Amplitude starts at zero, so "
            "the rig builds on the guide pose.",
            Form,
        )
        note.setWordWrap(True)
        main_layout.addWidget(note)

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
