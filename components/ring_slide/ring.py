"""Slide one closed loop along another. Pure functions, checked at import.

Points stay in whatever space the caller used. `turn` is a fraction of the
under loop's length: 0 is rest, 1 is a full lap, and values wrap.

The offset is stored in a frame that travels with the loop (tangent, the
ring normal, and their cross). A circle, an oval, and a bent loop all keep
that offset, because nothing here fits a circle.
"""

import math


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, scale):
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    size = length(a)
    if size < 1e-8:
        return None
    return mul(a, 1.0 / size)


def centroid(points):
    count = float(len(points))
    return (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
        sum(point[2] for point in points) / count,
    )


def newell(points):
    """Unit normal of a closed loop. The loop is in order and not repeated."""
    x = y = z = 0.0
    count = len(points)
    for index in range(count):
        a = points[index]
        b = points[(index + 1) % count]
        x += (a[1] - b[1]) * (a[2] + b[2])
        y += (a[2] - b[2]) * (a[0] + b[0])
        z += (a[0] - b[0]) * (a[1] + b[1])
    return norm((x, y, z))


def _side_axis(normal):
    """World axis that lies flattest in the plane, so the control sits square."""
    chosen = None
    best = 0.0
    for axis in ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)):
        flat = sub(axis, mul(normal, dot(axis, normal)))
        size = length(flat)
        if size > best:
            best = size
            chosen = norm(flat)
    return chosen


def guide_frame(over_points, under_points):
    """(origin, x, y, z). Y is the ring's plane normal, toward the over ring.

    Not the line between the two centroids: adjacent loops sit almost on top
    of each other, so that line is noise, and the twist turns about Y.
    X is a world axis laid into the plane, not the first vertex, so the
    control is not rolled.
    """
    if len(over_points) < 3:
        return None
    origin = centroid(over_points)
    y = newell(under_points if len(under_points) >= 3 else over_points)
    if y is None:
        return None
    if under_points and dot(y, sub(origin, centroid(under_points))) < 0.0:
        y = mul(y, -1.0)
    x = _side_axis(y)
    if x is None:
        return None
    z = norm(cross(x, y))
    if z is None:
        return None
    return origin, x, y, z


def shell_turn(size, other_size, mean, seam):
    """Share of the head's turn a mesh shell takes at a seam.

    size and other_size are vertex counts of the shell on this side of the
    seam and on the far side, mean the shell's average fraction along base to
    tip (0 base, 1 tip), seam the seam's own fraction. The bigger shell is
    the head or the chest, by which side of the seam its bulk lies: 1 or 0.
    The smaller one is neck and turns by the seam's own place. Ranges would
    not do: a tilted ring dips past the chest control.
    """
    if size <= other_size:
        return seam
    return 1.0 if mean > seam else 0.0


def loop_frame(points):
    """(origin, x, y, z). Y is the loop normal. X aims at the first point."""
    if len(points) < 3:
        return None
    origin = centroid(points)
    y = newell(points)
    if y is None:
        return None
    side = sub(points[0], origin)
    side = sub(side, mul(y, dot(side, y)))
    x = norm(side)
    if x is None:
        return None
    z = norm(cross(x, y))
    if z is None:
        return None
    return origin, x, y, z


def to_local(point, origin, x, y, z):
    delta = sub(point, origin)
    return (dot(delta, x), dot(delta, y), dot(delta, z))


def to_world(local, origin, x, y, z):
    return add(
        origin,
        add(add(mul(x, local[0]), mul(y, local[1])), mul(z, local[2])),
    )


def _spans(points):
    spans = []
    total = 0.0
    count = len(points)
    for index in range(count):
        a = points[index]
        b = points[(index + 1) % count]
        span = length(sub(b, a))
        spans.append((a, b, span, total))
        total += span
    return spans, total


def _at_distance(spans, total, distance):
    if total < 1e-8:
        return None
    distance = distance % total
    for start, end, span, origin in spans:
        if span < 1e-8:
            continue
        if distance <= origin + span + 1e-7:
            t = min(1.0, max(0.0, (distance - origin) / span))
            pos = add(start, mul(sub(end, start), t))
            tan = norm(sub(end, start)) or (1.0, 0.0, 0.0)
            return pos, tan
    start, end = spans[-1][0], spans[-1][1]
    return start, norm(sub(end, start)) or (1.0, 0.0, 0.0)


