"""Číselná pomoc pro tažení v rovině XY; bez modelování i bez OCCT/Qt."""

import math
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_STEP = 0.0  # stejné volné tažení jako dosud
MAX_STEP = 1000.0
DEFAULT_DIRECTION = "XY"
DIRECTION_CHOICES = (("XY", "XY (obě osy)"), ("X", "Pouze X"), ("Y", "Pouze Y"))


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


def axis_parameter(ray, anchor, direction):
    """Souřadnice nejbližšího bodu na ose vůči pohledovému paprsku.

    Osa prochází rukojetí, parametr je v mm od ní. Projekčně zaniklá osa je nejistá.
    Od počátečního parametru se při tahu odečte počátek uchopení (bez poskočení).
    """
    if direction not in ("X", "Y"):
        raise ValueError("Jedna osa tažení musí být X nebo Y.")
    if len(ray) != 6 or len(anchor) != 3 or not all(math.isfinite(v) for v in (*ray, *anchor)):
        return None
    length = math.hypot(*ray[3:])
    if not math.isfinite(length) or length == 0:
        return None
    d = [v/length for v in ray[3:]]
    axis = 0 if direction == "X" else 1
    others = [i for i in range(3) if i != axis]
    denominator = math.fsum(d[i]*d[i] for i in others)
    if denominator < 1e-6:  # sin² úhlu paprsku a osy; nekancelovat 1 - d[axis]²
        return None
    q = [v-a for v, a in zip(ray[:3], anchor, strict=True)]
    value = q[axis] - d[axis]*math.fsum(q[i]*d[i] for i in others)/denominator
    return value if math.isfinite(value) else None


def nearest_handle(points, cursor, radius=12):
    """Logické body obrazovky; −1 označuje překryté nerozlišitelné rukojeti."""
    distances = sorted((math.dist(p, cursor), i) for i, p in enumerate(points))
    if not distances or distances[0][0] > radius:
        return None
    if len(distances) > 1 and distances[1][0] <= radius \
            and distances[1][0] - distances[0][0] < 1:
        return -1
    return distances[0][1]


def snapped_delta(delta, step):
    """Posun po XY od začátku tahu; přesná polovina kroku se zaokrouhlí od nuly.

    Desítková aritmetika zabrání zbytkům typu 0.30000000000000004 ve výrazu modelu.
    Výsledek se znovu předá jádru jako běžná dvojice floatů.
    """
    if not math.isfinite(step) or not 0 <= step <= MAX_STEP:
        raise ValueError("Krok tažení musí být v rozsahu 0 až 1000 mm; 0 znamená Volně.")
    if not all(math.isfinite(v) for v in delta):
        raise ValueError("Posun rukojeti musí být konečný.")
    if step == 0:
        return tuple(delta)
    quantum = Decimal(str(step))
    result = tuple(float((Decimal(str(v))/quantum).to_integral_value(rounding=ROUND_HALF_UP)
                         * quantum) for v in delta)
    return tuple(0.0 if v == 0 else v for v in result)


def constrained_delta(delta, step, direction=DEFAULT_DIRECTION):
    """Přichycený posun po souřadnicích dílu; druhá souřadnice při zámku zůstane nulová."""
    if direction not in ("XY", "X", "Y"):
        raise ValueError("Směr tažení musí být XY, X nebo Y.")
    x, y = snapped_delta(delta, step)
    return (0.0 if direction == "Y" else x, 0.0 if direction == "X" else y)
