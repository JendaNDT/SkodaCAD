"""Mapa tloušťky stěny (NDT): tloušťka v hustě rozmístěných bodech po celém povrchu dílu.

Povrch se rozdělí na malé trojúhelníky (každá plocha zvlášť, nejdelší strana nejvýš
``step`` mm) a v těžišti každého trojúhelníku se tloušťka změří stejně jako u měření
v bodě: paprsek kolmo do materiálu až k protější ploše (jako ultrazvukový tloušťkoměr).
Okno trojúhelníky obarví podle tloušťky, příkazová řádka vypíše souhrn a uloží CSV.

Barvy: od červené (nejtenčí) přes žlutou a zelenou po modrou (horní mez škály, výchozí je
nejčastější tloušťka dílu = jmenovitá stěna). Pod minimální dovolenou tloušťkou fialová,
bez materiálu za plochou šedá.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from skodacad.inspection import number
from skodacad.measure import RayCaster

Point = tuple[float, float, float]
Color = tuple[float, float, float]

TARGET_TRIANGLES = 30_000  # automatická jemnost: zhruba tolik bodů (pár sekund výpočtu)
_AREA_PER_STEP2 = 0.045  # průměrný trojúhelník po půlení má obsah asi 0,045 · krok² (změřeno)
MIN_STEP = 0.2  # mm – jemněji se nepočítá (počet bodů by explodoval)
MAX_TRIANGLES = 400_000

BELOW_LIMIT: Color = (0.85, 0.0, 0.85)  # fialová – pod minimální dovolenou tloušťkou
NO_MATERIAL: Color = (0.6, 0.6, 0.6)  # šedá – paprsek nenašel protější stěnu
SCALE: tuple[tuple[float, Color], ...] = (  # od nejtenčí (0) po horní mez škály (1)
    (0.0, (0.85, 0.10, 0.10)),
    (0.33, (0.95, 0.85, 0.10)),
    (0.67, (0.15, 0.70, 0.25)),
    (1.0, (0.15, 0.35, 0.90)),
)


class MapError(ValueError):
    """Mapa nejde spočítat nebo má chybné nastavení (zpráva je česky)."""


@dataclass(frozen=True)
class MapSettings:
    """Nastavení mapy uložené v modelu (``Document.thickness_map``)."""

    limit: float | None = None  # minimální dovolená tloušťka [mm]
    step: float | None = None  # vzdálenost bodů [mm], None = automaticky
    scale_max: float | None = None  # horní mez škály [mm], None = nejčastější tloušťka

    @classmethod
    def from_dict(cls, data: Any) -> MapSettings:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise MapError("„thickness_map“ musí být objekt, např. {\"limit\": 4}.")
        unknown = set(data) - {"limit", "step", "scale_max"}
        if unknown:
            raise MapError(f"Neznámé nastavení mapy tloušťky: {', '.join(sorted(unknown))} "
                           "(umím limit, step, scale_max).")
        values = {}
        for key, label in (("limit", "Minimální tloušťka"), ("step", "Jemnost (krok bodů)"),
                           ("scale_max", "Horní mez škály")):
            value = data.get(key)
            if value is None:
                values[key] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise MapError(f"{label} mapy tloušťky musí být kladné číslo v mm "
                               f"(je {value!r}).")
            values[key] = float(value)
        return cls(**values)

    def to_dict(self) -> dict[str, float]:
        return {key: value for key, value in (("limit", self.limit), ("step", self.step),
                                              ("scale_max", self.scale_max))
                if value is not None}


@dataclass(frozen=True)
class ThicknessMap:
    """Spočítaná mapa: trojúhelníky povrchu a tloušťka v jejich těžištích.

    Souhrnné hodnoty (minimum, nejčastější tloušťka …) se počítají jednou a pamatují
    (``cached_property``) – barvení desítek tisíc uzlů by je jinak počítalo znovu a znovu.
    """

    nodes: list[Point]
    triangles: list[tuple[int, int, int]]  # indexy do ``nodes`` (od 0), vně proti hodinám
    centers: list[Point]  # těžiště trojúhelníků – tam se měřilo
    values: list[float | None]  # tloušťka v těžišti, None = za plochou není materiál
    areas: list[float]  # obsah trojúhelníku [mm²]
    step: float
    settings: MapSettings = field(default_factory=MapSettings)
    seconds: float = 0.0

    # --- souhrn ---------------------------------------------------------------------

    @cached_property
    def measured(self) -> list[float]:
        return [v for v in self.values if v is not None]

    @cached_property
    def minimum(self) -> float | None:
        return min(self.measured, default=None)

    @cached_property
    def maximum(self) -> float | None:
        return max(self.measured, default=None)

    @cached_property
    def thinnest(self) -> Point | None:
        """Kde je stěna nejtenčí (těžiště trojúhelníku s nejmenší tloušťkou)."""
        found = [(v, c) for v, c in zip(self.values, self.centers, strict=True) if v is not None]
        return min(found)[1] if found else None

    @cached_property
    def nominal(self) -> float | None:
        """Nejčastější tloušťka (medián vážený plochou) – u trubky či plechu jmenovitá stěna."""
        pairs = sorted((v, a) for v, a in zip(self.values, self.areas, strict=True)
                       if v is not None)
        half, total = sum(a for _, a in pairs) / 2, 0.0
        for value, area in pairs:
            total += area
            if total >= half:
                return value
        return None

    @cached_property
    def total_area(self) -> float:
        return sum(self.areas)

    @cached_property
    def area_below(self) -> float:
        """Plocha [mm²], kde je stěna tenčí než minimální dovolená tloušťka."""
        limit = self.settings.limit
        if limit is None:
            return 0.0
        return sum(a for v, a in zip(self.values, self.areas, strict=True)
                   if v is not None and v < limit)

    @cached_property
    def scale(self) -> tuple[float, float]:
        """Rozsah barevné škály (od – do) v mm."""
        low = self.minimum if self.minimum is not None else 0.0
        high = self.settings.scale_max or self.nominal or low
        if high <= low:
            high = low + max(1e-3, abs(low) * 1e-3)
        return low, high

    def color(self, value: float | None) -> Color:
        return color_for(value, *self.scale, self.settings.limit)

    def node_colors(self) -> list[Color]:
        """Barva v každém uzlu (průměr tloušťky okolních trojúhelníků) – plynulá mapa."""
        low, high = self.scale
        sums = [0.0] * len(self.nodes)
        counts = [0] * len(self.nodes)
        for triangle, value in zip(self.triangles, self.values, strict=True):
            if value is None:
                continue
            for index in triangle:
                sums[index] += value
                counts[index] += 1
        limit = self.settings.limit
        return [color_for(s / c if c else None, low, high, limit)
                for s, c in zip(sums, counts, strict=True)]

    def summary(self) -> list[str]:
        """Souhrn česky (panel v okně, příkazová řádka)."""
        if self.minimum is None:
            return ["Mapa tloušťky: za povrchem se nenašla žádná stěna."]
        x, y, z = self.thinnest
        lines = [
            f"Nejtenčí místo: {number(self.minimum)} mm "
            f"(X {number(x)}  Y {number(y)}  Z {number(z)})",
            f"Nejčastější tloušťka: {number(self.nominal)} mm, největší: "
            f"{number(self.maximum)} mm",
        ]
        limit = self.settings.limit
        if limit is not None:
            below = self.area_below
            share = 100 * below / self.total_area if self.total_area else 0.0
            if below:
                lines.append(f"Pod minimem {number(limit)} mm: {number(share)} % povrchu "
                             f"({number(below, 0)} mm²)")
            else:
                lines.append(f"Celý díl má stěnu aspoň {number(limit)} mm – vyhovuje.")
        lines.append(f"{len(self.values)} bodů po {number(self.step, 1)} mm, "
                     f"výpočet {number(self.seconds, 1)} s")
        return lines

    def write_csv(self, path: str | Path) -> Path:
        """Body mapy do CSV pro Excel: středník a desetinná čárka (česká nastavení)."""
        path = Path(path)
        limit = self.settings.limit

        def cz(value: float) -> str:
            return f"{value:.3f}".replace(".", ",")

        rows = ["x [mm];y [mm];z [mm];tloušťka [mm];pod minimem"]
        for (x, y, z), value in zip(self.centers, self.values, strict=True):
            thickness = cz(value) if value is not None else ""
            below = "ano" if limit is not None and value is not None and value < limit else ""
            rows.append(f"{cz(x)};{cz(y)};{cz(z)};{thickness};{below}")
        path.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")  # BOM → Excel pozná UTF-8
        return path


def color_for(value: float | None, low: float, high: float,
              limit: float | None = None) -> Color:
    """Barva tloušťky ``value`` na škále ``low`` (červená) … ``high`` (modrá)."""
    if value is None:
        return NO_MATERIAL
    if limit is not None and value < limit:
        return BELOW_LIMIT
    t = min(1.0, max(0.0, (value - low) / (high - low))) if high > low else 1.0
    for (t0, c0), (t1, c1) in zip(SCALE, SCALE[1:], strict=False):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * k for a, b in zip(c0, c1, strict=True))
    return SCALE[-1][1]


# --- výpočet -------------------------------------------------------------------------------


def auto_step(part: Any) -> float:
    """Jemnost podle velikosti povrchu: zhruba ``TARGET_TRIANGLES`` bodů."""
    return max(MIN_STEP, round(math.sqrt(part.area / (TARGET_TRIANGLES * _AREA_PER_STEP2)), 1))


def compute(part: Any, settings: MapSettings | None = None) -> ThicknessMap:
    """Spočítá mapu tloušťky stěny dílu ``part`` (build123d Part)."""
    settings = settings or MapSettings()
    if part is None or not part.faces():
        raise MapError("Mapa tloušťky potřebuje díl – model zatím nemá těleso.")
    started = time.monotonic()
    step = max(MIN_STEP, settings.step or auto_step(part))
    surface = _Surface(part, step)
    rays = RayCaster(part)
    values = [rays.thickness(center, (-nx, -ny, -nz))[0]
              for center, (nx, ny, nz) in zip(surface.centers, surface.normals, strict=True)]
    return ThicknessMap(surface.nodes, surface.triangles, surface.centers, values,
                        surface.areas, step, settings, time.monotonic() - started)


class _Surface:
    """Povrch dílu rozdělený na trojúhelníky s nejdelší stranou do ``step`` mm.

    Každá plocha zvlášť: síť z jádra (BRepMesh) se dělí půlením dlouhých hran v parametrech
    plochy (u, v) – nové body tak leží přesně na ploše, i zakřivené. Hranu dělí všechny
    trojúhelníky, které ji mají, stejným bodem, takže v síti nevzniknou díry.
    """

    def __init__(self, part: Any, step: float) -> None:
        from OCP.BRepMesh import BRepMesh_IncrementalMesh

        self.nodes: list[Point] = []
        self.triangles: list[tuple[int, int, int]] = []
        self.centers: list[Point] = []
        self.normals: list[Point] = []
        self.areas: list[float] = []
        self.step = step
        BRepMesh_IncrementalMesh(part.wrapped, max(0.05, step / 8), False, 0.5, False)
        for face in part.faces():
            self._add_face(face)
            if len(self.triangles) > MAX_TRIANGLES:
                raise MapError(f"Mapa by měla přes {MAX_TRIANGLES} bodů – zvol větší krok "
                               f"(teď {number(step, 1)} mm).")

    def _add_face(self, face: Any) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp_Face
        from OCP.gp import gp_Pnt, gp_Vec
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.TopLoc import TopLoc_Location

        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face.wrapped, location)
        if mesh is None or not mesh.HasUVNodes():
            return
        adaptor = BRepAdaptor_Surface(face.wrapped)
        normal_of = BRepGProp_Face(face.wrapped)
        reversed_face = face.wrapped.Orientation() == TopAbs_REVERSED
        transform = location.Transformation()
        points: list[Point] = []
        uvs: list[tuple[float, float]] = []
        for i in range(1, mesh.NbNodes() + 1):
            p = mesh.Node(i).Transformed(transform)
            uv = mesh.UVNode(i)
            points.append((p.X(), p.Y(), p.Z()))
            uvs.append((uv.X(), uv.Y()))
        triangles = []
        for i in range(1, mesh.NbTriangles() + 1):
            a, b, c = mesh.Triangle(i).Get()
            triangles.append((a - 1, c - 1, b - 1) if reversed_face else (a - 1, b - 1, c - 1))

        cache: dict[tuple[int, int], int] = {}  # hrana → její střed (sdílí ho oba sousedé)

        def midpoint(i: int, j: int) -> int:
            key = (i, j) if i < j else (j, i)
            if key not in cache:
                u = (uvs[i][0] + uvs[j][0]) / 2
                v = (uvs[i][1] + uvs[j][1]) / 2
                p = adaptor.Value(u, v)
                points.append((p.X(), p.Y(), p.Z()))
                uvs.append((u, v))
                cache[key] = len(points) - 1
            return cache[key]

        limit = self.step * self.step

        def longest(tri: tuple[int, int, int]) -> tuple[int, int]:
            a, b, c = tri
            edge = max(((a, b), (b, c), (c, a)), key=lambda e: _dist2(points[e[0]], points[e[1]]))
            return (min(edge), max(edge))

        for _ in range(60):  # každé kolo rozpůlí nejdelší strany delší než krok
            marked = {longest(tri) for tri in triangles
                      if _dist2(points[longest(tri)[0]], points[longest(tri)[1]]) > limit}
            if not marked:
                break
            changed = True
            while changed:  # soused dělené hrany musí dělit i svou nejdelší (bez děr v síti)
                changed = False
                for tri in triangles:
                    edges = _edges(tri)
                    if any(e in marked for e in edges) and longest(tri) not in marked:
                        marked.add(longest(tri))
                        changed = True
            refined = []
            for tri in triangles:
                refined.extend(_bisect(tri, longest(tri), marked, midpoint))
            triangles = refined
            if len(triangles) + len(self.triangles) > MAX_TRIANGLES:
                break  # hlášku dá __init__

        offset = len(self.nodes)
        self.nodes.extend(points)
        p, n = gp_Pnt(), gp_Vec()
        for a, b, c in triangles:
            u = (uvs[a][0] + uvs[b][0] + uvs[c][0]) / 3
            v = (uvs[a][1] + uvs[b][1] + uvs[c][1]) / 3
            normal_of.Normal(u, v, p, n)  # počítá s orientací plochy (ven z materiálu)
            length = n.Magnitude()
            if length < 1e-12:
                continue  # zdegenerovaný trojúhelník (vrchol kužele …)
            area = _area(points[a], points[b], points[c])
            if area < 1e-12:
                continue
            self.triangles.append((a + offset, b + offset, c + offset))
            self.centers.append((p.X(), p.Y(), p.Z()))
            self.normals.append((n.X() / length, n.Y() / length, n.Z() / length))
            self.areas.append(area)


def _edges(tri: tuple[int, int, int]) -> list[tuple[int, int]]:
    a, b, c = tri
    return [(min(i, j), max(i, j)) for i, j in ((a, b), (b, c), (c, a))]


def _bisect(tri: tuple[int, int, int], longest: tuple[int, int], marked: set,
            mid) -> list[tuple[int, int, int]]:
    """Půlení nejdelší strany (a další dělené strany v obou polovinách); orientace zůstane."""
    if not any(e in marked for e in _edges(tri)):
        return [tri]
    a, b, c = tri
    while (min(a, b), max(a, b)) != longest:  # otočit, aby nejdelší strana byla a–b
        a, b, c = b, c, a
    m = mid(a, b)
    result = []
    for child, other in (((a, m, c), (c, a)), ((m, b, c), (b, c))):
        key = (min(other), max(other))
        if key not in marked:
            result.append(child)
            continue
        k = mid(*other)
        if child[0] == a:  # (a, m, c), dělí se c–a
            result += [(a, m, k), (k, m, c)]
        else:  # (m, b, c), dělí se b–c
            result += [(m, b, k), (m, k, c)]
    return result


def _dist2(p: Point, q: Point) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def _area(p: Point, q: Point, r: Point) -> float:
    ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
    vx, vy, vz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
