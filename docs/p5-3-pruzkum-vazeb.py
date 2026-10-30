"""Průzkum P5.3 – řešič vazeb sestavy (souosost, dotyk, zarovnání, vzdálenost).

Jednorázový průzkum k návrhu `p5-3-navrh-vazeb.md`, NE test projektu a NE produkční kód.
Spuštění z kořene repozitáře:

    .venv/bin/python docs/p5-3-pruzkum-vazeb.py

Komponenta = tuhé těleso se 6 stupni volnosti (posun + otočení). Vazba = rovnice mezi
plochami dvou komponent v souřadnicích dílu. Řešič hledá nejmenší posun z dnešní polohy
(Levenberg–Marquardt nad numpy) a z hodnosti Jacobiho matice určí volné stupně volnosti;
zbytek, který nejde vynulovat, je spor. Díly: ukázka krabicka_s_vickem.
"""

from __future__ import annotations

import time

import numpy as np

from skodacad.assembly_build import angles_of, rotation_matrix
from skodacad.document import Document
from skodacad.rebuild import rebuild


def rodrigues(w: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(w))
    if theta < 1e-15:
        return np.eye(3)
    k = w / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * kx + (1 - np.cos(theta)) * kx @ kx


class Body:
    def __init__(self, name: str, angles=(0, 0, 0), position=(0, 0, 0), fixed=False):
        self.name, self.fixed = name, fixed
        self.r0 = np.array(rotation_matrix(angles), dtype=float)
        self.t0 = np.array(position, dtype=float)

    def pose(self, x: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
        if x is None:
            return self.r0, self.t0
        return rodrigues(x[3:]) @ self.r0, self.t0 + x[:3]


def plane(face) -> tuple[np.ndarray, np.ndarray]:
    return np.array(tuple(face.center())), np.array(tuple(face.normal_at()))


def find(part, normal, at, tol=1e-6):
    """Rovinná plocha se zadanou normálou, jejíž rovina prochází bodem ``at``."""
    for face in part.faces():
        if face.geom_type.name != "PLANE":
            continue
        p, n = plane(face)
        if np.allclose(n, normal, atol=1e-9) and abs(np.dot(np.array(at) - p, n)) < tol:
            return p, n
    raise LookupError((normal, at))


class Solver:
    def __init__(self, bodies: list[Body]):
        self.bodies = bodies
        self.movable = [b for b in bodies if not b.fixed]
        self.constraints: list[tuple] = []

    def add(self, kind, a, fa, b, fb, value=0.0):
        self.constraints.append((kind, a, fa, b, fb, value))

    def _poses(self, x):
        poses = {}
        for body in self.bodies:
            if body.fixed:
                poses[body.name] = body.pose(None)
            else:
                i = self.movable.index(body)
                poses[body.name] = body.pose(x[6 * i:6 * i + 6])
        return poses

    def residuals(self, x):
        poses, out = self._poses(x), []
        for kind, a, (pa, na), b, (pb, nb), value in self.constraints:
            (ra, ta), (rb, tb) = poses[a], poses[b]
            pa_w, na_w, pb_w, nb_w = ra @ pa + ta, ra @ na, rb @ pb + tb, rb @ nb
            if kind in ("mate", "distance"):  # normály proti sobě, vzdálenost rovin
                out += list(nb_w + na_w) + [np.dot(pb_w - pa_w, na_w) - value]
            elif kind == "flush":  # normály stejným směrem, jedna rovina
                out += list(nb_w - na_w) + [np.dot(pb_w - pa_w, na_w)]
            elif kind == "coaxial":  # (bod na ose, směr osy): osy splývají
                out += list(np.cross(na_w, nb_w)) + list(np.cross(pb_w - pa_w, na_w))
        return np.array(out)

    def jacobian(self, x, h=1e-7):
        columns = []
        for i in range(len(x)):
            step = np.zeros_like(x)
            step[i] = h
            columns.append((self.residuals(x + step) - self.residuals(x - step)) / (2 * h))
        return np.array(columns).T

    def solve_with_flips(self):
        """Když vazby nejdou splnit, zkusí každý pohyblivý díl předem obrátit o 180°
        kolem X, Y a Z (řešič sám díl neobrátí – uvízne v místním minimu)."""
        best = self.solve()
        if best[1] < 1e-6:
            return best, None
        for body in self.movable:
            original = body.r0
            for axis in ("x", "y", "z"):
                body.r0 = np.array(rotation_matrix({"x": (180, 0, 0), "y": (0, 180, 0),
                                                    "z": (0, 0, 180)}[axis])) @ original
                result = self.solve()
                if result[1] < 1e-6:
                    return result, (body.name, axis)
            body.r0 = original
        return best, None

    def solve(self, iterations=200):
        x = np.zeros(6 * len(self.movable))
        r = self.residuals(x)
        damping = 1e-3
        for _ in range(iterations):
            if np.linalg.norm(r) < 1e-12:
                break
            j = self.jacobian(x)
            a, g = j.T @ j, j.T @ r
            step = np.linalg.solve(a + damping * np.diag(np.diag(a) + 1e-12), -g)
            trial = self.residuals(x + step)
            if np.linalg.norm(trial) < np.linalg.norm(r):
                x, r, damping = x + step, trial, damping / 3
                if np.linalg.norm(step) < 1e-14:
                    break
            else:
                damping *= 4
        j = self.jacobian(x)
        singular = np.linalg.svd(j, compute_uv=False) if j.size else np.array([])
        rank = int(np.sum(singular > 1e-8 * max(1.0, singular.max(initial=0))))
        return x, float(np.linalg.norm(r)), j.shape[1] - rank, j.shape[0] - rank

    def placements(self, x):
        out = {}
        for name, (r, t) in self._poses(x).items():
            out[name] = ([round(float(v), 9) + 0.0 for v in t],
                         angles_of(tuple(tuple(float(v) for v in row) for row in r)))
        return out


def load(name):
    return rebuild(Document.load(name)).part


def main() -> None:
    box = load("examples/krabicka.json")
    lid = load("examples/sestavy/dily/vicko.json")
    foot = load("examples/sestavy/dily/nozicka.json")
    rim = find(box, (0, 0, 1), (0, 0, 30))  # horní okraj krabičky
    box_x = find(box, (1, 0, 0), (40, 0, 15))
    box_y = find(box, (0, -1, 0), (0, -25, 15))
    box_bottom = find(box, (0, 0, -1), (0, 0, 0))
    lid_ring = find(lid, (0, 0, 1), (0, 0, 2))  # deska víčka kolem lemu (v souřadnicích dílu)
    lid_x = find(lid, (1, 0, 0), (40, 0, 1))
    lid_y = find(lid, (0, 1, 0), (0, 25, 1))
    foot_top = find(foot, (0, 0, 1), (0, 0, 3))

    print("V1 Dotyk víčka s okrajem krabičky (víčko otočené o 180° kolem X, posunuté)")
    bodies = [Body("krabicka", fixed=True), Body("vicko", (180, 0, 0), (7, -4, 50))]
    s = Solver(bodies)
    s.add("mate", "krabicka", rim, "vicko", lid_ring)
    x, res, dof, redundant = s.solve()
    print(f"   zbytek {res:.1e}, volné stupně {dof}, nadbytečné rovnice {redundant},"
          f" víčko {s.placements(x)['vicko']}")

    print("V2 + zarovnání bočních stěn X a Y → plně určeno (start natočený o 12° a posunutý)")
    bodies = [Body("krabicka", fixed=True), Body("vicko", (180, 8, 12), (7, -4, 50))]
    s = Solver(bodies)
    s.add("mate", "krabicka", rim, "vicko", lid_ring)
    s.add("flush", "krabicka", box_x, "vicko", lid_x)
    s.add("flush", "krabicka", box_y, "vicko", lid_y)
    start = time.perf_counter()
    x, res, dof, redundant = s.solve()
    took = (time.perf_counter() - start) * 1000
    print(f"   zbytek {res:.1e}, volné stupně {dof}, nadbytečné rovnice {redundant}, {took:.1f} ms")
    print(f"   víčko {s.placements(x)['vicko']}  (ruční poloha ukázky: [0, 0, 32], [180, 0, 0])")

    print("V3 Spor: vzdálenost 0 a 5 mm mezi týmiž rovinami")
    s = Solver([Body("krabicka", fixed=True), Body("vicko", (180, 0, 0), (0, 0, 40))])
    s.add("mate", "krabicka", rim, "vicko", lid_ring)
    s.add("distance", "krabicka", rim, "vicko", lid_ring, 5.0)
    x, res, dof, redundant = s.solve()
    print(f"   zbytek {res:.3f} (≈ 5/√2 = {5 / 2 ** 0.5:.3f}) → spor, nadbytečné {redundant}")

    print("V4 Nožička: dotyk se dnem → zbývají 3 volné stupně (2 posuny, otočení kolem Z)")
    s = Solver([Body("krabicka", fixed=True), Body("noha", (4, -3, 0), (-30, -15, -10))])
    s.add("mate", "krabicka", box_bottom, "noha", foot_top)
    x, res, dof, redundant = s.solve()
    print(f"   zbytek {res:.1e}, volné {dof}, poloha {s.placements(x)['noha']}"
          " – x a y zůstaly blízko (nejmenší posun)")

    print("V4b Nožička vložená obráceně (180° kolem X): samotný řešič uvízne, s obrácením projde")
    s = Solver([Body("krabicka", fixed=True), Body("noha", (180, 0, 0), (-30, -15, -10))])
    s.add("mate", "krabicka", box_bottom, "noha", foot_top)
    x, res, dof, redundant = s.solve()
    print(f"   bez obrácení: zbytek {res:.3f} (normály míří stejným směrem)")
    (x, res, dof, redundant), flip = s.solve_with_flips()
    print(f"   s obrácením {flip}: zbytek {res:.1e}, poloha {s.placements(x)['noha']}")

    print("V5 Souosost: osa nožičky s osou Z krabičky (počátek dílu) → 2 volné stupně")
    axis_box = (np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]))
    axis_foot = (np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]))
    s = Solver([Body("krabicka", fixed=True), Body("noha", (5, -3, 0), (12, 9, -20))])
    s.add("coaxial", "krabicka", axis_box, "noha", axis_foot)
    x, res, dof, redundant = s.solve()
    print(f"   zbytek {res:.1e}, volné {dof} (posun podél osy a otočení kolem ní),"
          f" poloha {s.placements(x)['noha']}")

    print("V6 Rychlost: 40 víček s dotykem a dvěma zarovnáními (240 neznámých)")
    bodies = [Body("krabicka", fixed=True)] + [Body(f"v{i}", (180, 3, 4), (i, 2, 40))
                                               for i in range(40)]
    s = Solver(bodies)
    for i in range(40):
        s.add("mate", "krabicka", rim, f"v{i}", lid_ring)
        s.add("flush", "krabicka", box_x, f"v{i}", lid_x)
        s.add("flush", "krabicka", box_y, f"v{i}", lid_y)
    start = time.perf_counter()
    x, res, dof, redundant = s.solve()
    print(f"   najednou: zbytek {res:.1e}, volné {dof}, {time.perf_counter() - start:.2f} s")
    start, worst = time.perf_counter(), 0.0
    for i in range(40):  # každé víčko je vázané jen na pevnou krabičku → samostatná skupina
        group = Solver([bodies[0], bodies[i + 1]])
        group.constraints = [c for c in s.constraints if c[3] == f"v{i}"]
        worst = max(worst, group.solve()[1])
    print(f"   po skupinách: nejhorší zbytek {worst:.1e}, {time.perf_counter() - start:.2f} s")

    print("V7 Řešič slvs (skicář) – veřejné rozhraní")
    import slvs

    print("   ", [n for n in dir(slvs) if n.startswith("add_")])
    print("    žádná transformace tuhého tělesa (bod = poloha + otočení × bod dílu)")


if __name__ == "__main__":
    main()
