"""Guide for the In-Between Bounded Bow component."""

from functools import partial

from mgear.shifter.component import guide
from mgear.core import transform, pyqt
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
        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam(
            "parentJointIndex", "long", -1, None, None)


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
        self.update_drive_mode_enabled()

        for item in self.root.attr("ikrefarray").get().split(","):
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

        tab.refArrayAdd_pushButton.clicked.connect(
            partial(self.addItem2listWidget,
                    tab.refArray_listWidget,
                    "ikrefarray"))
        tab.refArrayRemove_pushButton.clicked.connect(
            partial(self.removeSelectedFromListWidget,
                    tab.refArray_listWidget,
                    "ikrefarray"))
        tab.refArray_listWidget.installEventFilter(self)

    def update_drive_mode_enabled(self, *args):
        """Grey out the threshold that the current drive mode ignores."""
        is_angle = self.settingsTab.driveMode_comboBox.currentIndex() == 1
        self.settingsTab.minLength_doubleSpinBox.setEnabled(not is_angle)
        self.settingsTab.maxBendAngle_doubleSpinBox.setEnabled(is_angle)

    def eventFilter(self, sender, event):
        if event.type() == QtCore.QEvent.ChildRemoved:
            if sender == self.settingsTab.refArray_listWidget:
                self.updateListAttr(sender, "ikrefarray")
            return True
        return QtWidgets.QDialog.eventFilter(self, sender, event)

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