def chain_fraction(point, points):
    """Arc-length fraction of the nearest point on an open chain. 0 is the start."""
    spans = []
    total = 0.0
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        span = length(sub(end, start))
        spans.append((start, end, span, total))
        total += span
    if total < 1e-8:
        return 0.0
    best = None
    found = 0.0
    for start, end, span, origin in spans:
        if span < 1e-8:
            continue
        edge = sub(end, start)
        t = dot(sub(point, start), edge) / (span * span)
        t = min(1.0, max(0.0, t))
        pos = add(start, mul(edge, t))
        dist = length(sub(point, pos))
        if best is None or dist < best:
            best = dist
            found = (origin + span * t) / total
    return found


def closest_fraction(point, loop):
    """Arc-length fraction of the nearest point on the closed loop."""
    spans, total = _spans(loop)
    if total < 1e-8:
        return 0.0
    best = None
    found = 0.0
    for start, end, span, origin in spans:
        if span < 1e-8:
            continue
        edge = sub(end, start)
        t = dot(sub(point, start), edge) / (span * span)
        t = min(1.0, max(0.0, t))
        pos = add(start, mul(edge, t))
        dist = length(sub(point, pos))
        if best is None or dist < best:
            best = dist
            found = (origin + span * t) / total
    return found


def sample_loop(loop, fraction):
    """(position, tangent) at an arc-length fraction. The fraction wraps."""
    spans, total = _spans(loop)
    if total < 1e-8:
        return loop[0], (1.0, 0.0, 0.0)
    return _at_distance(spans, total, (fraction % 1.0) * total)


def _track(tangent, normal):
    flat = sub(tangent, mul(normal, dot(tangent, normal)))
    aim = norm(flat)
    if aim is None:
        hint = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 0.0, 1.0)
        aim = norm(cross(normal, hint))
    if aim is None:
        return None
    side = norm(cross(normal, aim))
    if side is None:
        return None
    return aim, normal, side


def slide_sample(point, loop, normal, turn):
    """(slid position, point on the loop it was measured from)."""
    rest = closest_fraction(point, loop)
    origin, tangent = sample_loop(loop, rest)
    frame = _track(tangent, normal)
    if frame is None:
        return point, origin
    aim, up, side = frame
    delta = sub(point, origin)
    offset = (dot(delta, aim), dot(delta, up), dot(delta, side))
    moved, moved_tan = sample_loop(loop, rest + turn)
    frame = _track(moved_tan, normal)
    if frame is None:
        return point, moved
    aim, up, side = frame
    placed = add(
        moved,
        add(add(mul(aim, offset[0]), mul(up, offset[1])), mul(side, offset[2])),
    )
    return placed, moved


def slide_position(point, loop, normal, turn):
    """`point` after sliding `turn` loops along `loop`."""
    return slide_sample(point, loop, normal, turn)[0]


def vertex_fractions(loop):
    spans, total = _spans(loop)
    if total < 1e-8:
        return [0.0]
    return [origin / total for _start, _end, _span, origin in spans]


def twist_sign(point, loop, normal):
    """+1 or -1 so a positive turn matches Maya's positive rotateY.

    `point` and `loop` are in the control frame. Maya's rotateY sends
    (x, y, z) toward (z, 0, -x). The edge walk may run the other way.
    """
    delta = sub(slide_position(point, loop, normal, 0.05), point)
    expect = (point[2], 0.0, -point[0])
    if dot(delta, expect) < 0.0:
        return -1.0
    return 1.0


def slide_keys(point, loop, normal, sign=1.0):
    """(degrees, position) for one lap, including 0 and 360.

    ponytail: keys at the under vertices. Along one straight edge the
    traveling frame is constant, so linear interpolation is the slide.
    A curved edge between captured vertices would chord; the loop is the
    vertices, so that is the whole shape.
    """
    rest = closest_fraction(point, loop)
    home = slide_position(point, loop, normal, 0.0)
    fractions = [0.0]
    for vert in vertex_fractions(loop):
        fraction = (vert - rest) % 1.0
        if 1e-5 < fraction < 1.0 - 1e-5:
            fractions.append(fraction)
    fractions = sorted(set(fractions))
    keys = [(0.0, home)]
    for fraction in fractions:
        if fraction < 1e-5:
            continue
        keys.append((fraction * 360.0, slide_position(point, loop, normal, sign * fraction)))
    keys.append((360.0, home))
    return keys


