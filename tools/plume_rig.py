"""Author a cylinder, flare and bend it, drape feathers, then drop guides on them.

Create Guide builds a spine_S_shape_01 neck with one more joint than the
feather rows, then one control_01 per feather. The neck curve follows the
cylinder bend. The neck hangs under a chest control at its base. A root
control is at the origin. The head sits on the tip, parented to the chest,
not to the neck. After the build, the head moves the neck tip. Each neck
FK control blends from its rest pose toward the head, so a forward pitch
on the head is the same forward pitch at the tip. The neck IK and FK
controls are hidden and locked, and the head joint hangs off the tip.
Each feather row is parented to the nearest neck joint. After the rig is
built, a post step on the head control lifts each row, parents
each row of controls to the closest neck FK control, and skins the feathers
as one mesh. Extra joints under the feather joint bend the feather
with the cylinder. Host channels live on the head control. Volume starts
at 0. Splay is degrees, 0 to 90, per row, grouped as every Splay, then
every Splay Falloff, then every Splay Rotate. Falloff 0 splays
one feather, falloff 1 splays the row, and rotate moves that center.
Wind breathes that pose. Splay 0 stays shut. Wind is the amount, and
Wind Offset scrubs a noise field the user keys.

Run in Maya::

    import sys
    sys.path.append("C:/Users/andre/Documents/GitHub/the-in-between/tools")
    import plume_rig
    plume_rig.show()
"""

import math
import os
import tempfile
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om

from mgear.vendor.Qt import QtCore, QtGui, QtWidgets, QtCompat

ROLE = "plumeRole"
ROW = "plumeRow"
FRAME = "plumeFrame"
SIZE = "plumeSize"

#region constants

# Construction size. Placement is the cylinder's own translate, rotate, and scale.
# Divisions are only the mesh. Feather rows and columns are separate.
CYLINDER_RADIUS = 1.0
CYLINDER_HEIGHT = 4.0
CYLINDER_HEIGHT_DIVS = 16
CYLINDER_AROUND_DIVS = 16

# Just off the cylinder. The leading edge clears the next feather in the row.
# Row lift is the smallest curl that keeps the hanging half in front of the
# row below. Anything looser belongs on a rig control.
SURFACE_PAD = 0.02
OVERLAP_LIFT = 0.03
ROW_LIFT = 0.065
# Share of its row's twist a feather turns as one piece. 1 = rigid feathers but
# rows cut through each other; 0 = feathers follow their own joint, clean but shear.
TWIST_RIGIDITY = 0.5
# Joints inserted across each gap between stations. Linear skinning shrinks a
# feather where two influences twist far apart; more steps keep each blend small.
# 1 inserts nothing.
TWIST_STEPS = 2

# Shoulder wider than one column, so neighbors overlap. Length is two row
# heights, so each feather hangs over the row below.
WIDTH_SCALE = 1.5
LENGTH_SCALE = 2.0
ALONG_DIVS = 6
ACROSS_DIVS = 4

# Pull the card off the 0 and 1 edges so filtering stays inside the picture.
# ponytail: a fixed fraction, not a texel. 2% is about 10px on a 512 map.
UV_INSET = 0.02

# Widest station on the edge curve, in shoulder-widths. 1 is the built-in
# shoulder. ponytail: a hard cap so a drag cannot open the vane without bound.
EDGE_WIDTH_MAX = 1.5

# Top row first. The opening feathers linger, then the gap shrinks so the
# rest rush in. One feather per beat up to this many draws; denser plumes
# share beats. ponytail: cube ease between two beats, no slider. A default
# 4x12 opens near 0.13s and finishes in about two seconds.
FEATHER_REVEAL_DRAWS = 48
FEATHER_REVEAL_SLOW = 0.025
FEATHER_REVEAL_FAST = 0.007

# Guide icon and built control, times mGear's default of 1.
# Applied only when this tool draws the control.
HEAD_GUIDE_SIZE = 10.0
CHEST_GUIDE_SIZE = 5.0

_dialog = None

#endregion
#region layout

def column_angle(row, column, columns):
    """Angle around the cylinder. Odd rows shift by half a column."""
    step = 2.0 * math.pi / float(columns)
    shift = 0.5 * step if row % 2 else 0.0
    return column * step + shift


def scale_span(row, rows, length_scale=LENGTH_SCALE):
    """Root toward the end (+Y), tip toward the start. Returns (t_root, t_tip).

    Every row has the same length. Roots stay one row apart and the top root
    sits on the end of the cylinder, whatever the length. The bottom tip hangs
    past the start.
    """
    rows = max(int(rows), 1)
    band = 1.0 / float(rows)
    length = float(length_scale) * band
    t_root = 1.0 - (rows - 1 - row) * band
    return t_root, t_root - length


def petal_half(u):
    """Default outline half-width. u is 0 at the root and 1 at the tip.

    Narrower at the hinge, fullest at the shoulder, a point at the tip.
    The edge curve replaces this at each station. Same curve for every feather.
    """
    if u <= 0.0:
        return 0.75
    if u >= 1.0:
        return 0.0
    shoulder = 0.28
    if u < shoulder:
        s = u / shoulder
        return 0.75 + 0.25 * math.sin(s * math.pi * 0.5)
    s = (u - shoulder) / (1.0 - shoulder)
    return math.cos(s * math.pi * 0.5)


def default_edge():
    """Half-width at each cross-section. The tip itself stays a point."""
    steps = ALONG_DIVS + 1
    return [petal_half(i / float(steps)) for i in range(steps)]


def feather_uvs(n_along, n_across):
    """One card for every feather, inset from the 0-1 edge. U is across, V is root to tip.

    Each station spans the full width, so one picture fits every feather.
    Row i sits at i / n_along, matching the petal stations. The tip is the
    extra point at the top center.
    """
    span = 1.0 - 2.0 * UV_INSET
    uvs = []
    for i in range(n_along):
        v = UV_INSET + (i / float(n_along)) * span
        for j in range(n_across):
            u = UV_INSET + (j / float(n_across - 1)) * span
            uvs.append((u, v))
    uvs.append((0.5, 1.0 - UV_INSET))
    return uvs


def _edge_widths(profile):
    """Station widths, or None when the list is not one width per cross-section."""
    steps = ALONG_DIVS + 1
    if not profile or len(profile) != steps:
        return None
    out = []
    for width in profile:
        width = float(width)
        if width < 0.0:
            width = 0.0
        elif width > EDGE_WIDTH_MAX:
            width = EDGE_WIDTH_MAX
        out.append(width)
    return out


def angular_half_width(columns, width_scale=WIDTH_SCALE):
    """Half the angle at the shoulder. Wider than half a column."""
    return 0.5 * width_scale * (2.0 * math.pi / float(columns))


def half_angle(columns, u, r_root, r_here, width=None):
    """Half-angle of the petal at u.

    width replaces the default curve at this station. Where the cylinder is
    fatter toward the tip, shrink the angle so the point stays a point. Do not
    grow it on a pinch: the leading edge is only lifted enough to clear the
    designed overlap.
    """
    if r_here < 1e-4:
        return 0.0
    if width is None:
        width = petal_half(u)
    half = angular_half_width(columns) * width
    if r_here > r_root:
        half *= r_root / r_here
    return half


def surface_lift(u, side):
    """Fraction of local radius off the cylinder.

    side is 0 at the trailing edge and 1 at the leading edge. The leading
    edge sits further out and lays over the next feather in the row. Lift
    grows a little toward the tip, just enough to clear the row below.
    """
    return SURFACE_PAD + OVERLAP_LIFT * side + ROW_LIFT * u


def _hash01(row, column):
    """Stable 0-1 value for this feather."""
    n = ((int(row) + 1) * 374761393) ^ ((int(column) + 1) * 668265263)
    n &= 0xFFFFFFFF
    n ^= n >> 13
    n = (n * 1274126177) & 0xFFFFFFFF
    n ^= n >> 16
    return n / 4294967295.0


def tip_slide(row, column, variety):
    """Signed lean of one feather across its own end. -1 and 1 are the two edges.

    Zero keeps the feather centered. The tip never passes that feather's own edge.
    """
    variety = float(variety)
    if variety < 0.0:
        variety = 0.0
    elif variety > 1.0:
        variety = 1.0
    if variety == 0.0:
        return 0.0
    return (_hash01(row, column) * 2.0 - 1.0) * variety


def _tip_reach(columns):
    """How far a feather may lean toward its own edge, as a fraction of that edge.

    Below 8 around, centered feathers already meet, so the lean stays off.
    From 8 up the whole edge still clears the row below.
    ponytail: measured by the chord check. A new overlap or row lift needs
    that check run again.
    """
    return 1.0 if int(columns) >= 8 else 0.0


def _tip_lean(columns, slide, r_root=1.0, r_tip=1.0, width=None):
    """Angle the tip moves off center. The root stays put; u scales this to the tip.

    width is the last station on the edge curve, so the lean stays inside the
    edited edge.
    """
    slide = float(slide)
    if slide < -1.0:
        slide = -1.0
    elif slide > 1.0:
        slide = 1.0
    u_last = ALONG_DIVS / float(ALONG_DIVS + 1)
    half = half_angle(columns, u_last, r_root, r_tip, width)
    return slide * _tip_reach(columns) * half


def row_gap(columns):
    """Smallest clearance of a feather over the row below, fraction of radius.

    Samples the brick-offset overlap, including one vertex step further down
    the lower feather, which is the high side of the quad under this one.
    """
    tuck = 1.0 / LENGTH_SCALE
    step = 2.0 * math.pi / float(columns)
    du = 1.0 / float(ALONG_DIVS + 1)
    worst = None
    samples = 16
    for i in range(samples + 1):
        u = tuck + (1.0 - tuck) * i / float(samples)
        for extra in (0.0, du):
            ul = u - tuck + extra
            if ul > 1.0:
                continue
            gap = _gap_at(columns, step, u, ul)
            if gap is None:
                continue
            if worst is None or gap < worst:
                worst = gap
    return 0.0 if worst is None else worst


def _gap_at(columns, step, u, ul):
    """Lift of the upper feather minus the lower one where their angles overlap."""
    hu = half_angle(columns, min(u, 0.999), 1.0, 1.0)
    hl = half_angle(columns, ul, 1.0, 1.0)
    if hl < 1e-8:
        return None
    if u >= 0.999 or hu < 1e-8:
        sl = 0.5 - (0.5 * step) / (2.0 * hl)
        sl = min(1.0, max(0.0, sl))
        return surface_lift(1.0, 0.5) - surface_lift(ul, sl)
    lo = max(-hu, 0.5 * step - hl)
    hi = min(hu, 0.5 * step + hl)
    if lo >= hi:
        return None
    worst = None
    for k in range(9):
        x = lo + (hi - lo) * k / 8.0
        su = min(1.0, max(0.0, 0.5 + x / (2.0 * hu)))
        sl = min(1.0, max(0.0, 0.5 + (x - 0.5 * step) / (2.0 * hl)))
        gap = surface_lift(u, su) - surface_lift(ul, sl)
        if worst is None or gap < worst:
            worst = gap
    return worst


def orient_scale(axis_point, surface_point, normal, along):
    """Hinge frame. Local X toward the start, Y outward, Z the hinge.

    The cylinder's +Y is the top. The feather's tip points back toward the
    start, so each row hangs down over the one below. A cap hit falls back
    to the radial direction.
    """
    radial = _norm(_sub(surface_point, axis_point))
    down = _norm(along)
    down = _mul(down, -1.0)
    # A faceted tube reports a face normal aimed at the face center, not at
    # this column. Keep the flare's tilt, drop the around-the-tube skew.
    side = _cross(down, radial)
    if _length(side) > 1e-8:
        side = _norm(side)
        y = _sub(normal, _mul(side, _dot(normal, side)))
    else:
        y = normal
    if _dot(y, radial) < 0.0:
        y = _mul(y, -1.0)
    if abs(_dot(y, down)) > abs(_dot(y, radial)):
        y = radial
    y = _norm(y)
    x = _norm(_sub(down, _mul(y, _dot(down, y))))
    if _length(x) < 1e-8:
        helper = (1.0, 0.0, 0.0) if abs(y[0]) < 0.9 else (0.0, 0.0, 1.0)
        x = _norm(_sub(helper, _mul(y, _dot(helper, y))))
    z = _cross(x, y)
    return x, y, z


def _neck_divisions(rows):
    """Joint count for the neck: one more than the feather rows.

    The extra joint is the base, so each row root lands on the next joint.
    The neck spine will not draw fewer than 3.
    """
    return max(3, int(rows) + 1)


def _spine_joint_t(index, divisions):
    """Height parameter of one neck joint, 0 at the base and 1 at the top.

    The component parks the first joint just above the base. The last sits on top.
    """
    step = 1.0 / float(int(divisions) - 1)
    if index <= 0:
        return step / 10.0
    return index * step


def _closest_joint(t, divisions):
    """Spine joint index nearest this height parameter."""
    best = 0
    best_d = None
    for i in range(int(divisions)):
        d = abs(_spine_joint_t(i, divisions) - t)
        if best_d is None or d < best_d:
            best = i
            best_d = d
    return best


def _neck_parent_index(row, rows):
    """jointList index of the neck joint this row hangs from.

    _closest_joint is the division along the curve. spine_S_shape_01
    inserts a hip joint at 0, so the list index is one higher. Without
    that, row 1 lands on fk0 and row 2 on fk1.
    """
    divisions = _neck_divisions(rows)
    return _closest_joint(scale_span(row, rows)[0], divisions) + 1


def _feather_slot(feather):
    """Row and column from a plume_feather_ROW_COL name. None if it does not match."""
    parts = feather.split("|")[-1].split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[-2]), int(parts[-1])
    except ValueError:
        return None


def _feather_joint_slot(joint):
    """Row and column from a control_01 joint, feather_ROW_COL_*_0_jnt.

    None if the name is not that joint. The 0 is the component's joint index.
    """
    parts = joint.split("|")[-1].split("_")
    if len(parts) < 6 or parts[0] != "feather" or parts[-1] != "jnt":
        return None
    if parts[-2] != "0":
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


# A nearer feather than this wins. Anything closer keeps the earlier angle,
# which is the lower column when angles are passed in column order.
_SPLAY_TIE = 1e-6
_SPLAY_PEAK = 1e-8


def splay_weights(angles, center, falloff):
    """Weight of each feather in one row.

    angles and center are radians, 0 at +X. Falloff 0 picks the nearest
    feather. Falloff 1 weights every feather at 1. In between, the nearest
    feather stays at 1 and the rest fall off around the row. On a tie the
    earlier angle wins, so pass the row in column order.
    """
    count = len(angles)
    if count == 0:
        return []
    falloff = float(falloff)
    if falloff < 0.0:
        falloff = 0.0
    elif falloff > 1.0:
        falloff = 1.0
    center = float(center)
    nearest = 0
    nearest_d = None
    distances = []
    for index, angle in enumerate(angles):
        delta = float(angle) - center
        dist = abs(math.atan2(math.sin(delta), math.cos(delta)))
        distances.append(dist)
        if nearest_d is None or dist < nearest_d - _SPLAY_TIE:
            nearest = index
            nearest_d = dist
    if falloff >= 1.0:
        return [1.0] * count
    if falloff <= 0.0:
        weights = [0.0] * count
        weights[nearest] = 1.0
        return weights
    # 0.5 reaches 90 degrees around the row and is quiet past that.
    reach = 0.5 * falloff / (1.0 - falloff)
    raw = []
    for dist in distances:
        span = (dist / math.pi) / reach
        if span >= 1.0:
            raw.append(0.0)
        else:
            raw.append(math.cos(span * math.pi * 0.5))
    peak = max(raw)
    if peak <= _SPLAY_PEAK:
        weights = [0.0] * count
        weights[nearest] = 1.0
        return weights
    return [item / peak for item in raw]


def wind_sample(angle, row):
    """Noise coordinates for one feather. Angle is degrees.

    Half a turn is one noise feature, so neighbours rustle together.
    Rows are a feature apart. Wind Offset is the axis the user keys.
    """
    return (float(angle) / 180.0, float(row))


def wind_hinge(pose, wave, wind):
    """Posed splay plus the gust. Wind 0 keeps the pose. Pose 0 stays shut."""
    wind = float(wind)
    if wind < 0.0:
        wind = 0.0
    elif wind > 1.0:
        wind = 1.0
    hinge = float(pose) * (1.0 + wind * float(wave))
    if hinge < 0.0:
        return 0.0
    if hinge > 90.0:
        return 90.0
    return hinge


def _splay_expression(host, row, feathers, twist=None):
    """MEL for one row. feathers is (degrees, node), column order.

    Same curve as splay_weights, then the same gust as wind_hinge.
    0 degrees is +X. The gust is noise at wind_sample, scrubbed by Wind Offset.
    twist is (plug, share): the row's ring is turned by plug * share, so the
    centre is moved the same amount and keeps its direction in root space.
    """
    tie = math.degrees(_SPLAY_TIE)
    count = len(feathers)
    spin = ""
    if twist:
        spin = " + %s * %.9g" % (twist[0], twist[1])
    lines = [
        "// Same curve as splay_weights, then wind_hinge. 0 degrees is +X.",
        "float $fall = %s.splayFalloff%d;" % (host, row),
        "float $rot = %s.splayRotate%d%s;" % (host, row, spin),
        "float $peak = %s.splay%d;" % (host, row),
        "float $wind = %s.wind;" % host,
        "float $off = %s.windOffset;" % host,
        "float $reach = 1;",
        "float $best = 0;",
        "float $which = 0;",
        "float $m = 1;",
        "float $wave = 0;",
        "float $hinge = 0;",
    ]
    for index in range(count):
        lines.append("float $d%d = 0;" % index)
        lines.append("float $w%d = 1;" % index)
        lines.append("float $t%d = 0;" % index)
    lines.append("if ($fall < 0) $fall = 0;")
    lines.append("if ($fall > 1) $fall = 1;")
    lines.append("if ($wind < 0) $wind = 0;")
    lines.append("if ($wind > 1) $wind = 1;")
    for index, (angle, _node) in enumerate(feathers):
        lines.append(
            "$d%d = atan2d(sind(%.8f - $rot), cosd(%.8f - $rot));"
            % (index, angle, angle)
        )
        lines.append("if ($d%d < 0) $d%d = -$d%d;" % (index, index, index))
    if count:
        lines.append("$best = $d0;")
        lines.append("$which = 0;")
    for index in range(1, count):
        lines.append(
            "if ($d%d < $best - %.8f) { $best = $d%d; $which = %d; }"
            % (index, tie, index, index)
        )

    def one_hot(indent):
        for index in range(count):
            lines.append("%s$w%d = 0;" % (indent, index))
        for index in range(count):
            lines.append(
                "%sif ($which == %d) $w%d = 1;" % (indent, index, index)
            )

    lines.append("if ($fall < 1) {")
    lines.append("if ($fall <= 0) {")
    one_hot("")
    lines.append("} else {")
    lines.append("$reach = 90.0 * $fall / (1.0 - $fall);")
    for index in range(count):
        lines.append("$t%d = $d%d / $reach;" % (index, index))
        lines.append("if ($t%d >= 1) {" % index)
        lines.append("$w%d = 0;" % index)
        lines.append("} else {")
        lines.append("$w%d = cosd($t%d * 90.0);" % (index, index))
        lines.append("}")
    if count:
        lines.append("$m = $w0;")
    for index in range(1, count):
        lines.append("if ($w%d > $m) $m = $w%d;" % (index, index))
    lines.append("if ($m <= %.8f) {" % _SPLAY_PEAK)
    one_hot("")
    lines.append("} else {")
    for index in range(count):
        lines.append("$w%d = $w%d / $m;" % (index, index))
    lines.append("}")
    lines.append("}")
    lines.append("}")
    for index, (angle, node) in enumerate(feathers):
        across, up = wind_sample(angle, row)
        lines.append("$wave = noise(<<$off, %.8f, %.8f>>);" % (across, up))
        lines.append(
            "$hinge = $peak * $w%d * (1 + $wind * $wave);" % index
        )
        lines.append("if ($hinge < 0) $hinge = 0;")
        lines.append("if ($hinge > 90) $hinge = 90;")
        lines.append("%s.rotateZ = $hinge;" % node)
    return "\n".join(lines)


def _splay_channel_names(rows):
    """Splay, then falloff, then rotate, so each kind keys as one block."""
    rows = list(rows)
    return (
        ["splay%d" % row for row in rows]
        + ["splayFalloff%d" % row for row in rows]
        + ["splayRotate%d" % row for row in rows]
    )


