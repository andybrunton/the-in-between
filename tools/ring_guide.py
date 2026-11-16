"""Pick the base spline, the base control, and the tip control, then capture the edge rings.

The base spline is the chain the seams sit on: a spine, a neck, a sleeve.
Create draws a spine_S_shape_01 with the neck defaults, under the base
control when one is filled in. Base and tip are control_01 guides. Create
puts the base on the spline root and the tip on its end. The tip is parented
to the base control's parent, so a base under root gets a tip under root.
Do not parent the tip under the spline. Then capture an over edge ring and
an under edge ring. Build it with Shifter. The spline's own controls are
hidden. The base and the tip drive the chain, and each seam twists between
them. The center takes its orientation from the spline joints.

One guide is one seam. Run it again for the other end of the neck. Select a
ring guide and Create Guide to replace that one.

Run in Maya::

    import sys
    sys.path.append("C:/Users/andre/Documents/GitHub/the-in-between/tools")
    import ring_guide
    ring_guide.show()
"""

import os

import maya.cmds as cmds

from mgear.vendor.Qt import QtCore, QtWidgets, QtCompat

_dialog = None

C_SKY = "#8ecae6"
C_TEAL = "#219ebc"
C_NAVY = "#023047"
C_BG = "#000000"

_STYLE = """
QDialog {{ background-color: {bg}; color: {sky}; font-size: 11px; }}
QLabel {{ color: {sky}; background: transparent; }}
QLineEdit {{
    background-color: {bg}; color: {sky};
    border: 1px solid {teal}; border-radius: 3px; padding: 2px 4px; min-height: 20px;
}}
QPushButton {{
    background-color: {teal}; color: {bg}; border: none; border-radius: 3px;
    min-height: 24px; padding: 2px 8px;
}}
QPushButton:hover {{ background-color: {sky}; }}
""".format(bg=C_BG, sky=C_SKY, teal=C_TEAL, navy=C_NAVY)


def _components_path():
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "components"))


def _ensure_path():
    import sys

    comp = _components_path()
    if comp not in sys.path:
        sys.path.insert(0, comp)
    key = "MGEAR_SHIFTER_COMPONENT_PATH"
    parts = [part for part in os.environ.get(key, "").split(os.pathsep) if part]
    if comp not in parts:
        os.environ[key] = os.pathsep.join(parts + [comp])
    return comp


def _short(node):
    return node.split("|")[-1]


def _guide_root(node):
    current = node.split(".")[0]
    while current:
        if cmds.attributeQuery("comp_type", node=current, exists=True):
            return current
        parent = cmds.listRelatives(current, parent=True, fullPath=True)
        if not parent:
            return None
        current = parent[0]
    return None


def _edge_verts(edge):
    found = cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True, long=True) or []
    return found if len(found) == 2 else None


def _point(vert):
    return tuple(cmds.xform(vert, query=True, worldSpace=True, translation=True))


def _onward(edge, vert, border):
    """The edge leaving this vertex that continues the contour."""
    ends = _edge_verts(edge)
    other = ends[0] if ends[1] == vert else ends[1]
    here = _point(vert)
    there = _point(other)
    incoming = (here[0] - there[0], here[1] - there[1], here[2] - there[2])
    scale = sum(value * value for value in incoming) ** 0.5
    if scale < 1e-8:
        return None
    incoming = tuple(value / scale for value in incoming)
    best = None
    best_dot = None
    connected = cmds.ls(cmds.polyListComponentConversion(vert, toEdge=True), flatten=True, long=True) or []
    for cand in connected:
        if cand == edge:
            continue
        faces = cmds.ls(cmds.polyListComponentConversion(cand, toFace=True), flatten=True) or []
        if border and len(faces) != 1:
            continue
        c_ends = _edge_verts(cand)
        if not c_ends or vert not in c_ends:
            continue
        far = c_ends[0] if c_ends[1] == vert else c_ends[1]
        far_point = _point(far)
        direction = (far_point[0] - here[0], far_point[1] - here[1], far_point[2] - here[2])
        span = sum(value * value for value in direction) ** 0.5
        if span < 1e-8:
            continue
        score = sum(a * (b / span) for a, b in zip(incoming, direction))
        if best is None or score > best_dot:
            best = cand
            best_dot = score
    return best