def _dist(a, b):
    return length(sub(a, b))


def _circle(count, radius, y=0.0):
    points = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        points.append((radius * math.cos(angle), y, radius * math.sin(angle)))
    return points


def _check():
    normal = (0.0, 1.0, 0.0)
    under = _circle(8, 1.0)
    over = (1.0, 0.4, 0.0)
    assert _dist(slide_position(over, under, normal, 0.0), over) < 1e-6
    assert _dist(slide_position(over, under, normal, 1.0), over) < 1e-6
    assert _dist(slide_position(over, under, normal, 0.5), (-1.0, 0.4, 0.0)) < 1e-4
    assert _dist(
        slide_position(over, under, normal, 1.25),
        slide_position(over, under, normal, 0.25),
    ) < 1e-6

    ellipse = []
    for index in range(12):
        angle = 2.0 * math.pi * index / 12.0
        ellipse.append((2.2 * math.cos(angle), 0.0, 0.7 * math.sin(angle)))
    samples = []
    for index, point in enumerate(ellipse):
        flat = norm((point[0], 0.0, point[2]))
        lifted = add(add(point, (0.0, 0.25, 0.0)), mul(flat, 0.1))
        home_len = None
        home_up = None
        for turn in (0.0, 0.17, 0.5, 0.83, 1.0):
            placed, sampled = slide_sample(lifted, ellipse, normal, turn)
            delta = sub(placed, sampled)
            up = dot(delta, normal)
            size = length(delta)
            if home_len is None:
                home_len = size
                home_up = up
            assert abs(size - home_len) < 1e-5
            assert abs(up - home_up) < 1e-5
            if turn in (0.0, 1.0):
                assert _dist(placed, lifted) < 1e-5
        samples.append(index)
    assert len(samples) == 12

    bumped = _circle(8, 2.0)
    bumped[3] = (bumped[3][0], 1.1, bumped[3][2])
    above = (bumped[0][0], bumped[0][1] + 0.4, bumped[0][2])
    turn = vertex_fractions(bumped)[3]
    placed, sampled = slide_sample(above, bumped, normal, turn)
    assert abs(sampled[1] - 1.1) < 1e-5
    assert abs(placed[1] - 1.5) < 1e-5

    assert twist_sign((1.0, 0.0, 0.0), under, normal) == -1.0
    assert twist_sign((1.0, 0.0, 0.0), list(reversed(under)), normal) == 1.0
    high = [(point[0], 2.0, point[2]) for point in under]
    low = [(point[0], 0.0, point[2]) for point in under]
    origin, x, y, z = guide_frame(high, low)
    assert _dist(origin, (0.0, 2.0, 0.0)) < 1e-6
    assert abs(y[1] - 1.0) < 1e-6
    assert abs(x[0] - 1.0) < 1e-6
    assert abs(dot(z, cross(x, y)) - 1.0) < 1e-6
    # A tilted over loop beside the under loop: Y stays the ring normal.
    skewed = [(point[0] + 0.5, 0.01, point[2]) for point in under]
    assert guide_frame(skewed, under)[2][1] > 0.999
    assert shell_turn(3600, 44, 1.6, 0.75) == 1.0
    assert shell_turn(3500, 44, -1.0, 0.1) == 0.0
    assert shell_turn(44, 3600, 0.45, 0.73) == 0.73
    assert shell_turn(44, 44, 0.45, 0.73) == 0.73
    chain = [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 4.0, 0.0)]
    assert abs(chain_fraction((0.0, 1.0, 0.0), chain) - 0.25) < 1e-6
    assert chain_fraction((0.0, -1.0, 0.0), chain) == 0.0
    assert abs(chain_fraction((0.0, 5.0, 0.0), chain) - 1.0) < 1e-6


_check()