def _check_layout():
    assert column_angle(0, 0, 8) == 0.0
    assert abs(column_angle(1, 0, 8) - math.pi / 8.0) < 1e-9
    assert abs(column_angle(0, 1, 8) - math.pi / 4.0) < 1e-9

    x, y, z = orient_scale((0, 0, 0), (2, 0, 0), (1, 0, 0), (0, 1, 0))
    assert _dot(y, (1, 0, 0)) > 0.99
    assert _dot(x, (0, -1, 0)) > 0.99
    assert _dot(_cross(x, y), z) > 0.99

    step = 2.0 * math.pi / 8.0
    shoulder = half_angle(8, 0.28, 1.0, 1.0)
    assert 2.0 * shoulder > step
    assert half_angle(8, 0.28, 1.0, 2.0) < shoulder
    assert abs(half_angle(8, 0.28, 1.0, 0.5) - shoulder) < 1e-9
    assert half_angle(8, 1.0, 1.0, 1.0) == 0.0
    assert surface_lift(0.28, 1.0) > surface_lift(0.28, 0.0)
    assert row_gap(8) > 0.02
    assert row_gap(12) > 0.02
    assert tip_slide(0, 0, 0.0) == 0.0
    assert abs(tip_slide(2, 5, 1.0)) <= 1.0
    assert abs(tip_slide(2, 5, 0.4)) <= 0.4 + 1e-9
    assert abs((scale_span(0, 4)[0] - scale_span(0, 4)[1]) - 0.5) < 1e-9
    root, tip = scale_span(2, 4)
    lower_root, lower_tip = scale_span(1, 4)
    assert tip < lower_root
    assert abs((root - tip) - (lower_root - lower_tip)) < 1e-9
    assert scale_span(0, 4)[1] < 0.0
    assert abs(scale_span(3, 4)[0] - 1.0) < 1e-9
    assert _neck_divisions(1) == 3
    assert _neck_divisions(2) == 3
    assert _neck_divisions(4) == 5
    for rows in (2, 6):
        divisions = _neck_divisions(rows)
        for row in range(rows):
            assert _closest_joint(scale_span(row, rows)[0], divisions) == row + 1
            assert _neck_parent_index(row, rows) == row + 2
    assert _closest_joint(scale_span(0, 2)[0], 4) == 2
    assert _closest_joint(scale_span(1, 2)[0], 4) == 3
    assert _closest_joint(scale_span(0, 6)[0], 3) == 0
    assert _closest_joint(scale_span(5, 6)[0], 3) == 2
    assert _feather_slot("|grp|plume_feather_2_5") == (2, 5)
    assert _feather_slot("not_a_feather") is None
    assert _feather_joint_slot("feather_2_5_C0_0_jnt") == (2, 5)
    assert _feather_joint_slot("|grp|feather_0_10_C0_0_jnt") == (0, 10)
    assert _feather_joint_slot("feather_2_5_C0_ctl") is None
    assert _feather_joint_slot("leaf_feather_2_5_C0_0_jnt") is None
    assert _feather_joint_slot("feather_2_5_C0_1_jnt") is None
    assert abs(petal_half(0.28) - 1.0) < 1e-9
    assert petal_half(0.0) < petal_half(0.28)
    assert petal_half(1.0) == 0.0
    assert petal_half(0.5) > petal_half(0.85)
    steps = ALONG_DIVS + 1
    edge = default_edge()
    assert len(edge) == steps
    for i, width in enumerate(edge):
        assert abs(width - petal_half(i / float(steps))) < 1e-9
    # A station's width scales that cross-section and does not move it along the feather.
    u = 1.0 / steps
    assert abs(half_angle(8, u, 1.0, 1.0, 0.1) - angular_half_width(8) * 0.1) < 1e-9
    assert abs(half_angle(8, u, 1.0, 1.0) - angular_half_width(8) * petal_half(u)) < 1e-9
    assert _edge_widths(edge) == edge
    assert _edge_widths([2.0]) is None
    assert _edge_widths([-1.0] + edge[1:])[0] == 0.0
    uvs = feather_uvs(ALONG_DIVS + 1, ACROSS_DIVS + 1)
    assert len(uvs) == (ALONG_DIVS + 1) * (ACROSS_DIVS + 1) + 1
    assert uvs[0] == (UV_INSET, UV_INSET)
    assert abs(uvs[ACROSS_DIVS][0] - (1.0 - UV_INSET)) < 1e-9
    assert uvs[ACROSS_DIVS][1] == UV_INSET
    assert uvs[-1] == (0.5, 1.0 - UV_INSET)
    span = 1.0 - 2.0 * UV_INSET
    assert abs(uvs[-2][1] - (UV_INSET + ALONG_DIVS / float(ALONG_DIVS + 1) * span)) < 1e-9
    assert min(u for u, _v in uvs) >= UV_INSET - 1e-9
    assert max(u for u, _v in uvs) <= 1.0 - UV_INSET + 1e-9

    # Cap normal is replaced by the outward radial.
    _, y, _ = orient_scale((0, 0, 0), (2, 0, 0), (0, -1, 0), (0, 1, 0))
    assert _dot(y, (1, 0, 0)) > 0.99

    # A flare slope stays in the normal instead of being flattened.
    _, y, _ = orient_scale((0, 0, 0), (2, 0, 0), (0.9, 0.4, 0), (0, 1, 0))
    assert y[0] > 0.8 and y[1] > 0.3

    angles = [column_angle(0, col, 8) for col in range(8)]
    assert splay_weights([], 0.0, 0.5) == []
    assert splay_weights(angles, 0.0, 1.0) == [1.0] * 8
    assert splay_weights(angles, 0.0, 2.0) == [1.0] * 8
    picked = splay_weights(angles, 0.0, 0.0)
    assert picked == [1.0] + [0.0] * 7
    assert splay_weights(angles, math.pi / 8.0, 0.0) == picked
    spun = splay_weights(angles, angles[3], 0.0)
    assert spun[3] == 1.0 and sum(spun) == 1.0
    half = splay_weights(angles, 0.0, 0.5)
    assert abs(half[0] - 1.0) < 1e-9
    assert abs(half[1] - math.cos(math.pi / 4.0)) < 1e-9
    assert abs(half[2]) < 1e-9
    assert abs(half[4]) < 1e-9
    assert abs(half[1] - half[7]) < 1e-9
    assert abs(splay_weights(angles, 0.0, 0.75)[4] - 0.5) < 1e-9
    assert abs(max(splay_weights(angles, 0.2, 0.5)) - 1.0) < 1e-9
    assert splay_weights([0.0], math.pi, 0.3) == [1.0]
    assert splay_weights(angles, 4.0 * math.pi, 0.0) == picked
    odd = splay_weights(
        [column_angle(1, col, 8) for col in range(8)], 0.0, 0.0
    )
    assert odd[0] == 1.0 and sum(odd) == 1.0
    text = _splay_expression(
        "head_C0_ctl",
        0,
        [(0.0, "feather_0_0_C0_splay"), (45.0, "feather_0_1_C0_splay")],
    )
    assert "head_C0_ctl.splayFalloff0" in text
    assert "head_C0_ctl.splayRotate0" in text
    assert "head_C0_ctl.wind;" in text
    assert "head_C0_ctl.windOffset;" in text
    assert "splayRotate0;" in text
    spun = _splay_expression(
        "head_C0_ctl", 0, [(0.0, "f")], ("head_C0_ctl.rotateY", 0.5)
    )
    assert "splayRotate0 + head_C0_ctl.rotateY * 0.5;" in spun
    assert _splay_channel_names([0, 2]) == [
        "splay0",
        "splay2",
        "splayFalloff0",
        "splayFalloff2",
        "splayRotate0",
        "splayRotate2",
    ]
    assert "windSpeed" not in text
    assert "time" not in text
    across, up = wind_sample(45.0, 0)
    assert ("noise(<<$off, %.8f, %.8f>>);" % (across, up)) in text
    assert wind_sample(0.0, 0) == (0.0, 0.0)
    assert wind_sample(180.0, 2) == (1.0, 2.0)
    assert "90.0 * $fall / (1.0 - $fall)" in text
    assert "sind(45.00000000 - $rot)" in text
    assert "$hinge = $peak * $w1 * (1 + $wind * $wave);" in text
    assert "feather_0_1_C0_splay.rotateZ = $hinge;" in text
    assert wind_hinge(30.0, 1.0, 0.0) == 30.0
    assert wind_hinge(30.0, -1.0, 0.0) == 30.0
    assert wind_hinge(0.0, 1.0, 1.0) == 0.0
    assert wind_hinge(30.0, -1.0, 1.0) == 0.0
    assert wind_hinge(30.0, 1.0, 1.0) == 60.0
    assert wind_hinge(60.0, 1.0, 1.0) == 90.0
    assert wind_hinge(80.0, -0.5, 1.0) == 40.0
    assert wind_hinge(30.0, 1.0, 2.0) == 60.0


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a):
    return math.sqrt(_dot(a, a))


def _norm(a):
    n = _length(a)
    if n < 1e-8:
        return (0.0, 0.0, 0.0)
    return _mul(a, 1.0 / n)


def skin_weights(t, count):
    """Two nearest joints for a 0..1 position along the chain. Ends clamp.

    0 is the first joint, 1 is the last.
    """
    if count < 1:
        return []
    if t < 0.0:
        t = 0.0
    if t > 1.0:
        t = 1.0
    if count == 1:
        return [(0, 1.0)]
    u = t * (count - 1)
    index = int(u)
    if index >= count - 1:
        return [(count - 1, 1.0)]
    frac = u - index
    if frac <= 1e-8:
        return [(index, 1.0)]
    return [(index, 1.0 - frac), (index + 1, frac)]


def chain_parameter(point, positions):
    """0 at the first joint, 1 at the last, by closest point on the polyline.

    The fraction is the joint index, not arc length, so a point sitting on
    joint i lands on i / (count - 1) even when the gaps differ.
    """
    count = len(positions)
    if count < 2:
        return 0.0
    best = None
    for index in range(count - 1):
        start = positions[index]
        end = positions[index + 1]
        span = _sub(end, start)
        length2 = _dot(span, span)
        if length2 < 1e-12:
            frac = 0.0
            dist = _length(_sub(point, start))
        else:
            frac = _dot(_sub(point, start), span) / length2
            if frac < 0.0:
                frac = 0.0
            elif frac > 1.0:
                frac = 1.0
            dist = _length(_sub(point, _add(start, _mul(span, frac))))
        if best is None or dist < best[0]:
            best = (dist, index, frac)
    _dist, index, frac = best
    return (index + frac) / float(count - 1)


def _bend_local(point, curvature, height):
    """Maya bend in the cylinder's YZ plane. Positive curvature bends toward +Z.

    The handle is scaled to half the height, bounds -1 to 1, and spun so its
    local +X is the cylinder's +Z. Points past either end travel on the end
    tangent, which is what the deformer does.
    """
    if abs(curvature) < 1e-8:
        return point
    half = float(height) * 0.5
    if half < 1e-8:
        return point
    x, y, z = point
    hx = z / half
    hy = y / half
    hz = -x / half
    hy_b = hy
    if hy_b > 1.0:
        hy_b = 1.0
    elif hy_b < -1.0:
        hy_b = -1.0
    extra = hy - hy_b
    k = math.radians(curvature)
    theta = k * hy_b
    c = math.cos(theta)
    s = math.sin(theta)
    inv = 1.0 / k
    nx = (1.0 - c) * inv + hx * c + extra * s
    ny = s * inv - hx * s + extra * c
    return (-hz * half, ny * half, nx * half)


def _neck_guide_locals(curvature, height):
    """Cylinder-space neck guide: base, two handles, top.

    The handles are the cubic that follows Maya's bend. With no bend they
    sit on the straight line, one third and two thirds of the way up.
    ponytail: one cubic. tan() runs away as the sweep nears a full circle
    (curvature ±180). Past that, drop the handles onto the arc. A multi-span
    curve would match a loop.
    """
    half = float(height) * 0.5
    if half < 1e-8:
        return ((0.0, 0.0, 0.0),) * 4
    alpha = math.radians(float(curvature))
    base = _bend_local((0.0, -half, 0.0), curvature, height)
    top = _bend_local((0.0, half, 0.0), curvature, height)
    if abs(alpha) < 1e-4:
        return (
            (0.0, -half, 0.0),
            (0.0, -half / 3.0, 0.0),
            (0.0, half / 3.0, 0.0),
            (0.0, half, 0.0),
        )
    if abs(alpha) > math.radians(178.0):
        return (
            base,
            _bend_local((0.0, -half / 3.0, 0.0), curvature, height),
            _bend_local((0.0, half / 3.0, 0.0), curvature, height),
            top,
        )
    radius = half / abs(alpha)
    handle = radius * (4.0 / 3.0) * math.tan(abs(alpha) * 0.5)
    c = math.cos(alpha)
    s = math.sin(alpha)
    t0 = _norm((0.0, c, -s))
    t1 = _norm((0.0, c, s))
    return (
        base,
        _add(base, _mul(t0, handle)),
        _sub(top, _mul(t1, handle)),
        top,
    )


def _bend_dir(vector, y, curvature, height):
    """Rotate a cylinder-local direction by the bend at this height."""
    if abs(curvature) < 1e-8:
        return vector
    half = float(height) * 0.5
    if half < 1e-8:
        return vector
    hy = y / half
    if hy > 1.0:
        hy = 1.0
    elif hy < -1.0:
        hy = -1.0
    theta = math.radians(curvature) * hy
    if abs(theta) < 1e-8:
        return vector
    c = math.cos(theta)
    s = math.sin(theta)
    vx, vy, vz = vector
    return (vx, vy * c - vz * s, vy * s + vz * c)


def _cubic(p0, p1, p2, p3, t):
    u = 1.0 - t
    b0 = u * u * u
    b1 = 3.0 * u * u * t
    b2 = 3.0 * u * t * t
    b3 = t * t * t
    return (
        p0[0] * b0 + p1[0] * b1 + p2[0] * b2 + p3[0] * b3,
        p0[1] * b0 + p1[1] * b1 + p2[1] * b2 + p3[1] * b3,
        p0[2] * b0 + p1[2] * b1 + p2[2] * b2 + p3[2] * b3,
    )


def _neck_arc_error(curvature, height):
    """How far the neck cubic sits off Maya's bend, in cylinder units."""
    p0, p1, p2, p3 = _neck_guide_locals(curvature, height)
    center_z = (float(height) * 0.5) / math.radians(curvature)
    radius = abs(center_z)
    worst = 0.0
    for i in range(9):
        point = _cubic(p0, p1, p2, p3, i / 8.0)
        dist = math.sqrt(point[1] ** 2 + (point[2] - center_z) ** 2)
        worst = max(worst, abs(dist - radius))
    return worst


def _check_bend():
    # Numbers taken from Maya's bend deformer, height 4, curvature in degrees.
    got = _bend_local((0.0, 2.0, 0.0), 90.0, 4.0)
    assert abs(got[0]) < 1e-3 and abs(got[1] - 1.2732) < 1e-3
    assert abs(got[2] - 1.2732) < 1e-3
    got = _bend_local((0.0, 3.0, 0.0), 90.0, 4.0)
    assert abs(got[0]) < 1e-3 and abs(got[1] - 1.2732) < 1e-3
    assert abs(got[2] - 2.2732) < 1e-3
    got = _bend_local((0.0, -3.0, 0.0), 90.0, 4.0)
    assert abs(got[1] + 1.2732) < 1e-3 and abs(got[2] - 2.2732) < 1e-3
    got = _bend_local((1.0, 2.0, 0.0), 90.0, 4.0)
    assert abs(got[0] - 1.0) < 1e-3 and abs(got[2] - 1.2732) < 1e-3
    got = _bend_local((0.0, 2.0, 1.0), -90.0, 4.0)
    assert abs(got[1] - 2.2732) < 1e-3 and abs(got[2] + 1.2732) < 1e-3
    assert _bend_local((1.0, 2.0, 0.5), 0.0, 4.0) == (1.0, 2.0, 0.5)
    bent = _bend_dir((0.0, 0.0, 1.0), 2.0, 90.0, 4.0)
    assert abs(bent[0]) < 1e-6 and abs(bent[1] + 1.0) < 1e-6 and abs(bent[2]) < 1e-6
    # Centerline tangent. +Y in, bent direction out. Top of a +90 bend leaves along +Z.
    up = _bend_dir((0.0, 1.0, 0.0), 2.0, 90.0, 4.0)
    assert abs(up[0]) < 1e-6 and abs(up[1]) < 1e-6 and abs(up[2] - 1.0) < 1e-6
    down = _bend_dir((0.0, 1.0, 0.0), -2.0, 90.0, 4.0)
    assert abs(down[0]) < 1e-6 and abs(down[1]) < 1e-6 and abs(down[2] + 1.0) < 1e-6
    assert _bend_dir((0.0, 1.0, 0.0), 1.0, 0.0, 4.0) == (0.0, 1.0, 0.0)

    straight = _neck_guide_locals(0.0, 4.0)
    assert straight[0] == (0.0, -2.0, 0.0) and straight[3] == (0.0, 2.0, 0.0)
    assert abs(straight[1][1] + 2.0 / 3.0) < 1e-9
    assert abs(straight[2][1] - 2.0 / 3.0) < 1e-9
    assert _neck_arc_error(45.0, 4.0) < 0.01
    assert _neck_arc_error(90.0, 4.0) < 0.05
    assert _neck_arc_error(-90.0, 4.0) < 0.05
    for curvature in (90.0, -45.0, 120.0):
        pts = _neck_guide_locals(curvature, 4.0)
        base = _bend_local((0.0, -2.0, 0.0), curvature, 4.0)
        top = _bend_local((0.0, 2.0, 0.0), curvature, 4.0)
        assert _length(_sub(pts[0], base)) < 1e-6
        assert _length(_sub(pts[3], top)) < 1e-6
    bowed = _neck_guide_locals(90.0, 4.0)
    assert abs(bowed[1][2] - bowed[0][2]) > 0.5
    loop = _neck_guide_locals(180.0, 4.0)
    assert all(abs(coord) < 20.0 for point in loop for coord in point)


def _check_bind():
    """An unrotated child joint skins like its parent. A hinge rotate lifts off."""
    straight = [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 3.0, 0.0)]
    assert abs(chain_parameter((0.0, 0.0, 0.0), straight)) < 1e-9
    assert abs(chain_parameter((0.0, 3.0, 0.0), straight) - 1.0) < 1e-9
    assert abs(chain_parameter((0.0, 0.5, 0.0), straight) - 0.25) < 1e-9
    assert abs(chain_parameter((5.0, 1.0, 0.0), straight) - 0.5) < 1e-9
    assert skin_weights(chain_parameter((0.0, 1.0, 0.0), straight), 3) == [(1, 1.0)]
    assert skin_weights(-0.2, 4) == [(0, 1.0)]
    assert skin_weights(1.2, 4) == [(3, 1.0)]

    # Column vectors. Joint matrix is parent * translate * hinge-rotate.
    # Bind hinge is 0 and the parent bind is identity, so the child delta
    # equals the parent delta until the hinge turns.
    point = (1.02, -0.5, 0.0)
    pivot = (1.0, 0.0, 0.0)

    def _rot_z(point, angle):
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return (
            point[0] * cosine - point[1] * sine,
            point[0] * sine + point[1] * cosine,
            point[2],
        )

    def _skin_child(point, parent_angle, hinge_angle):
        local = _rot_z(_sub(point, pivot), hinge_angle)
        return _rot_z(_add(pivot, local), parent_angle)

    parent_angle = math.radians(40.0)
    posed = _skin_child(point, parent_angle, 0.0)
    assert _length(_sub(posed, _rot_z(point, parent_angle))) < 1e-6
    lifted = _skin_child(point, 0.0, math.radians(30.0))
    assert lifted[0] > point[0] + 0.05
    assert abs(_skin_child(point, 0.0, 0.0)[0] - point[0]) < 1e-9


_check_layout()
_check_bend()
_check_bind()

#endregion
#region scene

def _tag(node, role):
    """Role lives on the transform, so the outliner can find it."""
    if not cmds.attributeQuery(ROLE, node=node, exists=True):
        cmds.addAttr(node, longName=ROLE, dataType="string")
    cmds.setAttr(node + "." + ROLE, role, type="string")


def _by_role(role):
    """Transforms whose role attr equals role."""
    found = []
    for node in cmds.ls("*." + ROLE, objectsOnly=True, long=True) or []:
        if cmds.getAttr(node + "." + ROLE) == role:
            found.append(node)
    return found


def author_root():
    # Find the authored group, if it exists. There should be only one.
    nodes = _by_role("author")
    return nodes[0] if nodes else None


def cylinder():
    nodes = _by_role("cylinder")
    return nodes[0] if nodes else None


def feathers_group():
    """Sibling of the cylinder. Every feather is parented here."""
    nodes = _by_role("feathers")
    if nodes:
        return nodes[0]
    root = author_root()
    if not root:
        return None
    group = cmds.group(empty=True, name="plume_feathers", parent=root)
    _tag(group, "feathers")
    return group


def _nonlinear(marker):
    """The nonLinear deformer on the cylinder that carries this attribute."""
    cyl = cylinder()
    shape = _mesh_shape(cyl) if cyl else None
    if not shape:
        return None
    for node in cmds.listHistory(shape) or []:
        if cmds.nodeType(node) == "nonLinear" and cmds.attributeQuery(
            marker, node=node, exists=True
        ):
            return node
    return None


def flare_deformer():
    """The nonLinear flare on the authored cylinder, if it has been created."""
    return _nonlinear("startFlareX")


def bend_deformer():
    """The nonLinear bend on the authored cylinder, if it has been created."""
    return _nonlinear("curvature")


def _deformer_handle(node):
    """Viewport handle for a nonLinear deformer. None if it has not been built."""
    if not node or not cmds.objExists(node):
        return None
    if cmds.attributeQuery("matrix", node=node, exists=True):
        for source in cmds.listConnections(
            node + ".matrix", source=True, destination=False
        ) or []:
            if cmds.nodeType(source) == "transform":
                return source
            parent = cmds.listRelatives(source, parent=True, fullPath=True) or []
            if parent:
                return parent[0]
    found = cmds.ls(node.split("|")[-1] + "Handle", type="transform") or []
    return found[0] if found else None


