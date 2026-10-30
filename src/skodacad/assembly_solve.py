"""Řešič vazeb sestavy (P5.3, rozhodnutí M3–M8): tuhá tělesa nad numpy.

Komponenta je tuhé těleso se šesti neznámými – posun ``d`` (mm) a otočení ``w`` (osa × úhel
v radiánech), které se přidává k dnešní poloze: ``R = rodrigues(w) · R0``, ``t = t0 + d``.
Vazba je rovnice mezi plochami dvou komponent (bod a směr v souřadnicích dílu):

- dotyk / vzdálenost: normály proti sobě a vzdálenost rovin = 0 / hodnota,
- zarovnání: normály stejným směrem, jedna rovina,
- souosost: osy (bod na ose, směr) splývají.

Rovnice směrů se násobí délkou ``scale`` (největší rameno bodu vazby od počátku dílu,
nejméně 1 mm): chyba směru se tak počítá v mm na velikosti dílu. Bez toho by řešič
dorovnával vzdálenost natočením dílu (rameno 24 mm je „levnější“ než posun) a sbíhal by
se pomalu. Zbytek vazby je proto v mm.

Řeší se Levenberg–Marquardtem od dnešní polohy (nejmenší posun, M4), každá skupina
propojených komponent zvlášť (M3). Když vazby nejdou splnit, zkusí se každý díl skupiny
předem obrátit o 180° kolem X, Y a Z (M5); teprve potom je to spor (M7). Volné pohyby
komponenty se poznají z hodnosti Jacobiho matice (M6). Průzkum: ``docs/p5-3-pruzkum-vazeb.py``.

Modul nezná OCCT ani soubory – dostane hotové body a směry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np

SATISFIED = 1e-6  # zbytek vazby pod touto mezí = splněno (M7)
STILL = 1e-7  # vazby splněné už v uložené poloze se neřeší – čísla zůstanou, jak jsou
_ITERATIONS = 200
_STEP = 1e-7  # krok numerické derivace
_RANK = 1e-8  # relativní mez singulární hodnoty pro hodnost
_FLIPS = {"x": np.diag([1.0, -1.0, -1.0]), "y": np.diag([-1.0, 1.0, -1.0]),
          "z": np.diag([-1.0, -1.0, 1.0])}  # otočení o 180° kolem osy


def rodrigues(w: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(w))
    if theta < 1e-15:
        return np.eye(3)
    k = w / theta
    kx = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + np.sin(theta) * kx + (1 - np.cos(theta)) * kx @ kx


@dataclass
class Body:
    """Komponenta pro řešič: dnešní poloha a jestli s ní smí pohnout."""

    id: str
    rotation: np.ndarray  # 3 × 3
    position: np.ndarray  # 3
    movable: bool = True


@dataclass
class Link:
    """Vazba připravená pro řešič: (bod, směr) obou ploch v souřadnicích jejich dílů."""

    id: str
    kind: str  # "mate" / "flush" / "distance" / "coaxial"
    a: str
    pa: np.ndarray
    na: np.ndarray
    b: str
    pb: np.ndarray
    nb: np.ndarray
    value: float = 0.0


@dataclass
class Freedom:
    """Volné pohyby komponenty, které vazby neurčují (M6)."""

    translations: int
    rotations: int

    @property
    def total(self) -> int:
        return self.translations + self.rotations


@dataclass
class Group:
    """Skupina propojených komponent a výsledek jejího řešení."""

    bodies: list[str]  # pohyblivé komponenty skupiny v pořadí sestavy
    links: list[Link]
    anchor: str = ""  # komponenta, která skupinu drží, když v ní není pevná (M8)
    held: list[str] = field(default_factory=list)  # nepohyblivé komponenty ve vazbách
    residual: float = 0.0  # zbytek celé skupiny
    flipped: tuple[str, str] | None = None  # (komponenta, osa) obrácená o 180°

    @property
    def satisfied(self) -> bool:
        return self.residual <= SATISFIED


@dataclass
class Solution:
    poses: dict[str, tuple[np.ndarray, np.ndarray]]  # nová poloha (R, t) pohnutých komponent
    residuals: dict[str, float]  # zbytek každé vazby
    freedom: dict[str, Freedom]  # pohyblivé komponenty ve vazbách
    groups: list[Group]


def residual_rows(kind: str, pa: np.ndarray, na: np.ndarray, pb: np.ndarray, nb: np.ndarray,
                  value: float, scale: float = 1.0) -> np.ndarray:
    """Rovnice jedné vazby v souřadnicích sestavy (všechny mají být nula); rovnice směrů
    jsou vynásobené délkou ``scale``."""
    gap = float(np.dot(pb - pa, na))
    if kind in ("mate", "distance"):
        return np.array([*(scale * (nb + na)), gap - (value if kind == "distance" else 0.0)])
    if kind == "flush":
        return np.array([*(scale * (nb - na)), gap])
    if kind == "coaxial":
        return np.array([*(scale * np.cross(na, nb)), *np.cross(pb - pa, na)])
    raise ValueError(f"neznámý druh vazby {kind!r}")


class _Problem:
    """Jedna skupina: neznámé jsou posuny a otočení pohyblivých komponent."""

    def __init__(self, bodies: dict[str, Body], movable: Sequence[str], links: list[Link]):
        self.bodies = bodies
        self.movable = list(movable)
        self.index = {body_id: number for number, body_id in enumerate(self.movable)}
        self.links = links
        self.base = {body_id: (bodies[body_id].rotation, bodies[body_id].position)
                     for body_id in bodies}
        self.scale = max([1.0, *(float(np.linalg.norm(point)) for link in links
                                 for point in (link.pa, link.pb))])

    def pose(self, body_id: str, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r0, t0 = self.base[body_id]
        if body_id not in self.index:
            return r0, t0
        i = 6 * self.index[body_id]
        return rodrigues(x[i + 3:i + 6]) @ r0, t0 + x[i:i + 3]

    def rows(self, x: np.ndarray) -> list[np.ndarray]:
        poses: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        out = []
        for link in self.links:
            for body_id in (link.a, link.b):
                if body_id not in poses:
                    poses[body_id] = self.pose(body_id, x)
            (ra, ta), (rb, tb) = poses[link.a], poses[link.b]
            out.append(residual_rows(link.kind, ra @ link.pa + ta, ra @ link.na,
                                     rb @ link.pb + tb, rb @ link.nb, link.value, self.scale))
        return out

    def residuals(self, x: np.ndarray) -> np.ndarray:
        rows = self.rows(x)
        return np.concatenate(rows) if rows else np.zeros(0)

    def jacobian(self, x: np.ndarray) -> np.ndarray:
        columns = []
        for i in range(len(x)):
            step = np.zeros_like(x)
            step[i] = _STEP
            columns.append((self.residuals(x + step) - self.residuals(x - step)) / (2 * _STEP))
        return np.array(columns).T

    def solve(self) -> tuple[np.ndarray, float]:
        """Levenberg–Marquardt od dnešní polohy (x = 0), pak návrat volných pohybů.

        Krok je řešení nejmenších čtverců s nejmenší normou (SVD) v měřítku „mm“ (otočení
        × ``scale``) a útlum je v tomtéž měřítku stejný pro všechny pohyby. Útlum podle
        velikosti sloupců (Marquardt) by téměř volný pohyb zlevnil a díl by ujel do strany
        (krabička o 43 mm, se šumem bez SVD o 536 mm). Co se z volných pohybů přesto
        nasbíralo (nelineární kroky), vrátí ``_pull_back`` – výsledek je nejmenší posun (M4)."""
        x = np.zeros(6 * len(self.movable))
        r = self.residuals(x)
        if not len(x) or np.linalg.norm(r) <= STILL:
            return x, float(np.linalg.norm(r))
        metric = np.tile([1.0, 1.0, 1.0, self.scale, self.scale, self.scale],
                         len(self.movable))
        x, residual = self._descend(x, metric)
        for _ in range(3):
            if residual > SATISFIED:
                break
            back = self._pull_back(x, metric)
            if back is None:
                break
            trial, trial_residual = self._descend(back, metric)
            if trial_residual > max(residual, 1e-10):
                break
            x, residual = trial, trial_residual
        return x, residual

    def _descend(self, x: np.ndarray, metric: np.ndarray) -> tuple[np.ndarray, float]:
        r = self.residuals(x)
        damping = 1e-3
        for _ in range(_ITERATIONS):
            if np.linalg.norm(r) < 1e-12:
                break
            j = self.jacobian(x) / metric
            system = np.vstack([j, np.sqrt(damping) * np.eye(len(x))])
            rhs = np.concatenate([-r, np.zeros(len(x))])
            step = np.linalg.lstsq(system, rhs, rcond=1e-10)[0] / metric
            trial = self.residuals(x + step)
            if np.linalg.norm(trial) < np.linalg.norm(r):
                x, r, damping = x + step, trial, damping / 3
                if np.linalg.norm(step) < 1e-14:
                    break
            else:
                damping *= 4
                if damping > 1e12:
                    break
        return x, float(np.linalg.norm(r))

    def _pull_back(self, x: np.ndarray, metric: np.ndarray) -> np.ndarray | None:
        """Odebere z řešení složku ve volných pohybech (jádro Jacobiho matice) – ty vazby
        neurčují, tak mají zůstat jako v dnešní poloze. None = není co vracet."""
        j = self.jacobian(x) / metric
        _, singular, vt = np.linalg.svd(j, full_matrices=True)
        rank = int(np.sum(singular > _RANK * max(1.0, float(singular.max(initial=0)))))
        null = vt[rank:].T
        scaled = x * metric
        drift = null @ (null.T @ scaled)
        if np.linalg.norm(drift) < 1e-12:
            return None
        return (scaled - drift) / metric

    def freedom(self, x: np.ndarray) -> dict[str, Freedom]:
        """Volné pohyby každé pohyblivé komponenty z jádra Jacobiho matice (M6)."""
        if not len(x):
            return {}
        j = self.jacobian(x)
        if j.size:
            _, singular, vt = np.linalg.svd(j, full_matrices=True)
            rank = int(np.sum(singular > _RANK * max(1.0, float(singular.max(initial=0)))))
            null = vt[rank:].T
        else:
            null = np.eye(len(x))
        out = {}
        for body_id, number in self.index.items():
            block = null[6 * number:6 * number + 6]
            total = _rank(block)
            rotations = _rank(block[3:6])
            out[body_id] = Freedom(translations=total - rotations, rotations=rotations)
        return out


def _rank(block: np.ndarray) -> int:
    if not block.size:
        return 0
    return int(np.linalg.matrix_rank(block, tol=1e-6))


def groups(bodies: dict[str, Body], links: list[Link]) -> list[Group]:
    """Skupiny propojených komponent (M3). Nepohyblivá komponenta skupiny nespojuje –
    obě strany se k ní vážou samostatně. Skupina bez nepohyblivé komponenty drží první
    komponentu v pořadí sestavy (M8)."""
    order = {body_id: number for number, body_id in enumerate(bodies)}
    parent = {body_id: body_id for body_id in bodies if bodies[body_id].movable}

    def root(body_id: str) -> str:
        while parent[body_id] != body_id:
            parent[body_id] = parent[parent[body_id]]
            body_id = parent[body_id]
        return body_id

    for link in links:
        if link.a in parent and link.b in parent:
            ra, rb = root(link.a), root(link.b)
            if ra != rb:
                parent[max(ra, rb, key=order.__getitem__)] = min(ra, rb, key=order.__getitem__)
    found: dict[str, Group] = {}
    loose: list[Group] = []  # vazby jen mezi nepohyblivými komponentami
    for link in links:
        movable = [body_id for body_id in (link.a, link.b) if body_id in parent]
        if not movable:
            loose.append(Group(bodies=[], links=[link], held=sorted(
                {link.a, link.b}, key=order.__getitem__)))
            continue
        key = root(movable[0])
        group = found.setdefault(key, Group(bodies=[], links=[]))
        group.links.append(link)
    for group in found.values():
        members = {body_id for link in group.links for body_id in (link.a, link.b)}
        group.bodies = sorted((b for b in members if b in parent), key=order.__getitem__)
        group.held = sorted((b for b in members if b not in parent), key=order.__getitem__)
        if not group.held:
            group.anchor = group.bodies.pop(0)
    ordered = sorted(found.values(), key=lambda g: min(order[b] for link in g.links
                                                       for b in (link.a, link.b)))
    return ordered + loose


def solve(bodies: dict[str, Body], links: list[Link]) -> Solution:
    """Vyřeší všechny skupiny. Splněná skupina dá nové polohy svých komponent; skupina ve
    sporu polohy nemění (M7) – volající ze zbytků vazeb pozná, které jsou ve sporu."""
    solution = Solution(poses={}, residuals={}, freedom={}, groups=groups(bodies, links))
    for group in solution.groups:
        problem = _Problem(bodies, group.bodies, group.links)
        x, residual = problem.solve()
        if residual > SATISFIED:
            flipped = _with_flips(bodies, group)
            if flipped is not None:
                problem, x, residual, group.flipped = flipped
        group.residual = residual
        for link, rows in zip(group.links, problem.rows(x), strict=True):
            solution.residuals[link.id] = float(np.linalg.norm(rows))
        solution.freedom.update(problem.freedom(x))
        if group.satisfied:
            for body_id in group.bodies:
                solution.poses[body_id] = problem.pose(body_id, x)
    return solution


def _with_flips(bodies: dict[str, Body], group: Group
                ) -> tuple[_Problem, np.ndarray, float, tuple[str, str]] | None:
    """M5: každý díl skupiny zkusí předem obrátit o 180° kolem X, Y a Z (sám řešič díl
    neobrátí – uvízne v místním minimu). Vrátí první řešení, které vazby splní."""
    for body_id in group.bodies:
        for axis, flip in _FLIPS.items():
            body = bodies[body_id]
            trial_bodies = dict(bodies)
            trial_bodies[body_id] = replace(body, rotation=flip @ body.rotation)
            trial = _Problem(trial_bodies, group.bodies, group.links)
            x, residual = trial.solve()
            if residual <= SATISFIED:
                return trial, x, residual, (body_id, axis)
    return None
