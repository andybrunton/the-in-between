"""PySide6 UI for the In-Between Maya companion tool."""

from __future__ import annotations

import json
import os

import maya.cmds as cmds
import maya.OpenMayaUI as omui
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from in_between.core.context import RigContext
from in_between.core.drive import DRIVE_ANGLE, DRIVE_DISTANCE
from in_between.core.dag_targets import list_selected_targets
from in_between.core.naming import sanitize_name
from in_between.registry import BEHAVIOUR_LABELS, behaviour_ids, build_rig

# Brand palette (matches index.html)
_BG = "#121316"
_PANEL = "#1a1b1f"
_RAISE = "#24252a"
_TEXT = "#eae9e4"
_DIM = "#918f89"
_BORDER = "#2e3036"
_ACCENT = "#57d1ff"
_OK = "#8fd457"
_ERR = "#ff5f5f"

RIG_NAME_BY_BEHAVIOUR: dict[str, str] = {
    "muscle_curve": "rig_mc",
    "volume_3d": "rig_vol",
    "angle_push": "rig_ap",
    "wave_billow": "rig_wb",
    "skin_wrinkle": "rig_sw",
    "bounded_bow": "rig_bb",
}

_PREFS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".in_between_prefs.json",
)

_STYLESHEET = f"""
QDialog {{
    background: {_BG};
    color: {_TEXT};
    font-size: 11px;
}}
QLabel#sectionTitle {{
    color: {_DIM};
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QLabel#hint {{
    color: {_DIM};
    font-size: 10px;
}}
QLabel#statusOk {{
    color: {_OK};
    font-size: 10px;
    padding: 4px 6px;
    background: rgba(143, 212, 87, 0.08);
    border-radius: 4px;
}}
QLabel#statusErr {{
    color: {_ERR};
    font-size: 10px;
    padding: 4px 6px;
    background: rgba(255, 95, 95, 0.08);
    border-radius: 4px;
}}
QFrame#section {{
    background: {_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
}}
QFrame#behaviourHero {{
    background: {_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
}}
QLabel#behaviourLabel {{
    color: {_DIM};
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QComboBox#behaviourCombo {{
    background: {_RAISE};
    border: 1px solid {_ACCENT};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 13px;
    font-weight: bold;
    color: {_TEXT};
    min-height: 20px;
}}
QComboBox#behaviourCombo::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox#behaviourCombo QAbstractItemView {{
    background: {_RAISE};
    border: 1px solid {_BORDER};
    selection-background-color: {_ACCENT};
    selection-color: {_BG};
}}
QLineEdit, QComboBox, QSpinBox {{
    background: {_RAISE};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    color: {_TEXT};
    min-height: 14px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {_RAISE};
    border: 1px solid {_BORDER};
    selection-background-color: {_ACCENT};
    selection-color: {_BG};
}}
QCheckBox {{
    spacing: 6px;
    color: {_TEXT};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {_BORDER};
    background: {_RAISE};
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
    border-color: {_ACCENT};
}}
QPushButton#pickBtn {{
    background: {_RAISE};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    color: {_DIM};
    padding: 2px 6px;
    min-width: 30px;
}}
QPushButton#pickBtn:hover {{
    color: {_TEXT};
    border-color: {_ACCENT};
}}
QPushButton#segBtn {{
    background: {_RAISE};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    color: {_DIM};
    padding: 4px 10px;
}}
QPushButton#segBtn:checked {{
    background: rgba(87, 209, 255, 0.15);
    border-color: {_ACCENT};
    color: {_TEXT};
}}
QPushButton#primaryBtn {{
    background: {_ACCENT};
    border: none;
    border-radius: 4px;
    color: {_BG};
    font-weight: 700;
    padding: 6px 18px;
}}
QPushButton#primaryBtn:hover {{
    background: #6dd8ff;
}}
QPushButton#primaryBtn:pressed {{
    background: #45b8e8;
}}
QPushButton#secondaryBtn {{
    background: transparent;
    border: 1px solid {_BORDER};
    border-radius: 4px;
    color: {_TEXT};
    padding: 5px 10px;
}}
QPushButton#secondaryBtn:hover {{
    border-color: {_ACCENT};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
"""


def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _display_name(dag_path: str) -> str:
    """Strip DAG path and namespace for display only."""
    leaf = dag_path.split("|")[-1].strip()
    if ":" in leaf:
        return leaf.rsplit(":", 1)[-1]
    return leaf


def _default_rig_name(behaviour_id: str) -> str:
    return RIG_NAME_BY_BEHAVIOUR.get(behaviour_id, "rig")