def _hide_deformer(node, record_undo=True):
    """Keep the handle out of the viewport. The select button still finds it.

    Slider edits record the hide with the rest of the change. Opening the
    window passes record_undo False so a scene saved with the handles showing
    does not gain an undo step just for hiding them.
    """
    handle = _deformer_handle(node)
    if not handle or not cmds.getAttr(handle + ".visibility"):
        return
    if record_undo:
        cmds.setAttr(handle + ".visibility", 0)
        return
    undo = cmds.undoInfo(query=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        cmds.setAttr(handle + ".visibility", 0)
    finally:
        if undo:
            cmds.undoInfo(stateWithoutFlush=True)


def _bend_after_flare(cyl):
    """Flare shapes the tube. Bend runs after it and curves that result."""
    flare = flare_deformer()
    bend = bend_deformer()
    if not flare or not bend:
        return
    shape = _mesh_shape(cyl)
    hist = [cmds.ls(node, long=True)[0] for node in (cmds.listHistory(shape or cyl) or [])]
    flare = cmds.ls(flare, long=True)[0]
    bend = cmds.ls(bend, long=True)[0]
    # listHistory is downstream first, so the bend should appear before the flare.
    if flare in hist and bend in hist and hist.index(bend) > hist.index(flare):
        cmds.reorderDeformers(bend, flare, cyl)


def clear_authoring():
    """Delete the authored group and deformer nodes left behind in the DG."""
    leftovers = [flare_deformer(), bend_deformer()]
    roots = _by_role("author")
    if roots:
        cmds.delete(roots)
    for node in leftovers:
        if node and cmds.objExists(node):
            cmds.delete(node)


def create_cylinder():
    """Step 1. Unlocked transform, length along local Y. Returns the transform."""
    root = cmds.group(empty=True, name="plume")
    _tag(root, "author")
    transform, _history = cmds.polyCylinder(
        name="plume_cylinder",
        radius=CYLINDER_RADIUS,
        height=CYLINDER_HEIGHT,
        subdivisionsX=CYLINDER_AROUND_DIVS,
        subdivisionsY=CYLINDER_HEIGHT_DIVS,
        subdivisionsZ=1,
        axis=(0, 1, 0),
        constructionHistory=True,
    )
    transform = cmds.parent(transform, root)[0]
    _tag(transform, "cylinder")
    feathers = cmds.group(empty=True, name="plume_feathers", parent=root)
    _tag(feathers, "feathers")
    cmds.select(transform)
    return transform


def set_flare(start_x, end_x, curve, start_z=None, end_z=None):
    """Step 2. First call creates the deformer.

    Leave start_z and end_z empty to flare X and Z together.
    """
    if start_z is None:
        start_z = start_x
    if end_z is None:
        end_z = end_x
    cyl = cylinder()
    if not cyl:
        cmds.warning("Create the cylinder first.")
        return None
    node = flare_deformer()
    if node is None:
        # The shape, not the transform. The transform also holds the other
        # deformer's handle, and nonLinear would try to deform that too.
        created = cmds.nonLinear(_mesh_shape(cyl), type="flare", name="plume_flare")
        node, handle = created[0], created[1]
        # Maya sizes the handle from the world bounding box, which is wrong
        # once the cylinder has been scaled. Parent it and refit in local
        # space: half the construction height, bounds -1 to 1, axis along Y.
        height = _cylinder_size(cyl)[1]
        cmds.parent(handle, cyl)
        cmds.setAttr(handle + ".translate", 0, 0, 0)
        cmds.setAttr(handle + ".rotate", 0, 0, 0)
        half = height * 0.5
        cmds.setAttr(handle + ".scale", half, half, half)
        cmds.setAttr(node + ".lowBound", -1)
        cmds.setAttr(node + ".highBound", 1)
        cmds.setAttr(handle + ".visibility", 0)
        _bend_after_flare(cyl)
    cmds.setAttr(node + ".startFlareX", start_x)
    cmds.setAttr(node + ".startFlareZ", start_z)
    cmds.setAttr(node + ".endFlareX", end_x)
    cmds.setAttr(node + ".endFlareZ", end_z)
    cmds.setAttr(node + ".curve", curve)
    _hide_deformer(node)
    return node


def set_bend(curvature):
    """Bend forward and back. Positive curvature bends toward the cylinder's +Z.

    The handle's rotate is locked. Curvature is the only direction.
    """
    cyl = cylinder()
    if not cyl:
        cmds.warning("Create the cylinder first.")
        return None
    node = bend_deformer()
    if node is None:
        created = cmds.nonLinear(_mesh_shape(cyl), type="bend", name="plume_bend")
        node, handle = created[0], created[1]
        # Same fit as the flare: local -1 to 1 covers the cylinder. Spun so
        # the bend, which runs toward the handle's +X, points down local +Z.
        height = _cylinder_size(cyl)[1]
        cmds.parent(handle, cyl)
        cmds.setAttr(handle + ".translate", 0, 0, 0)
        cmds.setAttr(handle + ".rotate", 0, -90, 0)
        half = height * 0.5
        cmds.setAttr(handle + ".scale", half, half, half)
        cmds.setAttr(node + ".lowBound", -1)
        cmds.setAttr(node + ".highBound", 1)
        for axis in "xyz":
            cmds.setAttr(handle + ".r" + axis, lock=True)
        cmds.setAttr(handle + ".visibility", 0)
        _bend_after_flare(cyl)
    cmds.setAttr(node + ".curvature", curvature)
    _hide_deformer(node)
    return node


def _set_curvature(node, value):
    """Set the bend without adding an undo step. Sampling turns it off and back."""
    undo = cmds.undoInfo(query=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        cmds.setAttr(node + ".curvature", value)
    finally:
        if undo:
            cmds.undoInfo(stateWithoutFlush=True)

#endregion
#region feathers

def generate_feathers(rows, columns, custom=None, variety=0.0, profile=None):
    """Step 3. Brick-laid feathers on the cylinder. Replaces the old ones.

    The flare and the bend are optional. Feathers are built from the cylinder
    as it is now. They land under plume_feathers, next to the cylinder.
    variety is 0 to 1 and leans each procedural feather across its own end.
    profile is one half-width per cross-section. None keeps the default edge.
    The viewport shows the top row first, then the rows below, slow at the
    start and quicker toward the end. Sampling keeps the bend off, so
    nothing is drawn until the bend is restored.
    """
    cyl = cylinder()
    if not cyl:
        cmds.warning("Create the cylinder first.")
        return []
    rows = int(rows)
    columns = int(columns)
    if rows < 1 or columns < 1:
        cmds.warning("Rows and columns must be at least 1.")
        return []

    source = _custom_source(custom)
    if custom and not source:
        return []
    if not _by_role("feathers") and not author_root():
        cmds.warning("Create the cylinder first.")
        return []

    base = _cylinder_base(cyl)
    curvature = base.curvature
    bend_node = bend_deformer()
    # Read the flared tube with the bend off, then apply that bend in the same
    # way Maya does. The deformer stays put for the user. Refresh stays
    # suspended so the straight tube never draws. Both curvature edits sit in
    # the chunk, so one undo restores the bend and removes the feathers.
    suspend_bend = bool(bend_node) and abs(curvature) > 1e-8
    made = []
    cmds.refresh(suspend=True)
    # stateWithoutFlush inside an open chunk closes it. Set the bend directly.
    undo = cmds.undoInfo(query=True, state=True)
    if undo:
        cmds.undoInfo(openChunk=True, chunkName="generate feathers")
    try:
        try:
            if suspend_bend:
                cmds.setAttr(bend_node + ".curvature", 0.0)
            group = feathers_group()
            old = _by_role("feather")
            if old:
                cmds.delete(old)
            shape = _mesh_shape(cyl)
            mesh_fn = _mesh_fn(shape)
            base.rings = _ring_radii(mesh_fn)

            for row in range(rows):
                for column in range(columns):
                    if source:
                        scale = _instance_custom(
                            group, source, mesh_fn, base, rows, columns, row, column,
                        )
                    else:
                        scale = _drape_scale(
                            group, base, rows, columns, row, column, variety, profile,
                        )
                    cmds.setAttr(scale + ".visibility", 0)
                    made.append(scale)
        finally:
            try:
                if suspend_bend and cmds.objExists(bend_node):
                    cmds.setAttr(bend_node + ".curvature", curvature)
            finally:
                cmds.refresh(suspend=False)
                _reveal_feathers(made, columns)
        cmds.select(cyl)
    finally:
        if undo:
            cmds.undoInfo(closeChunk=True)
    return made


def _reveal_group(count, draws=FEATHER_REVEAL_DRAWS):
    """Feathers per viewport beat. One, until the draw cap is passed."""
    count = max(int(count), 1)
    return int(math.ceil(count / float(min(count, draws))))


def _row_reveal_order(scales, columns):
    """Top row first. Each row still sweeps in column order."""
    columns = max(int(columns), 1)
    rows = [scales[i:i + columns] for i in range(0, len(scales), columns)]
    ordered = []
    for band in reversed(rows):
        ordered.extend(band)
    return ordered


def _reveal_beat(shown, count, group):
    """Gap after `shown` feathers. Slow for the first, fast for the last."""
    span = count - group
    if span <= 0:
        return 0.0
    t = (shown - group) / float(span)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    linger = (1.0 - t) ** 3
    return FEATHER_REVEAL_FAST + (FEATHER_REVEAL_SLOW - FEATHER_REVEAL_FAST) * linger


assert _reveal_group(1) == 1
assert _reveal_group(48) == 1
assert _reveal_group(49) == 2
assert _reveal_group(96) == 2
assert _row_reveal_order(list(range(6)), 3) == [3, 4, 5, 0, 1, 2]
assert _row_reveal_order(list(range(3)), 3) == [0, 1, 2]
assert _reveal_beat(1, 1, 1) == 0.0
assert _reveal_beat(1, 48, 1) > _reveal_beat(24, 48, 1) > _reveal_beat(47, 48, 1)


def _reveal_feathers(scales, columns):
    """Show the top row first, then accelerate down the plume.

    Batch Maya just turns them on. A failed refresh still leaves every feather
    visible.
    """
    pending = [scale for scale in scales if cmds.objExists(scale)]
    if not pending:
        return
    pending = _row_reveal_order(pending, columns)
    if cmds.about(batch=True):
        for scale in pending:
            cmds.setAttr(scale + ".visibility", 1)
        return
    count = len(pending)
    group = _reveal_group(count)
    index = 0
    try:
        while index < count:
            for scale in pending[index:index + group]:
                cmds.setAttr(scale + ".visibility", 1)
            index += group
            cmds.refresh(force=True)
            if index < count:
                time.sleep(_reveal_beat(index, count, group))
    finally:
        for scale in pending[index:]:
            if cmds.objExists(scale):
                cmds.setAttr(scale + ".visibility", 1)


def _mesh_shape(transform):
    if not transform or not cmds.objExists(transform):
        return None
    shapes = cmds.listRelatives(
        transform, shapes=True, fullPath=True, noIntermediate=True
    ) or []
    meshes = cmds.ls(shapes, type="mesh", long=True) or []
    return meshes[0] if meshes else None


def _cylinder_size(cyl):
    history = cmds.ls(cmds.listHistory(cyl) or [], type="polyCylinder") or []
    if not history:
        cmds.warning("Cylinder history is gone. Using the original radius and height.")
        return CYLINDER_RADIUS, CYLINDER_HEIGHT
    node = history[0]
    return cmds.getAttr(node + ".radius"), cmds.getAttr(node + ".height")


def _custom_source(custom):
    if not custom:
        return None
    if not cmds.objExists(custom):
        cmds.warning("Custom mesh '%s' was not found." % custom)
        return None
    if cmds.nodeType(custom) == "mesh":
        custom = cmds.listRelatives(custom, parent=True, fullPath=True)[0]
    cyl = cylinder()
    if custom == cyl or custom.split("|")[-1] == (cyl or "").split("|")[-1]:
        cmds.warning("The custom mesh is the cylinder. Use a separate mesh.")
        return None
    if not _mesh_shape(custom):
        cmds.warning("Custom mesh '%s' has no mesh shape." % custom)
        return None
    return custom


def _mesh_fn(shape):
    sel = om.MSelectionList()
    sel.add(shape)
    return om.MFnMesh(sel.getDagPath(0))


class CylinderBase(object):
    """The authored cylinder as something to feather.

    Feathers only call radius(), point(), hit() and spine(). The neck only
    calls spine() and neck_guide(). Another base answers the same calls.
    t is 0 at the base and 1 at the top, angle goes around the axis, and
    lift is in radius units off the surface. rings may be None when only
    the spine is needed.
    """

    def __init__(self, matrix, height, curvature=0.0, rings=None):
        self.matrix = matrix
        self.height = height
        self.curvature = curvature
        self.rings = rings

    def radius(self, t, angle):
        return _radius_at(self.rings, _sample_y(self.height, _clamp01(t)), angle)

    def point(self, t, angle, lift=0.0):
        # Past either end, keep the end radius but stay on that y. Clamping back
        # onto the rim stacks the root into a flat cap whose normal points along
        # the cylinder, and the outward test then flips some of the end row.
        radius = self.radius(t, angle) * (1.0 + lift)
        local = (radius * math.cos(angle), (t - 0.5) * self.height, radius * math.sin(angle))
        return _transform_point(
            self.matrix, _bend_local(local, self.curvature, self.height)
        )

    def hit(self, mesh_fn, t, angle):
        """World point and unit normal where this cross-section ray leaves the mesh."""
        y = _sample_y(self.height, t)
        ray = om.MFloatVector(math.cos(angle), 0.0, math.sin(angle))
        hit = mesh_fn.closestIntersection(
            om.MFloatPoint(0.0, y, 0.0),
            ray,
            om.MSpace.kObject,
            1e6,
            False,
        )
        if hit is None:
            cmds.warning("Feather ray missed the cylinder.")
            local = (ray.x, y, ray.z)
            face = 0
        else:
            local = (hit[0].x, hit[0].y, hit[0].z)
            face = hit[2]
        if abs(self.curvature) > 1e-8:
            n_obj = mesh_fn.getPolygonNormal(face, om.MSpace.kObject)
            n = _bend_dir(
                (n_obj.x, n_obj.y, n_obj.z), local[1], self.curvature, self.height
            )
            local = _bend_local(local, self.curvature, self.height)
            point = _transform_point(self.matrix, local)
            return point, _norm(_transform_vector(self.matrix, n))
        normal = mesh_fn.getPolygonNormal(face, om.MSpace.kWorld)
        point = _transform_point(self.matrix, local)
        return point, _norm((normal.x, normal.y, normal.z))

    def spine(self, t):
        """World centerline point and up-tangent at t, following the bend."""
        y = (float(t) - 0.5) * self.height
        axis = _transform_point(
            self.matrix, _bend_local((0.0, y, 0.0), self.curvature, self.height)
        )
        along = _transform_vector(
            self.matrix, _bend_dir((0.0, 1.0, 0.0), y, self.curvature, self.height)
        )
        return axis, along

    def neck_guide(self):
        """World neck curve: base, two handles, top."""
        return [
            _transform_point(self.matrix, point)
            for point in _neck_guide_locals(self.curvature, self.height)
        ]


def _cylinder_base(cyl, rings=None):
    """The cylinder as it stands now, bend included."""
    bend_node = bend_deformer()
    curvature = cmds.getAttr(bend_node + ".curvature") if bend_node else 0.0
    matrix = cmds.xform(cyl, query=True, matrix=True, worldSpace=True)
    return CylinderBase(matrix, _cylinder_size(cyl)[1], curvature, rings)


def _drape_scale(root, base, rows, columns, row, column, variety=0.0, profile=None):
    """One petal. Wide root toward the end, point toward the start, on the surface."""
    grid, tip = _feather_points(
        base, rows, columns, row, column, tip_slide(row, column, variety), profile
    )
    scale = _petal_mesh(root, "plume_feather_%d_%d" % (row, column), grid, tip)
    t_root, t_tip = scale_span(row, rows)
    mid = len(grid) // 2
    u_mid = mid / float(ALONG_DIVS + 1)
    axis, _along = base.spine(t_root + (t_tip - t_root) * u_mid)
    _tag_feather(scale, row)
    _face_outward(scale, _sub(grid[mid][ACROSS_DIVS // 2], axis))
    _store_frame(scale, base, grid[0][ACROSS_DIVS // 2], t_root, columns)
    _assign_scale_material(scale)
    return scale


def _petal_row(base, t_root, t_tip, center, columns, r_root, u, width=None):
    t = t_root + (t_tip - t_root) * u
    r_here = base.radius(t, center)
    half = half_angle(columns, u, r_root, r_here, width)
    band = []
    for j in range(ACROSS_DIVS + 1):
        v = j / float(ACROSS_DIVS)
        angle = center + (v - 0.5) * 2.0 * half
        band.append(_petal_point(base, t_root, t_tip, angle, u, v))
    return band


def _petal_point(base, t_root, t_tip, angle, u, side):
    return base.point(t_root + (t_tip - t_root) * u, angle, surface_lift(u, side))


def _feather_points(base, rows, columns, row, column, slide=0.0, profile=None):
    """World-space grid and tip for one feather.

    slide is -1 to 1. The root stays centered and the whole feather leans
    with the tip. The tip stays on the centerline radius and does not pass
    the last ring's edges. profile is one half-width per cross-section.
    """
    t_root, t_tip = scale_span(row, rows)
    center = column_angle(row, column, columns)
    r_root = base.radius(t_root, center)
    steps = ALONG_DIVS + 1
    u_last = ALONG_DIVS / float(steps)
    r_last = base.radius(t_root + (t_tip - t_root) * u_last, center)
    widths = _edge_widths(profile)
    lean = _tip_lean(
        columns, slide, r_root, r_last, None if widths is None else widths[-1]
    )
    grid = []
    for i in range(steps):
        u = i / float(steps)
        grid.append(
            _petal_row(
                base, t_root, t_tip, center + lean * u, columns, r_root, u,
                None if widths is None else widths[i],
            )
        )
    tip = _petal_point(base, t_root, t_tip, center + lean, 1.0, 0.5)
    return grid, tip


def _clamp01(t):
    if t < 0.0:
        return 0.0
    if t > 1.0:
        return 1.0
    return t


def _hinge_axes(base, origin, t, normal=None):
    """X down the spine, Y off the surface, Z the hinge. The bend is included.

    normal is the surface normal. Without one, Y is the radial from the spine.
    """
    axis, along = base.spine(t)
    if normal is None:
        normal = _norm(_sub(origin, axis))
    return orient_scale(axis, origin, normal, along)


def _instance_custom(root, source, mesh_fn, base, rows, columns, row, column):
    t_root, _t_tip = scale_span(row, rows)
    angle = column_angle(row, column, columns)
    surface, normal = base.hit(mesh_fn, t_root, angle)
    x, y, z = _hinge_axes(base, surface, t_root, normal)
    before = set(cmds.ls(long=True))
    cmds.instance(source)
    created = set(cmds.ls(long=True)) - before
    inst = [node for node in created if cmds.nodeType(node) == "transform"][0]
    root_long = cmds.ls(root, long=True)[0]
    parent = cmds.listRelatives(inst, parent=True, fullPath=True)
    if not parent or parent[0] != root_long:
        inst = cmds.parent(inst, root)[0]
    inst = cmds.rename(inst, "plume_feather_%d_%d" % (row, column))
    cmds.setAttr(inst + ".visibility", 1)
    cmds.xform(inst, matrix=_matrix(x, y, z, surface), worldSpace=True)
    _tag_feather(inst, row)
    _store_frame(inst, base, surface, t_root, columns, normal)
    return inst


def _petal_mesh(parent, name, grid, tip):
    """Quads along the petal, then a fan into the point. Root row is grid[0]."""
    n_along = len(grid)
    n_across = len(grid[0])
    points = om.MPointArray()
    for band in grid:
        for point in band:
            points.append(om.MPoint(*point))
    tip_index = n_along * n_across
    points.append(om.MPoint(*tip))
    counts = om.MIntArray()
    connects = om.MIntArray()
    for i in range(n_along - 1):
        for j in range(n_across - 1):
            a = i * n_across + j
            b = a + 1
            c = a + n_across + 1
            d = a + n_across
            counts.append(4)
            for index in (a, b, c, d):
                connects.append(index)
    last = (n_along - 1) * n_across
    for j in range(n_across - 1):
        counts.append(3)
        for index in (last + j, last + j + 1, tip_index):
            connects.append(index)
    transform = om.MFnMesh().create(points, counts, connects)
    u, v = _uv_arrays(feather_uvs(n_along, n_across))
    _write_mesh_uvs(_fn_mesh(transform), ("map1", u, v, counts, connects))
    path = om.MDagPath.getAPathTo(transform)
    scale = cmds.rename(path.fullPathName(), name)
    scale = cmds.parent(scale, parent)[0]
    return scale


def _fn_mesh(transform):
    """MFnMesh for a transform MObject or a shape path string."""
    if isinstance(transform, str):
        sel = om.MSelectionList()
        sel.add(transform)
        dag = sel.getDagPath(0)
    else:
        dag = om.MDagPath.getAPathTo(transform)
    if dag.apiType() != om.MFn.kMesh:
        dag.extendToShape()
    return om.MFnMesh(dag)


def _uv_arrays(uvs):
    return (
        om.MFloatArray([u for u, _v in uvs]),
        om.MFloatArray([v for _u, v in uvs]),
    )


def _read_mesh_uvs(fn):
    """Current UV set as (name, u, v, counts, ids), or None when the mesh has none."""
    names = fn.getUVSetNames()
    if not names:
        return None
    uv_set = names[0]
    u, v = fn.getUVs(uv_set)
    if len(u) == 0:
        return None
    counts, ids = fn.getAssignedUVs(uv_set)
    return uv_set, u, v, counts, ids


def _write_mesh_uvs(fn, saved):
    """Put a saved UV set onto fn."""
    if not saved:
        return
    uv_set, u, v, counts, ids = saved
    if uv_set not in fn.getUVSetNames():
        fn.createUVSet(uv_set)
    fn.setUVs(u, v, uv_set)
    fn.assignUVs(counts, ids, uv_set)


def _ring_radii(mesh_fn):
    """Object-space (y, rx, rz) rings.

    Separate X and Z flares make an ellipse. The fattest vertex is only
    one axis, so each height keeps both. The cylinder has vertices on +X
    and +Z, and the flare only scales those axes.
    """
    buckets = {}
    for point in mesh_fn.getPoints(om.MSpace.kObject):
        ax = abs(point.x)
        az = abs(point.z)
        if ax < 1e-3 and az < 1e-3:
            continue
        y = round(point.y, 5)
        rx, rz = buckets.get(y, (0.0, 0.0))
        buckets[y] = (ax if ax > rx else rx, az if az > rz else rz)
    return sorted((y, rx, rz) for y, (rx, rz) in buckets.items())


def _radius_at(rings, y, angle):
    """Distance from the axis to the cross-section along angle.

    A round flare has rx == rz. Split X and Z do not, and the ray at
    angle hits the ellipse, not the wider axis.
    """
    if not rings:
        rx, rz = CYLINDER_RADIUS, CYLINDER_RADIUS
    elif y <= rings[0][0]:
        rx, rz = rings[0][1], rings[0][2]
    elif y >= rings[-1][0]:
        rx, rz = rings[-1][1], rings[-1][2]
    else:
        rx, rz = rings[-1][1], rings[-1][2]
        for (y0, x0, z0), (y1, x1, z1) in zip(rings, rings[1:]):
            if y0 <= y <= y1:
                span = y1 - y0
                t = 0.0 if span < 1e-8 else (y - y0) / span
                rx = x0 + (x1 - x0) * t
                rz = z0 + (z1 - z0) * t
                break
    c = math.cos(angle)
    s = math.sin(angle)
    dx = c / rx if abs(rx) > 1e-8 else 0.0
    dz = s / rz if abs(rz) > 1e-8 else 0.0
    denom = math.hypot(dx, dz)
    if denom < 1e-8:
        return 0.0
    return 1.0 / denom


def _tag_feather(scale, row):
    _tag(scale, "feather")
    if not cmds.attributeQuery(ROW, node=scale, exists=True):
        cmds.addAttr(scale, longName=ROW, attributeType="long")
    cmds.setAttr(scale + "." + ROW, row)


def _store_frame(feather, base, origin, t, columns, normal=None):
    """Root hinge and control size, kept on the feather for the guide.

    X runs down the feather along the base's spine, Y off the base. The
    frame is in the feather's own space, so moving the feather carries it.
    Control size is about half a column wide at this root. normal, when
    passed, is the same surface normal the mesh was oriented with.
    """
    axis, _along = base.spine(t)
    offset = _sub(origin, axis)
    x, y, z = _hinge_axes(base, origin, t, normal)
    world = om.MMatrix(_matrix(x, y, z, origin))
    parent = om.MMatrix(cmds.xform(feather, query=True, matrix=True, worldSpace=True))
    if not cmds.attributeQuery(FRAME, node=feather, exists=True):
        cmds.addAttr(feather, longName=FRAME, dataType="matrix")
    cmds.setAttr(feather + "." + FRAME, *list(world * parent.inverse()), type="matrix")
    radius = _length(offset)
    if radius < 1e-4:
        radius = CYLINDER_RADIUS
    if not cmds.attributeQuery(SIZE, node=feather, exists=True):
        cmds.addAttr(feather, longName=SIZE, attributeType="double")
    cmds.setAttr(
        feather + "." + SIZE,
        max(0.05, radius * (2.0 * math.pi / float(max(columns, 1))) * 0.45),
    )


def _feather_frame(feather):
    """World root position and hinge axes from _store_frame, or None."""
    if not cmds.attributeQuery(FRAME, node=feather, exists=True):
        return None
    local = om.MMatrix(cmds.getAttr(feather + "." + FRAME))
    parent = om.MMatrix(cmds.xform(feather, query=True, matrix=True, worldSpace=True))
    m = list(local * parent)
    return (
        (m[12], m[13], m[14]),
        _norm((m[0], m[1], m[2])),
        _norm((m[4], m[5], m[6])),
        _norm((m[8], m[9], m[10])),
    )


def _face_outward(scale, outward):
    shape = _mesh_shape(scale)
    if not shape or _length(outward) < 1e-8:
        return
    sel = om.MSelectionList()
    sel.add(shape)
    fn = om.MFnMesh(sel.getDagPath(0))
    # Not face 0. The end row's root can lie across the rim, and that face
    # normal points along the cylinder. Testing it flips about half the row.
    face = (ALONG_DIVS // 2) * ACROSS_DIVS
    normal = fn.getPolygonNormal(face, om.MSpace.kWorld)
    n = _norm((normal.x, normal.y, normal.z))
    if _dot(n, _norm(outward)) < -0.2:
        cmds.polyNormal(scale, normalMode=3, constructionHistory=False)


def _assign_scale_material(scale):
    """One shared Blinn. Lambert1 is the flat default, and reads as green."""
    shader = "plume_feather_mat"
    sg = "plume_feather_sg"
    if not cmds.objExists(shader):
        shader = cmds.shadingNode("blinn", asShader=True, name=shader)
        cmds.setAttr(shader + ".color", 0.62, 0.48, 0.32, type="double3")
        cmds.setAttr(shader + ".specularColor", 0.28, 0.24, 0.18, type="double3")
        cmds.setAttr(shader + ".eccentricity", 0.35)
    if not cmds.objExists(sg):
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg)
        cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
    cmds.sets(scale, edit=True, forceElement=sg)


def _sample_y(height, t):
    """Keep the sample off the cap faces, which have no outward normal."""
    eps = height * 0.01
    y = (t - 0.5) * height
    limit = height * 0.5 - eps
    if y < -limit:
        return -limit
    if y > limit:
        return limit
    return y


def _transform_vector(matrix, vector):
    x, y, z = vector
    return (
        x * matrix[0] + y * matrix[4] + z * matrix[8],
        x * matrix[1] + y * matrix[5] + z * matrix[9],
        x * matrix[2] + y * matrix[6] + z * matrix[10],
    )


def _transform_point(matrix, point):
    x, y, z = point
    return (
        x * matrix[0] + y * matrix[4] + z * matrix[8] + matrix[12],
        x * matrix[1] + y * matrix[5] + z * matrix[9] + matrix[13],
        x * matrix[2] + y * matrix[6] + z * matrix[10] + matrix[14],
    )


def _matrix(x, y, z, pos):
    return [
        x[0], x[1], x[2], 0.0,
        y[0], y[1], y[2], 0.0,
        z[0], z[1], z[2], 0.0,
        pos[0], pos[1], pos[2], 1.0,
    ]


def _chord_gap(
    base, rows, columns, outer_row, outer_col, inner_row, inner_col,
    slide=0.0, inner_slide=0.0,
):
    """Smallest radius gap from the outer feather's chords to the inner arc.

    None when the two feathers do not overlap. The arc sits outside that
    feather's own chords, so a positive gap clears the mesh too.
    """
    grid, tip = _feather_points(base, rows, columns, outer_row, outer_col, slide)
    segments = []
    for ring in grid:
        segments.extend(zip(ring, ring[1:]))
    for left, right in zip(grid, grid[1:]):
        segments.extend(zip(left, right))
    for point in grid[-1]:
        segments.append((point, tip))
    center = column_angle(inner_row, inner_col, columns)
    worst = None
    for start, end in segments:
        for step in (0.0, 0.5, 1.0):
            point = (
                start[0] + (end[0] - start[0]) * step,
                start[1] + (end[1] - start[1]) * step,
                start[2] + (end[2] - start[2]) * step,
            )
            gap = _arc_gap(
                columns, rows, base.height, inner_row, center, point, inner_slide
            )
            if gap is None:
                continue
            if worst is None or gap < worst:
                worst = gap
    return worst


def _arc_gap(columns, rows, height, row, center, point, slide=0.0):
    """Point radius minus the feather's ideal radius, or None if it misses."""
    t_root, t_tip = scale_span(row, rows)
    u = (point[1] / height + 0.5 - t_root) / (t_tip - t_root)
    if u < -1e-5 or u > 1.0 + 1e-5:
        return None
    u = min(max(u, 0.0), 0.999999)
    full = half_angle(columns, u, 1.0, 1.0)
    if full < 1e-8:
        return None
    delta = math.atan2(point[2], point[0]) - center - _tip_lean(columns, slide) * u
    delta = (delta + math.pi) % (2.0 * math.pi) - math.pi
    if abs(delta) > full + 1e-7:
        return None
    side = min(1.0, max(0.0, 0.5 + delta / (2.0 * full)))
    return math.hypot(point[0], point[2]) - (1.0 + surface_lift(u, side))


def _check_clearance():
    """Mesh chords stay outside the neighboring feather."""
    rows = 6
    base = CylinderBase(_IDENTITY, 4.0, rings=((-4.0, 1.0, 1.0), (4.0, 1.0, 1.0)))
    pairs = (
        (1, 0, 1, 1),
        (1, 0, 0, 0),
        (1, 0, 0, 1),
        (2, 0, 1, 0),
        (2, 0, 1, 1),
    )
    leans = ((1.0, -1.0), (-1.0, 1.0), (1.0, 0.0), (-1.0, 0.0), (0.0, 0.0))
    for columns in (8, 12, 24):
        worst = None
        for slide, inner_slide in leans:
            for outer_row, outer_col, inner_row, inner_col in pairs:
                gap = _chord_gap(
                    base, rows, columns,
                    outer_row, outer_col, inner_row, inner_col,
                    slide, inner_slide,
                )
                if gap is not None and (worst is None or gap < worst):
                    worst = gap
        assert worst is not None and worst > 0.004


def _angle_span(ring):
    a0 = math.atan2(ring[0][2], ring[0][0])
    a1 = math.atan2(ring[-1][2], ring[-1][0])
    return abs((a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi)


def _check_edge():
    """A wider station opens that cross-section and leaves the others on their y."""
    rows = 6
    base = CylinderBase(_IDENTITY, 4.0, rings=((-4.0, 1.0, 1.0), (4.0, 1.0, 1.0)))
    plain, _tip = _feather_points(base, rows, 8, 1, 0)
    wide = default_edge()
    wide[2] = EDGE_WIDTH_MAX
    edited, _tip = _feather_points(base, rows, 8, 1, 0, 0.0, wide)
    for index, (left, right) in enumerate(zip(plain, edited)):
        assert abs(left[0][1] - right[0][1]) < 1e-9
        if index == 2:
            assert _angle_span(right) > _angle_span(left) + 0.01
        else:
            assert abs(_angle_span(left) - _angle_span(right)) < 1e-6


def _check_ellipse():
    """Split end flares: +Z feathers use end Z, +X feathers use end X."""
    # Start is round. The end, where the root sits, is wide in X and narrow in Z.
    base = CylinderBase(_IDENTITY, 4.0, rings=((-2.0, 1.0, 1.0), (2.0, 2.0, 0.5)))
    on_z, _tip = _feather_points(base, 1, 4, 0, 1)
    z_root = on_z[0][ACROSS_DIVS // 2]
    assert abs(z_root[0]) < 0.05
    assert 0.4 < z_root[2] < 0.7
    on_x, _tip = _feather_points(base, 1, 4, 0, 0)
    x_root = on_x[0][ACROSS_DIVS // 2]
    assert x_root[0] > 1.5
    assert abs(x_root[2]) < 0.05


def _check_spine():
    """The neck rides the spine. Its ends are the spine's ends, bend or not."""
    straight = CylinderBase(_IDENTITY, 4.0)
    axis, along = straight.spine(0.5)
    assert _length(axis) < 1e-9 and _length(_sub(along, (0.0, 1.0, 0.0))) < 1e-9
    for curvature in (0.0, 90.0, -45.0):
        base = CylinderBase(_IDENTITY, 4.0, curvature)
        guide = base.neck_guide()
        assert _length(_sub(guide[0], base.spine(0.0)[0])) < 1e-6
        assert _length(_sub(guide[3], base.spine(1.0)[0])) < 1e-6
    _axis, top = CylinderBase(_IDENTITY, 4.0, 90.0).spine(1.0)
    assert abs(top[2] - 1.0) < 1e-6
    # A bent custom feather hangs along the spine, not the cylinder's straight Y.
    bent = CylinderBase(_IDENTITY, 4.0, 90.0)
    axis, along = bent.spine(1.0)
    x, y, _z = _hinge_axes(bent, _add(axis, (1.0, 0.0, 0.0)), 1.0, (1.0, 0.0, 0.0))
    assert abs(_dot(x, along)) > 0.9
    assert y[0] > 0.9
    straight = CylinderBase(_IDENTITY, 4.0)
    axis, _along = straight.spine(0.5)
    x, y, _z = _hinge_axes(straight, _add(axis, (1.0, 0.0, 0.0)), 0.5, (1.0, 0.0, 0.0))
    assert abs(x[1] + 1.0) < 1e-6
    assert y[0] > 0.9


_IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)

_check_clearance()
_check_edge()
_check_ellipse()
_check_spine()

#endregion
#region guide

def _guide_model():
    """The Shifter guide root, when the scene has one."""
    if not cmds.objExists("guide"):
        return None
    return cmds.ls("guide", long=True)[0]


def _named_component(comp_type, comp_name):
    """Component root of this type and name under the guide, or None."""
    guide = _guide_model()
    if not guide:
        return None
    prefix = guide + "|"
    for node in cmds.ls("*.comp_type", objectsOnly=True, long=True) or []:
        if node != guide and not node.startswith(prefix):
            continue
        if cmds.getAttr(node + ".comp_type") != comp_type:
            continue
        if (cmds.getAttr(node + ".comp_name") or "") != comp_name:
            continue
        return node
    return None


def _draw_control(guide_rig, parent, name, position, joint):
    """One control_01. position is a world translation."""
    import mgear.pymaya as pm

    comp = guide_rig.getComponentGuide("control_01")
    if not comp:
        cmds.warning("Could not find the control_01 component.")
        return None
    comp.setParamDefValue("comp_name", name)
    comp.setParamDefValue("joint", bool(joint))
    parent_node = parent if hasattr(parent, "hasAttr") else pm.PyNode(parent)
    _apply_draw_parent(comp, parent_node)
    comp.draw(parent_node)
    root = comp.root.longName()
    cmds.xform(
        root,
        worldSpace=True,
        translation=(position[0], position[1], position[2]),
    )
    size = {"head": HEAD_GUIDE_SIZE, "chest": CHEST_GUIDE_SIZE}.get(name)
    if size:
        _scale_guide_icon(root, size)
    return root


def _scale_guide_icon(root, size):
    """Guide curves and the built control. Child guides stay where they are."""
    if cmds.attributeQuery("ctlSize", node=root, exists=True):
        cmds.setAttr(root + ".ctlSize", float(size))
    pivot = cmds.xform(root, query=True, worldSpace=True, rotatePivot=True)
    for shape in cmds.listRelatives(root, shapes=True, fullPath=True) or []:
        if cmds.nodeType(shape) != "nurbsCurve":
            continue
        cmds.scale(
            size,
            size,
            size,
            shape + ".cv[*]",
            pivot=(pivot[0], pivot[1], pivot[2]),
            relative=True,
        )


def _ensure_control(guide_rig, parent, name, position, joint):
    """The named control_01 under the guide, drawn when it is missing."""
    existing = _named_component("control_01", name)
    if existing:
        return existing
    return _draw_control(guide_rig, parent, name, position, joint)


def _apply_draw_parent(comp, parent):
    """Copy side, UI host, and control group the way Draw Component does."""
    node = parent
    while node:
        if node.hasAttr("ismodel"):
            return
        if node.hasAttr("comp_type"):
            parent_type = node.attr("comp_type").get()
            if parent_type in comp.connectors:
                comp.setParamDefValue("connector", parent_type)
            comp.setParamDefValue("comp_side", node.attr("comp_side").get())
            comp.setParamDefValue("ui_host", node.attr("ui_host").get())
            comp.setParamDefValue("ctlGrp", node.attr("ctlGrp").get())
            return
        node = node.getParent()


def create_guide():
    """A neck spine, then one control_01 per feather.

    The neck has one more joint than the feather rows, and never fewer
    than 3. The root is the base and the effector is the top. If the
    cylinder is bent, the neck curve follows that bend, and the built FK
    chain follows the curve instead of the straight root-to-tip line.
    Each feather control sits on that feather's root, aims down it, and
    is parented to the neck joint closest to its row. World-orientation
    align is off. The neck is parented to chest. A root control is created
    at the origin, and a chest control at the neck base, when those are
    missing. Both include a joint. Chest is parented to root. A chest
    this tool draws is 5 times the default size, and a head is 10.
    One that was already in the scene keeps its size. The head
    is parented to chest, on the tip, and is not a child of the neck.
    The head guide is the UI host, so built channels land on the head
    control. A post step then aims the neck tip at that head. Running
    this again replaces the neck and the feather guides.
    """
    cyl = cylinder()
    feathers = _by_role("feather")
    if not cyl or not feathers:
        cmds.warning("Create the cylinder and generate the feathers first.")
        return []
    frames = dict((feather, _feather_frame(feather)) for feather in feathers)
    if None in frames.values():
        cmds.warning("Some feathers have no stored root. Generate the feathers again.")
        return []
    base = _cylinder_base(cyl)

    undo = cmds.undoInfo(query=True, state=True)
    if undo:
        cmds.undoInfo(openChunk=True, chunkName="create plume guide")
    try:
        return _build_guide(base, feathers, frames)
    finally:
        if undo:
            cmds.undoInfo(closeChunk=True)


def _build_guide(base, feathers, frames):
    import mgear.pymaya as pm
    import mgear.shifter as shifter

    _ensure_shifter_path()
    shifter.clearComponentCache()

    guide_rig = shifter.guide.Rig()
    if not _guide_model():
        guide_rig.initialHierarchy()
    guide = pm.PyNode(_guide_model())
    parked = set(_clear_generated_guides())

    slots = []
    for feather in feathers:
        slot = _feather_slot(feather)
        if slot is None:
            cmds.warning("Skipped %s. Its name is not plume_feather_ROW_COL." % feather)
            continue
        slots.append((slot, feather))
    if not slots:
        return []
    slots.sort()
    row_count = 1 + max(row for (row, _col), _feather in slots)
    columns = 1 + max(col for (_row, col), _feather in slots)
    divisions = _neck_divisions(row_count)
    curve = base.neck_guide()
    root_ctl = _ensure_control(guide_rig, guide, "root", (0.0, 0.0, 0.0), True)
    if not root_ctl:
        return []
    chest = _ensure_control(guide_rig, pm.PyNode(root_ctl), "chest", curve[0], True)
    if not chest:
        return []
    head = _place_head(guide_rig, chest, parked, curve[3])
    host_guide = _head_guide_name(head)
    _point_ui_host(root_ctl, host_guide)
    _point_ui_host(chest, host_guide)
    _point_ui_host(head, host_guide)
    neck, _eff = _draw_neck(guide_rig, pm.PyNode(chest), base, divisions)
    if not neck:
        return []
    _point_ui_host(neck, host_guide)
    neck_node = pm.PyNode(neck)
    ctl = cmds.getAttr(slots[0][1] + "." + SIZE)

    made = [neck]
    for (row, col), feather in slots:
        origin, x, y, z = frames[feather]
        comp = guide_rig.getComponentGuide("control_01")
        if not comp:
            cmds.warning("Could not find the control_01 component.")
            return made
        comp.setParamDefValue("comp_name", "feather_%d_%d" % (row, col))
        comp.setParamDefValue("joint", True)
        comp.setParamDefValue("neutralRotation", False)
        comp.setParamDefValue("useIndex", True)
        comp.setParamDefValue(
            "parentJointIndex",
            _neck_parent_index(row, row_count),
        )
        _apply_draw_parent(comp, neck_node)
        comp.draw(neck_node)
        root = comp.root.longName()
        _point_ui_host(root, host_guide)
        cmds.xform(root, matrix=_matrix(x, y, z, origin), worldSpace=True)
        ref = comp.sizeRef.longName()
        cmds.setAttr(ref + ".tz", lock=False)
        cmds.setAttr(ref + ".tz", ctl)
        made.append(root)
    if head:
        made.append(head)
    _hook_neck_step()
    _hook_splay_step()
    cmds.select(neck)
    return made


def _draw_neck(guide_rig, parent, base, divisions):
    """Neck spine along the base's spine, including its bend.

    lock_ori stays off. At 1 the first and last FK controls copy the
    ik handles, which aim straight from root to tip and ignore the bend.
    """
    comp = guide_rig.getComponentGuide("spine_S_shape_01")
    if not comp:
        cmds.warning("Could not find the spine_S_shape_01 component.")
        return None, None
    comp.setParamDefValue("comp_name", "neck")
    comp.setParamDefValue("division", int(divisions))
    comp.setParamDefValue("maxstretch", 5.0)
    comp.setParamDefValue("maxsquash", 0.1)
    comp.setParamDefValue("lock_ori", 0.0)
    _apply_draw_parent(comp, parent)
    comp.draw(parent)
    root = comp.root.longName()
    nodes = (root, comp.tan0.longName(), comp.tan1.longName(), comp.eff.longName())
    for node, point in zip(nodes, base.neck_guide()):
        cmds.xform(node, worldSpace=True, translation=point)
    matrix = base.matrix
    _aim_neck_blade(comp.blade.longName(), (matrix[0], matrix[1], matrix[2]))
    return root, comp.eff.longName()


def _aim_neck_blade(blade, up):
    """Keep the neck from twisting when it runs straight up the cylinder."""
    constraints = cmds.listConnections(blade, type="aimConstraint") or []
    if not constraints:
        return
    cmds.setAttr(constraints[0] + ".worldUpType", 3)
    cmds.setAttr(
        constraints[0] + ".worldUpVector", up[0], up[1], up[2], type="double3"
    )


def _clear_generated_guides():
    """Remove the guides this tool drew last time.

    Root, chest, and head stay. One of those sitting under a guide that
    is about to be deleted is moved onto the guide root and returned.
    """
    old = []
    preserved = []
    for node in cmds.ls("*.comp_type", objectsOnly=True, long=True) or []:
        kind = cmds.getAttr(node + ".comp_type")
        name = cmds.getAttr(node + ".comp_name") or ""
        if kind == "control_01" and name in ("root", "chest", "head"):
            preserved.append(node)
            continue
        if kind == "owl_neck_scales":
            old.append(node)
        elif kind in ("spine_ik_02", "spine_S_shape_01") and name == "neck":
            old.append(node)
        elif kind == "control_01" and name.startswith("feather_"):
            old.append(node)
    guide = _guide_model()
    parked = []
    for node in preserved:
        if any(node.startswith(doomed + "|") for doomed in old):
            if not guide:
                continue
            moved = cmds.parent(node, guide, relative=True)[0]
            parked.append(cmds.ls(moved, long=True)[0])
    if old:
        cmds.delete(old)
    return parked


def add_splay():
    """Splay, parent each row to its neck FK control, and skin the meshes.

    Splay is the peak outward hinge, 0 to 90. Falloff spreads it around the
    row: 0 is the one feather under Splay Rotate, 1 is the whole row. Zero
    splay is the tight mesh. Channels live on the head control: every Splay,
    then every Splay Falloff, then every Splay Rotate, then Wind. Volume's
    default is 0. Wind breathes that pose. Wind Offset scrubs the noise.
    Safe to run again. Skins one feather mesh, with a station joint on
    every neck joint each feather crosses.
    """
    controls = _feather_controls()
    if not controls:
        cmds.warning("Build the rig first. No feather controls were found.")
        return None
    host = _splay_host(controls[0][2])
    _zero_volume(host)
    if not host:
        cmds.warning("Could not find the rig host for Splay.")
        return None
    rows = sorted({row for row, _col, _node in controls})
    columns = max(col for _row, col, _node in controls) + 1
    offsets = {}
    _ensure_host_channels(host, rows)
    for row, col, ctl in controls:
        offsets[(row, col)] = _drive_splay(ctl)
    for row in rows:
        chosen = [
            (col, offsets[(row, col)])
            for col in range(columns)
            if (row, col) in offsets
        ]
        _drive_splay_row(host, row, columns, chosen)
    _parent_feather_rows()
    _pin_feathers(host)
    cmds.select(host)
    return host


def _feather_controls():
    """(row, column, node) for each built feather control."""
    found = []
    for node in cmds.ls("feather_*_ctl", type="transform", long=True) or []:
        parts = node.split("|")[-1].split("_")
        if len(parts) < 5 or parts[0] != "feather" or parts[-1] != "ctl":
            continue
        try:
            found.append((int(parts[1]), int(parts[2]), node))
        except ValueError:
            continue
    return found


def _head_guide_name(head):
    """Short name of the head guide root. Shifter stores that as the UI host."""
    if not head:
        return ""
    return head.split("|")[-1]


def _point_ui_host(node, guide_name):
    """Send this component's host channels to the head guide."""
    if not guide_name or not node or not cmds.objExists(node):
        return
    if not cmds.attributeQuery("ui_host", node=node, exists=True):
        return
    cmds.setAttr(node + ".ui_host", guide_name, type="string")


def _splay_host(ctl):
    """Host channels live on the head control."""
    head = _solo("head_*_ctl")
    if head:
        return head
    if ctl and cmds.attributeQuery("uiHost", node=ctl, exists=True):
        host = cmds.getAttr(ctl + ".uiHost")
        if host and cmds.objExists(host):
            return cmds.ls(host, long=True)[0]
    for name in ("global_C0_ctl", "world_ctl"):
        if cmds.objExists(name):
            return cmds.ls(name, long=True)[0]
    return None


def _keyable_double(host, name, nice, default, minimum=None, maximum=None):
    """Add a keyable double. An existing one keeps its value."""
    plug = host + "." + name
    if not cmds.attributeQuery(name, node=host, exists=True):
        extra = {}
        if minimum is not None:
            extra["minValue"] = minimum
        if maximum is not None:
            extra["maxValue"] = maximum
        cmds.addAttr(
            host,
            longName=name,
            niceName=nice,
            attributeType="double",
            defaultValue=default,
            keyable=True,
            **extra
        )
        return plug
    if minimum is None:
        cmds.addAttr(plug, edit=True, hasMinValue=False)
    else:
        cmds.addAttr(plug, edit=True, hasMinValue=True, minValue=minimum)
    if maximum is None:
        cmds.addAttr(plug, edit=True, hasMaxValue=False)
    else:
        cmds.addAttr(plug, edit=True, hasMaxValue=True, maxValue=maximum)
    cmds.setAttr(plug, keyable=True)
    return plug


def _host_channel_names(rows):
    """Splay blocks, then wind. Wind stays after the splay groups."""
    return _splay_channel_names(rows) + ["wind", "windOffset"]


def _host_channel_spec(name):
    """(nice name, default, min, max) for one host channel."""
    if name == "wind":
        return "Wind", 0.0, 0.0, 1.0
    if name == "windOffset":
        return "Wind Offset", 0.0, None, None
    if name.startswith("splayFalloff"):
        row = int(name[len("splayFalloff"):])
        return "Splay Falloff %d" % row, 1.0, 0.0, 1.0
    if name.startswith("splayRotate"):
        row = int(name[len("splayRotate"):])
        return "Splay Rotate %d" % row, 0.0, None, None
    row = int(name[len("splay"):])
    return "Splay %d" % row, 0.0, 0.0, 90.0


def _drop_splay_expressions():
    nodes = cmds.ls("plumeSplayRow*", type="expression") or []
    if nodes:
        cmds.delete(nodes)


def _lift_user_attr(host, name):
    """Delete a user attr. Returns value and the plugs that were wired to it."""
    plug = host + "." + name
    cmds.setAttr(plug, lock=False)
    value = cmds.getAttr(plug)
    incoming = cmds.listConnections(
        plug, source=True, destination=False, plugs=True
    ) or []
    outgoing = cmds.listConnections(
        plug, source=False, destination=True, plugs=True
    ) or []
    for src in incoming:
        cmds.disconnectAttr(src, plug)
    for dest in outgoing:
        cmds.disconnectAttr(plug, dest)
    cmds.deleteAttr(plug)
    return value, incoming, outgoing


def _restore_user_attr(plug, saved):
    value, incoming, outgoing = saved
    wired = False
    for src in incoming:
        if cmds.objExists(src.split(".")[0]):
            cmds.connectAttr(src, plug, force=True)
            wired = True
    for dest in outgoing:
        if cmds.objExists(dest.split(".")[0]):
            cmds.connectAttr(plug, dest, force=True)
    if not wired:
        cmds.setAttr(plug, value)


def _retire_old_wind(host):
    """Drop the wind channels from before Wind and Wind Offset."""
    for name in ("windSpeed", "windFrequency", "windLag"):
        if not cmds.attributeQuery(name, node=host, exists=True):
            continue
        plug = host + "." + name
        _undrive(plug)
        dests = cmds.listConnections(
            plug, source=False, destination=True, plugs=True
        ) or []
        for dest in dests:
            cmds.disconnectAttr(plug, dest)
        cmds.deleteAttr(plug)


def _is_splay_channel(name):
    """True for the channels this tool authors on the host."""
    if name in ("wind", "windOffset"):
        return True
    for prefix in ("splayFalloff", "splayRotate", "splay"):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return True
    return False


def _ensure_host_channels(host, rows):
    """Create Splay, Falloff, Rotate, then Wind, in that order.

    An existing set in another order is rebuilt so the channel box matches.
    Channels left on the global control from the old host are moved here.
    Values and keys are put back. Defaults stay the authored defaults.
    """
    _retire_old_wind(host)
    wanted = _host_channel_names(rows)
    wanted_set = set(wanted)
    saved = {}
    for name in ("global_C0_ctl", "world_ctl"):
        if not cmds.objExists(name):
            continue
        old = cmds.ls(name, long=True)[0]
        if old == host:
            continue
        _retire_old_wind(old)
        stale = [
            attr
            for attr in (cmds.listAttr(old, userDefined=True) or [])
            if _is_splay_channel(attr)
        ]
        if not stale:
            continue
        _drop_splay_expressions()
        for attr in stale:
            if cmds.attributeQuery(attr, node=host, exists=True):
                _lift_user_attr(old, attr)
            else:
                saved[attr] = _lift_user_attr(old, attr)
    have = [
        name
        for name in (cmds.listAttr(host, userDefined=True) or [])
        if name in wanted_set
    ]
    if have != wanted:
        _drop_splay_expressions()
        for name in have:
            saved[name] = _lift_user_attr(host, name)
    for name in wanted:
        if name.startswith("splay") and name[5:].isdigit():
            stale = host.split("|")[-1] + "_%s_toDeg" % name
            if cmds.objExists(stale):
                cmds.delete(stale)
        if (
            name not in saved
            and cmds.attributeQuery(name, node=host, exists=True)
            and cmds.attributeQuery(name, node=host, attributeType=True) != "double"
        ):
            saved[name] = _lift_user_attr(host, name)
        nice, default, minimum, maximum = _host_channel_spec(name)
        plug = _keyable_double(host, name, nice, default, minimum, maximum)
        if name in saved:
            _restore_user_attr(plug, saved[name])


def _is_volume_channel(name, nice):
    """The neck's Volume channel. The long name uses the component type.

    spine_S_shape_01 always prefixes that channel spine_volume. Renaming
    the guide to neck does not change it. The channel box label is Volume.
    """
    if isinstance(nice, (list, tuple)):
        nice = nice[0] if nice else ""
    return nice == "Volume" and (name == "volume" or name.endswith("_volume"))


def _check_volume_channel():
    assert _is_volume_channel("spine_volume", "Volume")
    assert _is_volume_channel("neck_volume", "Volume")
    assert not _is_volume_channel("spine_position", "Position")
    assert not _is_volume_channel("spine_maxstretch", "Max Stretch")


_check_volume_channel()


def _zero_volume(host):
    """Neck Volume is built at 1. The plume default is 0.

    A keyed or connected value is left alone. The reset value still becomes 0.
    """
    nodes = []
    if host and cmds.objExists(host):
        nodes.append(host)
    for name in ("global_C0_ctl", "world_ctl"):
        if not cmds.objExists(name):
            continue
        found = cmds.ls(name, long=True)[0]
        if found not in nodes:
            nodes.append(found)
    for node in nodes:
        for name in cmds.listAttr(node, userDefined=True) or []:
            nice = cmds.attributeQuery(name, node=node, niceName=True)
            if not _is_volume_channel(name, nice):
                continue
            plug = node + "." + name
            cmds.addAttr(plug, edit=True, defaultValue=0)
            if cmds.listConnections(plug, source=True, destination=False):
                continue
            if cmds.keyframe(plug, query=True, keyframeCount=True):
                continue
            if abs(cmds.getAttr(plug) - 1.0) < 1e-6:
                cmds.setAttr(plug, 0)


def _drive_splay(ctl):
    """Parent an offset under the control. Its hinge is driven per row."""
    parent = cmds.listRelatives(ctl, parent=True, fullPath=True)[0]
    if parent.split("|")[-1].endswith("_splay"):
        offset = parent
    else:
        offset = cmds.createNode(
            "transform",
            name=ctl.split("|")[-1].replace("_ctl", "_splay"),
            parent=parent,
        )
        cmds.xform(
            offset,
            worldSpace=True,
            matrix=cmds.xform(ctl, query=True, matrix=True, worldSpace=True),
        )
        ctl = cmds.parent(ctl, offset)[0]
        for channel in ("tx", "ty", "tz", "rx", "ry", "sx", "sy", "sz", "v"):
            cmds.setAttr(offset + "." + channel, lock=True)
    return cmds.ls(offset, long=True)[0]


def _undrive(plug):
    """Drop whatever is writing this plug, including a leftover conversion."""
    if not cmds.objExists(plug):
        return
    sources = cmds.listConnections(
        plug, source=True, destination=False, plugs=True
    ) or []
    stale = []
    for src in sources:
        cmds.disconnectAttr(src, plug)
        node = src.split(".")[0]
        if cmds.nodeType(node) != "unitConversion":
            continue
        if cmds.listConnections(node, source=False, destination=True):
            continue
        stale.append(node)
    if stale:
        cmds.delete(stale)


def _drive_splay_row(host, row, columns, offsets):
    """One expression writes each feather's hinge from this row's channels.

    offsets is (column, node). Column count is the full ring, so a missing
    feather does not change the step of the ones that remain.
    """
    name = "plumeSplayRow%d" % row
    if cmds.objExists(name):
        cmds.delete(name)
    feathers = []
    for col, node in offsets:
        _undrive(node + ".rotateZ")
        feathers.append(
            (
                math.degrees(column_angle(row, col, columns)),
                node.split("|")[-1],
            )
        )
    if not feathers:
        return
    cmds.expression(
        name=name,
        string=_splay_expression(
            host.split("|")[-1], row, feathers, _row_twist(row, offsets)
        ),
        alwaysEvaluate=False,
    )


def _row_twist(row, offsets):
    """(head rotateY plug, share) for this row, or None.

    The neck gives its joint index / (count - 1) of the head's ry, the same
    share _twist_expression assumes. ponytail: ry alone, so a pitched head
    is off by the extra twist the bend adds. Upgrade: read the measured twist.
    """
    head = _solo("head_*_ctl")
    necks = _neck_division_joints()
    if not head or len(necks) < 2:
        return None
    long_necks = [cmds.ls(neck, long=True)[0] for neck in necks]
    for col, _node in offsets:
        for joint in cmds.ls("feather_%d_%d_*_jnt" % (row, col), long=True) or []:
            if _feather_joint_slot(joint) != (row, col):
                continue
            parent = cmds.listRelatives(joint, parent=True, fullPath=True) or []
            if parent and cmds.ls(parent[0], long=True)[0] in long_necks:
                index = long_necks.index(cmds.ls(parent[0], long=True)[0])
                return head.split("|")[-1] + ".rotateY", index / float(len(necks) - 1)
    return None


def _splay_offset_plug(ctl):
    """Weighted hinge on the offset above this control, or None."""
    if not ctl or not cmds.objExists(ctl):
        return None
    parents = cmds.listRelatives(ctl, parent=True, fullPath=True) or []
    if not parents or not parents[0].split("|")[-1].endswith("_splay"):
        return None
    return parents[0] + ".rotateZ"


def _parent_feather_rows():
    """Parent each row's controls under the FK control for its neck joint.

    parentJointIndex already parents the feather joint. The control sits
    under ik_cns, which the build leaves on the neck root, so that is the
    node that has to move. Every feather in the row shares that joint.
    """
    joints = {}
    for node in cmds.ls("feather_*_jnt", type="joint", long=True) or []:
        slot = _feather_joint_slot(node)
        if slot and slot not in joints:
            joints[slot] = node
    rows = {}
    for row, col, ctl in _feather_controls():
        rows.setdefault(row, []).append((col, ctl))
    for row, items in rows.items():
        fk = None
        for col, _ctl in items:
            joint = joints.get((row, col))
            if not joint:
                continue
            fk = _fk_for_feather_joint(joint)
            if fk:
                break
        if not fk:
            cmds.warning("No neck FK control for feather row %d." % row)
            continue
        for _col, ctl in items:
            cns = _ik_cns_of(ctl)
            if not cns:
                cmds.warning("No ik_cns above %s." % ctl.split("|")[-1])
                continue
            _reparent(cns, fk)


def _fk_for_feather_joint(joint):
    """FK control driving the neck joint this feather joint hangs from.

    The spine drives each joint from a scl_ref under that FK control.
    """
    parents = cmds.listRelatives(joint, parent=True, fullPath=True) or []
    if not parents:
        return None
    short = parents[0].split("|")[-1]
    if not short.endswith("_jnt"):
        return None
    refs = cmds.ls(short[:-4] + "_scl_ref", long=True) or []
    if not refs:
        return None
    node = refs[0]
    while node:
        name = node.split("|")[-1]
        if name.endswith("_ctl") and "_fk" in name:
            return node
        up = cmds.listRelatives(node, parent=True, fullPath=True) or []
        node = up[0] if up else None
    return None


def _ik_cns_of(ctl):
    """The buffer above this control. Splay, when present, sits in between."""
    node = ctl
    while node:
        if node.split("|")[-1].endswith("_ik_cns"):
            return node
        up = cmds.listRelatives(node, parent=True, fullPath=True) or []
        node = up[0] if up else None
    return None


def _reparent(child, parent):
    """Parent child under parent without moving it. Skip when already there.

    The buffer channels are locked after the build. Parenting writes them,
    so unlock for the call and lock them again. The long path changes in
    the process, so the lock uses the name parent returns.
    """
    parent = cmds.ls(parent, long=True)[0]
    channels = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
    current = cmds.listRelatives(child, parent=True, fullPath=True) or []
    if current and current[0] == parent:
        for channel in channels:
            cmds.setAttr(child + "." + channel, lock=True)
        return
    locked = []
    for channel in channels:
        plug = child + "." + channel
        if cmds.getAttr(plug, lock=True):
            locked.append(channel)
            cmds.setAttr(plug, lock=False)
    moved = child
    try:
        moved = cmds.parent(child, parent)[0]
    finally:
        for channel in locked:
            cmds.setAttr(moved + "." + channel, lock=True)


def _pin_feathers(host=None):
    """Skin the feathers as one mesh. Safe to run again.

    Each feather is weighted to station joints under its feather joint.
    Those joints are labeled, the meshes are combined in that same vertex
    order, and the weights are written onto the one mesh. It is parented
    under plume_rig_drivers. A driver beside the skeleton follows the neck,
    and mGear's matrix constraint writes that onto the station.
    """
    _clear_rig_geo()
    necks = _neck_division_joints()
    if len(necks) < 2:
        cmds.warning("No neck joints to skin. Feathers were not bound.")
        return
    joints = {}
    for node in cmds.ls("feather_*_jnt", type="joint", long=True) or []:
        slot = _feather_joint_slot(node)
        if slot and slot not in joints:
            joints[slot] = node
    controls = {}
    for row, col, ctl in _feather_controls():
        controls[(row, col)] = ctl
    feathers = _by_role("feather")
    if not joints or not feathers:
        cmds.warning("No feather joints found. Feathers were not bound.")
        return
    positions = [_world_translation(joint) for joint in necks]
    saved = _zero_splay(host)
    twist = {"reads": {}, "fixes": {}, "count": len(necks)}
    try:
        drivers = _driver_group()
        pieces = []
        for feather in feathers:
            slot = _feather_slot(feather)
            joint = joints.get(slot) if slot else None
            if not joint:
                cmds.warning("No joint for %s." % feather.split("|")[-1])
                continue
            bound = _bind_feather(
                feather,
                joint,
                necks,
                positions,
                drivers,
                controls.get(slot),
                twist,
            )
            if bound:
                pieces.append((slot, bound))
        pieces.sort(key=lambda item: item[0])
        if pieces:
            _skin_combined(
                [item[1][0] for item in pieces],
                [item[1][1:] for item in pieces],
                drivers,
            )
        else:
            cmds.warning("No feathers were bound.")
        _twist_expression(twist)
        author = author_root()
        if author:
            cmds.setAttr(author + ".visibility", 0)
    finally:
        _restore_splay(saved)


def _clear_rig_geo():
    """Drop the previous bind so the feather setup can run again."""
    for name in ("plume_rig_geo", "plume_cylinder_rig", "plume_feathers_rig", "plume_rig_drivers"):
        if cmds.objExists(name):
            cmds.delete(name)
    old = (cmds.ls("plumeStation_*") or []) + (cmds.ls("plumeTwist*") or [])
    if old:
        cmds.delete(old)
    for feather in _by_role("feather"):
        cons = cmds.listRelatives(
            feather, children=True, type="parentConstraint", fullPath=True
        ) or []
        if cons:
            cmds.delete(cons)
    author = author_root()
    if author and cmds.objExists(author):
        cmds.setAttr(author + ".visibility", 1)


def _neck_division_joints():
    """Neck division joints, base to tip. The hip joint is left out."""
    found = []
    for node in cmds.ls("neck_*_jnt", type="joint", long=True) or []:
        short = node.split("|")[-1]
        parts = short.split("_")
        if len(parts) < 4 or not parts[-2].isdigit():
            continue
        if not cmds.objExists(short[:-4] + "_scl_ref"):
            continue
        found.append((int(parts[-2]), node))
    found.sort()
    return [node for _index, node in found]


def _world_translation(node):
    pos = cmds.xform(node, query=True, translation=True, worldSpace=True)
    return (pos[0], pos[1], pos[2])


def _world_points(mesh):
    raw = cmds.xform(mesh + ".vtx[*]", query=True, translation=True, worldSpace=True)
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]


def _rig_model():
    """Built rig root. |rig when the rig keeps its default name."""
    for model in cmds.ls("*.is_rig", objectsOnly=True, long=True) or []:
        if cmds.getAttr(model + ".is_rig"):
            return model
    found = cmds.ls("|rig", long=True)
    return found[0] if found else None


def _driver_group():
    """Hinge transforms and the skinned feather mesh. Sibling of setup.

    The group turns inheritsTransform off so a moved rig does not double
    the skin. The hinge transforms stay in this group, off the skeleton.
    """
    name = "plume_rig_drivers"
    if cmds.objExists(name):
        return cmds.ls(name, long=True)[0]
    parent = _rig_model()
    if parent:
        node = cmds.group(empty=True, name=name, parent=parent)
    else:
        cmds.warning("No rig. plume_rig_drivers stays at the world.")
        node = cmds.group(empty=True, name=name)
    cmds.setAttr(node + ".inheritsTransform", False)
    return cmds.ls(node, long=True)[0]


def station_point(index, parent_index, positions, axis):
    """Point on the feather where neck joint index has weight 1.

    axis runs from the feather root to the tip. Weight is 1 at
    index / (count - 1). The root station stays on the root. A joint
    past either end stays on that end, so the tip station sits on the tip.
    """
    if not axis:
        return (0.0, 0.0, 0.0)
    if parent_index is None or index == parent_index:
        return axis[0]
    count = len(positions)
    if count < 2:
        return axis[0]
    return _point_at_parameter(axis, positions, index / float(count - 1))


def _point_at_parameter(axis, positions, target):
    """Point on axis whose chain parameter is target. Ends clamp.

    ponytail: the first segment that brackets target wins. A centerline
    that folds back along the neck would need the nearest sample instead.
    """
    if len(axis) == 1 or len(positions) < 2:
        return axis[0]
    keyed = [(chain_parameter(point, positions), point) for point in axis]
    for (t0, p0), (t1, p1) in zip(keyed, keyed[1:]):
        if (t0 - target) * (t1 - target) > 0.0:
            continue
        span = t1 - t0
        u = 0.0 if abs(span) < 1e-8 else (target - t0) / span
        return (
            p0[0] + (p1[0] - p0[0]) * u,
            p0[1] + (p1[1] - p0[1]) * u,
            p0[2] + (p1[2] - p0[2]) * u,
        )
    end = min(keyed, key=lambda item: abs(item[0] - target))
    return end[1]


def _local_translate(matrix, point):
    """Translate in matrix's local space that lands a child on point."""
    origin = (matrix[12], matrix[13], matrix[14])
    delta = _sub(point, origin)
    x = (matrix[0], matrix[1], matrix[2])
    y = (matrix[4], matrix[5], matrix[6])
    z = (matrix[8], matrix[9], matrix[10])
    det = _dot(x, _cross(y, z))
    if abs(det) < 1e-12:
        return (0.0, 0.0, 0.0)
    return (
        _dot(delta, _cross(y, z)) / det,
        _dot(x, _cross(delta, z)) / det,
        _dot(x, _cross(y, delta)) / det,
    )


def _station_offset(index, parent_index, positions, axis, matrix):
    """Local translate from the feather root out to this station. Root is 0."""
    if parent_index is None or index == parent_index:
        return (0.0, 0.0, 0.0)
    return _local_translate(
        matrix, station_point(index, parent_index, positions, axis)
    )


def _feather_axis(points, matrix):
    """Centerline from the feather joint to the tip.

    A generated petal is rings of ACROSS_DIVS + 1, then one tip. The axis
    takes the center of each ring. Anything else uses the point furthest
    down the joint's X, which is the tip on this hinge.
    """
    root = (matrix[12], matrix[13], matrix[14])
    n_across = ACROSS_DIVS + 1
    n_along = ALONG_DIVS + 1
    if len(points) == n_along * n_across + 1:
        line = [root]
        mid = n_across // 2
        for i in range(n_along):
            point = points[i * n_across + mid]
            if _length(_sub(point, line[-1])) > 1e-5:
                line.append(point)
        tip = points[-1]
        if _length(_sub(tip, line[-1])) > 1e-5:
            line.append(tip)
        return line
    direction = (matrix[0], matrix[1], matrix[2])
    far = None
    far_d = None
    for point in points:
        dist = _dot(_sub(point, root), direction)
        if far_d is None or dist > far_d:
            far = point
            far_d = dist
    if far is None or _length(_sub(far, root)) < 1e-5:
        return [root]
    return [root, far]


def _check_station_point():
    """Two row gaps: root stays, the next joint is halfway, the far one is the tip."""
    positions = [(0.0, float(i), 0.0) for i in range(5)]
    root = (1.0, 4.0, 0.0)
    mid = (1.4, 3.0, 0.2)
    tip = (1.2, 2.0, 0.0)
    axis = [root, mid, tip]
    assert station_point(4, 4, positions, axis) == root
    assert _length(_sub(station_point(3, 4, positions, axis), mid)) < 1e-6
    assert _length(_sub(station_point(2, 4, positions, axis), tip)) < 1e-6
    assert _length(_sub(station_point(0, 4, positions, axis), tip)) < 1e-6
    halfway = station_point(3, 4, positions, [root, tip])
    assert abs(halfway[1] - 3.0) < 1e-6 and abs(halfway[0] - 1.1) < 1e-6
    scaled = [
        2.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        5.0, 6.0, 7.0, 1.0,
    ]
    local = _local_translate(scaled, (7.0, 6.0, 7.0))
    assert abs(local[0] - 1.0) < 1e-6 and abs(local[1]) < 1e-6 and abs(local[2]) < 1e-6
    n_across = ACROSS_DIVS + 1
    n_along = ALONG_DIVS + 1
    points = []
    for i in range(n_along):
        for j in range(n_across):
            points.append((float(j), float(i), 0.0))
    points.append((float(n_across // 2), float(n_along), 0.0))
    ident = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        float(n_across // 2), 0.0, 0.0, 1.0,
    ]
    line = _feather_axis(points, ident)
    assert line[0] == (float(n_across // 2), 0.0, 0.0)
    assert line[-1] == points[-1]
    assert all(abs(point[0] - n_across // 2) < 1e-6 for point in line)
    assert _station_offset(4, 4, positions, axis, ident) == (0.0, 0.0, 0.0)


_check_station_point()


def _drive_joint(driver, joint):
    """Write the driver's world pose onto the joint, like an mGear control.

    The rest rotation goes into jointOrient, so the rotate channels stay 0
    until splay or the feather control moves.
    """
    import mgear.pymaya as pm
    from mgear.core import applyop
    from mgear.pymaya import datatypes

    driven = pm.PyNode(joint)
    cns = applyop.gear_matrix_cns(pm.PyNode(driver), driven, connect_srt="rt")
    rest = datatypes.TransformationMatrix(cns.drivenRestMatrix.get())
    rotation = datatypes.degrees(rest.getRotation())
    driven.jointOrient.set(rotation[0], rotation[1], rotation[2])
    cmds.rename(cns.name(), joint.split("|")[-1].replace("_jnt", "_cns"))


def splay_blend(degrees):
    """0 when the feather is shut, 1 at 90 degrees. Past either end stays put."""
    if degrees <= 0.0:
        return 0.0
    if degrees >= 90.0:
        return 1.0
    return degrees / 90.0


def _check_splay_blend():
    assert splay_blend(0.0) == 0.0
    assert abs(splay_blend(45.0) - 0.5) < 1e-9
    assert splay_blend(90.0) == 1.0
    assert splay_blend(-10.0) == 0.0
    assert splay_blend(120.0) == 1.0


_check_splay_blend()


def _make_align(name, neck, matrix, rotate_order):
    """Feather-root frame parent-constrained to this neck joint."""
    align = cmds.createNode("transform", name=name + "_align", parent=_driver_group())
    cmds.setAttr(align + ".rotateOrder", rotate_order)
    cmds.xform(align, worldSpace=True, matrix=matrix)
    cmds.parentConstraint(neck, align, maintainOffset=True)
    return align


def _hang_splay(align, rotate_order, splay=None, ctl=None):
    """Splay, then the feather control, both about this hinge."""
    short = align.split("|")[-1]
    pose = cmds.createNode("transform", name=short.replace("_align", "_pose"), parent=align)
    cmds.setAttr(pose + ".rotateOrder", rotate_order)
    if splay:
        cmds.connectAttr(splay, pose + ".rotateZ", force=True)
    grip = cmds.createNode("transform", name=short.replace("_align", "_grip"), parent=pose)
    cmds.setAttr(grip + ".rotateOrder", rotate_order)
    if ctl:
        for axis in ("X", "Y", "Z"):
            cmds.connectAttr(
                ctl + ".rotate" + axis, grip + ".rotate" + axis, force=True
            )
    return grip


def _splay_weight(splay, name):
    """0 when splay is shut, 1 at 90 degrees. Wind past that stays at the end.

    The rotate plug arrives as degrees through Maya's unit conversion.
    """
    remap = cmds.createNode("remapValue", name=name + "_remap")
    cmds.connectAttr(splay, remap + ".inputValue")
    cmds.setAttr(remap + ".inputMin", 0.0)
    cmds.setAttr(remap + ".inputMax", 90.0)
    cmds.setAttr(remap + ".outputMin", 0.0)
    cmds.setAttr(remap + ".outputMax", 1.0)
    clamp = cmds.createNode("clamp", name=name + "_clamp")
    cmds.setAttr(clamp + ".minR", 0.0)
    cmds.setAttr(clamp + ".maxR", 1.0)
    cmds.connectAttr(remap + ".outValue", clamp + ".inputR")
    return clamp + ".outputR"


def _put_place(parent, name, offset, rotate_order):
    """Fixed translate out to where this station's weight is 1."""
    place = cmds.createNode("transform", name=name + "_place", parent=parent)
    cmds.setAttr(place + ".rotateOrder", rotate_order)
    cmds.setAttr(
        place + ".translate", offset[0], offset[1], offset[2], type="double3"
    )
    return place


def _skin_joint(name, driver, feather_joint, rotate_order):
    """One skinned joint. Rest is whatever the driver is at this moment."""
    joint = cmds.createNode("joint", name=name + "_jnt", parent=feather_joint)
    cmds.setAttr(joint + ".rotateOrder", rotate_order)
    cmds.setAttr(joint + ".segmentScaleCompensate", 0)
    cmds.setAttr(joint + ".radius", 0.15)
    cmds.getAttr(driver + ".worldMatrix[0]")
    _drive_joint(driver, joint)
    joint = cmds.ls(joint, long=True)[0]
    _label_joint(joint)
    return joint


def _blend_places(name, hug, free, weight):
    """World blend of the neck-hugging station and the rigid parented one."""
    blend = cmds.createNode("blendMatrix", name=name + "_blend")
    cmds.connectAttr(hug + ".worldMatrix[0]", blend + ".inputMatrix")
    cmds.connectAttr(free + ".worldMatrix[0]", blend + ".target[0].targetMatrix")
    cmds.connectAttr(weight, blend + ".target[0].weight")
    mid = cmds.createNode("transform", name=name + "_mid", parent=_driver_group())
    cmds.setAttr(mid + ".inheritsTransform", 0)
    cmds.setAttr(mid + ".rotateOrder", 0)
    dec = cmds.createNode("decomposeMatrix", name=name + "_dm")
    cmds.connectAttr(blend + ".outputMatrix", dec + ".inputMatrix")
    cmds.connectAttr(dec + ".outputTranslate", mid + ".translate")
    cmds.connectAttr(dec + ".outputRotate", mid + ".rotate")
    return mid


def _hang_station(name, grip, feather_joint, rotate_order, offset):
    """Joint drawn at the fixed offset down this feather, driven by grip."""
    place = _put_place(grip, name, offset, rotate_order)
    return _skin_joint(name, place, feather_joint, rotate_order)


def _make_station(
    name, neck, feather_joint, matrix, rotate_order,
    splay=None, ctl=None, offset=(0.0, 0.0, 0.0),
):
    """One station with its own splay, when the feather has no neck parent."""
    align = _make_align(name, neck, matrix, rotate_order)
    grip = _hang_splay(align, rotate_order, splay, ctl)
    return _hang_station(name, grip, feather_joint, rotate_order, offset)



def twist_degrees(quat, axis):
    """Twist of a rotation about axis, -180 to 180. quat is (x, y, z, w).

    The swing is what is left over, so it carries none. Splitting either
    way round gives the same twist. _twist_expression repeats this in MEL.
    """
    x, y, z, w = quat
    s = x * axis[0] + y * axis[1] + z * axis[2]
    if w < 0.0:
        w, s = -w, -s
    return math.degrees(2.0 * math.atan2(s, w))


def _quat(axis, degrees):
    half = math.radians(degrees) * 0.5
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _check_twist():
    """Twist reads back whatever swing sits beside it, in either order."""
    axis = _norm((0.3, 1.0, 0.2))
    perp = _norm(_cross(axis, (1.0, 0.0, 0.0)))
    for degrees in (70.0, -130.0, 0.0):
        twist = _quat(axis, degrees)
        swing = _quat(perp, 40.0)
        for q in (_quat_mul(swing, twist), _quat_mul(twist, swing)):
            assert abs(twist_degrees(q, axis) - degrees) < 1e-6
            flipped = (-q[0], -q[1], -q[2], -q[3])
            assert abs(twist_degrees(flipped, axis) - degrees) < 1e-6


_check_twist()


def _twist_base(twist, necks):
    """(inverse node, bind rotation) of the joint above the neck, or None. Made once."""
    if "base" not in twist:
        parent = cmds.listRelatives(necks[0], parent=True, fullPath=True)
        twist["base"] = None
        if parent:
            m = cmds.xform(parent[0], query=True, matrix=True, worldSpace=True)
            rows = [_norm(m[0:3]), _norm(m[4:7]), _norm(m[8:11])]
            bind = [v for row in rows for v in (row[0], row[1], row[2], 0.0)] + [0, 0, 0, 1.0]
            inverse = cmds.createNode("inverseMatrix", name="plumeTwistBase_inv")
            cmds.connectAttr(parent[0] + ".worldMatrix[0]", inverse + ".inputMatrix")
            twist["base"] = (inverse, bind)
    return twist["base"]


def _twist_reader(twist, necks, positions, index):
    """(decompose node, bone axis, orient node) for one neck joint, made once.

    The decompose node holds the joint's rotation since the pin, relative
    to the joint above the neck, in its own bind-local axes. The bone axis is the direction to the next joint,
    taken into those axes, so it is the same line whatever the joint's own
    orientation. It is also the line _align_neck_to_head twists this joint
    about. The orient node rides the joint with its Y on that line.
    """
    if index in twist["reads"]:
        return twist["reads"][index]
    neck = necks[index]
    bone = _neck_bone(positions, index)
    m = cmds.xform(neck, query=True, matrix=True, worldSpace=True)
    rows = [_norm(m[0:3]), _norm(m[4:7]), _norm(m[8:11])]
    axis = tuple(_dot(bone, row) for row in rows)
    # Bind rotation inverse. Its transpose, so scale in the joint is ignored.
    bind_inv = [
        rows[0][0], rows[1][0], rows[2][0], 0.0,
        rows[0][1], rows[1][1], rows[2][1], 0.0,
        rows[0][2], rows[1][2], rows[2][2], 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]
    name = "plumeTwist_%d" % index
    mult = cmds.createNode("multMatrix", name=name + "_mm")
    cmds.connectAttr(neck + ".worldMatrix[0]", mult + ".matrixIn[0]")
    base = _twist_base(twist, necks)
    if base:
        # Rotation relative to the neck's base, so the whole character
        # moving or turning reads as no twist at all.
        cmds.connectAttr(base[0] + ".outputMatrix", mult + ".matrixIn[1]")
        cmds.setAttr(mult + ".matrixIn[2]", *base[1], type="matrix")
        cmds.setAttr(mult + ".matrixIn[3]", *bind_inv, type="matrix")
    else:
        cmds.setAttr(mult + ".matrixIn[1]", *bind_inv, type="matrix")
    decompose = cmds.createNode("decomposeMatrix", name=name + "_dm")
    cmds.connectAttr(mult + ".matrixSum", decompose + ".inputMatrix")
    ref = (0.0, 0.0, 1.0) if abs(bone[2]) < 0.9 else (1.0, 0.0, 0.0)
    x = _norm(_cross(bone, ref))
    orient = cmds.createNode(
        "transform", name=name + "_orient", parent=_driver_group()
    )
    cmds.xform(
        orient,
        worldSpace=True,
        matrix=_matrix(x, bone, _cross(x, bone), positions[index]),
    )
    cmds.parentConstraint(neck, orient, maintainOffset=True)
    twist["reads"][index] = (decompose, axis, orient)
    return twist["reads"][index]


def _twist_fix(twist, necks, positions, row_index, index):
    """Transform riding neck joint index, turned about the bone to match row_index.

    Its Y is the bone. The expression writes the row joint's twist minus
    this joint's own, so a station constrained to it keeps this joint's
    bend and takes the row joint's twist. One per pair, shared by the row.
    Each station turns about its own joint's bone, so the feather stays
    on the neck's surface as the neck curves. A single shared axis would
    keep the feather rigid, but its rows then cut through each other.
    """
    key = (row_index, index)
    if key not in twist["fixes"]:
        _twist_reader(twist, necks, positions, row_index)
        orient = _twist_reader(twist, necks, positions, index)[2]
        fix = cmds.createNode(
            "transform", name="plumeTwistFix_%d_%d" % key, parent=orient
        )
        twist["fixes"][key] = cmds.ls(fix, long=True)[0]
    return twist["fixes"][key]


def _twist_expression(twist):
    """One expression: each twist fix turns by TWIST_RIGIDITY of (row twist minus own twist)."""
    if not twist["fixes"]:
        return
    head = _solo("head_*_ctl")
    lines = ["float $w, $s;", "float $r = %s;" % (head + ".rotateY" if head else "0")]
    for index, (decompose, axis, _orient) in sorted(twist["reads"].items()):
        lines.append(
            "$w = %s.outputQuatW; $s = %.9g * %s.outputQuatX + %.9g * %s.outputQuatY"
            " + %.9g * %s.outputQuatZ;"
            % (decompose, axis[0], decompose, axis[1], decompose, axis[2], decompose)
        )
        lines.append("if ($w < 0.0) { $w = -$w; $s = -$s; }")
        lines.append("float $t%d = rad_to_deg(2.0 * atan2($s, $w));" % index)
        if head:
            # The read is only good to +-180. Pick the turn nearest the share of the
            # head ry this joint was given, so rows do not flip as ry goes past 180.
            lines.append(
                "$t%d += 360.0 * floor(($r * %.9g - $t%d) / 360.0 + 0.5);"
                % (index, index / float(max(twist["count"] - 1, 1)), index)
            )
    for (row_index, index), fix in sorted(twist["fixes"].items()):
        lines.append(
            "%s.rotateY = %g * ($t%d - $t%d);"
            % (fix.split("|")[-1], TWIST_RIGIDITY, row_index, index)
        )
    cmds.expression(
        name="plumeTwistExpr",
        string="\n".join(lines),
        alwaysEvaluate=False,
    )


def _splay_peaks(names):
    """Peak splay channels. Falloff and rotate are left as they are."""
    peaks = []
    for name in names:
        if name.startswith("splay") and name[len("splay"):].isdigit():
            peaks.append(name)
    return peaks


assert _splay_peaks(
    ["splay0", "splayFalloff0", "splay2", "wind", "splayRotate1"]
) == ["splay0", "splay2"]
assert _splay_peaks(["splay10", "splay"]) == ["splay10"]


def _zero_splay(host):
    """Splay 0 is the bind pose. The caller puts the values back.

    Every peak is cleared, including when a row number is missing. A walk
    from splay0 would stop at the gap and bind the posed rows above it.
    """
    saved = []
    if not host or not cmds.objExists(host):
        return saved
    for name in _splay_peaks(cmds.listAttr(host, userDefined=True) or []):
        plug = host + "." + name
        saved.append((plug, cmds.getAttr(plug)))
        cmds.setAttr(plug, 0)
    # The hinge is an expression on the offset. Read it so the bind sees splay 0.
    for node in cmds.ls("feather_*_splay", type="transform") or []:
        cmds.getAttr(node + ".rotateZ")
    return saved


def _restore_splay(saved):
    for plug, value in saved:
        if cmds.objExists(plug.split(".")[0]):
            cmds.setAttr(plug, value)


def _duplicate_mesh(source, parent, name):
    """A real mesh in parent, with the flare and bend baked in."""
    dup = cmds.duplicate(source, name=name, upstreamNodes=False, returnRootsOnly=True)[0]
    kids = cmds.listRelatives(dup, children=True, type="transform", fullPath=True) or []
    if kids:
        cmds.delete(kids)
    cmds.delete(dup, constructionHistory=True)
    dup = _uninstance(dup)
    dup = cmds.parent(dup, parent)[0]
    if dup.split("|")[-1] != name:
        dup = cmds.rename(dup, name)
    return dup


def _uninstance(transform):
    """A private mesh when duplicate handed back another instance."""
    shape = _mesh_shape(transform)
    if not shape:
        return transform
    if len(cmds.listRelatives(shape, allParents=True) or []) < 2:
        return transform
    fn = _fn_mesh(shape)
    counts, connects = fn.getVertices()
    saved_uvs = _read_mesh_uvs(fn)
    raw = cmds.xform(shape + ".vtx[*]", query=True, translation=True, worldSpace=True)
    points = om.MPointArray()
    for index in range(0, len(raw), 3):
        points.append(om.MPoint(raw[index], raw[index + 1], raw[index + 2]))
    parent = cmds.listRelatives(transform, parent=True, fullPath=True)
    name = transform.split("|")[-1]
    cmds.delete(transform)
    created = om.MFnMesh().create(points, counts, connects)
    _write_mesh_uvs(_fn_mesh(created), saved_uvs)
    new_name = cmds.rename(om.MDagPath.getAPathTo(created).fullPathName(), name)
    if parent:
        new_name = cmds.parent(new_name, parent[0])[0]
    return new_name


def _mapped_weights(weights, influences):
    """Renormalize onto the stations this mesh actually has."""
    total = 0.0
    pairs = []
    for index, weight in weights:
        if index >= len(influences) or not influences[index] or weight <= 0.0:
            continue
        pairs.append((influences[index], weight))
        total += weight
    if total < 1e-8:
        for joint in influences:
            if joint:
                return [(joint, 1.0)]
        return []
    return [(joint, weight / total) for joint, weight in pairs]


def _skin_weight_rows(points, influences, positions):
    """One weight per influence for each point. None influences are skipped."""
    joints = []
    seen = set()
    for joint in influences:
        if not joint or joint in seen:
            continue
        seen.add(joint)
        joints.append(joint)
    columns = {}
    for index, joint in enumerate(joints):
        columns[joint] = index
    count = len(positions)
    rows = []
    width = len(joints)
    for point in points:
        row = [0.0] * width
        for joint, weight in _mapped_weights(
            skin_weights(chain_parameter(point, positions), count),
            influences,
        ):
            column = columns.get(joint)
            if column is not None:
                row[column] += weight
        rows.append(row)
    return joints, rows


def _check_skin_rows():
    positions = [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0)]
    joints, rows = _skin_weight_rows(
        [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 2.0, 0.0)],
        ["a", "b"],
        positions,
    )
    assert joints == ["a", "b"]
    assert rows[0] == [1.0, 0.0]
    assert abs(rows[1][0] - 0.5) < 1e-9 and abs(rows[1][1] - 0.5) < 1e-9
    assert rows[2] == [0.0, 1.0]
    joints, rows = _skin_weight_rows(
        [(0.0, 2.0, 0.0)],
        [None, "b"],
        positions,
    )
    assert joints == ["b"] and rows == [[1.0]]


_check_skin_rows()


def _apply_skin_weights(skin, shape, joints, rows):
    """Write every vertex in one call."""
    import maya.api.OpenMayaAnim as oma

    sel = om.MSelectionList()
    sel.add(shape)
    sel.add(skin)
    dag = sel.getDagPath(0)
    if dag.apiType() != om.MFn.kMesh:
        dag.extendToShape()
    fn = oma.MFnSkinCluster(sel.getDependNode(1))
    indices = om.MIntArray()
    for joint in joints:
        chosen = om.MSelectionList()
        chosen.add(joint)
        indices.append(fn.indexForInfluenceObject(chosen.getDagPath(0)))
    comp_fn = om.MFnSingleIndexedComponent()
    comp = comp_fn.create(om.MFn.kMeshVertComponent)
    comp_fn.addElements(om.MIntArray(range(len(rows))))
    flat = []
    for row in rows:
        flat.extend(row)
    fn.setWeights(dag, comp, indices, om.MDoubleArray(flat), True)


def _stack_weight_rows(parts):
    """parts is (joints, rows) per mesh, in vertex order. One shared joint list."""
    order = []
    index = {}
    for joints, _rows in parts:
        for joint in joints:
            if joint not in index:
                index[joint] = len(order)
                order.append(joint)
    width = len(order)
    stacked = []
    for joints, mesh_rows in parts:
        columns = [index[joint] for joint in joints]
        for row in mesh_rows:
            full = [0.0] * width
            for column, weight in zip(columns, row):
                full[column] += weight
            stacked.append(full)
    return order, stacked


def _check_stack_weight_rows():
    joints, rows = _stack_weight_rows([
        (["a"], [[1.0]]),
        (["b", "a"], [[0.25, 0.75]]),
    ])
    assert joints == ["a", "b"]
    assert rows[0] == [1.0, 0.0]
    assert abs(rows[1][0] - 0.75) < 1e-9 and abs(rows[1][1] - 0.25) < 1e-9
    assert _stack_weight_rows([]) == ([], [])


_check_stack_weight_rows()


def _label_joint(joint):
    """Unique Other label so copySkinWeights can match this influence by label.

    side is Center and type is Other. otherType is the joint name without
    the _jnt suffix, so two station joints never share a label.
    """
    short = joint.split("|")[-1]
    if short.endswith("_jnt"):
        short = short[:-4]
    cmds.setAttr(joint + ".side", 0)
    cmds.setAttr(joint + ".type", 18)
    cmds.setAttr(joint + ".otherType", short, type="string")


def _skin_mesh(mesh, joints, rows):
    """One linear skin with these weights. rows already match the vertex order."""
    if not joints:
        cmds.warning("No joints for %s." % mesh.split("|")[-1])
        return None
    created = cmds.skinCluster(
        joints,
        mesh,
        toSelectedBones=True,
        maximumInfluences=2,
        normalizeWeights=1,
        skinMethod=0,
        name=mesh.split("|")[-1] + "_skin",
    )
    skin = created[0] if isinstance(created, (list, tuple)) else created
    shape = _mesh_shape(mesh)
    count = cmds.polyEvaluate(mesh, vertex=True) if shape else None
    if shape and rows and count == len(rows):
        _apply_skin_weights(skin, shape, joints, rows)
    elif shape:
        cmds.warning(
            "Vertex count %s does not match %d weights on %s."
            % (count, len(rows), mesh.split("|")[-1])
        )
    return skin


def _combine_meshes(meshes, parent, name):
    """One mesh. Vertex order is the input order. Sources are removed."""
    parent = cmds.ls(parent, long=True)[0]
    if len(meshes) == 1:
        node = cmds.ls(meshes[0], long=True)[0]
        current = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if not current or current[0] != parent:
            node = cmds.parent(node, parent)[0]
        if node.split("|")[-1] != name:
            node = cmds.rename(node, name)
        return cmds.ls(node, long=True)[0]
    result = cmds.polyUnite(
        meshes, constructionHistory=False, mergeUVSets=True, name=name
    )
    united = None
    for node in result:
        if cmds.objExists(node) and cmds.nodeType(node) == "transform":
            united = node
            break
    if not united:
        cmds.warning("Could not combine the feathers.")
        return None
    for mesh in meshes:
        if cmds.objExists(mesh):
            cmds.delete(mesh)
    current = cmds.listRelatives(united, parent=True, fullPath=True) or []
    if not current or current[0] != parent:
        united = cmds.parent(united, parent)[0]
    return cmds.ls(united, long=True)[0]


def _skin_combined(meshes, parts, parent):
    """Combine, then write the per-feather weights in that same vertex order.

    Feathers overlap, so a closest-point transfer can pick up a neighbor.
    The combine keeps each feather's vertices in order, and the rows were
    computed for those vertices. Labels are for a later copy onto another mesh.
    """
    joints, rows = _stack_weight_rows(parts)
    mesh = _combine_meshes(meshes, parent, "plume_feathers_rig")
    if not mesh:
        return None
    _assign_scale_material(mesh)
    return _skin_mesh(mesh, joints, rows)


def twist_gap_positions(positions, present, steps):
    """Neck positions with `steps - 1` points inserted across each live gap.

    A gap is live when both ends have a station. The new points sit on the
    straight line between those ends, so the chain's shape does not change.
    """
    out = []
    steps = max(int(steps), 1)
    for index, pos in enumerate(positions):
        out.append(pos)
        nxt = index + 1
        if (
            steps < 2
            or nxt >= len(positions)
            or not present[index]
            or not present[nxt]
        ):
            continue
        span = _sub(positions[nxt], pos)
        for step in range(1, steps):
            out.append(_add(pos, _mul(span, step / float(steps))))
    return out


def _check_twist_gaps():
    """A point halfway along a gap lands on the middle inserted joint."""
    positions = [(0.0, 0.0, 0.0), (0.0, 4.0, 0.0)]
    filled = twist_gap_positions(positions, [True, True], 4)
    assert len(filled) == 5
    assert abs(filled[2][1] - 2.0) < 1e-6
    assert skin_weights(chain_parameter((0.0, 2.0, 0.0), filled), 5) == [(2, 1.0)]
    assert twist_gap_positions(positions, [True, False], 4) == positions
    assert twist_gap_positions(positions, [True, True], 1) == positions


_check_twist_gaps()


def _tween_joint(name, start, end, fraction, feather_joint, rotate_order):
    """Joint held on a quaternion blend of two stations, so it keeps its size.

    Linear skinning between the stations is what collapses the feather. This
    joint takes the rotation blend, and the skin then only blends a short step.
    """
    blend = cmds.createNode("pairBlend", name=name + "_pb")
    cmds.setAttr(blend + ".rotInterpolation", 1)
    cmds.setAttr(blend + ".weight", fraction)
    for src, slot in ((start, "1"), (end, "2")):
        dec = cmds.createNode("decomposeMatrix", name=name + "_dm" + slot)
        cmds.connectAttr(src + ".worldMatrix[0]", dec + ".inputMatrix")
        cmds.connectAttr(dec + ".outputTranslate", blend + ".inTranslate" + slot)
        cmds.connectAttr(dec + ".outputRotate", blend + ".inRotate" + slot)
    mid = cmds.createNode("transform", name=name + "_mid", parent=_driver_group())
    cmds.setAttr(mid + ".inheritsTransform", 0)
    cmds.connectAttr(blend + ".outTranslate", mid + ".translate")
    cmds.connectAttr(blend + ".outRotate", mid + ".rotate")
    return _skin_joint(name, mid, feather_joint, rotate_order)


def _fill_twist_gaps(influences, positions, feather_joint, rotate_order, name):
    """Stations plus a joint on each even step between neighbours."""
    present = [bool(joint) for joint in influences]
    filled = twist_gap_positions(positions, present, TWIST_STEPS)
    if len(filled) == len(positions):
        return influences, positions
    out = []
    steps = max(int(TWIST_STEPS), 1)
    for index, joint in enumerate(influences):
        out.append(joint)
        nxt = index + 1
        if (
            steps < 2
            or nxt >= len(influences)
            or not joint
            or not influences[nxt]
        ):
            continue
        for step in range(1, steps):
            out.append(_tween_joint(
                "%s_t%d_%d" % (name, index, step),
                joint,
                influences[nxt],
                step / float(steps),
                feather_joint,
                rotate_order,
            ))
    return out, filled


def _bind_feather(feather, joint, necks, positions, group, ctl=None, twist=None):
    """Stations for the neck joints this feather crosses.

    Returns the duplicate mesh and its weight rows. The caller combines
    those meshes and writes one skin.

    The feather joint stays on the control. It is not a skin influence:
    the matrix constraint on it is not a hinge rotate, and feeding that
    rotate into the stations turns splay into a twist.

    With twist, a shut feather follows each neck joint's bend but takes the
    twist of the joint the feather hangs from, so it turns as one piece
    instead of shearing between joints.

    Splay blends that drape toward a second copy parented only to the neck
    joint the feather hangs from. Fully open, the feather is that rigid
    copy, so pulling the neck apart cannot lengthen it.
    """
    slot = _feather_slot(feather)
    if not slot:
        return
    row, col = slot
    parent = cmds.listRelatives(joint, parent=True, fullPath=True) or []
    parent_index = None
    if parent:
        parent_long = cmds.ls(parent[0], long=True)[0]
        for index, neck in enumerate(necks):
            if cmds.ls(neck, long=True)[0] == parent_long:
                parent_index = index
                break
    points = _world_points(feather)
    if not points:
        cmds.warning("No points on %s." % feather.split("|")[-1])
        return
    count = len(positions)
    needed = set()
    if parent_index is not None:
        needed.add(parent_index)
    for point in points:
        for index, weight in skin_weights(chain_parameter(point, positions), count):
            if weight > 1e-4:
                needed.add(index)
    if parent_index is None:
        cmds.warning(
            "%s is not under a neck joint."
            % joint.split("|")[-1]
        )
    order = cmds.getAttr((ctl or joint) + ".rotateOrder")
    # Shut: each station hugs its own neck joint. Open: every station is a
    # fixed offset under the one neck joint this feather hangs from. The
    # skinned joint blends those two by splay, 0 to 90. Joints are drawn
    # where that station's weight is already 1. Bind runs with splay at 0,
    # so the rest pose is the hug.
    matrix = cmds.xform(joint, query=True, matrix=True, worldSpace=True)
    axis = _feather_axis(points, matrix)
    splay = _splay_offset_plug(ctl)
    free_grip = None
    weight = None
    if parent_index is not None and splay:
        free_align = _make_align(
            "plumeStation_%d_%d_free" % (row, col),
            necks[parent_index],
            matrix,
            order,
        )
        free_grip = _hang_splay(free_align, order, splay, ctl)
        weight = _splay_weight(splay, "plumeStation_%d_%d_splay" % (row, col))
    influences = [None] * count
    for index in sorted(needed):
        target = necks[index]
        if twist is not None and parent_index is not None and index != parent_index:
            target = _twist_fix(twist, necks, positions, parent_index, index)
        name = "plumeStation_%d_%d_%d" % (row, col, index)
        offset = _station_offset(index, parent_index, positions, axis, matrix)
        if free_grip is None:
            influences[index] = _make_station(
                name, target, joint, matrix, order, splay, ctl, offset
            )
            continue
        hug_align = _make_align(name + "_hug", target, matrix, order)
        hug_grip = _hang_splay(hug_align, order, None, ctl)
        hug = _put_place(hug_grip, name + "_hug", offset, order)
        free = _put_place(free_grip, name + "_free", offset, order)
        mid = _blend_places(name, hug, free, weight)
        influences[index] = _skin_joint(name, mid, joint, order)
    influences, weight_positions = _fill_twist_gaps(
        influences, positions, joint, order, "plumeStation_%d_%d" % (row, col)
    )
    name = "plume_feather_%d_%d_rig" % (row, col)
    dup = _duplicate_mesh(feather, group, name)
    joints, rows = _skin_weight_rows(
        _world_points(dup), influences, weight_positions
    )
    if not joints:
        cmds.delete(dup)
        cmds.warning("No joints for %s." % feather.split("|")[-1])
        return None
    return dup, joints, rows


def _place_head(guide_rig, chest, parked, tip):
    """Head on the tip, under the chest. Not a child of the neck.

    Parenting it under the neck effector would put the control downstream
    of the curve, and the tip constraint would cycle.
    """
    head = _named_component("control_01", "head")
    if head and head in parked:
        head = cmds.ls(cmds.parent(head, chest, relative=True)[0], long=True)[0]
    elif not head:
        import mgear.pymaya as pm

        head = _draw_control(guide_rig, pm.PyNode(chest), "head", tip, True)
    if not head:
        return None
    if cmds.attributeQuery("joint", node=head, exists=True):
        cmds.setAttr(head + ".joint", True)
    cmds.xform(head, worldSpace=True, translation=(tip[0], tip[1], tip[2]))
    return cmds.ls(head, long=True)[0]


def drive_neck_from_head():
    """Point the neck tip at the head, then hide the neck controls.

    ik1 translation follows the head. Each FK control takes a share of the
    head's own rotation, the tip the whole of it, so a forward pitch matches
    and the twist does not flip. The neck IK and FK controls stay locked.
    The tangent controls stay.
    """
    head = _solo("head_*_ctl")
    ik0 = _solo("neck_*_ik0_ctl")
    ik1 = _solo("neck_*_ik1_ctl")
    if not head or not ik0 or not ik1:
        cmds.warning("Head or neck IK controls are missing. Neck was left alone.")
        return None
    fk = _neck_fk_controls()
    # Twist first, then pitch in the chest's frame. With the default XYZ the
    # twist swings the pitch around, and each neck row twists by a different
    # amount, so after a full ry turn every row pitched a different way.
    cmds.setAttr(head + ".rotateOrder", 4)
    _constrain_tip_to_head(head, ik1)
    for ctl in [ik0, ik1] + fk:
        _ghost_neck_control(ctl)
    _align_neck_to_head(head, fk)
    _reparent_head_joint()
    return head


def _solo(pattern):
    """One transform matching pattern, or None."""
    found = cmds.ls(pattern, type="transform", long=True) or []
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        cmds.warning("Expected one %s, found %d." % (pattern, len(found)))
    return None


def _constrain_tip_to_head(head, ik1):
    """Position ik1 on the head. Rotation is handled by the FK blend.

    An aim here rotates the tip tangent under ik1, and that tangent swings
    behind the head, so the neck bows backward.
    """
    existing = cmds.listConnections(
        ik1, source=True, destination=False, type="parentConstraint"
    ) or []
    if existing:
        return
    cmds.parentConstraint(
        head, ik1, maintainOffset=True, skipRotate=["x", "y", "z"]
    )


def _neck_fk_controls():
    """Neck FK controls, base to tip."""
    found = []
    for node in cmds.ls("neck_*_fk*_ctl", type="transform", long=True) or []:
        index = _fk_index(node)
        if index is None:
            continue
        found.append((index, node))
    found.sort()
    return [node for _index, node in found]


def _fk_index(node):
    for part in node.split("|")[-1].split("_"):
        if part.startswith("fk") and part[2:].isdigit():
            return int(part[2:])
    return None


def _rotation_matrix(node):
    """World rotation of node, translation and scale removed."""
    matrix = om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    transform = om.MTransformationMatrix(matrix)
    transform.setTranslation(om.MVector(0.0, 0.0, 0.0), om.MSpace.kTransform)
    transform.setScale([1.0, 1.0, 1.0], om.MSpace.kTransform)
    return transform.asMatrix()


def _flat(matrix):
    return [matrix[i] for i in range(16)]


def _align_neck_to_head(head, controls):
    """Turn each FK control by a share of the head's own rotation.

    Shares step evenly from 0 at the base to 1 at the tip, so the feather
    rows, which hang from the joints above the base, twist by even steps.
    The tip takes the whole rotation, so it pitches and twists with the
    head. The share is a multiply on the head's rotate channels, taken in
    the neck's own frame (ry twists, rx and rz bend), then a matrix, so the
    twist does not flip the way an orient blend does. The next segment is
    parented beside the control, not under it.
    """
    if not controls:
        cmds.warning("No neck FK controls. Neck orientation was left alone.")
        return
    count = len(controls)
    host = cmds.listRelatives(head, parent=True, fullPath=True)[0]
    names = [ctl.split("|")[-1] for ctl in controls]
    npos = [name.replace("_ctl", "_npo") for name in names]
    for index in range(count - 1, 0, -1):
        cmds.parent(npos[index], npos[index - 1])
    group = cmds.createNode("transform", name="neckOri_grp", parent=host)
    # Each share turns in a frame whose Y is that segment's own bone, so
    # the head's ry is a pure twist of every segment. In the host's own
    # axes it swings a leaning neck, and by a full turn the segments are
    # tilted different ways. rx and rz still pitch and roll, about X and Z.
    necks = _neck_division_joints()
    positions = [_world_translation(joint) for joint in necks]
    for index, name in enumerate(names):
        ctl = cmds.ls(name, long=True)[0]
        share = index / float(max(count - 1, 1))
        frame = cmds.createNode(
            "transform", name="neckOriFrame%d" % index, parent=group
        )
        if len(positions) >= 2:
            bone = _neck_bone(positions, min(index, len(positions) - 1))
            cmds.xform(frame, objectSpace=True, matrix=_bone_frame(host, bone))
        driver = cmds.createNode(
            "transform", name="neckOriDriver%d" % index, parent=frame
        )
        cmds.connectAttr(head + ".rotateOrder", driver + ".rotateOrder")
        for channel in "xyz":
            mult = cmds.createNode("multDL", name="neckOriMul%d%s" % (index, channel))
            cmds.connectAttr(head + ".r" + channel, mult + ".input1")
            cmds.setAttr(mult + ".input2", share)
            cmds.connectAttr(mult + ".output", driver + ".r" + channel)
        _drive_neck_orientation(ctl, driver)
    cmds.setAttr(group + ".visibility", 0)


def _neck_bone(positions, index):
    """Direction from neck joint index to the next. The tip uses the last segment."""
    if index + 1 < len(positions):
        return _norm(_sub(positions[index + 1], positions[index]))
    return _norm(_sub(positions[index], positions[index - 1]))


def _frame_axes(y):
    """Right-handed (x, y, z) with Y given and X as near the host's X as it can stay."""
    ref = (1.0, 0.0, 0.0) if abs(y[0]) < 0.9 else (0.0, 0.0, 1.0)
    x = _norm(_sub(ref, _mul(y, _dot(ref, y))))
    return x, y, _cross(x, y)


def _bone_frame(host, bone):
    """Matrix in host's space with Y along the world direction bone."""
    inverse = _rotation_matrix(host).inverse()
    y = _norm(tuple(sum(bone[i] * inverse[i * 4 + j] for i in range(3)) for j in range(3)))
    x, y, z = _frame_axes(y)
    return [
        x[0], x[1], x[2], 0.0,
        y[0], y[1], y[2], 0.0,
        z[0], z[1], z[2], 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def _check_frame_axes():
    for y in (_norm((0.0, 0.92, 0.39)), _norm((0.3, 0.5, 0.8)), (1.0, 0.0, 0.0)):
        x, y2, z = _frame_axes(y)
        assert y2 == y
        assert abs(_dot(x, y)) < 1e-9 and abs(_dot(z, y)) < 1e-9 and abs(_dot(x, z)) < 1e-9
        assert abs(_length(x) - 1.0) < 1e-9 and abs(_length(z) - 1.0) < 1e-9
    assert abs(_frame_axes(_norm((0.0, 0.92, 0.39)))[0][0] - 1.0) < 1e-9


_check_frame_axes()


def _drive_neck_orientation(ctl, driver):
    """World rotation of ctl tracks driver, position stays on the curve.

    The bind offset is ctl_rest * inv(driver_rest). Multiplying the live
    driver after that turns the control in the head's space, so a forward
    pitch stays forward and the twist has no shortest-arc flip.
    """
    cmds.getAttr(driver + ".ry")
    driver_rest = _rotation_matrix(driver)
    ctl_rest = _rotation_matrix(ctl)
    # Row-vector matrices: rest first, then the driver's turn. The other
    # order pitches around the neck's axis instead of the head's.
    offset = ctl_rest * driver_rest.inverse()
    parent = cmds.listRelatives(ctl, parent=True, fullPath=True)[0]
    stem = ctl.split("|")[-1]
    pick_parent = cmds.createNode("pickMatrix", name=stem + "_oriPickP")
    pick_driver = cmds.createNode("pickMatrix", name=stem + "_oriPickD")
    inverse = cmds.createNode("inverseMatrix", name=stem + "_oriInv")
    product = cmds.createNode("multMatrix", name=stem + "_oriMul")
    for pick in (pick_parent, pick_driver):
        cmds.setAttr(pick + ".useTranslate", 0)
        cmds.setAttr(pick + ".useScale", 0)
        cmds.setAttr(pick + ".useShear", 0)
    cmds.connectAttr(parent + ".worldMatrix[0]", pick_parent + ".inputMatrix")
    cmds.connectAttr(pick_parent + ".outputMatrix", inverse + ".inputMatrix")
    cmds.setAttr(product + ".matrixIn[0]", *_flat(offset), type="matrix")
    cmds.connectAttr(pick_driver + ".outputMatrix", product + ".matrixIn[1]")
    cmds.connectAttr(driver + ".worldMatrix[0]", pick_driver + ".inputMatrix")
    cmds.connectAttr(inverse + ".outputMatrix", product + ".matrixIn[2]")
    cmds.connectAttr(product + ".matrixSum", ctl + ".offsetParentMatrix", force=True)


def _ghost_neck_control(ctl):
    """Hide shapes, lock channels, and drop it from the anim sets."""
    for shape in cmds.listRelatives(ctl, shapes=True, fullPath=True) or []:
        plug = shape + ".visibility"
        cmds.setAttr(plug, lock=False)
        for src in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            cmds.disconnectAttr(src, plug)
        cmds.setAttr(plug, 0)
    for channel in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
        cmds.setAttr(ctl + "." + channel, lock=True, keyable=False, channelBox=False)
    for grp in cmds.listConnections(ctl + ".instObjGroups[0]", type="objectSet") or []:
        short = grp.split("|")[-1].split(":")[-1]
        if not short.endswith("_grp"):
            continue
        try:
            cmds.sets(ctl, remove=grp)
        except RuntimeError:
            pass
    for attr in cmds.listAttr(ctl, userDefined=True) or []:
        try:
            cmds.deleteAttr(ctl + "." + attr)
        except RuntimeError:
            pass


def _reparent_head_joint():
    """Hang the head joint off the neck tip, still driven by its control."""
    found = [
        node for node in cmds.ls("head_*_jnt", type="joint", long=True) or []
        if node.split("|")[-1].endswith("_0_jnt")
    ]
    necks = _neck_division_joints()
    if len(found) != 1 or not necks:
        cmds.warning("Head joint or neck tip missing. Left the joint parent alone.")
        return
    target = found[0]
    tip = cmds.ls(necks[-1], long=True)[0]
    cons = cmds.listConnections(
        target, source=True, destination=False, type="mgear_matrixConstraint"
    ) or []
    if not cons:
        cmds.warning("Head joint has no matrix constraint. Left its parent alone.")
        return
    drivers = cmds.listConnections(cons[0] + ".driverMatrix", source=True, destination=False) or []
    if not drivers:
        cmds.warning("Head joint constraint has no driver. Left its parent alone.")
        return
    driver = drivers[0]
    cmds.delete(cons[0])
    parent = cmds.listRelatives(target, parent=True, fullPath=True) or []
    if not parent or parent[0] != tip:
        target = cmds.parent(target, tip)[0]
    cmds.parentConstraint(driver, target, maintainOffset=True)
    cmds.scaleConstraint(driver, target, maintainOffset=True)


def _hook_neck_step():
    """Run the head-to-tip wiring at the end of the next full guide build."""
    _hook_post_step("plume_neck_step.py")


def _post_step_list(current, script_name, step):
    """Comma list with this script's path. An older path for the same file is replaced."""
    parts = [part.strip() for part in (current or "").split(",") if part.strip()]
    seen = False
    updated = []
    for part in parts:
        normal = part.replace("\\", "/")
        if os.path.basename(normal) != script_name:
            updated.append(normal)
            continue
        if seen:
            continue
        seen = True
        updated.append(step)
    if not seen:
        updated.append(step)
    return ",".join(updated)


assert _post_step_list(
    "", "plume_neck_step.py", "C:/tools/plume_neck_step.py"
) == "C:/tools/plume_neck_step.py"
assert _post_step_list(
    "D:/old/plume_neck_step.py,C:/tools/plume_splay_step.py",
    "plume_neck_step.py",
    "C:/tools/plume_neck_step.py",
) == "C:/tools/plume_neck_step.py,C:/tools/plume_splay_step.py"
assert _post_step_list(
    "D:/old/plume_neck_step.py,C:/tools/plume_splay_step.py,E:/other/plume_neck_step.py",
    "plume_neck_step.py",
    "C:/tools/plume_neck_step.py",
) == "C:/tools/plume_neck_step.py,C:/tools/plume_splay_step.py"


def _hook_post_step(script_name):
    guide = "guide"
    if not cmds.attributeQuery("postCustomStep", node=guide, exists=True):
        return
    step = os.path.join(os.path.dirname(__file__), script_name).replace("\\", "/")
    current = cmds.getAttr(guide + ".postCustomStep") or ""
    updated = _post_step_list(current, script_name, step)
    if updated != current.replace("\\", "/"):
        cmds.setAttr(guide + ".postCustomStep", updated, type="string")
    cmds.setAttr(guide + ".doPostCustomStep", 1)


def _hook_splay_step():
    """Run the feather-rig setup at the end of the next full guide build."""
    _hook_post_step("plume_splay_step.py")


def _ensure_shifter_path():
    import os
    import sys

    comp = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "components"))
    if comp not in sys.path:
        sys.path.insert(0, comp)
    key = "MGEAR_SHIFTER_COMPONENT_PATH"
    current = os.environ.get(key, "")
    parts = [part for part in current.split(os.pathsep) if part]
    if comp not in parts:
        os.environ[key] = os.pathsep.join(parts + [comp])

#endregion
#region dialog

UI_OBJECT_NAME = "PlumeRigUI"
UI_FIXED_WIDTH = 380
UI_BUTTON_HEIGHT = 32
UI_FIELD_LABEL_WIDTH = 92

# coolors.co palette: 8ecae6 · 219ebc · 023047 · ffb703 · fb8500
C_SKY = "#8ecae6"
C_TEAL = "#219ebc"
C_NAVY = "#023047"
C_GOLD = "#ffb703"
C_ORANGE = "#fb8500"
C_PANEL = "#034a6e"
C_BG = "#000000"

_SPINBOX_ARROW_IMAGES = {}


def _spinbox_arrow_image_path(direction):
    if direction not in _SPINBOX_ARROW_IMAGES:
        path = os.path.join(
            tempfile.gettempdir(), "plume_rig_spin_{}.png".format(direction)
        )
        if not os.path.exists(path):
            width, height = 10, 6
            pixmap = QtGui.QPixmap(width, height)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setBrush(QtGui.QColor(C_SKY))
            painter.setPen(QtCore.Qt.NoPen)
            if direction == "up":
                points = [
                    QtCore.QPoint(5, 1),
                    QtCore.QPoint(1, height - 1),
                    QtCore.QPoint(width - 1, height - 1),
                ]
            else:
                points = [
                    QtCore.QPoint(5, height - 1),
                    QtCore.QPoint(1, 1),
                    QtCore.QPoint(width - 1, 1),
                ]
            painter.drawPolygon(QtGui.QPolygon(points))
            painter.end()
            pixmap.save(path, "PNG")
        _SPINBOX_ARROW_IMAGES[direction] = path.replace("\\", "/")
    return _SPINBOX_ARROW_IMAGES[direction]


_SPIN_UP_IMAGE = _spinbox_arrow_image_path("up")
_SPIN_DOWN_IMAGE = _spinbox_arrow_image_path("down")

STYLE_SHEET = f"""
QDialog {{
    background-color: {C_BG};
    color: {C_SKY};
    font-family: "Segoe UI", sans-serif;
    font-size: 11px;
}}
QLabel {{
    color: {C_SKY};
    border: none;
    background: transparent;
    padding: 0;
}}
QLabel:disabled {{ color: #557486; }}
QLineEdit {{
    background-color: {C_BG};
    color: {C_SKY};
    border: 1px solid {C_TEAL};
    border-radius: 3px;
    padding: 2px 4px;
    min-height: 20px;
}}
QLineEdit:focus {{ border: 1px solid {C_GOLD}; }}
QLineEdit:disabled {{ color: #557486; border-color: #557486; }}
QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{
    height: 6px;
    background: {C_NAVY};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {C_TEAL};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal:disabled {{ background: #557486; }}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -4px 0;
    background: {C_TEAL};
    border: 1px solid {C_SKY};
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {C_SKY}; }}
QSlider::handle:horizontal:disabled {{
    background: #557486;
    border: 1px solid #557486;
}}
QToolTip {{
    background-color: {C_NAVY};
    color: #ffffff;
    border: 1px solid {C_TEAL};
    padding: 4px;
}}
"""

SPINBOX_STYLE = f"""
QSpinBox {{
    background-color: {C_BG};
    color: {C_SKY};
    border: 1px solid {C_TEAL};
    border-radius: 3px;
    padding: 1px 18px 1px 3px;
    min-height: 20px;
}}
QSpinBox:focus {{ border: 1px solid {C_GOLD}; }}
QSpinBox:disabled {{ color: #557486; border-color: #557486; }}
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 14px;
    height: 11px;
    border: none;
    outline: none;
    border-top-right-radius: 2px;
    background-color: {C_NAVY};
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 14px;
    height: 11px;
    border: none;
    outline: none;
    border-bottom-right-radius: 2px;
    background-color: {C_NAVY};
}}
QSpinBox::up-button:hover,
QSpinBox::down-button:hover {{ background-color: {C_TEAL}; }}
QSpinBox:focus::up-button,
QSpinBox:focus::down-button {{
    border: none;
    background-color: {C_NAVY};
}}
QSpinBox::up-arrow {{
    width: 10px;
    height: 6px;
    border: none;
    outline: none;
    image: url({_SPIN_UP_IMAGE});
}}
QSpinBox::down-arrow {{
    width: 10px;
    height: 6px;
    border: none;
    outline: none;
    image: url({_SPIN_DOWN_IMAGE});
}}
"""


def _button_style(background, foreground, border, hover, hover_text=None):
    hover_text = foreground if hover_text is None else hover_text
    return f"""
    QPushButton {{
        background-color: {background};
        color: {foreground};
        border: 1px solid {border};
        border-radius: 4px;
        font-weight: bold;
        padding: 6px 8px;
    }}
    QPushButton:hover {{ background-color: {hover}; color: {hover_text}; }}
    QPushButton:pressed {{ background-color: {C_NAVY}; color: {C_SKY}; }}
    QPushButton:disabled {{
        background-color: {C_NAVY};
        color: #557486;
        border-color: {C_NAVY};
    }}
    """


BUTTON_STYLES = {
    "primary": _button_style(C_TEAL, "#ffffff", C_SKY, C_SKY, C_NAVY),
    "secondary": _button_style(C_GOLD, C_NAVY, C_ORANGE, "#ffc933"),
    "cta": _button_style(C_ORANGE, "#ffffff", "#c96a00", "#ff9619"),
}

# Hover stays dark so the white arrow icon keeps contrast.
ICON_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {C_TEAL};
    border: 1px solid {C_SKY};
    border-radius: 4px;
    padding: 2px;
}}
QPushButton:hover {{ background-color: #187a96; }}
QPushButton:pressed {{ background-color: {C_NAVY}; }}
"""


def _check_image_path():
    path = os.path.join(tempfile.gettempdir(), "plume_rig_check.png")
    if not os.path.exists(path):
        pixmap = QtGui.QPixmap(14, 14)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#ffffff"))
        pen.setWidth(2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(
            QtGui.QPolygon(
                [QtCore.QPoint(2, 7), QtCore.QPoint(5, 11), QtCore.QPoint(12, 3)]
            )
        )
        painter.end()
        pixmap.save(path, "PNG")
    return path.replace("\\", "/")


_CHECK_IMAGE = _check_image_path()

CHECKBOX_STYLE = f"""
QCheckBox {{
    color: {C_SKY};
    font-family: "Segoe UI", sans-serif;
    font-size: 11px;
    spacing: 6px;
    background: transparent;
}}
QCheckBox:disabled {{ color: #557486; }}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {C_TEAL};
    border-radius: 3px;
    background: {C_BG};
}}
QCheckBox::indicator:hover {{ border: 1px solid {C_GOLD}; }}
QCheckBox::indicator:checked {{
    background: {C_TEAL};
    border: 1px solid {C_SKY};
    image: url({_CHECK_IMAGE});
}}
QCheckBox::indicator:disabled {{
    border-color: #557486;
    background: {C_NAVY};
}}
"""


def _select_icon():
    """Maya's select-tool arrow. Drawn fallback if the resource is missing."""
    icon = QtGui.QIcon(":/aselect.png")
    if not icon.isNull():
        return icon
    pixmap = QtGui.QPixmap(32, 32)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setBrush(QtGui.QColor("#ffffff"))
    painter.setPen(QtCore.Qt.NoPen)
    shape = QtGui.QPainterPath()
    shape.moveTo(5, 3)
    shape.lineTo(5, 22)
    shape.lineTo(11, 16)
    shape.lineTo(9, 28)
    shape.lineTo(15, 26)
    shape.lineTo(17, 16)
    shape.lineTo(26, 16)
    shape.closeSubpath()
    painter.drawPath(shape)
    painter.end()
    return QtGui.QIcon(pixmap)

SECTION_HEADER_STYLE = f"""
QPushButton {{
    text-align: left;
    padding: 6px 8px;
    font-weight: bold;
    color: {C_SKY};
    background-color: {C_NAVY};
    border: none;
    border-radius: 4px;
}}
QPushButton:hover {{ background-color: {C_PANEL}; color: #ffffff; }}
"""

SECTION_HEADER_OPEN_STYLE = f"""
QPushButton {{
    text-align: left;
    padding: 6px 8px;
    font-weight: bold;
    color: {C_SKY};
    background-color: {C_NAVY};
    border: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QPushButton:hover {{ background-color: {C_PANEL}; color: #ffffff; }}
"""


def _apply_button_style(button, style):
    button.setStyleSheet(style)
    button.setAutoFillBackground(True)


def _make_button(label, slot, style="primary"):
    button = QtWidgets.QPushButton(label)
    button.setMinimumHeight(UI_BUTTON_HEIGHT)
    _apply_button_style(button, BUTTON_STYLES[style])
    button.clicked.connect(slot)
    return button


def _select_button(tooltip, slot):
    """Square select-arrow button. Hidden until its target exists."""
    button = QtWidgets.QPushButton()
    button.setIcon(_select_icon())
    button.setIconSize(QtCore.QSize(18, 18))
    button.setFixedSize(UI_BUTTON_HEIGHT, UI_BUTTON_HEIGHT)
    button.setToolTip(tooltip)
    button.setVisible(False)
    _apply_button_style(button, ICON_BUTTON_STYLE)
    button.clicked.connect(slot)
    return button


def _style_spinbox(spinbox):
    spinbox.setStyleSheet(SPINBOX_STYLE)
    spinbox.setAutoFillBackground(True)
    palette = spinbox.palette()
    palette.setColor(spinbox.backgroundRole(), QtGui.QColor(C_BG))
    palette.setColor(spinbox.foregroundRole(), QtGui.QColor(C_SKY))
    spinbox.setPalette(palette)


def _spin_int(low, high, value):
    spin = QtWidgets.QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    spin.setFixedWidth(72)
    spin.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    _style_spinbox(spin)
    return spin


def _field_row(label, widget):
    row = QtWidgets.QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    text = QtWidgets.QLabel(label)
    text.setFixedWidth(UI_FIELD_LABEL_WIDTH)
    text.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    row.addWidget(text)
    row.addWidget(widget)
    row.addStretch(1)
    return row


class CollapsibleFrame(QtWidgets.QWidget):
    """ABG section. Collapse sets max height and hides, so the window can shrink."""

    toggled_signal = QtCore.Signal()

    def __init__(self, title, parent=None, default_open=True):
        super(CollapsibleFrame, self).__init__(parent)
        self._title = title

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 2)
        outer.setSpacing(0)

        self.toggle_btn = QtWidgets.QPushButton()
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setMinimumHeight(30)
        self.toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )

        self.content_area = QtWidgets.QFrame()
        self.content_area.setStyleSheet(
            f"QFrame {{ background-color: {C_PANEL}; border: none; "
            f"border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }}"
        )
        self.content_layout = QtWidgets.QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(8, 6, 8, 6)
        self.content_layout.setSpacing(4)

        outer.addWidget(self.toggle_btn)
        outer.addWidget(self.content_area)

        self.toggle_btn.toggled.connect(self.toggle_content)
        self.toggle_btn.setChecked(not default_open)
        self.toggle_content(not default_open)

    def toggle_content(self, collapsed):
        arrow = "\u25b6" if collapsed else "\u25bc"
        self.toggle_btn.setText("{}  {}".format(arrow, self._title))
        _apply_button_style(
            self.toggle_btn,
            SECTION_HEADER_STYLE if collapsed else SECTION_HEADER_OPEN_STYLE,
        )
        if collapsed:
            self.content_area.setMaximumHeight(0)
            self.content_area.setMinimumHeight(0)
            self.content_area.setVisible(False)
        else:
            self.content_area.setVisible(True)
            self.content_area.setMaximumHeight(16777215)
            self.content_area.setMinimumHeight(0)
        self.updateGeometry()
        self.toggled_signal.emit()

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class FlareSlider(QtWidgets.QWidget):
    """Horizontal slider plus a readout. QSlider is integer.

    ponytail: scale 1000, so the smallest step is 0.001. A wider range needs a bigger scale.
    """

    value_changed = QtCore.Signal(float)
    drag_started = QtCore.Signal()
    drag_finished = QtCore.Signal()

    def __init__(self, label, minimum, maximum, value, step):
        super(FlareSlider, self).__init__()
        self._scale = 1000
        self.setMinimumHeight(32)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        text = QtWidgets.QLabel(label)
        text.setFixedWidth(UI_FIELD_LABEL_WIDTH)
        text.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(
            int(round(minimum * self._scale)),
            int(round(maximum * self._scale)),
        )
        tick = max(1, int(round(step * self._scale)))
        self.slider.setSingleStep(tick)
        self.slider.setPageStep(tick * 10)
        self.slider.setValue(int(round(value * self._scale)))

        self.readout = QtWidgets.QLabel()
        self.readout.setFixedWidth(52)
        self.readout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._show_raw(self.slider.value())

        row.addWidget(text)
        row.addWidget(self.slider, 1)
        row.addWidget(self.readout)

        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderPressed.connect(self.drag_started)
        self.slider.sliderReleased.connect(self.drag_finished)

    def _show_raw(self, raw):
        self.readout.setText("{:.3f}".format(raw / float(self._scale)))

    def _on_slider(self, raw):
        self._show_raw(raw)
        self.value_changed.emit(raw / float(self._scale))

    def value(self):
        return self.slider.value() / float(self._scale)

    def setValue(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(float(value) * self._scale)))
        self.slider.blockSignals(False)
        self._show_raw(self.slider.value())


def _pointer(event):
    point = event.position() if hasattr(event, "position") else event.pos()
    return point.x(), point.y()


class EdgeCurve(QtWidgets.QWidget):
    """Feather outline. Each point stays on its station; drag changes width only.

    Root at the top, tip at the bottom. Both edges are the same width. The tip
    is a point and is not a handle.
    """

    def __init__(self):
        super(EdgeCurve, self).__init__()
        self._widths = default_edge()
        self._drag = None
        self._hover = None
        self.setFixedHeight(156)
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setToolTip(
            "Drag a point left or right to set the width at that station. "
            "It stays put along the feather, and both edges match. "
            "The tip stays a point. Double-click to restore the default. "
            "Applied when you generate."
        )

    def widths(self):
        return list(self._widths)

    def _canvas(self):
        return self.rect().adjusted(16, 14, -16, -12)

    def _stations(self):
        rect = self._canvas()
        mid = rect.center().x()
        span = rect.width() * 0.5 - 8.0
        if span < 1.0:
            span = 1.0
        count = len(self._widths)
        top = float(rect.top())
        height = float(rect.height())
        stations = []
        for index, width in enumerate(self._widths):
            y = top + (index / float(count)) * height
            dx = (width / EDGE_WIDTH_MAX) * span
            stations.append((QtCore.QPointF(mid - dx, y), QtCore.QPointF(mid + dx, y)))
        tip = QtCore.QPointF(mid, top + height)
        return stations, tip, mid, span

    def _hit(self, x, y):
        stations, _tip, _mid, _span = self._stations()
        best = None
        best_d = 12.0 * 12.0
        for index, (left, right) in enumerate(stations):
            for point in (left, right):
                dist = (point.x() - x) ** 2 + (point.y() - y) ** 2
                if dist <= best_d:
                    best = index
                    best_d = dist
        return best

    def _set_width(self, index, x):
        _stations, _tip, mid, span = self._stations()
        width = EDGE_WIDTH_MAX * abs(x - mid) / span
        if width < 0.0:
            width = 0.0
        elif width > EDGE_WIDTH_MAX:
            width = EDGE_WIDTH_MAX
        self._widths[index] = width

    def mousePressEvent(self, event):
        if not self.isEnabled() or event.button() != QtCore.Qt.LeftButton:
            return
        x, y = _pointer(event)
        self._drag = self._hit(x, y)
        if self._drag is not None:
            self.setCursor(QtCore.Qt.SizeHorCursor)
        self.update()

    def mouseMoveEvent(self, event):
        if not self.isEnabled():
            return
        x, y = _pointer(event)
        if self._drag is None:
            hover = self._hit(x, y)
            self.setCursor(
                QtCore.Qt.SizeHorCursor if hover is not None else QtCore.Qt.ArrowCursor
            )
            if hover != self._hover:
                self._hover = hover
                self.update()
            return
        self._set_width(self._drag, x)
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.update()

    def mouseDoubleClickEvent(self, event):
        if not self.isEnabled():
            return
        self._widths = default_edge()
        self._drag = None
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        enabled = self.isEnabled()
        ink = QtGui.QColor(C_SKY if enabled else "#557486")
        dim = QtGui.QColor("#557486")
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(C_NAVY))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)

        stations, tip, _mid, _span = self._stations()
        if not stations:
            painter.end()
            return
        path = QtGui.QPainterPath()
        path.moveTo(stations[0][1])
        for _left, right in stations[1:]:
            path.lineTo(right)
        path.lineTo(tip)
        for left, _right in reversed(stations):
            path.lineTo(left)
        path.closeSubpath()
        fill = QtGui.QColor(C_TEAL if enabled else "#557486")
        fill.setAlpha(70 if enabled else 40)
        painter.setBrush(fill)
        painter.drawPath(path)

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(dim, 1))
        painter.drawLine(QtCore.QPointF(tip.x(), stations[0][0].y()), tip)
        painter.setPen(QtGui.QPen(ink, 1.5))
        painter.drawPath(path)

        active = self._drag if self._drag is not None else self._hover
        for index, (left, right) in enumerate(stations):
            if enabled and index == active:
                painter.setBrush(QtGui.QColor(C_GOLD))
            else:
                painter.setBrush(QtGui.QColor(C_TEAL if enabled else "#557486"))
            painter.setPen(QtGui.QPen(ink, 1))
            for point in (left, right):
                painter.drawEllipse(point, 4.5, 4.5)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(tip, 2.5, 2.5)
        painter.end()


class Dialog(QtWidgets.QDialog):
    """Base cylinder in one section, plumage in another."""

    def __init__(self, parent=None):
        super(Dialog, self).__init__(parent)
        self.setObjectName(UI_OBJECT_NAME)
        self.setWindowTitle("Plume Rig")
        self.setWindowFlags(QtCore.Qt.Window)
        self.setStyleSheet(STYLE_SHEET)
        self.setFixedWidth(UI_FIXED_WIDTH)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.create_btn = _make_button("Create Cylinder", self._create, "primary")
        self.select_cyl_btn = _select_button("Select cylinder", self._select_cylinder)
        self.select_flare_btn = _select_button("Select flare", self._select_flare)
        self.select_bend_btn = _select_button("Select bend", self._select_bend)

        self.flare_label = QtWidgets.QLabel("Flare")
        self.bend_label = QtWidgets.QLabel("Bend")
        self.separate = QtWidgets.QCheckBox("Separate XZ")
        self.separate.setToolTip("Flare X and Z independently")
        self.separate.setStyleSheet(CHECKBOX_STYLE)
        self.start = FlareSlider("Start", 0.0, 2.0, 1.0, 0.05)
        self.end = FlareSlider("End", 0.0, 2.0, 1.0, 0.05)
        self.start_x = FlareSlider("Start X", 0.0, 2.0, 1.0, 0.05)
        self.start_z = FlareSlider("Start Z", 0.0, 2.0, 1.0, 0.05)
        self.end_x = FlareSlider("End X", 0.0, 2.0, 1.0, 0.05)
        self.end_z = FlareSlider("End Z", 0.0, 2.0, 1.0, 0.05)
        self.curve = FlareSlider("Curve", -1.0, 1.0, 0.0, 0.05)
        self.bend = FlareSlider("Angle", -180.0, 180.0, 0.0, 1.0)
        self.bend.setToolTip(
            "Bends the cylinder forward and back, in degrees. "
            "Positive bends toward its local +Z, negative toward -Z. "
            "It does not bend sideways."
        )
        self.bend_label.setToolTip(self.bend.toolTip())
        for widget in (self.start_x, self.start_z, self.end_x, self.end_z):
            widget.setVisible(False)
        self._flare_widgets = (
            self.flare_label,
            self.separate,
            self.start,
            self.end,
            self.start_x,
            self.start_z,
            self.end_x,
            self.end_z,
            self.curve,
            self.bend_label,
            self.bend,
        )

        self.rows = _spin_int(1, 80, 4)
        self.columns = _spin_int(3, 64, 12)
        self.variety = FlareSlider("Variety", 0.0, 1.0, 0.0, 0.01)
        self.variety.setToolTip(
            "Leans each feather around the row, up to its own tip edge. "
            "Below 8 around, the feathers already meet, so this stays off. "
            "Applied when you generate."
        )
        self.edge_label = QtWidgets.QLabel("Edge")
        self.edge = EdgeCurve()
        self.custom = QtWidgets.QLineEdit()
        self.custom.setPlaceholderText("procedural feather")
        self.pick = _make_button("<<", self._pick_mesh, "secondary")
        self.pick.setFixedWidth(40)
        self.pick.setToolTip("Use the selected mesh")
        self.generate_btn = _make_button("Generate Feathers", self._generate, "primary")
        self.guide_btn = _make_button("Create Guide", self._guide, "cta")
        self.guide_btn.setToolTip(
            "One more neck joint than feather rows, and one jointed control "
            "per feather on the nearest neck joint. The neck follows the "
            "cylinder bend and is parented to chest. The head is parented "
            "to chest, not the neck, and drives the tip after the build. "
            "A head or chest drawn here is 10 and 5 times the default size."
        )

        cylinder_section = CollapsibleFrame("Create Base Cylinder")
        create_row = QtWidgets.QHBoxLayout()
        create_row.setContentsMargins(0, 0, 0, 0)
        create_row.setSpacing(6)
        create_row.addWidget(self.create_btn, 1)
        create_row.addWidget(self.select_cyl_btn)
        cylinder_section.add_layout(create_row)
        cylinder_section.content_layout.addSpacing(6)
        flare_head = QtWidgets.QHBoxLayout()
        flare_head.setContentsMargins(0, 0, 0, 0)
        flare_head.setSpacing(8)
        flare_head.addWidget(self.flare_label)
        flare_head.addWidget(self.separate)
        flare_head.addStretch(1)
        flare_head.addWidget(self.select_flare_btn)
        cylinder_section.add_layout(flare_head)
        cylinder_section.add_widget(self.start)
        cylinder_section.add_widget(self.end)
        cylinder_section.add_widget(self.start_x)
        cylinder_section.add_widget(self.start_z)
        cylinder_section.add_widget(self.end_x)
        cylinder_section.add_widget(self.end_z)
        cylinder_section.add_widget(self.curve)
        cylinder_section.content_layout.addSpacing(2)
        seam = QtWidgets.QWidget()
        seam.setFixedHeight(1)
        seam.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        seam.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        seam.setStyleSheet("background-color: #0e6a90;")
        cylinder_section.add_widget(seam)
        cylinder_section.content_layout.addSpacing(2)
        bend_head = QtWidgets.QHBoxLayout()
        bend_head.setContentsMargins(0, 0, 0, 0)
        bend_head.setSpacing(8)
        bend_head.addWidget(self.bend_label)
        bend_head.addStretch(1)
        bend_head.addWidget(self.select_bend_btn)
        cylinder_section.add_layout(bend_head)
        cylinder_section.add_widget(self.bend)
        cylinder_section.toggled_signal.connect(self.resize_to_fit)

        self.feathers_section = CollapsibleFrame("Plumage")
        self.feathers_section.add_layout(_field_row("Rows", self.rows))
        self.feathers_section.add_layout(_field_row("Columns", self.columns))
        self.feathers_section.add_widget(self.variety)
        self.feathers_section.add_widget(self.edge_label)
        self.feathers_section.add_widget(self.edge)
        custom_row = QtWidgets.QHBoxLayout()
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(6)
        custom_label = QtWidgets.QLabel("Custom mesh")
        custom_label.setFixedWidth(UI_FIELD_LABEL_WIDTH)
        custom_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        custom_row.addWidget(custom_label)
        custom_row.addWidget(self.custom, 1)
        custom_row.addWidget(self.pick)
        self.feathers_section.add_layout(custom_row)
        self.feathers_section.add_widget(self.generate_btn)
        self.feathers_section.toggled_signal.connect(self.resize_to_fit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.addWidget(cylinder_section)
        layout.addWidget(self.feathers_section)
        layout.addWidget(self.guide_btn)

        self._slider_drag = False
        self._slider_chunk = False
        self.custom.textChanged.connect(self._apply_procedural)
        self.separate.toggled.connect(self._toggle_separate)
        for slider in (
            self.start,
            self.end,
            self.start_x,
            self.start_z,
            self.end_x,
            self.end_z,
            self.curve,
            self.bend,
        ):
            slider.drag_started.connect(self._slider_pressed)
            slider.drag_finished.connect(self._slider_released)
        for slider in (
            self.start,
            self.end,
            self.start_x,
            self.start_z,
            self.end_x,
            self.end_z,
            self.curve,
        ):
            slider.value_changed.connect(self._push_flare)
        self.bend.value_changed.connect(self._push_bend)
        self.refresh()

    def showEvent(self, event):
        self.refresh()
        super(Dialog, self).showEvent(event)

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.ActivationChange and self.isActiveWindow():
            self.refresh()
        super(Dialog, self).changeEvent(event)

    def closeEvent(self, event):
        self._slider_drag = False
        self._close_slider_chunk()
        super(Dialog, self).closeEvent(event)

    def _slider_pressed(self):
        self._slider_drag = True

    def _slider_released(self):
        self._slider_drag = False
        self._close_slider_chunk()

    def _open_slider_chunk(self):
        if self._slider_chunk or not cmds.undoInfo(query=True, state=True):
            return
        cmds.undoInfo(openChunk=True, chunkName="plume slider")
        self._slider_chunk = True

    def _close_slider_chunk(self):
        if not self._slider_chunk:
            return
        self._slider_chunk = False
        cmds.undoInfo(closeChunk=True)

    def resize_to_fit(self):
        QtWidgets.QApplication.processEvents()
        layout = self.layout()
        if not layout:
            return
        layout.invalidate()
        layout.activate()
        target_height = layout.sizeHint().height()
        if target_height > 0:
            self.setFixedHeight(target_height)
            self.setFixedWidth(UI_FIXED_WIDTH)

    def refresh(self):
        has_cylinder = cylinder() is not None
        flare = flare_deformer()
        bend = bend_deformer()
        _hide_deformer(flare, record_undo=False)
        _hide_deformer(bend, record_undo=False)
        self.select_cyl_btn.setVisible(has_cylinder)
        self.select_flare_btn.setVisible(flare is not None)
        self.select_bend_btn.setVisible(bend is not None)
        for widget in self._flare_widgets:
            widget.setEnabled(has_cylinder)
        self.feathers_section.content_area.setEnabled(has_cylinder)
        if has_cylinder:
            self._apply_procedural(self.custom.text())
        self.guide_btn.setEnabled(bool(_by_role("feather")))
        if flare:
            self._pull_flare()
        if bend:
            self._pull_bend()

    def _select_cylinder(self):
        cyl = cylinder()
        if cyl:
            cmds.select(cyl)

    def _select_flare(self):
        self._select_deformer(flare_deformer())

    def _select_bend(self):
        self._select_deformer(bend_deformer())

    def _select_deformer(self, node):
        target = _deformer_handle(node) or node
        if target:
            cmds.select(target)

    def _show_xz(self, separate):
        self.start.setVisible(not separate)
        self.end.setVisible(not separate)
        for widget in (self.start_x, self.start_z, self.end_x, self.end_z):
            widget.setVisible(separate)

    def _toggle_separate(self, separate):
        if separate:
            self.start_x.setValue(self.start.value())
            self.start_z.setValue(self.start.value())
            self.end_x.setValue(self.end.value())
            self.end_z.setValue(self.end.value())
        else:
            self.start.setValue(self.start_x.value())
            self.end.setValue(self.end_x.value())
        self._show_xz(separate)
        self._push_flare()
        self.resize_to_fit()

    def _create(self):
        if _by_role("author"):
            choice = cmds.confirmDialog(
                title="Plume",
                message="Replace the existing cylinder and feathers?",
                button=["Replace", "Cancel"],
                defaultButton="Cancel",
                cancelButton="Cancel",
                dismissString="Cancel",
            )
            if choice != "Replace":
                cmds.select(cylinder())
                return
            clear_authoring()
        create_cylinder()
        self.separate.blockSignals(True)
        self.separate.setChecked(False)
        self.separate.blockSignals(False)
        self._show_xz(False)
        for slider, value in (
            (self.start, 1.0),
            (self.end, 1.0),
            (self.start_x, 1.0),
            (self.start_z, 1.0),
            (self.end_x, 1.0),
            (self.end_z, 1.0),
            (self.curve, 0.0),
            (self.bend, 0.0),
        ):
            slider.setValue(value)
        self.refresh()
        self.resize_to_fit()

    def _push_flare(self, *_args):
        if self._slider_drag:
            self._open_slider_chunk()
        if not cylinder():
            return
        if self.separate.isChecked():
            set_flare(
                self.start_x.value(),
                self.end_x.value(),
                self.curve.value(),
                self.start_z.value(),
                self.end_z.value(),
            )
        else:
            set_flare(self.start.value(), self.end.value(), self.curve.value())
        self.select_flare_btn.setVisible(flare_deformer() is not None)

    def _push_bend(self, *_args):
        if self._slider_drag:
            self._open_slider_chunk()
        if cylinder():
            set_bend(self.bend.value())
            self.select_bend_btn.setVisible(bend_deformer() is not None)

    def _pull_bend(self):
        node = bend_deformer()
        if node:
            self.bend.setValue(cmds.getAttr(node + ".curvature"))

    def _pull_flare(self):
        node = flare_deformer()
        if not node:
            return
        start_x = cmds.getAttr(node + ".startFlareX")
        start_z = cmds.getAttr(node + ".startFlareZ")
        end_x = cmds.getAttr(node + ".endFlareX")
        end_z = cmds.getAttr(node + ".endFlareZ")
        self.start_x.setValue(start_x)
        self.start_z.setValue(start_z)
        self.end_x.setValue(end_x)
        self.end_z.setValue(end_z)
        self.curve.setValue(cmds.getAttr(node + ".curve"))
        split = abs(start_x - start_z) > 0.0005 or abs(end_x - end_z) > 0.0005
        if split and not self.separate.isChecked():
            self.start.setValue(start_x)
            self.end.setValue(end_x)
            self.separate.blockSignals(True)
            self.separate.setChecked(True)
            self.separate.blockSignals(False)
            self._show_xz(True)
            self.resize_to_fit()
            return
        if not self.separate.isChecked():
            self.start.setValue(start_x)
            self.end.setValue(end_x)

    def _pick_mesh(self):
        for node in cmds.ls(selection=True, long=True) or []:
            if cmds.nodeType(node) == "mesh":
                node = cmds.listRelatives(node, parent=True, fullPath=True)[0]
            if _mesh_shape(node):
                self.custom.setText(node)
                return
        cmds.warning("Select a mesh to use as the feather.")

    def _apply_procedural(self, text):
        """Custom meshes keep their own outline. The edge curve is for procedural feathers."""
        procedural = not str(text).strip()
        self.edge_label.setEnabled(procedural)
        self.edge.setEnabled(procedural)

    def _generate(self):
        custom = self.custom.text().strip() or None
        variety = 0.0 if custom else self.variety.value()
        profile = None if custom else self.edge.widths()
        generate_feathers(
            self.rows.value(), self.columns.value(), custom, variety, profile
        )
        self.guide_btn.setEnabled(bool(_by_role("feather")))

    def _guide(self):
        create_guide()


def show():
    """Open the authoring dialog. Closes any dialog left open by a reload."""
    global _dialog
    try:
        if _dialog is not None:
            _dialog.close()
            _dialog.deleteLater()
    except Exception:
        pass

    app = QtWidgets.QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if widget.objectName() == UI_OBJECT_NAME:
                try:
                    widget.close()
                    widget.deleteLater()
                except Exception:
                    pass

    _dialog = Dialog(_main_window())
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    _dialog.resize_to_fit()
    QtCore.QTimer.singleShot(0, _dialog.resize_to_fit)
    return _dialog


def _main_window():
    import maya.OpenMayaUI as omui

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return QtCompat.wrapInstance(int(ptr), QtWidgets.QWidget)

#endregion