def _grow_loop(edge):
    """Closed contour through one edge. A border edge stays on the border."""
    edge = cmds.ls(edge, long=True)[0]
    ends = _edge_verts(edge)
    if not ends:
        return []
    border = len(cmds.ls(cmds.polyListComponentConversion(edge, toFace=True), flatten=True) or []) == 1
    current = edge
    at = ends[1]
    loop = [edge]
    for _step in range(10000):
        nxt = _onward(current, at, border)
        if not nxt or nxt == edge:
            break
        if nxt in loop:
            return []
        loop.append(nxt)
        c_ends = _edge_verts(nxt)
        at = c_ends[0] if c_ends[1] == at else c_ends[1]
        current = nxt
    if _onward(current, at, border) != edge:
        return []
    return loop


def _walk_verts(edges):
    """Vertex names in loop order, or None when the edges are not one closed loop."""
    adj = {}
    for edge in edges:
        verts = _edge_verts(edge)
        if not verts:
            return None
        a, b = verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if len(adj) < 3 or any(len(nbrs) != 2 for nbrs in adj.values()):
        return None
    start = _edge_verts(edges[0])[0]
    ordered = [start]
    prev = None
    current = start
    for _step in range(len(adj)):
        nbrs = adj[current]
        nxt = nbrs[0] if nbrs[1] == prev else nbrs[1]
        if nxt == start:
            return ordered
        if nxt in ordered:
            return None
        ordered.append(nxt)
        prev, current = current, nxt
    return None


def _ordered_verts(spec):
    """Vertex names in loop order. One edge grows the connected contour."""
    tokens = [part for part in (spec or "").split() if part]
    if not tokens or not all(cmds.objExists(part) for part in tokens):
        return None
    edges = cmds.ls(tokens, flatten=True, long=True) or []
    ordered = _walk_verts(edges)
    if ordered:
        return ordered
    if not edges:
        return None
    grown = _grow_loop(edges[0])
    if not grown:
        return None
    return _walk_verts(grown)


def _positions(verts):
    # One at a time. A batch query comes back in vertex-index order, so a
    # walked loop would be drawn in the order the vertices were built.
    return [tuple(cmds.xform(vert, query=True, worldSpace=True, translation=True)) for vert in verts]


def _loop_curve(name, points, parent, color):
    curve = cmds.curve(name=name, degree=1, point=[tuple(point) for point in points] + [tuple(points[0])])
    curve = cmds.parent(curve, parent, relative=True)[0]
    shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", 1)
    cmds.setAttr(shape + ".overrideColor", color)
    return curve


def _selected_ring():
    for node in cmds.ls(selection=True, long=True) or []:
        root = _guide_root(node)
        if root and cmds.getAttr(root + ".comp_type") == "ring_slide":
            return root
    return None


def _ring():
    """The ring module, re-read from disk.

    Maya keeps the first import for the whole session, so a guide drawn
    after the file changed was still calling the old module.
    """
    import importlib
    import sys

    _ensure_path()
    expected = os.path.normcase(os.path.normpath(
        os.path.join(_components_path(), "ring_slide", "ring.py")
    ))
    loaded = sys.modules.get("ring_slide.ring")
    loaded_file = os.path.normcase(os.path.normpath(getattr(loaded, "__file__", "") or ""))
    if os.path.splitext(loaded_file)[0] != os.path.splitext(expected)[0]:
        for name in list(sys.modules):
            if name == "ring_slide" or name.startswith("ring_slide."):
                sys.modules.pop(name, None)
        import ring_slide.ring as ring
        return ring
    module = importlib.reload(loaded)
    package = sys.modules.get("ring_slide")
    if package is not None:
        importlib.reload(package)
    return module


SPINE_TYPE = "spine_S_shape_01"

