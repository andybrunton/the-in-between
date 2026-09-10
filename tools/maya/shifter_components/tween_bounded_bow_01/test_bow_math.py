"""Self-check for bow_math. Run with: python test_bow_math.py (no Maya needed)."""

import bow_math


def reference_bezier(u, length, height, tangent_weight):
    """Straight cubic bezier evaluation, the thing bow_math is a refactor of."""
    s = 0.5 * length * tangent_weight
    pts = [(0.0, 0.0), (s, height), (length - s, height), (length, 0.0)]
    v = 1.0 - u
    basis = [v**3, 3 * v**2 * u, 3 * v * u**2, u**3]
    return (
        sum(w * p[0] for w, p in zip(basis, pts)),
        sum(w * p[1] for w, p in zip(basis, pts)),
    )


def main():
    length, height, tangent = 42.0, 18.0, 0.55

    for i in range(21):
        u = i / 20.0
        got = bow_math.sample(u, length, height, tangent)
        want = reference_bezier(u, length, height, tangent)
        assert abs(got[0] - want[0]) < 1e-9, (u, got, want)
        assert abs(got[1] - want[1]) < 1e-9, (u, got, want)

    # Endpoints pin to the chord regardless of bulge or tangent settings.
    for tw in (0.0, 0.55, 1.0):
        assert bow_math.sample(0.0, length, height, tw) == (0.0, 0.0)
        assert bow_math.sample(1.0, length, height, tw) == (length, 0.0)

    # Apex matches the card's de Casteljau midpoint: 0.75 * h at the halfway point.
    mid = bow_math.sample(0.5, length, height, tangent)
    assert abs(mid[0] - length * 0.5) < 1e-9, mid
    assert abs(mid[1] - height * 0.75) < 1e-9, mid

    assert bow_math.params(2) == [0.0, 1.0]
    assert bow_math.params(5)[2] == 0.5

    print("bow_math OK")


if __name__ == "__main__":
    main()
