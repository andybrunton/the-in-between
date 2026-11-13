"""Guide for one sliding seam between two edge rings."""

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
TYPE = "ring_slide"
NAME = "ring"
DESCRIPTION = (
    "One seam. Two edge rings, an over and an under, and a center at the "
    "over ring. An optional parent component, which the center control lines "
    "up with exactly.\n\n"
    "Draw it from the sheet_rig window: select each edge ring and capture "
    "it. The guide marks the center and both loops. Build with Shifter. "
    "The center control translates and rotates. Rotate X and rotate Z move "
    "both rings together. Rotate Y slides the over joints along the under "
    "loop, in 3D, so the seam does not intersect. One component is one seam. "
    "A neck needs two of these, and an ordinary twist chain between them."
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
        tab.parent_label.setText(self.root.attr("parentComp").get() or "—")
        tab.over_label.setText(count("overVerts") + " vertices")
        tab.under_label.setText(count("underVerts") + " vertices")

    def create_componentLayout(self):
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)
        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        return

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
