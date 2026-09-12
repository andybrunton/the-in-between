"""Guide for the In-Between Wave Billow component."""

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
TYPE = "tween_wave_billow_01"
NAME = "waveBillow"
DESCRIPTION = (
    "Wave Billow. A chain of joints on a bezier spine between two points, "
    "displaced by a stack of harmonic waves. Winding the phase sends the wave "
    "travelling down the spine; turning the controls bends the spine under "
    "it.\n\n"
    "Place the root at the anchor, the tip at the loose end, and aim the "
    "blade flag along the axis the wave should swing on."
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
        # The wave itself has no build-time settings: amplitude starts at zero
        # so the rig binds on the guide pose, and everything that shapes the
        # wave is an anim attr the animator tunes per shot.
        self.pDiv = self.addParam("div", "long", 10, 2, None)
        # 0 = free start, 1 = free end, 2 = pinned
        self.pPinMode = self.addParam("pinMode", "long", 1, 0, 2)
        self.pHandleRatio = self.addParam(
            "handleRatio", "double", 1.0 / 3.5, 0.0, 1.0)

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
        self.resize(350, 400)

    def create_componentControls(self):
        return

    def populate_componentControls(self):
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")

        tab = self.settingsTab
        tab.div_spinBox.setValue(self.root.attr("div").get())
        tab.pinMode_comboBox.setCurrentIndex(self.root.attr("pinMode").get())
        tab.handle_doubleSpinBox.setValue(self.root.attr("handleRatio").get())

        for item in self.root.attr("ikrefarray").get().split(","):
            tab.refArray_listWidget.addItem(item)

    def create_componentLayout(self):
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)

        self.setLayout(self.settings_layout)

    def create_componentConnections(self):
        tab = self.settingsTab

        tab.pinMode_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox, tab.pinMode_comboBox, "pinMode"))

        for widget, attr in (
            (tab.div_spinBox, "div"),
            (tab.handle_doubleSpinBox, "handleRatio"),
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

    def eventFilter(self, sender, event):
        if event.type() == QtCore.QEvent.ChildRemoved:
            if sender == self.settingsTab.refArray_listWidget:
                self.updateListAttr(sender, "ikrefarray")
            return True
        return QtWidgets.QDialog.eventFilter(self, sender, event)

    def dockCloseEventTriggered(self):
        pyqt.deleteInstances(self, MayaQDockWidget)