# The component slider shows Lock Orient as 0-100. 100 is stored as 1.
SPINE_DEFAULTS = (
    ("softness", 0.0),
    ("position", 0.0),
    ("lock_ori", 1.0),
    ("maxstretch", 5.0),
    ("maxsquash", 0.1),
    ("division", 5),
    ("autoBend", 0),
    ("IKWorldOri", 1),
    ("centralTangent", 0),
)


def _draw_component(comp_type, comp_name, values=(), translation=None, parent=None):
    """Draw a guide component. Returns its root, or None."""
    import mgear.pymaya as pm
    import mgear.shifter as shifter

    _ensure_path()
    shifter.clearComponentCache()
    guide_rig = shifter.guide.Rig()
    if not cmds.objExists("guide"):
        guide_rig.initialHierarchy()
    comp = guide_rig.getComponentGuide(comp_type)
    if not comp:
        cmds.warning("Could not find the {} component.".format(comp_type))
        return None

    undo = cmds.undoInfo(query=True, state=True)
    if undo:
        cmds.undoInfo(openChunk=True, chunkName="create {} guide".format(comp_name))
    try:
        comp.setParamDefValue("comp_name", comp_name)
        parent = parent or "guide"
        if not cmds.objExists(parent):
            cmds.warning("Parent '{}' is missing. Drawing under the guide.".format(parent))
            parent = "guide"
        comp.draw(pm.PyNode(parent))
        root = comp.root.longName()
        for name, value in values:
            cmds.setAttr(root + "." + name, value)
        if translation is not None:
            cmds.xform(root, worldSpace=True, translation=translation)
        cmds.select(root)
        print("Drew {}.".format(_short(root)))
        return root
    finally:
        if undo:
            cmds.undoInfo(closeChunk=True)


def create_spine(parent=None):
    """Draw a spine_S_shape_01 with the neck defaults.

    parent is a guide root, usually the base control, so the chain hangs off
    it. Returns the guide root, or None. An existing neck or sleeve can be
    picked instead of calling this.
    """
    return _draw_component(SPINE_TYPE, "spine", SPINE_DEFAULTS, parent=parent)


def create_control(comp_name, translation=None, parent=None):
    """Draw a control_01 named comp_name. Returns the guide root, or None."""
    return _draw_component("control_01", comp_name, translation=translation, parent=parent)


def sibling_parent(control_root):
    """Where a tip guide hangs: the base control's parent, not the spline.

    A tip parented under the spline cycles once the tip drives the spline.
    """
    if not control_root or not cmds.objExists(control_root):
        return None
    found = cmds.listRelatives(control_root, parent=True, fullPath=True) or []
    return found[0] if found else None


def component_ends(root):
    """World positions (root, tip) of a guide. The tip is its ``_eff`` locator.

    A chain with no eff uses a point 4 units above the root, which is where
    a new spine draws its tip.
    """
    root = (cmds.ls(root, long=True) or [root])[0]
    base = tuple(cmds.xform(root, query=True, worldSpace=True, translation=True))
    short = _short(root)
    if short.endswith("_root"):
        short = short[:-5]
    tip = None
    for node in cmds.ls(short + "_eff", long=True) or []:
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if parent and parent[0] == root:
            tip = tuple(cmds.xform(node, query=True, worldSpace=True, translation=True))
            break
    if tip is None:
        tip = (base[0], base[1] + 4.0, base[2])
    return base, tip


def spline_joint_index(spline, point):
    """Numbered spline joint nearest a point, or -1 when it cannot be told.

    The guide has no joints yet. They sit evenly from the spline's root to
    its end, so the point's place along that line gives the index.
    """
    if not spline or not cmds.objExists(spline) or not cmds.attributeQuery("division", node=spline, exists=True):
        return -1
    count = int(cmds.getAttr(spline + ".division"))
    start, end = component_ends(spline)
    span = [end[i] - start[i] for i in range(3)]
    size = sum(part * part for part in span)
    if count < 2 or size < 1e-12:
        return -1
    along = sum((point[i] - start[i]) * span[i] for i in range(3)) / size
    return int(round(min(1.0, max(0.0, along)) * (count - 1)))