class TransformField(QtWidgets.QWidget):
    """Line edit + pick-from-selection. Shows short names, keeps full DAG path."""

    def __init__(self, label: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._full_path: str | None = None

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._label = QtWidgets.QLabel(label)
        self._label.setFixedWidth(72)
        self._label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )

        self._edit = QtWidgets.QLineEdit()
        if placeholder:
            self._edit.setPlaceholderText(placeholder)
        self._edit.textEdited.connect(self._on_text_edited)

        self._pick = QtWidgets.QPushButton("◀")
        self._pick.setObjectName("pickBtn")
        self._pick.setFixedWidth(30)
        self._pick.setToolTip("Use current selection")
        self._pick.clicked.connect(self._on_pick)

        layout.addWidget(self._label)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._pick)

    def _on_text_edited(self, _text: str) -> None:
        self._full_path = None

    def _on_pick(self):
        sel = list_selected_targets()
        if sel:
            self.setText(sel[0])

    def text(self) -> str:
        if self._full_path:
            return self._full_path
        return self._edit.text().strip()

    def setText(self, value: str) -> None:
        value = value.strip()
        self._full_path = value or None
        self._edit.setText(_display_name(value) if value else "")


class _Section(QtWidgets.QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(5)

        heading = QtWidgets.QLabel(title)
        heading.setObjectName("sectionTitle")
        outer.addWidget(heading)

        self.body = QtWidgets.QVBoxLayout()
        self.body.setSpacing(4)
        outer.addLayout(self.body)


class _BehaviourPicker(QtWidgets.QFrame):
    """Hero behaviour selector — larger type, single accent outline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("behaviourHero")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        label = QtWidgets.QLabel("Behaviour")
        label.setObjectName("behaviourLabel")
        layout.addWidget(label)

        self.combo = QtWidgets.QComboBox()
        self.combo.setObjectName("behaviourCombo")
        for bid in behaviour_ids():
            self.combo.addItem(BEHAVIOUR_LABELS[bid], bid)
        layout.addWidget(self.combo)


class InBetweenWindow(QtWidgets.QDialog):
    WINDOW_TITLE = "The In-Between"
    WINDOW_OBJECT_NAME = "inBetweenMainWindow"

    def __init__(self, parent=None):
        super().__init__(parent or _maya_main_window())
        self.setObjectName(self.WINDOW_OBJECT_NAME)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumWidth(400)
        self.setStyleSheet(_STYLESHEET)
        self._bulge_twist: str | None = None
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_body = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 0, 2, 0)
        scroll_layout.setSpacing(7)

        self._behaviour_picker = _BehaviourPicker()
        self.behaviour_combo = self._behaviour_picker.combo
        scroll_layout.addWidget(self._behaviour_picker)

        setup = _Section("Setup")
        self.rig_label = QtWidgets.QLineEdit()
        self.rig_label.setPlaceholderText("rig namespace root")

        drive_row = QtWidgets.QHBoxLayout()
        drive_row.setSpacing(4)
        self._drive_group = QtWidgets.QButtonGroup(self)
        self._drive_distance = QtWidgets.QPushButton("Distance")
        self._drive_distance.setObjectName("segBtn")
        self._drive_distance.setCheckable(True)
        self._drive_distance.setChecked(True)
        self._drive_angle = QtWidgets.QPushButton("Angle")
        self._drive_angle.setObjectName("segBtn")
        self._drive_angle.setCheckable(True)
        self._drive_group.addButton(self._drive_distance)
        self._drive_group.addButton(self._drive_angle)
        drive_row.addWidget(self._drive_distance)
        drive_row.addWidget(self._drive_angle)
        drive_row.addStretch()

        setup.body.addWidget(self._form_row("Rig name", self.rig_label))
        setup.body.addWidget(self._form_row("Drive", drive_row))
        scroll_layout.addWidget(setup)

        transforms = _Section("Transforms")
        self.start_field = TransformField("Start", "start transform")
        self.end_field = TransformField("End", "end transform")
        self.reference_field = TransformField("Reference", "optional bend target")
        self.reference_hint = QtWidgets.QLabel(
            "Bend at End: Start→End vs End→Reference. "
            "Empty = Start +X vs chord."
        )
        self.reference_hint.setObjectName("hint")
        self.reference_hint.setWordWrap(True)
        transforms.body.addWidget(self.start_field)
        transforms.body.addWidget(self.end_field)
        transforms.body.addWidget(self.reference_field)
        transforms.body.addWidget(self.reference_hint)
        scroll_layout.addWidget(transforms)

        self._bow_section = _Section("Bulge direction")
        self.place_bulge_btn = QtWidgets.QPushButton("Place bulge arrow")
        self.place_bulge_btn.setObjectName("secondaryBtn")
        self.bulge_hint = QtWidgets.QLabel(
            "Green arrow = main bulge direction (+Y along the chord). "
            "Twist it around the chord (rotate X only), then Build."
        )
        self.bulge_hint.setObjectName("hint")
        self.bulge_hint.setWordWrap(True)
        bulge_btn_row = QtWidgets.QHBoxLayout()
        bulge_btn_row.addWidget(self.place_bulge_btn)
        bulge_btn_row.addStretch()
        self._bow_section.body.addLayout(bulge_btn_row)
        self._bow_section.body.addWidget(self.bulge_hint)
        scroll_layout.addWidget(self._bow_section)
        self._bow_section.setVisible(False)

        parents = _Section("Parents")
        parent_hint = QtWidgets.QLabel("Empty → auto-create rig_group_*")
        parent_hint.setObjectName("hint")
        parents.body.addWidget(parent_hint)
        self.local_parent = TransformField("Local", "local parent")
        self.world_parent = TransformField("World", "world parent")
        self.joint_parent = TransformField("Joints", "joint parent")
        parents.body.addWidget(self.local_parent)
        parents.body.addWidget(self.world_parent)
        parents.body.addWidget(self.joint_parent)
        scroll_layout.addWidget(parents)

        joints = _Section("Joint chain")
        self.num_joints = QtWidgets.QSpinBox()
        self.num_joints.setRange(2, 64)
        self.num_joints.setValue(8)
        self.build_joints = QtWidgets.QCheckBox("Build joint chain on curve")
        self.build_joints.setChecked(True)
        joints.body.addWidget(self._form_row("Count", self.num_joints))
        joints.body.addWidget(self.build_joints)
        scroll_layout.addWidget(joints)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_body)
        root.addWidget(scroll, 1)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.hide()

        btn_row = QtWidgets.QHBoxLayout()
        self.build_btn = QtWidgets.QPushButton("Build rig")
        self.build_btn.setObjectName("primaryBtn")
        btn_row.addStretch()
        btn_row.addWidget(self.build_btn)
        root.addWidget(self.status)
        root.addLayout(btn_row)

        self.build_btn.clicked.connect(self._on_build)
        self.place_bulge_btn.clicked.connect(self._on_place_bulge_arrow)
        self.behaviour_combo.currentIndexChanged.connect(self._on_behaviour_changed)
        self._drive_group.buttonClicked.connect(self._on_drive_changed)
        self._load_prefs()

    def closeEvent(self, event) -> None:
        self._save_prefs()
        super().closeEvent(event)

    def _prefs_data(self) -> dict:
        return {
            "behaviour_id": self.behaviour_combo.currentData(),
            "rig_label": self.rig_label.text().strip(),
            "drive_mode": self._drive_mode(),
            "start": self.start_field.text(),
            "end": self.end_field.text(),
            "reference": self.reference_field.text(),
            "local_parent": self.local_parent.text(),
            "world_parent": self.world_parent.text(),
            "joint_parent": self.joint_parent.text(),
            "num_joints": self.num_joints.value(),
            "build_joints": self.build_joints.isChecked(),
        }

    def _save_prefs(self) -> None:
        try:
            with open(_PREFS_PATH, "w", encoding="utf-8") as handle:
                json.dump(self._prefs_data(), handle, indent=2)
        except OSError:
            pass

    def _load_prefs(self) -> None:
        if not os.path.isfile(_PREFS_PATH):
            self._on_behaviour_changed()
            self._on_drive_changed()
            return
        try:
            with open(_PREFS_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self._on_behaviour_changed()
            self._on_drive_changed()
            return

        behaviour_id = data.get("behaviour_id")
        if behaviour_id:
            for i in range(self.behaviour_combo.count()):
                if self.behaviour_combo.itemData(i) == behaviour_id:
                    self.behaviour_combo.setCurrentIndex(i)
                    break

        if data.get("rig_label"):
            self.rig_label.setText(data["rig_label"])
        else:
            self._on_behaviour_changed()

        if data.get("drive_mode") == DRIVE_ANGLE:
            self._drive_angle.setChecked(True)
        else:
            self._drive_distance.setChecked(True)

        self.start_field.setText(data.get("start", ""))
        self.end_field.setText(data.get("end", ""))
        self.reference_field.setText(data.get("reference", ""))
        self.local_parent.setText(data.get("local_parent", ""))
        self.world_parent.setText(data.get("world_parent", ""))
        self.joint_parent.setText(data.get("joint_parent", ""))

        if "num_joints" in data:
            self.num_joints.setValue(int(data["num_joints"]))
        if "build_joints" in data:
            self.build_joints.setChecked(bool(data["build_joints"]))

        self._on_drive_changed()
        self._update_behaviour_ui()

    def _is_bounded_bow(self) -> bool:
        return self.behaviour_combo.currentData() == "bounded_bow"

    def _update_behaviour_ui(self) -> None:
        self._bow_section.setVisible(self._is_bounded_bow())

    def _form_row(self, label: str, widget) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QtWidgets.QLabel(label)
        lbl.setFixedWidth(72)
        lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        if isinstance(widget, QtWidgets.QLayout):
            layout.addWidget(lbl)
            layout.addLayout(widget, 1)
        else:
            layout.addWidget(lbl)
            layout.addWidget(widget, 1)
        return row

    def _drive_mode(self) -> str:
        return DRIVE_ANGLE if self._drive_angle.isChecked() else DRIVE_DISTANCE

    def _is_angle_drive(self) -> bool:
        return self._drive_mode() == DRIVE_ANGLE

    def _on_behaviour_changed(self, _index: int = 0) -> None:
        behaviour_id = self.behaviour_combo.currentData()
        current = self.rig_label.text().strip()
        known_defaults = set(RIG_NAME_BY_BEHAVIOUR.values()) | {"", "rig"}
        if current in known_defaults:
            self.rig_label.setText(_default_rig_name(behaviour_id))
        self._update_behaviour_ui()

    def _resolve_bulge_twist(self) -> str | None:
        if self._bulge_twist and cmds.objExists(self._bulge_twist):
            return self._bulge_twist
        base = sanitize_name(self.rig_label.text().strip() or "rig")
        for pattern in (f"{base}_BulgeTwist", f"{base}_Blade"):
            matches = cmds.ls(pattern, transforms=True) or []
            if matches:
                return matches[0]
        return None

    def _on_place_bulge_arrow(self) -> None:
        if not self._is_bounded_bow():
            return
        try:
            from in_between.builders.bounded_bow import place_bulge_arrow

            twist = place_bulge_arrow(
                self.start_field.text(),
                self.end_field.text(),
                self.rig_label.text().strip() or "rig",
            )
            self._bulge_twist = twist
            self._set_status(
                f"Twist {twist} around the chord (+Y = bulge), then Build rig.",
                ok=True,
            )
        except Exception as exc:
            self._set_status(f"Error: {exc}", ok=False)

    def _on_drive_changed(self, _button=None):
        angle = self._is_angle_drive()
        self.reference_field.setVisible(angle)
        self.reference_hint.setVisible(angle)

    def _set_status(self, text: str, ok: bool) -> None:
        if not text:
            self.status.hide()
            return
        self.status.setText(text)
        self.status.setObjectName("statusOk" if ok else "statusErr")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.show()

    def _make_context(self) -> RigContext:
        reference = self.reference_field.text() if self._is_angle_drive() else None
        bulge_twist = self._resolve_bulge_twist() if self._is_bounded_bow() else None
        return RigContext(
            behaviour_id=self.behaviour_combo.currentData(),
            drive_mode=self._drive_mode(),
            start=self.start_field.text(),
            end=self.end_field.text(),
            rig_label=self.rig_label.text().strip() or "rig",
            local_parent=self.local_parent.text() or None,
            world_parent=self.world_parent.text() or None,
            joint_parent=self.joint_parent.text() or None,
            num_joints=self.num_joints.value(),
            build_joints=self.build_joints.isChecked(),
            reference=reference or None,
            bulge_twist=bulge_twist,
        )

    def _on_build(self):
        try:
            ctx = self._make_context()
            result = build_rig(ctx)
            self._bulge_twist = None
            self._set_status(f"Built '{ctx.base_name}' → {result.root}", ok=True)
        except Exception as exc:
            self._set_status(f"Error: {exc}", ok=False)
        finally:
            self._save_prefs()


_window: InBetweenWindow | None = None


def _close_existing_windows() -> None:
    """Close any In-Between windows (survives module reload)."""
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    for widget in app.topLevelWidgets():
        if widget.objectName() == InBetweenWindow.WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()


def _clear_window_ref(*_args) -> None:
    global _window
    _window = None


def show():
    global _window
    _close_existing_windows()
    _window = InBetweenWindow()
    _window.destroyed.connect(_clear_window_ref)
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window
