"""Guide for one sliding seam between two edge rings."""

from functools import partial

import mgear.pymaya as pm

from mgear.shifter.component import guide
from mgear.core import attribute, pyqt
from mgear.vendor.Qt import QtWidgets, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya.app.general.mayaMixin import MayaQDockWidget

from . import settingsUI as sui


AUTHOR = "In-Between"
URL = "https://github.com/andre/the-in-between"
EMAIL = ""
VERSION = [0, 1, 0]


def guide_name(text):
    """A guide node name as typed. Underscores are legal and must stay."""
    return (text or "").strip()


assert guide_name("neck_C0_root") == "neck_C0_root"


TYPE = "ring_slide"
NAME = "ring"
DESCRIPTION = (
    "One seam. Two edge rings, an over and an under, and a center at the "
    "over ring. Point it at a base spline, a base control, and a tip control "
    "and the spline's own controls are hidden: the seam rides the spline "
    "joints and twists between the base and the tip. An optional parent "
    "component still lines the center up exactly "
    "when no spline is set.\n\n"
    "Draw it from the ring_guide window. The tip has to stay a sibling of "
    "the base. Parenting the tip under the spline cycles the tip constraint."
)


_UPGRADE_PARAMS = (
    ("mesh", "string", "", None, None),
    ("overEdge", "string", "", None, None),
    ("underEdge", "string", "", None, None),
    ("overVerts", "string", "", None, None),
    ("underVerts", "string", "", None, None),
    ("overCrv", "string", "", None, None),
    ("underCrv", "string", "", None, None),
    ("parentComp", "string", "", None, None),
    ("baseSpline", "string", "", None, None),
    ("baseCtl", "string", "", None, None),
    ("tipCtl", "string", "", None, None),
    ("splineJoint", "long", -1, None, None),
    ("underTurn", "long", -1, None, None),
    ("overTurn", "long", -1, None, None),
    ("useIndex", "bool", False, None, None),
    ("parentJointIndex", "long", -1, None, None),
)


class Guide(guide.ComponentGuide):
    """Component Guide Class"""

    compType = TYPE
    compName = NAME
    description = DESCRIPTION

    author = AUTHOR
    url = URL
    email = EMAIL
    version = VERSION

    def postInit(self):
        self.save_transform = ["root"]

    def addObjects(self):
        self.root = self.addRoot()

    def addParameters(self):
        self.pMesh = self.addParam("mesh", "string", "")
        self.pOverEdge = self.addParam("overEdge", "string", "")
        self.pUnderEdge = self.addParam("underEdge", "string", "")
        self.pOverVerts = self.addParam("overVerts", "string", "")
        self.pUnderVerts = self.addParam("underVerts", "string", "")
        self.pOverCrv = self.addParam("overCrv", "string", "")
        self.pUnderCrv = self.addParam("underCrv", "string", "")
        self.pParentComp = self.addParam("parentComp", "string", "")
        self.pBaseSpline = self.addParam("baseSpline", "string", "")
        self.pBaseCtl = self.addParam("baseCtl", "string", "")
        self.pTipCtl = self.addParam("tipCtl", "string", "")
        self.pSplineJoint = self.addParam("splineJoint", "long", -1, None, None)
        self.pUnderTurn = self.addParam("underTurn", "long", -1, None, None)
        self.pOverTurn = self.addParam("overTurn", "long", -1, None, None)
        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam(
            "parentJointIndex", "long", -1, None, None
        )

    @classmethod
    def upgrade_root(cls, root):
        for script_name, value_type, value, minimum, maximum in _UPGRADE_PARAMS:
            if root.hasAttr(script_name):
                continue
            attribute.ParamDef2(
                script_name, value_type, value, None, None, minimum, maximum
            ).create(root)

    def setFromHierarchy(self, root):
        self.upgrade_root(root)
        super(Guide, self).setFromHierarchy(root)


class settingsTab(QtWidgets.QDialog, sui.Ui_Form):
    def __init__(self, parent=None):
        super(settingsTab, self).__init__(parent)
        self.setupUi(self)


class componentSettings(MayaQWidgetDockableMixin, guide.componentMainSettings):
    def __init__(self, parent=None):
        self.toolName = TYPE
        pyqt.deleteInstances(self, MayaQDockWidget)
        Guide.upgrade_root(pm.selected()[0])
        super(componentSettings, self).__init__(parent=parent)
        self.settingsTab = settingsTab()
        self.setup_componentSettingWindow()
        self.create_componentControls()
        self.populate_componentControls()
        self.create_componentLayout()
        self.create_componentConnections()

    def setup_componentSettingWindow(self):
        self.mayaMainWindow = pyqt.maya_main_window()
        self.setObjectName(self.toolName)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(TYPE)
        self.resize(360, 280)

    def create_componentControls(self):
        return

    def populate_componentControls(self):
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")
        tab = self.settingsTab

        def count(attr):
            text = self.root.attr(attr).get() or ""
            found = [part for part in text.split() if part]
            return str(len(found)) if found else "—"

        tab.mesh_label.setText(self.root.attr("mesh").get() or "—")
        tab.spline_edit.setText(self.root.attr("baseSpline").get() or "")
        tab.base_edit.setText(self.root.attr("baseCtl").get() or "")
        tab.tip_edit.setText(self.root.attr("tipCtl").get() or "")
        tab.joint_spin.setValue(self.root.attr("splineJoint").get())
        tab.under_spin.setValue(self.root.attr("underTurn").get())
        tab.over_spin.setValue(self.root.attr("overTurn").get())
        tab.over_label.setText(count("overVerts") + " vertices")
        tab.under_label.setText(count("underVerts") + " vertices")

    def create_componentLayout(self):
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)
        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        tab = self.settingsTab
        for edit, attr in (
            (tab.spline_edit, "baseSpline"),
            (tab.base_edit, "baseCtl"),
            (tab.tip_edit, "tipCtl"),
        ):
            edit.editingFinished.connect(partial(self._keep_name, edit, attr))
        tab.joint_spin.valueChanged.connect(
            partial(self.updateSpinBox, tab.joint_spin, "splineJoint")
        )
        tab.under_spin.valueChanged.connect(
            partial(self.updateSpinBox, tab.under_spin, "underTurn")
        )
        tab.over_spin.valueChanged.connect(
            partial(self.updateSpinBox, tab.over_spin, "overTurn")
        )

    def _keep_name(self, edit, attr):
        # updateLineEdit strips "_". Maya node names need them.
        self.root.attr(attr).set(guide_name(edit.text()))

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
