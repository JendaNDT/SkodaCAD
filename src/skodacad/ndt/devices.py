"""Virtuální NDT zařízení (etapa 03): sonda a její přiložení na plochu dílu.

Obecná sonda – ne katalogová: **přímá** (válec Ø D × H, výstupní bod uprostřed kontaktní
plochy) a **úhlová** (kvádr L × W × H, výstupní bod ``front`` mm od čela, paprsek míří
dopředu). Sonda vždy dosedá kontaktní plochou do tečné roviny v bodě přiložení; souřadný
systém sondy: Z = normála plochy ven z materiálu, X = směr paprsku sklopený do tečné roviny,
Y = Z × X.

Kontroly přiložení jdou přes geometrické jádro (``geometry.PartGeometry``): mezera pod
kontaktní plochou (paprsky z bodů otisku kolmo dolů – přesně, ne vzorcem), přesah přes okraj
či otvor, kolize těla s dílem a vůle k překážkám **nad** rovinou přiložení (stěna díry nebo
vnitřek trubky pod sondou nejsou překážka). Mez mezery 0,5 mm odpovídá EN ISO 17640 (mezera
mezi povrchem a spodkem sondy nejvýš 0,5 mm) – jde změnit, nejde o tvrzení o normové shodě.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from skodacad.ndt.geometry import (
    LENGTH_TOL,
    OVERLAP_TOL,
    GeometryError,
    PartGeometry,
    Point,
    SurfacePoint,
)

DEFAULT_MAX_GAP = 0.5  # mm – EN ISO 17640: mezera pod sondou nejvýš 0,5 mm
DEFAULT_RESERVE = 0.0  # mm – manipulační rezerva (schváleno: jen fyzická kolize)
SEARCH_DEPTH = 10.0  # mm – hlouběji pod kontaktní plochou už povrch nehledá = přesah
LIFT = 1.0  # mm – paprsky otisku startují kousek nad rovinou přiložení
INSET = 0.01  # mm – krajní body otisku kousek dovnitř (hrana sondy přesně na hraně dílu)
SNAP = 1.0  # mm – jak daleko smí zadaný bod ležet od povrchu (přichytí se k němu)
KINDS = {"straight": "přímá sonda", "angle": "úhlová sonda"}
STATES = {"ok": "přiloženo", "tight": "málo místa", "lift_off": "nedosedá",
          "overhang": "přesahuje", "collision": "koliduje", "uncertain": "nejisté"}
_LIMITS = {"diameter": (1, 200), "length": (1, 500), "width": (1, 300), "height": (1, 1000),
           "front": (0, 500), "beam_angle": (1, 85), "bounces": (0, 10), "max_gap": (0, 50),
           "reserve": (0, 500)}
_LABELS = {"diameter": "Průměr sondy", "length": "Délka sondy", "width": "Šířka sondy",
           "height": "Výška sondy", "front": "Výstupní bod od čela",
           "beam_angle": "Úhel lomu v materiálu", "bounces": "Počet odrazů",
           "max_gap": "Dovolená mezera pod sondou", "reserve": "Manipulační rezerva"}
_UNITS = {"beam_angle": "°", "bounces": ""}


class DeviceError(ValueError):
    """Chybně zadaná sonda nebo přiložení (zpráva česky)."""


# --- sonda -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """Virtuální sonda (rozměry v mm, úhel lomu v °) a meze přiložení."""

    kind: str = "angle"  # straight / angle
    diameter: float = 10.0  # přímá: průměr kontaktní plochy
    length: float = 40.0  # úhlová: délka ve směru paprsku
    width: float = 20.0  # úhlová: šířka napříč
    height: float = 25.0  # výška těla
    front: float = 12.0  # úhlová: výstupní bod od čela
    beam_angle: float = 45.0  # úhlová: úhel lomu v materiálu od kolmice [°]
    bounces: int = -1  # počet odrazů (výchozí: 0 přímá, 1 úhlová)
    max_gap: float = DEFAULT_MAX_GAP
    reserve: float = DEFAULT_RESERVE

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise DeviceError(f"Druh sondy musí být „straight“ (přímá) nebo „angle“ (úhlová), "
                              f"je {self.kind!r}.")
        if self.bounces == -1:
            object.__setattr__(self, "bounces", 0 if self.kind == "straight" else 1)
        for key in self._keys():
            value = getattr(self, key)
            low, high = _LIMITS[key]
            unit = _UNITS.get(key, "mm")
            suffix = f" {unit}" if unit else ""
            if key == "bounces":
                if not isinstance(value, int) or isinstance(value, bool) or not (
                        low <= value <= high):
                    raise DeviceError(f"{_LABELS[key]} musí být celé číslo {low}–{high} "
                                      f"(je {value!r}).")
                continue
            if not isinstance(value, int | float) or isinstance(value, bool) or not (
                    low <= value <= high):
                raise DeviceError(f"{_LABELS[key]} musí být číslo {low:g}–{high:g}{suffix} "
                                  f"(je {value!r}).")
        if self.kind == "angle" and self.front > self.length:
            raise DeviceError(f"Výstupní bod ({self.front:g} mm od čela) musí ležet na sondě "
                              f"dlouhé {self.length:g} mm.")

    def _keys(self) -> tuple[str, ...]:
        shape = ("diameter",) if self.kind == "straight" else (
            "length", "width", "front", "beam_angle")
        return (*shape, "height", "bounces", "max_gap", "reserve")

    @classmethod
    def straight(cls, diameter: float = 10.0, height: float = 25.0, **limits: Any) -> Probe:
        return cls("straight", diameter=diameter, height=height, **limits)

    @classmethod
    def angle(cls, length: float = 40.0, width: float = 20.0, height: float = 25.0,
              front: float = 12.0, **limits: Any) -> Probe:
        return cls("angle", length=length, width=width, height=height, front=front, **limits)

    @classmethod
    def from_dict(cls, data: Any) -> Probe:
        """Sonda ze záznamu ve studii (``device``); chybějící hodnoty = výchozí."""
        if not isinstance(data, dict):
            raise DeviceError('Sonda („device“) musí být objekt {"kind": "angle", …}.')
        kind = data.get("kind", "angle")
        known = {"kind", *cls(kind if kind in KINDS else "angle")._keys()}
        unknown = sorted(set(data) - known)
        if unknown:
            raise DeviceError(f"Sonda: neznámá položka „{unknown[0]}“ (umím: "
                              f"{', '.join(sorted(known))}).")
        values = {key: value for key, value in data.items() if key != "kind"}
        return cls(kind, **values)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **{key: _clean(getattr(self, key)) for key in self._keys()}}

    @property
    def label(self) -> str:
        if self.kind == "straight":
            size = f"Ø {_num(self.diameter)} × {_num(self.height)} mm"
        else:
            size = (f"{_num(self.length)} × {_num(self.width)} × {_num(self.height)} mm, "
                    f"výstupní bod {_num(self.front)} mm od čela")
        return f"{KINDS[self.kind].capitalize()} {size}"

    def body(self) -> Any:
        """Tělo sondy v místních souřadnicích: kontaktní plocha z = 0, výstupní bod v počátku,
        paprsek míří po +X."""
        from build123d import Align, Box, Cylinder, Pos

        bottom = (Align.CENTER, Align.CENTER, Align.MIN)
        if self.kind == "straight":
            return Cylinder(self.diameter / 2, self.height, align=bottom)
        return Pos(self.front - self.length / 2, 0, 0) * Box(self.length, self.width,
                                                             self.height, align=bottom)

    def footprint(self) -> list[tuple[float, float]]:
        """Body kontaktní plochy (místní x, y), kde se měří mezera a přesah."""
        if self.kind == "straight":
            radius = self.diameter / 2 - INSET
            points = [(0.0, 0.0)]
            for ring in (radius / 2, radius):
                points += [(ring * math.cos(a), ring * math.sin(a))
                           for a in (k * math.pi / 6 for k in range(12))]
            return points
        xs = _spaced(self.front - self.length + INSET, self.front - INSET, 9)
        ys = _spaced(-self.width / 2 + INSET, self.width / 2 - INSET, 5)
        return [(x, y) for x in xs for y in ys]


# --- přiložení ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """Sonda přiložená na díl: stav, důvody a čísla (mm, mm³)."""

    probe: Probe
    state: str  # ok / tight / lift_off / overhang / collision / uncertain
    messages: tuple[str, ...]
    origin: Point  # výstupní bod paprsku (na povrchu)
    x_dir: Point  # směr paprsku v tečné rovině
    y_dir: Point
    z_dir: Point  # normála plochy ven z materiálu
    gap: float | None  # největší mezera pod sondou (None = pod sondou není povrch)
    overhang: float  # podíl kontaktní plochy bez povrchu pod sebou (0–1)
    volume: float  # průnik těla s dílem
    clearance: float | None  # vůle k překážkám nad rovinou přiložení (None = žádné nejsou)
    body: Any = field(default=None, compare=False, repr=False)  # těleso sondy v prostoru
    surface: SurfacePoint | None = field(default=None, compare=False, repr=False)

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    @property
    def label(self) -> str:
        return STATES[self.state]

    @property
    def text(self) -> str:
        return f"{self.label.capitalize()}. " + " ".join(self.messages)

    @property
    def short(self) -> str:
        """Krátký popisek do 3D (stav a hlavní číslo)."""
        detail = {
            "collision": f"{self.volume:.0f} mm³",
            "overhang": f"{self.overhang * 100:.0f} % mimo",
            "lift_off": f"mezera {self.gap or 0:.2f} mm",
            "tight": f"volno {self.clearance or 0:.1f} mm",
            "ok": (f"volno {self.clearance:.1f} mm" if self.clearance is not None
                   else "volno"),
        }.get(self.state, "")
        return f"{self.label} · {detail}" if detail else self.label


def place(geo: PartGeometry, probe: Probe, point: Any, beam: Any = None,
          angle: float | None = None, face: Any = None) -> Placement:
    """Přiloží sondu do bodu plochy (přichytí se k nejbližšímu povrchu, nebo k ``face``).

    Směr paprsku je ``beam`` (sklopí se do tečné roviny), nebo ``angle`` ve stupních: 0° =
    průmět osy +X do plochy (u plochy kolmé na X osa +Y), kladně proti směru hodin při
    pohledu na plochu zvenku. U přímé sondy směr jen natočí otisk.
    """
    from build123d import Location, Plane, Vector

    try:
        surface = geo.surface_at(point, face)
    except GeometryError as exc:
        raise DeviceError(str(exc)) from None
    if surface.distance > SNAP:
        raise DeviceError(f"Bod přiložení leží {surface.distance:.2f} mm od povrchu dílu – "
                          "klikni přímo na plochu.")
    normal = Vector(*surface.normal)
    if normal.length < 0.5:
        raise DeviceError("Směr plochy v bodě přiložení nejde určit – zkus jiné místo.")
    if angle is not None:
        base, turn = _tangent(normal, None, False), math.radians(float(angle))
        x_dir = (base * math.cos(turn) + normal.cross(base) * math.sin(turn)).normalized()
    else:
        x_dir = _tangent(normal, beam, probe.kind == "angle")
    plane = Plane(origin=Vector(*surface.point), x_dir=x_dir, z_dir=normal)
    templates = getattr(geo, "_probe_templates", None)
    if templates is None:
        templates = {}
        geo._probe_templates = templates
    if probe not in templates:
        templates[probe] = probe.body()
    body = Location(plane) * templates[probe]  # násobení polohou vytváří nový tvar

    gaps, contact, missing = [], 0, 0
    for sx, sy in probe.footprint():
        start = plane.from_local_coords((sx, sy, LIFT))
        ray = geo.cast(tuple(start), tuple(-normal), LIFT + SEARCH_DEPTH)
        if ray.segments and ray.segments[0].start <= LENGTH_TOL:
            contact += 1  # bod otisku je v materiálu – vyřeší kolize těla
            continue
        if not ray.hits:
            missing += 1
            continue
        contact += 1
        gaps.append(ray.hits[0].distance - LIFT)
    total = contact + missing
    overhang = missing / total if total else 1.0
    gap = max(gaps) if gaps else None
    clearance = _clearance_above(geo, body, surface.point, surface.normal)
    # Ořez pro vůli začíná 0,001 mm nad rovinou; drobnou kolizi tím nelze vyloučit.
    volume = geo.collision(body).volume

    messages, problems = [], []
    if volume > OVERLAP_TOL:
        problems.append("collision")
        messages.append(f"Průnik těla sondy s dílem {volume:.0f} mm³.")
    if missing:
        problems.append("overhang")
        messages.append(f"{overhang * 100:.0f} % kontaktní plochy nemá pod sebou povrch "
                        "(okraj nebo otvor).")
    if gap is not None and gap > probe.max_gap + LENGTH_TOL:
        problems.append("lift_off")
        messages.append(f"Mezera pod sondou {gap:.2f} mm, dovoleno {probe.max_gap:.2f} mm – "
                        "na zakřivené ploše je potřeba přizpůsobená předsádka nebo menší sonda.")
    if clearance is not None and clearance < probe.reserve - 1e-6 and "collision" not in problems:
        problems.append("tight")
        messages.append(f"Volno jen {clearance:.2f} mm, požadovaná rezerva "
                        f"{probe.reserve:.2f} mm.")
    if surface.reasons:
        problems.append("uncertain")
        messages += list(surface.reasons)
    order = ("collision", "overhang", "lift_off", "tight", "uncertain")
    state = next((s for s in order if s in problems), "ok")
    if state == "ok":
        free = (f"volno k překážkám {clearance:.2f} mm" if clearance is not None
                else "kolem žádné překážky")
        messages.append(f"Mezera pod sondou {gap or 0:.2f} mm, {free}.")
    return Placement(probe, state, tuple(messages), surface.point, _tuple(x_dir),
                     _tuple(normal.cross(x_dir)), _tuple(normal), gap, overhang, volume,
                     clearance, body, surface)


@dataclass(frozen=True)
class ScanResult:
    """Posun sondy po přímce: přiložení v každém kroku a úseky, kde sonda volně jede."""

    positions: tuple[tuple[float, Placement], ...]  # (posun od začátku [mm], přiložení)
    free_ranges: tuple[tuple[float, float], ...]  # [(od, do)] mm – stav „přiloženo“

    @property
    def summary(self) -> str:
        """Český souhrn volných úseků a první potíže pro okno."""
        free = ", ".join(f"{a:g}–{b:g} mm" for a, b in self.free_ranges) or "nikde"
        text = f"Volně: {free}."
        problem = next(((offset, p) for offset, p in self.positions if not p.ok), None)
        if problem is not None:
            text += f" První potíž po {problem[0]:g} mm: {problem[1].text}"
        return text


def scan_line(geo: PartGeometry, probe: Probe, start: Any, beam: Any = None, move: Any = None,
              length: float = 50.0, step: float = 1.0, angle: float | None = None,
              face: Any = None) -> ScanResult:
    """Posouvá sondu od ``start`` směrem ``move`` (výchozí = směr paprsku) po krocích ``step``
    až do ``length`` mm (každá poloha se přichytí k povrchu) a najde úseky, kde jde volně
    přiložit."""
    from build123d import Vector

    if not step > 0 or not length >= 0:
        raise DeviceError("Krok posunu musí být kladný a délka nezáporná.")
    origin = Vector(*_vector(start, "Začátek posunu"))
    first = place(geo, probe, tuple(origin), beam, angle=angle, face=face)
    if move is None:
        direction = Vector(*first.x_dir)
    else:
        direction = Vector(*_vector(move, "Směr posunu"))
        if direction.length < 1e-12:
            raise DeviceError("Směr posunu nesmí být nulový.")
        direction = direction.normalized()
    count = int(math.floor(length / step + 1e-9))
    positions = [(0.0, first)]
    for index in range(1, count + 1):
        offset = index * step
        positions.append((
            offset,
            place(geo, probe, tuple(origin + direction * offset), beam, angle=angle, face=face),
        ))
    ranges: list[tuple[float, float]] = []
    for offset, placed in positions:
        if not placed.ok:
            continue
        if ranges and abs(ranges[-1][1] - (offset - step)) < 1e-9:
            ranges[-1] = (ranges[-1][0], offset)
        else:
            ranges.append((offset, offset))
    return ScanResult(tuple(positions), tuple(ranges))


# --- pomocné výpočty -----------------------------------------------------------------------


def _clearance_above(geo: PartGeometry, body: Any, origin: Point, normal: Point
                     ) -> float | None:
    """Nejmenší vzdálenost těla sondy k části dílu **nad** rovinou přiložení (None = nic tam
    není). Co leží pod rovinou (stěna díry, vnitřek trubky), sondě nepřekáží."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    upper = _upper_part(geo, origin, normal)
    if upper is None:
        return None
    distance = BRepExtrema_DistShapeShape(upper, body.wrapped)
    return distance.Value() if distance.IsDone() and distance.NbSolution() else None