def create_guide(over, under, parent_comp="", base_spline="", base_ctl="", tip_ctl=""):
    """Draw a ring_slide guide. Returns the guide root, or None.

    A selected ring_slide guide is replaced. Otherwise a new one is added,
    so the two ends of a neck can both exist. parent_comp is a guide
    component: the new guide hangs under it and the rig's center control
    lines up with it exactly.
    """
    import mgear.pymaya as pm
    import mgear.shifter as shifter

    ring = _ring()
    shifter.clearComponentCache()

    over_verts = _ordered_verts(over)
    if not over_verts:
        cmds.warning("Over is not one closed edge ring.")
        return None
    under_verts = _ordered_verts(under)
    if not under_verts:
        cmds.warning("Under is not one closed edge ring.")
        return None
    over_mesh = _short(over_verts[0].split(".")[0])
    under_mesh = _short(under_verts[0].split(".")[0])
    if over_mesh != under_mesh:
        cmds.warning("Both rings have to be on the same mesh.")
        return None

    over_points = _positions(over_verts)
    under_points = _positions(under_verts)
    frame = ring.guide_frame(over_points, under_points)
    if frame is None:
        cmds.warning("The over ring has no center.")
        return None
    origin, x, y, z = frame
    over_local = [ring.to_local(point, origin, x, y, z) for point in over_points]
    under_local = [ring.to_local(point, origin, x, y, z) for point in under_points]

    guide_rig = shifter.guide.Rig()
    if not cmds.objExists("guide"):
        guide_rig.initialHierarchy()
    replacing = _selected_ring()
    parent = "guide"
    if replacing:
        found = cmds.listRelatives(replacing, parent=True, fullPath=True)
        if found:
            parent = found[0]
    parent_comp = (parent_comp or "").strip()
    if parent_comp:
        found = cmds.ls(parent_comp, long=True) or []
        owner = _guide_root(found[0]) if found else None
        if not owner or cmds.getAttr(owner + ".comp_type") == "ring_slide":
            cmds.warning("Parent '{}' is not a guide component.".format(parent_comp))
            return None
        parent = owner
        parent_comp = _short(owner)

    undo = cmds.undoInfo(query=True, state=True)
    if undo:
        cmds.undoInfo(openChunk=True, chunkName="create ring guide")
    try:
        if replacing and cmds.objExists(replacing):
            cmds.delete(replacing)
        comp = guide_rig.getComponentGuide("ring_slide")
        if not comp:
            cmds.warning("Could not find the ring_slide component.")
            return None
        comp.setParamDefValue("comp_name", "ring")
        comp.draw(pm.PyNode(parent))
        root = comp.root.longName()
        cmds.xform(root, worldSpace=True, matrix=[
            x[0], x[1], x[2], 0.0,
            y[0], y[1], y[2], 0.0,
            z[0], z[1], z[2], 0.0,
            origin[0], origin[1], origin[2], 1.0,
        ])
        base = _short(root)
        if base.endswith("_root"):
            base = base[:-5]
        over_crv = _loop_curve(base + "_over_crv", over_local, root, 17)
        under_crv = _loop_curve(base + "_under_crv", under_local, root, 18)
        resolved = (cmds.ls(base_spline, long=True) or [""])[0] if base_spline else ""
        centre = [
            (sum(point[i] for point in over_points) / len(over_points)
             + sum(point[i] for point in under_points) / len(under_points)) * 0.5
            for i in range(3)
        ]
        cmds.setAttr(root + ".splineJoint", spline_joint_index(resolved, centre))
        for attr, value in (
            ("mesh", over_mesh),
            ("overEdge", " ".join(_short(part) for part in over.split())),
            ("underEdge", " ".join(_short(part) for part in under.split())),
            ("overVerts", " ".join(_short(vert) for vert in over_verts)),
            ("underVerts", " ".join(_short(vert) for vert in under_verts)),
            ("overCrv", _short(over_crv)),
            ("underCrv", _short(under_crv)),
            ("parentComp", parent_comp),
            ("baseSpline", _short(base_spline) if base_spline else ""),
            ("baseCtl", _short(base_ctl) if base_ctl else ""),
            ("tipCtl", _short(tip_ctl) if tip_ctl else ""),
        ):
            cmds.setAttr(root + "." + attr, value, type="string")
        cmds.select(root)
        print("Drew {}. Build it to skin the seam.".format(_short(root)))
        return root
    finally:
        if undo:
            cmds.undoInfo(closeChunk=True)


class Dialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(Dialog, self).__init__(parent)
        self.setObjectName("RingSlideUI")
        self.setWindowTitle("Ring Slide")
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(460)
        self._name_jobs = {}
        layout = QtWidgets.QVBoxLayout(self)
        self.spline = self._row(
            layout, "Base Spline", "Spine, neck, sleeve, or another chain",
            self._capture_spline, "Use the selected chain component.",
            self._create_spline, "Draw a spine_S_shape_01 with the neck defaults.",
        )
        self.base = self._row(
            layout, "Base", "control_01 at the root of the chain",
            self._capture_control, "Use the selected control_01.",
            self._create_base, "Draw a control_01 named base.",
        )
        self.tip = self._row(
            layout, "Tip", "control_01 at the end of the chain",
            self._capture_control, "Use the selected control_01.",
            self._create_tip, "Draw a control_01 named tip.",
        )
        self.over = self._row(layout, "Over", "Edge ring that slides")
        self.under = self._row(layout, "Under", "Edge ring it slides along")
        button = QtWidgets.QPushButton("Create Guide")
        button.clicked.connect(self._create)
        layout.addWidget(button)
        self._load_selected()

    def _row(self, layout, label, tip, capture=None, pick_tip=None, create=None, create_tip=None):
        row = QtWidgets.QHBoxLayout()
        text = QtWidgets.QLabel(label)
        text.setFixedWidth(76)
        field = QtWidgets.QLineEdit()
        field.setPlaceholderText(tip)
        pick = QtWidgets.QPushButton("<<")
        pick.setFixedWidth(36)
        pick.setToolTip(pick_tip or "Connected edge loop around the seam. One edge grows that loop.")
        capture = capture or self._capture
        pick.clicked.connect(lambda _checked=False, box=field: capture(box))
        row.addWidget(text)
        row.addWidget(field)
        row.addWidget(pick)
        if create:
            made = QtWidgets.QPushButton("Create")
            made.setFixedWidth(52)
            made.setToolTip(create_tip or "")
            made.clicked.connect(create)
            row.addWidget(made)
        layout.addLayout(row)
        return field

    def _capture(self, field):
        edges = cmds.polyListComponentConversion(cmds.ls(selection=True), toEdge=True)
        edges = cmds.ls(edges, flatten=True, long=True) or []
        if len(edges) == 1:
            edges = _grow_loop(edges[0])
        if not _walk_verts(edges):
            self._clear(field)
            cmds.warning("Select one closed edge loop.")
            return
        compact = cmds.ls(edges, flatten=False) or edges
        text = " ".join(_short(edge) for edge in compact)
        field.setText(text)
        field.setToolTip(text)

    def _fill(self, field, root):
        """Show this guide, and follow later renames of the same node."""
        short = _short(root)
        field.setText(short)
        field.setToolTip(short)
        self._watch(field, root)

    def _clear(self, field):
        self._unwatch(field)
        field.clear()
        field.setToolTip("")

    def _watch(self, field, root):
        """Notice when this guide's node is renamed, and write the new name.

        The Maya API callback follows the node, so it still fires after the
        name has changed. A scriptJob for the same event does not.
        """
        import maya.api.OpenMaya as om

        self._unwatch(field)
        picked = om.MSelectionList()
        picked.add(root)
        node = picked.getDependNode(0)

        def _renamed(renamed, _previous, _client):
            if field.hasFocus():
                return
            new = om.MFnDependencyNode(renamed).name()
            if field.text() != new:
                field.setText(new)
                field.setToolTip(new)

        self._name_jobs[field] = om.MNodeMessage.addNameChangedCallback(node, _renamed)

    def _unwatch(self, field):
        import maya.api.OpenMaya as om

        callback = self._name_jobs.pop(field, None)
        if callback is not None:
            om.MMessage.removeCallback(callback)

    def closeEvent(self, event):
        for field in (self.spline, self.base, self.tip):
            self._unwatch(field)
        super(Dialog, self).closeEvent(event)

    def _selected_guide(self, accept):
        for node in cmds.ls(selection=True, long=True) or []:
            root = _guide_root(node)
            if root and accept(cmds.getAttr(root + ".comp_type")):
                return root
        return None

    def _capture_spline(self, field):
        root = self._selected_guide(lambda kind: kind not in ("control_01", "ring_slide"))
        if not root:
            self._clear(field)
            cmds.warning("Select a chain component, such as a spine, neck, or sleeve.")
            return
        self._fill(field, root)

    def _capture_control(self, field):
        root = self._selected_guide(lambda kind: kind == "control_01")
        if not root:
            self._clear(field)
            cmds.warning("Select a control_01.")
            return
        self._fill(field, root)

    def _create_spline(self):
        base = self._resolve(self.base.text(), lambda kind: kind == "control_01")
        root = create_spine(base)
        if root:
            self._fill(self.spline, root)

    def _create_base(self):
        spline = self._resolve(self.spline.text(), self._is_spline)
        base = component_ends(spline)[0] if spline else None
        root = create_control("base", base)
        if root:
            self._fill(self.base, root)

    def _create_tip(self):
        spline = self._resolve(self.spline.text(), self._is_spline)
        tip = component_ends(spline)[1] if spline else (0.0, 4.0, 0.0)
        base = self._resolve(self.base.text(), lambda kind: kind == "control_01")
        root = create_control("tip", tip, parent=sibling_parent(base))
        if root:
            self._fill(self.tip, root)

    def _resolve(self, name, accept):
        found = cmds.ls((name or "").strip(), long=True) or []
        owner = _guide_root(found[0]) if found else None
        if not owner or not accept(cmds.getAttr(owner + ".comp_type")):
            return None
        return owner

    def _is_spline(self, kind):
        return kind not in ("control_01", "ring_slide")

    def _inputs_ready(self):
        spline = self._resolve(self.spline.text(), self._is_spline)
        base = self._resolve(self.base.text(), lambda kind: kind == "control_01")
        tip = self._resolve(self.tip.text(), lambda kind: kind == "control_01")
        if not spline:
            cmds.warning("Pick a base spline or create one. A spine, neck, or sleeve.")
            return False
        if not base:
            cmds.warning("Pick a base control_01 or create one.")
            return False
        if not tip:
            cmds.warning("Pick a tip control_01 or create one.")
            return False
        if base == tip:
            cmds.warning("Base and tip have to be two different controls.")
            return False
        self._fill(self.spline, spline)
        self._fill(self.base, base)
        self._fill(self.tip, tip)
        return True

    def _load_selected(self):
        root = _selected_ring()
        if not root:
            return
        self.over.setText(cmds.getAttr(root + ".overEdge") or "")
        self.under.setText(cmds.getAttr(root + ".underEdge") or "")

    def _create(self):
        if not self._inputs_ready():
            return
        create_guide(
            self.over.text().strip(),
            self.under.text().strip(),
            base_spline=self.spline.text().strip(),
            base_ctl=self.base.text().strip(),
            tip_ctl=self.tip.text().strip(),
        )


def show():
    """Open the capture window."""
    global _dialog
    _ensure_path()
    try:
        if _dialog is not None:
            _dialog.close()
            _dialog.deleteLater()
    except Exception:
        pass
    _dialog = Dialog(_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def _main_window():
    import maya.OpenMayaUI as omui

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return QtCompat.wrapInstance(int(ptr), QtWidgets.QWidget)
