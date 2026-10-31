"""Číselná pomoc pro tažení v rovině XY; bez modelování i bez OCCT/Qt."""

import math


def on_xy_plane(ray, height):
    """Průsečík pohledového paprsku s XY; téměř boční pohled je neprůkazný."""
    if len(ray) != 6 or not all(math.isfinite(v) for v in (*ray, height)):
        return None
    x, y, z, dx, dy, dz = ray
    length = math.hypot(dx, dy, dz)
    if length == 0 or abs(dz) / length < 1e-3:
        return None
    t = (height-z)/dz
    result = (x+t*dx, y+t*dy)
    return result if all(math.isfinite(v) for v in result) else None


def nearest_handle(points, cursor, radius=12):
    """Logické body obrazovky; −1 označuje překryté nerozlišitelné rukojeti."""
    distances = sorted((math.dist(p, cursor), i) for i, p in enumerate(points))
    if not distances or distances[0][0] > radius:
        return None
    if len(distances) > 1 and distances[1][0] <= radius \
            and distances[1][0] - distances[0][0] < 1:
        return -1
    return distances[0][1]
