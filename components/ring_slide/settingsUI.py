"""Component settings tab for ring_slide."""

from mgear.vendor.Qt import QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("ring_slide_settings")
        Form.resize(360, 200)
        layout = QtWidgets.QVBoxLayout(Form)
        names = QtWidgets.QGroupBox("Captured", Form)
        form = QtWidgets.QFormLayout(names)
        self.mesh_label = QtWidgets.QLabel(names)
        self.over_label = QtWidgets.QLabel(names)
        self.under_label = QtWidgets.QLabel(names)
        self.parent_label = QtWidgets.QLabel(names)
        for label in (self.mesh_label, self.over_label, self.under_label, self.parent_label):
            label.setWordWrap(True)
        form.addRow("Parent", self.parent_label)
        form.addRow("Mesh", self.mesh_label)
        form.addRow("Over", self.over_label)
        form.addRow("Under", self.under_label)
        layout.addWidget(names)
