"""Guide for the In-Between Bounded Bow component."""

from functools import partial

import mgear.pymaya as pm

from mgear.shifter.component import guide
from mgear.core import attribute, transform, pyqt
from mgear.vendor.Qt import QtWidgets, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya.app.general.mayaMixin import MayaQDockWidget

from . import settingsUI as sui

# guide info
AUTHOR = "In-Between"
URL = "https://github.com/andre/the-in-between"
EMAIL = ""
VERSION = [0, 1, 0]
TYPE = "tween_bounded_bow_01"
NAME = "boundedBow"
DESCRIPTION = (
    "Bounded Bow. A symmetric bow of joints between two points. The bulge "
    "grows as the span compresses (distance mode) or as the tip bends away "
    "from the chord, whether it swings off it or just turns on the spot "
    "(angle mode).\n\n"
    "Place the root at the start, the tip at the end, and aim the blade flag "
    "at the direction the bulge should push."
)


##########################################################
# CLASS
##########################################################


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
        self.save_transform = ["root", "tip"]
        self.save_blade = ["blade"]

    def addObjects(self):
        self.root = self.addRoot()
        vTemp = transform.getOffsetPosition(self.root, [4, 0, 0])
        self.tip = self.addLoc("tip", self.root, vTemp)
        self.blade = self.addBlade("blade", self.root, self.tip)

        self.dispcrv = self.addDispCurve("crv", [self.root, self.tip])

    def addParameters(self):
        # 0 = distance, 1 = angle
        self.pDriveMode = self.addParam("driveMode", "long", 0, 0, 1)
        # 0 = smooth, 1 = linear, 2 = ease in, 3 = ease out
        self.pEasing = self.addParam("easing", "long", 0, 0, 3)
        self.pDiv = self.addParam("div", "long", 5, 2, None)

        # Ratios of the guide length, so the defaults survive a rescaled guide.
        self.pMinLengthRatio = self.addParam(
            "minLengthRatio", "double", 0.36, 0.01, 1.0)
        self.pMaxBendAngle = self.addParam(
            "maxBendAngle", "double", 90.0, 1.0, 180.0)
        self.pBulgeRatio = self.addParam("bulgeRatio", "double", 0.43, 0.0, 10.0)
        self.pTangentWeight = self.addParam(
            "tangentWeight", "double", 0.55, 0.0, 1.0)

        self.pRefArray = self.addParam("ikrefarray", "string", "")
        self.pIkrefJointDriver = self.addParam("ikrefJointDriver", "bool", False)
        self.pIkrefJointIndex = self.addParam("ikrefJointIndex", "long", 0, 0, None)
        # mGear guide name of the control or locator to read (e.g. arm_L0_elbow).
        self.pAngleRef = self.addParam("angleRef", "string", "")
        # 0 = rotateX, 1 = rotateY, 2 = rotateZ on the angleRef driver.
        self.pAngleAxis = self.addParam("angleAxis", "long", 2, 0, 2)
        self.pAngleReverse = self.addParam("angleReverse", "bool", False)
        # Read a joint index from the angleRef component instead of a ctl/loc.
        self.pAngleJointDriver = self.addParam("angleJointDriver", "bool", False)
        self.pAngleJointIndex = self.addParam("angleJointIndex", "long", 0, 0, None)
        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam(
            "parentJointIndex", "long", -1, None, None)

    # ponytail: attrs added after guides were drawn; upgrade_root back-fills them.
    _UPGRADE_PARAMS = (
        ("angleRef", "string", "", None, None),
        ("angleAxis", "long", 2, 0, 2),
        ("angleReverse", "bool", False, None, None),
        ("angleJointDriver", "bool", False, None, None),
        ("angleJointIndex", "long", 0, 0, None),
        ("ikrefJointDriver", "bool", False, None, None),
        ("ikrefJointIndex", "long", 0, 0, None),
    )

    @classmethod
    def upgrade_root(cls, root):
        """Add any component attrs missing from guides drawn on older versions."""
        for scriptName, valueType, value, minimum, maximum in cls._UPGRADE_PARAMS:
            if root.hasAttr(scriptName):
                continue
            attribute.ParamDef2(
                scriptName,
                valueType,
                value,
                None,
                None,
                minimum,
                maximum,
            ).create(root)

    def setFromHierarchy(self, root):
        """Back-fill new params before mGear reads guide settings (build path)."""
        self.upgrade_root(root)
        super(Guide, self).setFromHierarchy(root)