def _upper_part(geo: PartGeometry, origin: Point, normal: Point) -> Any | None:
    """Část dílu nad tečnou rovinou (ořezaná jednou pro každou rovinu na dílu)."""
    from build123d import Align, Box, Location, Plane, Vector
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    offset = sum(o * n for o, n in zip(origin, normal, strict=True))
    key = (round(normal[0], 5), round(normal[1], 5), round(normal[2], 5), round(offset, 4))
    cache = getattr(geo, "_upper_cache", None)
    if cache is None:
        cache = {}
        object.__setattr__(geo, "_upper_cache", cache)
    if key in cache:
        return cache[key]
    box = geo.part.bounding_box()
    size = 4 * (box.diagonal + 10)
    center = Vector(box.center())
    n_vec = Vector(*normal)
    plane_origin = center + n_vec * (offset - center.dot(n_vec) + 1e-3)
    half = Location(Plane(origin=plane_origin, z_dir=n_vec)) * Box(
        size, size, size, align=(Align.CENTER, Align.CENTER, Align.MIN))
    common = BRepAlgoAPI_Common(geo.part.wrapped, half.wrapped)
    upper = None
    if common.IsDone():
        shape = common.Shape()
        if TopExp_Explorer(shape, TopAbs_FACE).More():
            upper = shape
    cache[key] = upper
    return upper


