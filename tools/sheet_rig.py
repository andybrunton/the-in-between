"""Capture an over edge ring and an under edge ring, then draw the guide.

The guide marks the center of the over ring and both loops. Build it with
Shifter: one center joint, one joint on every vertex, and a linear skin.
Rotate X and rotate Z move both rings together. Rotate Y slides the over
joints along the under loop.

One guide is one seam. Run it again for the other end of the neck. Select a
ring guide and Create Guide to replace that one.

Run in Maya::

    import sys
    sys.path.append("C:/Users/andre/Documents/GitHub/the-in-between/tools")
    import sheet_rig
    sheet_rig.show()
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


def create_guide(over, under, parent_comp=""):
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
        for attr, value in (
            ("mesh", over_mesh),
            ("overEdge", " ".join(_short(part) for part in over.split())),
            ("underEdge", " ".join(_short(part) for part in under.split())),
            ("overVerts", " ".join(_short(vert) for vert in over_verts)),
            ("underVerts", " ".join(_short(vert) for vert in under_verts)),
            ("overCrv", _short(over_crv)),
            ("underCrv", _short(under_crv)),
            ("parentComp", parent_comp),
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
        self.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(self)
        self.over = self._row(layout, "Over", "Edge ring that slides")
        self.under = self._row(layout, "Under", "Edge ring it slides along")
        self.parent = self._row(
            layout, "Parent", "Optional. Control lines up with this component",
            self._capture_parent, "Use the selected guide component. An empty selection clears it.",
        )
        button = QtWidgets.QPushButton("Create Guide")
        button.clicked.connect(self._create)
        layout.addWidget(button)
        self._load_selected()

    def _row(self, layout, label, tip, capture=None, pick_tip=None):
        row = QtWidgets.QHBoxLayout()
        text = QtWidgets.QLabel(label)
        text.setFixedWidth(52)
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
        layout.addLayout(row)
        return field

    def _capture(self, field):
        edges = cmds.polyListComponentConversion(cmds.ls(selection=True), toEdge=True)
        edges = cmds.ls(edges, flatten=True, long=True) or []
        if len(edges) == 1:
            edges = _grow_loop(edges[0])
        if not _walk_verts(edges):
            field.clear()
            cmds.warning("Select one closed edge loop.")
            return
        compact = cmds.ls(edges, flatten=False) or edges
        text = " ".join(_short(edge) for edge in compact)
        field.setText(text)
        field.setToolTip(text)

    def _capture_parent(self, field):
        for node in cmds.ls(selection=True, long=True) or []:
            root = _guide_root(node)
            if root and cmds.getAttr(root + ".comp_type") != "ring_slide":
                field.setText(_short(root))
                field.setToolTip(_short(root))
                return
        field.clear()
        field.setToolTip("")

    def _load_selected(self):
        root = _selected_ring()
        if not root:
            return
        self.over.setText(cmds.getAttr(root + ".overEdge") or "")
        self.under.setText(cmds.getAttr(root + ".underEdge") or "")
        if cmds.attributeQuery("parentComp", node=root, exists=True):
            self.parent.setText(cmds.getAttr(root + ".parentComp") or "")

    def _create(self):
        create_guide(
            self.over.text().strip(),
            self.under.text().strip(),
            self.parent.text().strip(),
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