##########################################################
# Setting Page
##########################################################


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
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")

        tab = self.settingsTab
        tab.driveMode_comboBox.setCurrentIndex(self.root.attr("driveMode").get())
        tab.easing_comboBox.setCurrentIndex(self.root.attr("easing").get())
        tab.div_spinBox.setValue(self.root.attr("div").get())
        tab.minLength_doubleSpinBox.setValue(
            self.root.attr("minLengthRatio").get())
        tab.maxBendAngle_doubleSpinBox.setValue(
            self.root.attr("maxBendAngle").get())
        tab.bulge_doubleSpinBox.setValue(self.root.attr("bulgeRatio").get())
        tab.tangent_doubleSpinBox.setValue(
            self.root.attr("tangentWeight").get())
        tab.angleRef_lineEdit.setText(self.root.attr("angleRef").get())
        tab.angleAxis_comboBox.setCurrentIndex(self.root.attr("angleAxis").get())
        tab.angleReverse_checkBox.setChecked(
            self.root.attr("angleReverse").get())
        tab.angleJointDriver_checkBox.setChecked(
            self.root.attr("angleJointDriver").get())
        tab.angleJointIndex_spinBox.setValue(
            self.root.attr("angleJointIndex").get())
        self.update_drive_mode_enabled()
        self.update_angle_driver_mode()

        tab.ikrefJointDriver_checkBox.setChecked(
            self.root.attr("ikrefJointDriver").get())
        tab.ikrefJointIndex_spinBox.setValue(
            self.root.attr("ikrefJointIndex").get())
        self.update_ikref_mode()

        for item in self.root.attr("ikrefarray").get().split(","):
            if item:
                tab.refArray_listWidget.addItem(item)

    def create_componentLayout(self):
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)

        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        tab = self.settingsTab

        tab.driveMode_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox, tab.driveMode_comboBox, "driveMode"))
        tab.driveMode_comboBox.currentIndexChanged.connect(
            self.update_drive_mode_enabled)
        tab.easing_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox, tab.easing_comboBox, "easing"))

        for widget, attr in (
            (tab.div_spinBox, "div"),
            (tab.minLength_doubleSpinBox, "minLengthRatio"),
            (tab.maxBendAngle_doubleSpinBox, "maxBendAngle"),
            (tab.bulge_doubleSpinBox, "bulgeRatio"),
            (tab.tangent_doubleSpinBox, "tangentWeight"),
        ):
            widget.valueChanged.connect(
                partial(self.updateSpinBox, widget, attr))

        tab.refArrayAdd_pushButton.clicked.connect(self.add_ikref_item)
        tab.refArrayRemove_pushButton.clicked.connect(
            partial(self.removeSelectedFromListWidget,
                    tab.refArray_listWidget,
                    "ikrefarray"))
        tab.refArray_listWidget.installEventFilter(self)

        tab.angleRef_lineEdit.editingFinished.connect(
            partial(self.updateLineEdit, tab.angleRef_lineEdit, "angleRef"))
        tab.angleRef_pick_pushButton.clicked.connect(self.pick_angle_ref)
        tab.angleAxis_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox, tab.angleAxis_comboBox, "angleAxis"))
        tab.angleReverse_checkBox.stateChanged.connect(
            partial(self.updateCheck, tab.angleReverse_checkBox, "angleReverse"))
        tab.angleJointDriver_checkBox.stateChanged.connect(
            partial(
                self.updateCheck,
                tab.angleJointDriver_checkBox,
                "angleJointDriver",
            ))
        tab.angleJointDriver_checkBox.stateChanged.connect(
            self.update_angle_driver_mode)
        tab.angleJointIndex_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, tab.angleJointIndex_spinBox, "angleJointIndex"))
        tab.ikrefJointDriver_checkBox.stateChanged.connect(
            partial(
                self.updateCheck,
                tab.ikrefJointDriver_checkBox,
                "ikrefJointDriver",
            ))
        tab.ikrefJointDriver_checkBox.stateChanged.connect(self.update_ikref_mode)
        tab.ikrefJointIndex_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, tab.ikrefJointIndex_spinBox, "ikrefJointIndex"))

    def add_ikref_item(self):
        """Add a guide object to the tip reference list."""
        if self.settingsTab.ikrefJointDriver_checkBox.isChecked():
            sel = pm.selected()
            if not sel:
                pm.displayWarning("Select a guide component root.")
                return
            item = sel[0]
            if not item.hasAttr("isGearGuide") or not item.hasAttr("comp_type"):
                pm.displayWarning(
                    "Joint tip reference needs a component root "
                    "(e.g. neck_L0_root), not a locator."
                )
                return

        self.addItem2listWidget(
            self.settingsTab.refArray_listWidget, "ikrefarray")

    def update_ikref_mode(self, *args):
        """Joint mode lists component roots plus an index, not locators."""
        joint_ref = self.settingsTab.ikrefJointDriver_checkBox.isChecked()
        self.settingsTab.ikrefJointIndex_spinBox.setEnabled(joint_ref)
        tip = (
            "Add guide component roots (e.g. neck_L0_root), then set the "
            "joint index for each one."
            if joint_ref
            else "Add the selected guide component roots or locators as "
            "space references for the tip control"
        )
        self.settingsTab.refArrayAdd_pushButton.setToolTip(tip)

    def pick_angle_ref(self):
        """Store the selected guide object as the angle driver."""
        sel = pm.selected()
        if not sel:
            pm.displayWarning("Select a guide component root or locator.")
            return

        item = sel[0]
        if not item.hasAttr("isGearGuide"):
            pm.displayWarning(
                "{} is not a guide object; pick a component root or locator.".format(
                    item.name()
                )
            )
            return

        joint_driver = self.settingsTab.angleJointDriver_checkBox.isChecked()
        if joint_driver and not item.hasAttr("comp_type"):
            pm.displayWarning(
                "Joint driver needs a component root (e.g. neck_L0_root), "
                "not a locator."
            )
            return

        self.settingsTab.angleRef_lineEdit.setText(item.name())
        self.root.attr("angleRef").set(item.name())

    def update_angle_driver_mode(self, *args):
        """Joint mode picks a component root plus index, not a locator."""
        joint_driver = self.settingsTab.angleJointDriver_checkBox.isChecked()
        self.settingsTab.angleJointIndex_spinBox.setEnabled(joint_driver)
        tip = (
            "mGear guide name of the component whose joint drives the bow "
            "(e.g. neck_L0_root). Use << on the component root, then set "
            "the joint index."
            if joint_driver
            else
            "mGear guide name of the control or locator whose rotation "
            "drives the bow (e.g. arm_L0_elbow). Leave empty to infer bend "
            "from the tip control pose."
        )
        self.settingsTab.angleRef_lineEdit.setToolTip(tip)
        self.settingsTab.angleRef_pick_pushButton.setToolTip(
            "Use the selected guide component root"
            if joint_driver
            else "Use the selected guide component root or locator"
        )

    def update_drive_mode_enabled(self, *args):
        """Grey out the threshold that the current drive mode ignores."""
        is_angle = self.settingsTab.driveMode_comboBox.currentIndex() == 1
        tab = self.settingsTab
        tab.minLength_doubleSpinBox.setEnabled(not is_angle)
        tab.maxBendAngle_doubleSpinBox.setEnabled(is_angle)
        tab.angleDriver_group.setEnabled(is_angle)

    def eventFilter(self, sender, event):
        if event.type() == QtCore.QEvent.ChildRemoved:
            if sender == self.settingsTab.refArray_listWidget:
                self.updateListAttr(sender, "ikrefarray")
            return True
        return QtWidgets.QDialog.eventFilter(self, sender, event)

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
