"""Číselná pomoc rotačních prstenců; bez Qt, OCCT a bez změn modelu."""

import math

from skodacad.assembly_build import axis_direction
from skodacad.gui.guide_drag import snapped_delta

DEFAULT_ANGLE_STEP = 15.0
MIN_FACING = .15  # téměř boční prstenec nemá bezpečně určitelný úhel


def plane_axes(axis):
    """Pravotočivý rám prstence: u × v = kladná osa otáčení."""
    if axis not in (0, 1, 2):
        raise ValueError("Osa otočení musí být X, Y nebo Z.")
    return (axis+1) % 3, (axis+2) % 3


def ring_points(center, axis, radius, segments=96):
    _normal, u, v = plane_frame(axis)
    points = []
    for index in range(segments+1):
        angle = index*2*math.pi/segments
        points.append(tuple(c+radius*(a*math.cos(angle)+b*math.sin(angle))
                            for c, a, b in zip(center, u, v, strict=True)))
    return points


def plane_frame(axis):
    """Pravotočivý ortonormální rám i pro libovolný směr převzatého válce."""
    if isinstance(axis, int):
        a, b = plane_axes(axis)
        return tuple(tuple(float(j == i) for j in range(3)) for i in (axis, a, b))
    n = axis_direction(axis)
    index = min(range(3), key=lambda i: abs(n[i]))
    u = tuple(float(i == index)-n[index]*n[i] for i in range(3))
    length = math.hypot(*u)
    u = tuple(v/length for v in u)
    v = (n[1]*u[2]-n[2]*u[1], n[2]*u[0]-n[0]*u[2], n[0]*u[1]-n[1]*u[0])
    return n, u, v


def angle_on_plane(ray, center, axis, min_radius=0.):
    """Úhel paprsku v rovině prstence, stupně; boční pohled a střed jsou neurčité."""
    normal, u, v = plane_frame(axis)
    if (len(ray) != 6 or len(center) != 3
            or not all(math.isfinite(x) for x in (*ray, *center, min_radius))):
        return None
    length = math.hypot(*ray[3:])
    dot = sum(a*b for a, b in zip(normal, ray[3:], strict=True))
    if not length or abs(dot)/length < MIN_FACING:
        return None
    t = sum((c-p)*n for c, p, n in zip(center, ray[:3], normal, strict=True))/dot
    offset = tuple(p+t*d-c for p, d, c in zip(ray[:3], ray[3:], center, strict=True))
    x, y = (sum(a*b for a, b in zip(offset, basis, strict=True)) for basis in (u, v))
    if not all(math.isfinite(w) for w in (x, y)) or math.hypot(x, y) <= min_radius:
        return None
    return math.degrees(math.atan2(y, x))


def advance_angle(previous, current, total):
    """Rozbalení přechodu ±180°; po sobě jdoucí polohy dovolují více celých otáček."""
    return total+math.remainder(current-previous, 360.)


def snapped_angle(angle, step):
    if not math.isfinite(step) or not 0 <= step <= 180:
        raise ValueError("Krok otáčení musí být od 0 do 180°; 0 znamená Volně.")
    # Zbytky úhlové projekce nesmějí vytvořit změnu při návratu na 0/360°.
    return round(snapped_delta((round(angle, 9),), step)[0], 9)


def segment_distance(point, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length2 = dx*dx+dy*dy
    t = max(0., min(1., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length2)) if length2 else 0.
    return math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy)


def nearest_ring(rings, cursor, radius=8.):
    """Logické body obrazovky; −1 je nerozlišitelné křížení dvou prstenců."""
    distances = sorted((min((segment_distance(cursor, a, b)
                             for a, b in zip(points, points[1:], strict=False)),
                            default=math.inf), index) for index, points in enumerate(rings))
    if not distances or distances[0][0] > radius:
        return None
    if len(distances) > 1 and distances[1][0] <= radius \
            and distances[1][0]-distances[0][0] < 1.5:
        return -1
    return distances[0][1]