def _tangent(normal: Any, beam: Any, required: bool) -> Any:
    """Směr paprsku sklopený do tečné roviny (jednotkový). Bez směru (přímá sonda): průmět
    globální osy X, u plochy kolmé na X osy Y."""
    from build123d import Vector

    candidates = [beam] if beam is not None else []
    if not required or beam is None:
        candidates += [(1, 0, 0), (0, 1, 0)]
    for candidate in candidates:
        vector = Vector(*_vector(candidate, "Směr paprsku"))
        projected = vector - normal * vector.dot(normal)
        if projected.length > 1e-6 * max(1.0, vector.length):
            return projected.normalized()
        if required and candidate is beam:
            raise DeviceError("Směr paprsku míří kolmo do plochy – úhlová sonda potřebuje "
                              "směr podél plochy.")
    raise DeviceError("Směr paprsku nejde určit.")


def _vector(value: Any, what: str) -> Point:
    try:
        x, y, z = (float(v) for v in value)
    except (TypeError, ValueError):
        raise DeviceError(f"{what} musí být tři čísla [x, y, z].") from None
    return (x, y, z)


def _spaced(low: float, high: float, count: int) -> list[float]:
    return [low + (high - low) * i / (count - 1) for i in range(count)]


def _tuple(vector: Any) -> Point:
    return (vector.X, vector.Y, vector.Z)


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _clean(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def with_limits(probe: Probe, max_gap: float | None = None, reserve: float | None = None
                ) -> Probe:
    """Kopie sondy s jinými mezemi přiložení."""
    changes = {key: value for key, value in (("max_gap", max_gap), ("reserve", reserve))
               if value is not None}
    return replace(probe, **changes)
