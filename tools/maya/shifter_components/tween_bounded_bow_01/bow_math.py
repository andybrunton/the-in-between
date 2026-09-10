"""Pure-python bow geometry. No Maya imports so it can be unit tested standalone.

Chord space: start at origin, end at (L, 0, 0), bulge along +Y.
Cubic bezier from the Bounded_Bow card:

    P0 = (0, 0)              P1 = (s, h)
    P2 = (L - s, h)          P3 = (L, 0)      with s = 0.5 * L * tangentWeight

Expanding B(u) and collecting terms lets the rig drive each point with a handful of
constant coefficients instead of a live curve:

    x(u) = L * (kx_tangent(u) * tangentWeight + kx_base(u))
    y(u) = h * ky(u)
"""


def bezier_coefficients(u):
    """Constant per-point coefficients (kx_tangent, kx_base, ky) for parameter u."""
    a = 3.0 * (1.0 - u) ** 2 * u
    b = 3.0 * (1.0 - u) * u**2
    c = u**3
    return 0.5 * (a - b), b + c, a + b


def sample(u, length, height, tangent_weight):
    """Point on the bow at u, as (x, y)."""
    kx_tangent, kx_base, ky = bezier_coefficients(u)
    return length * (kx_tangent * tangent_weight + kx_base), height * ky


def params(divisions):
    """Evenly spaced u values for a chain of `divisions` joints."""
    if divisions < 2:
        raise ValueError("bounded bow needs at least 2 divisions")
    return [i / float(divisions - 1) for i in range(divisions)]
