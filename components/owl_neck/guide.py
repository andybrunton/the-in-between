"""Guide for the owl neck component."""

from functools import partial

import mgear.pymaya as pm

from mgear.shifter.component import guide
from mgear.core import attribute, pyqt, transform
from mgear.vendor.Qt import QtWidgets, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya.app.general.mayaMixin import MayaQDockWidget

from . import settingsUI as sui

AUTHOR = "In-Between"
URL = "https://github.com/andre/the-in-between"
EMAIL = ""
VERSION = [0, 1, 0]
TYPE = "owl_neck"
NAME = "neck"
DESCRIPTION = (
    "Owl neck. IK spline with a variable number of joints and no hip joint. "
    "Place the root at the chest and the effector at the top of the neck. "
    "Point the blade the way the neck should bend.\n\n"
    "Divisions is the joint count from base to tip. Twist leaves are added "
    "on every joint except the tip. The tip is where the head joint is "
    "parented.\n\n"
    "Select the head guide root and add it with << in Tip Reference. "
    "Do not parent that guide under this neck. On build, the tip IK follows "
    "that control, the IK controls hide, and the tangent controls stay."
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
        """Initialize the position for the guide"""
        self.save_transform = ["root", "eff"]
        self.save_blade = ["blade"]

    def addObjects(self):
        """Add the Guide Root, blade and locators"""
        self.root = self.addRoot()
        vTemp = transform.getOffsetPosition(self.root, [0, 4, 0])
        self.eff = self.addLoc("eff", self.root, vTemp)
        self.blade = self.addBlade("blade", self.root, self.eff)
        self.dispcrv = self.addDispCurve("crv", [self.root, self.eff])

    def addParameters(self):
        """Add the configurations settings"""
        self.pRefArray = self.addParam("ikrefarray", "string", "")
        # 0 = rotateX, 1 = rotateY, 2 = rotateZ on the tip reference.
        self.pTwistAxis = self.addParam("twistAxis", "long", 1, 0, 2)

        self.pPosition = self.addParam("position", "double", 0, 0, 1)
        self.pMaxStretch = self.addParam("maxstretch", "double", 3, 1)
        self.pMaxSquash = self.addParam("maxsquash", "double", 0.1, 0, 1)
        self.pSoftness = self.addParam("softness", "double", 0, 0, 1)
        self.pLockOri = self.addParam("lock_ori", "double", 1, 0, 1)

        self.pDivision = self.addParam("division", "long", 4, 3)

        self.pSt_profile = self.addFCurveParam(
            "st_profile", [[0, 0], [0.5, -1], [1, 0]])
        self.pSq_profile = self.addFCurveParam(
            "sq_profile", [[0, 0], [0.5, 1], [1, 0]])

        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam(
            "parentJointIndex", "long", -1, None, None)

    def get_divisions(self):
        """Returns correct segments divisions"""
        self.divisions = self.root.division.get()
        return self.divisions

    # Guides drawn before the tip reference list existed stored a head name.
    _UPGRADE_PARAMS = (
        ("ikrefarray", "string", "", None, None),
        ("twistAxis", "long", 1, 0, 2),
    )

    @classmethod
    def upgrade_root(cls, root):
        """Add ikrefarray to guides drawn on the previous version."""
        for scriptName, valueType, value, minimum, maximum in cls._UPGRADE_PARAMS:
            if root.hasAttr(scriptName):
                continue
            attribute.ParamDef2(
                scriptName, valueType, value, None, None, minimum, maximum
            ).create(root)

        if not root.hasAttr("head") or not root.hasAttr("ikrefarray"):
            return
        if (root.attr("ikrefarray").get() or "").strip():
            return
        head = (root.attr("head").get() or "").strip()
        if not head:
            return
        if not head.endswith("_root"):
            head = head + "_root"
        root.attr("ikrefarray").set(head)

    def setFromHierarchy(self, root):
        """Back-fill ikrefarray before mGear reads guide settings."""
        self.upgrade_root(root)
        super(Guide, self).setFromHierarchy(root)


class settingsTab(QtWidgets.QDialog, sui.Ui_Form):
    """The Component settings UI"""

    def __init__(self, parent=None):
        super(settingsTab, self).__init__(parent)
        self.setupUi(self)


class componentSettings(MayaQWidgetDockableMixin, guide.componentMainSettings):
    """Create the component setting window"""

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
        self.resize(350, 520)

    def create_componentControls(self):
        return

    def populate_componentControls(self):
        """Populate the controls values from the component attributes."""
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")
        tab = self.settingsTab

        for item in (self.root.attr("ikrefarray").get() or "").split(","):
            if item:
                tab.refArray_listWidget.addItem(item)
        tab.twistAxis_comboBox.setCurrentIndex(self.root.attr("twistAxis").get())
        tab.division_spinBox.setValue(self.root.attr("division").get())
        tab.position_spinBox.setValue(int(self.root.attr("position").get() * 100))
        tab.position_slider.setValue(int(self.root.attr("position").get() * 100))
        tab.lockOri_spinBox.setValue(int(self.root.attr("lock_ori").get() * 100))
        tab.lockOri_slider.setValue(int(self.root.attr("lock_ori").get() * 100))
        tab.softness_spinBox.setValue(int(self.root.attr("softness").get() * 100))
        tab.softness_slider.setValue(int(self.root.attr("softness").get() * 100))
        tab.maxStretch_spinBox.setValue(self.root.attr("maxstretch").get())
        tab.maxSquash_spinBox.setValue(self.root.attr("maxsquash").get())

    def create_componentLayout(self):
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)
        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        tab = self.settingsTab

        tab.refArrayAdd_pushButton.clicked.connect(
            partial(self.addItem2listWidget, tab.refArray_listWidget, "ikrefarray"))
        tab.refArrayRemove_pushButton.clicked.connect(
            partial(
                self.removeSelectedFromListWidget,
                tab.refArray_listWidget,
                "ikrefarray",
            ))
        tab.refArray_listWidget.installEventFilter(self)
        tab.twistAxis_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox, tab.twistAxis_comboBox, "twistAxis"))
        tab.division_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, tab.division_spinBox, "division"))

        for widget, attr in (
            (tab.position_slider, "position"),
            (tab.position_spinBox, "position"),
            (tab.lockOri_slider, "lock_ori"),
            (tab.lockOri_spinBox, "lock_ori"),
            (tab.softness_slider, "softness"),
            (tab.softness_spinBox, "softness"),
        ):
            widget.valueChanged.connect(partial(self.updateSlider, widget, attr))

        tab.maxStretch_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, tab.maxStretch_spinBox, "maxstretch"))
        tab.maxSquash_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, tab.maxSquash_spinBox, "maxsquash"))
        tab.squashStretchProfile_pushButton.clicked.connect(self.setProfile)

    def eventFilter(self, sender, event):
        if event.type() == QtCore.QEvent.ChildRemoved:
            if sender == self.settingsTab.refArray_listWidget:
                self.updateListAttr(sender, "ikrefarray")
            return True
        return QtWidgets.QDialog.eventFilter(self, sender, event)

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
