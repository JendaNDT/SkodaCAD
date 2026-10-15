"""Mapa tloušťky stěny: tloušťka v bodech po povrchu podle vzorců, síť bez děr, barvy, CSV."""

import math
from collections import Counter

import pytest
from build123d import Vector, Vertex

from conftest import box_features, face_at, make_doc
from skodacad import Document, rebuild
from skodacad.measure import MeasureError, wall_thickness
from skodacad.thickness_map import (
    BELOW_LIMIT,
    NO_MATERIAL,
    SCALE,
    MapError,
    MapSettings,
    color_for,
    compute,
)


def build_ok(features, parameters=None):
    result = rebuild(make_doc(features, parameters))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    return result.part


def corroded_plate():
    """Deska 20 × 20 × 10, zespodu jamka Ø10 hloubky 6 (jako koroze): nad ní zbývají 4 mm."""
    return build_ok(box_features(20, 20, 10) + [
        {"id": "j", "type": "sketch", "plane": "bottom",
         "elements": [{"shape": "circle", "diameter": 10}]},
        {"id": "r", "type": "extrude", "sketch": "j", "operation": "cut", "distance": 6},
    ])


def test_corrosion_pit_is_the_thinnest_place_and_area_below_limit():
    part = corroded_plate()
    found = compute(part, MapSettings(limit=5, step=1.5))
    assert found.minimum == pytest.approx(4)
    x, y, _ = found.thinnest
    assert math.hypot(x, y) <= 5 + 1e-6  # nad jamkou nebo na jejím dně
    assert found.nominal == pytest.approx(10)  # nejvíc plochy má jmenovitou tloušťku desky
    assert found.scale == pytest.approx((4, 10))
    # pod 5 mm: dno jamky a horní plocha nad ní, obojí kruh Ø10 (body ve vzdálenosti
    # do kroku od kraje kruhu jsou podle toho, kam padne těžiště trojúhelníku)
    assert found.area_below == pytest.approx(2 * math.pi * 5**2, rel=0.15)
    assert found.total_area == pytest.approx(part.area, rel=1e-3)  # stěna jamky tětivami
    assert "Pod minimem 5.00 mm" in found.summary()[2]


def test_tube_wall_is_the_same_everywhere():
    tube = build_ok([  # trubka Ø60 × 5, délka 100
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [{"shape": "circle",
                                                                   "diameter": 60}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 100},
        {"id": "v", "type": "sketch", "plane": "top", "elements": [{"shape": "circle",
                                                                    "diameter": 50}]},
        {"id": "r", "type": "extrude", "sketch": "v", "operation": "cut", "through_all": True},
    ])
    found = compute(tube, MapSettings(limit=4.5, step=8))
    on_mantle = [v for v, (x, y, _z) in zip(found.values, found.centers, strict=True)
                 if math.hypot(x, y) > 24.9 and 0.1 < _z < 99.9]
    assert on_mantle and all(v == pytest.approx(5, abs=1e-6) for v in on_mantle)
    assert found.minimum == pytest.approx(5) and found.maximum == pytest.approx(100)
    assert found.nominal == pytest.approx(5) and found.area_below == 0
    assert "vyhovuje" in found.summary()[2]
    assert found.total_area == pytest.approx(tube.area, rel=5e-3)  # tětivy místo oblouku


def test_mesh_is_fine_enough_on_the_surface_and_without_holes():
    part = corroded_plate()
    found = compute(part, MapSettings(step=2))
    for a, b, c in found.triangles:  # žádná strana delší než krok
        for i, j in ((a, b), (b, c), (c, a)):
            assert math.dist(found.nodes[i], found.nodes[j]) <= 2 + 1e-9
    for center in found.centers[::25]:  # měřené body leží na povrchu dílu
        assert part.distance_to(Vertex(*center)) < 1e-6
    # bez děr: hrana použitá jen jedním trojúhelníkem leží na hraně dílu (okraj plochy);
    # u kružnice Ø10 je to tětiva – její střed je od oblouku nejvýš o vzepětí (≈ 0,1 mm)
    uses = Counter(tuple(sorted(e)) for a, b, c in found.triangles
                   for e in ((a, b), (b, c), (c, a)))
    edges = list(part.edges())
    for (i, j), count in uses.items():
        assert count <= 2
        if count == 1:
            middle = Vector(*[(p + q) / 2 for p, q in zip(found.nodes[i], found.nodes[j],
                                                          strict=True)])
            assert min(edge.distance_to(middle) for edge in edges) < 0.11


def test_example_pipe_map_finds_the_pit(examples_dir):
    result = rebuild(Document.load(examples_dir / "trubka.json"))
    found = compute(result.part, MapSettings(limit=4))
    assert found.minimum == pytest.approx(6 - 3.5)  # zbytková stěna pod jamkou
    assert found.nominal == pytest.approx(6)
    assert 25_000 < len(found.values) < 35_000  # automatická jemnost ≈ 30 000 bodů


def test_oblique_back_wall_gives_no_reading(examples_dir):
    part = rebuild(Document.load(examples_dir / "trubka.json")).part
    outer = face_at(part, -100, 0, -57.15)
    rim = (38.54, 9.99, 56.27)  # na plášti těsně u okraje jamky – paprsek míjí její stěnu
    with pytest.raises(MeasureError, match="šikmo"):
        wall_thickness(part, outer, rim)
    found = compute(part, MapSettings(step=12))
    assert any(v is None for v in found.values)  # okraj jamky zůstane šedý


def test_colors_settings_and_csv(tmp_path):
    assert color_for(None, 2, 6) == NO_MATERIAL
    assert color_for(3, 2, 6, limit=4) == BELOW_LIMIT
    assert color_for(2, 2, 6) == SCALE[0][1]  # nejtenčí červeně
    assert color_for(9, 2, 6) == SCALE[-1][1]  # nad horní mezí modře
    assert MapSettings.from_dict({"limit": 4, "step": 2.5}).to_dict() == {"limit": 4,
                                                                          "step": 2.5}
    assert MapSettings.from_dict(None) == MapSettings()
    with pytest.raises(MapError, match="kladné číslo"):
        MapSettings.from_dict({"limit": -1})
    with pytest.raises(MapError, match="Neznámé"):
        MapSettings.from_dict({"barva": "červená"})
    with pytest.raises(MapError, match="potřebuje díl"):
        compute(None)

    found = compute(corroded_plate(), MapSettings(limit=5, step=4))
    path = found.write_csv(tmp_path / "mapa.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM – Excel pozná češtinu
    rows = raw.decode("utf-8-sig").splitlines()
    assert rows[0] == "x [mm];y [mm];z [mm];tloušťka [mm];pod minimem"
    assert len(rows) == len(found.values) + 1
    thin = [row for row in rows[1:] if row.endswith(";ano")]
    assert thin and all(row.split(";")[3] == "4,000" for row in thin)
