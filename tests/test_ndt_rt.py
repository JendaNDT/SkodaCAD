"""RT – geometrie projekce a expozice (etapa 13, krok 13A.1): ručně spočítané výsledky
z ``docs/ndt/23-navrh-etapa-13.md`` (deska s otvorem, tupý svar V, trubka přes dvě stěny)."""

import math

import pytest

from conftest import EXAMPLES
from skodacad.document import Document
from skodacad.ndt import RT_DISCLAIMER, RT_MAP
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.rt import (
    Projection,
    RtError,
    RtSettings,
    angles_of,
    check_points,
    compute,
    estimate,
    image_of,
    prepare,
    self_check,
    study_target,
    tilted,
)
from skodacad.rebuild import rebuild

NDT = EXAMPLES / "ndt"
R = 57.15  # vnější poloměr trubky Ø 114,3
TOP = {"kind": "faces", "faces": [{"face": {"at": [50, 0, 20], "normal": [0, 0, 1],
                                            "type": "plane"}}]}
NOMINAL_30 = 20 / math.cos(math.radians(30))  # plech 20 mm prozářený pod 30°


def part(name):
    return rebuild(Document.load(NDT / f"{name}.json")).part


@pytest.fixture(scope="module")
def otvor():
    return part("otvor")


def straight(**changes):
    """Kolmo nad středem otvoru, f = 500, detektor volně v rovině spodní plochy (z = 0)."""
    values = {"distance_mm": 500, "detector": "free", "detector_distance_mm": 520,
              "reference_mm": 20, **changes}
    return Projection("P1", (0, 0, 20), (0, 0, 1), **values)


def slanted(reference=NOMINAL_30):
    """Zdroj sklopený o 30° k +X, S = (250; 0; 453,0), detektor na spodní ploše."""
    return Projection("P2", (0, 0, 20), tilted((0, 0, 1), 30, 0), 500, "contact", 0, None,
                      reference)


def test_settings_defaults_roundtrip_and_czech_errors():
    settings = RtSettings(projections=(straight(), slanted()))
    data = settings.to_dict()
    assert data["class"] == "B" and data["focal_mm"] == 3 and "step_mm" not in data
    assert data["projections"][0]["detector_distance_mm"] == 520
    assert "reference_mm" in data["projections"][1]
    assert RtSettings.from_dict(data) == settings
    assert RtSettings.from_dict(None) == RtSettings()
    with pytest.raises(RtError, match="Třída zkoušky"):
        RtSettings.from_dict({"class": "C"})
    with pytest.raises(RtError, match="nezná"):
        RtSettings.from_dict({"trida": "B"})
    with pytest.raises(RtError, match="Rozměr ohniska"):
        RtSettings(focal_mm=-1)
    with pytest.raises(RtError, match="dvakrát"):
        RtSettings(projections=(straight(), straight()))
    with pytest.raises(RtError, match="vzdálenost od zdroje"):
        Projection("P", (0, 0, 0), (0, 0, 1), 500, "free")
    with pytest.raises(RtError, match="dál od zdroje"):
        Projection("P", (0, 0, 0), (0, 0, 1), 500, "free", 0, 400)
    with pytest.raises(RtError, match="nulový"):
        Projection("P", (0, 0, 0), (0, 0, 0))


def test_tilt_and_turn_roundtrip():
    direction = tilted((0, 0, 1), 30, 0)
    assert direction == pytest.approx((0.5, 0, math.sqrt(0.75)))
    assert angles_of((0, 0, 1), direction) == pytest.approx((30, 0))
    assert angles_of((0, 0, 1), tilted((0, 0, 1), 25, 135)) == pytest.approx((25, 135))
    assert tilted((1, 0, 0), 10, 0) == pytest.approx(
        (math.cos(math.radians(10)), math.sin(math.radians(10)), 0))  # 0° = osa +Y


def test_plate_thickness_ratio_unsharpness_and_detector_edge(otvor):
    settings = RtSettings(projections=(straight(),))
    plate, edge, inside, outside, hole = check_points(
        otvor, [(50, 0, 20), (95, 0, 20), (0, 48.0, 20), (0, 48.2, 20), (0, 0, 10)],
        settings)[0]
    assert plate.state == "ok"
    assert plate.thickness == pytest.approx(20 / math.cos(math.atan(50 / 500)))
    assert plate.unsharpness == pytest.approx(0.12) and plate.magnification == pytest.approx(1.04)
    assert edge.ratio == pytest.approx(1 / math.cos(math.atan(95 / 500)))  # 1,018
    assert inside.state == "ok" and outside.state == "blocked"  # |y| ≤ 50 · 500/520 = 48,08
    assert "Mimo detektor o 0,1 mm" in outside.reasons[0][1]
    assert hole.thickness == 0 and hole.state == "ok"  # paprsek osou otvoru


def test_hole_image_narrows_when_the_beam_tilts(otvor):
    """Podmínka dokončení z plánu: otvor mění projektovanou tloušťku a obraz při změně úhlu.
    Kolmo je průhledné x ∈ ⟨−10; 10⟩, pod 30° x ∈ ⟨−10; −1,09⟩ (ručně, oddíl 7)."""
    settings = RtSettings(detector_width_mm=1, detector_length_mm=30, image_step_mm=0.2,
                          projections=(straight(), slanted()))
    geo = PartGeometry(otvor)
    for name, low, high in (("P1", -10.0, 10.0), ("P2", -10.0, -1.0851)):
        image = image_of(otvor, settings, name)
        setup = prepare(geo, settings, settings.projection(name))
        clear = [setup.center[0] + setup.long[0] * (-15 + (c + 0.5) * image.cell_long)
                 for c in range(image.columns) if image.value(c, 0)[0] < 1e-6]
        assert min(clear) == pytest.approx(low, abs=0.2)  # na jednu buňku náhledu
        assert max(clear) == pytest.approx(high, abs=0.2)
        assert image.flags.count("b") == 0
    image = image_of(otvor, settings, "P2")  # nejšikmější paprsek na kraji detektoru x = −26,45
    assert image.max_mm == pytest.approx(20 / math.cos(math.atan(276.447 / 453.0127)), abs=0.01)


def test_beam_into_hole_needs_nominal_thickness(otvor):
    no_reference = RtSettings(projections=(slanted(reference=None),))
    [shot] = check_points(otvor, [(50, 0, 20)], no_reference)[0]
    assert shot.state == "uncertain" and "jmenovitou tloušťku" in shot.reasons[0][1]
    [shot] = check_points(otvor, [(50, 0, 20)], RtSettings(projections=(slanted(),)))[0]
    assert shot.state == "ok" and shot.ratio == pytest.approx(
        20 / math.cos(math.atan(200 / 433.0127)) / NOMINAL_30)


def test_plate_map_two_projections_distances_summary_and_csv(otvor, tmp_path):
    settings = RtSettings(step_mm=10, image_step_mm=20, projections=(straight(), slanted()))
    record = {"method": "RT", "target": TOP}
    first = compute(otvor, record, settings, "ocel")
    p1, p2 = first.projections
    assert (p1.f, p1.b) == pytest.approx((500, 20))  # f, b ze strany předmětu u zdroje
    assert (p1.f_min_a, p1.f_min_b) == pytest.approx((165.8, 331.6), abs=0.05)
    assert p1.unsharpness == pytest.approx(0.12) and p1.distance_ok
    assert (p2.f, p2.b) == pytest.approx((500, NOMINAL_30))  # i když střed míří do otvoru
    assert p2.setup.center == pytest.approx((-20 * math.tan(math.radians(30)), 0, 0))
    assert first.percent("blocked") == pytest.approx(3.9, abs=2.5)  # pruhy u delších hran
    assert first.percent("ok") + first.percent("blocked") == pytest.approx(100)
    both = sum(s.weight for s in first.samples if s.covered == 2) / first.total
    assert both > 0.85 and {s.covered for s in first.samples} <= {0, 1, 2}
    second = compute(otvor, record, settings, "ocel")
    assert [s.state for s in second.samples] == [s.state for s in first.samples]
    summary = first.summary()
    assert summary[0] == RT_MAP and summary[1] == RT_DISCLAIMER
    assert any("f_min A 165,8 mm / B 331,6 mm – vyhoví třídě B" in line for line in summary)
    index = first.nearest((0, 30, 20))
    text = "\n".join(first.describe(index))
    assert "P1: promítne se" in text and "P2: promítne se" in text
    rows = first.write_csv(tmp_path / "rt.csv").read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == RT_MAP and rows[1] == RT_DISCLAIMER
    assert any(row.startswith("x [mm];y [mm];z [mm];obsah [mm²];stav") for row in rows)
    nodes, triangles, colors = first.mesh("p1")
    assert len(nodes) == len(colors) == 3 * len(triangles) == 3 * len(first.samples)


def test_v_weld_volume_on_film_and_minimum_distance():
    document = Document.load(NDT / "cilove_objemy" / "tupy_svar_objem.json")
    weld = rebuild(document).part
    record = {"method": "RT", "target": document.ndt["studies"][0]["target"]}
    near = Projection("P1", (0, 0, 14), (0, 0, 1), 250, "contact", 90)
    result = compute(weld, record, RtSettings(step_mm=5, image_step_mm=20,
                                              projections=(near,)), "ocel")
    [p1] = result.projections
    assert p1.setup.w0 == pytest.approx(15)  # převýšení 2 + plech 12 + kořen 1
    assert p1.setup.center == pytest.approx((0, 0, -1)) and p1.setup.offset == 0
    assert abs(p1.setup.long[1]) == pytest.approx(1)  # delší strana podél svaru
    assert p1.b == pytest.approx(15) and p1.f == pytest.approx(250)
    assert (p1.f_min_a, p1.f_min_b) == pytest.approx((136.8, 273.7), abs=0.05)
    assert p1.f_min_a < p1.f < p1.f_min_b  # třída A by vyhověla
    assert result.percent("limited") == pytest.approx(100)  # třída B: zdroj moc blízko
    assert all(s.shots[0].reasons[0][0] == "distance" for s in result.samples)
    far = Projection("P1", (0, 0, 14), (0, 0, 1), 500, "contact", 90)
    [[end]] = check_points(weld, [(0, 49, 7)], RtSettings(projections=(far,)))
    assert end.state == "ok" and end.ratio == pytest.approx(
        1 / math.cos(math.atan(49 / 507)), abs=0.002)
    beside = prepare(PartGeometry(weld), RtSettings(),
                     Projection("P2", (30, 0, 12), (0, 0, 1), 500, "contact", 90))
    assert beside.ok and beside.offset == pytest.approx(1, abs=0.01)  # kořen vyčnívá 1 mm


def test_pipe_double_wall_ratio_overlap_and_minimum_distance():
    pipe = part("trubka")
    geo = PartGeometry(pipe)
    narrow = RtSettings(detector_width_mm=1, detector_length_mm=80, image_step_mm=0.25,
                        projections=(Projection("P1", (0, 0, R), (0, 0, 1), 500, "contact",
                                                90),))
    setup = prepare(geo, narrow, narrow.projections[0])
    assert setup.w0 == pytest.approx(12) and setup.center == pytest.approx((0, 0, -R))
    image = image_of(pipe, narrow, "P1")
    inside = [abs(-40 + (c + 0.5) * image.cell_long) for c in range(image.columns)
              if image.value(c, 0)[0] / 12 <= 1.1]
    assert max(inside) == pytest.approx(24.85, abs=0.25)  # přesně ze zdroje (skript ±24,85)
    [shell] = [f for f in pipe.faces() if abs(geo.surface_at((0, 0, R), f).distance) < 1e-6]
    settings = RtSettings(projections=(Projection("P1", (0, 0, R), (0, 0, 1), 500, "contact",
                                                  90),
                                       Projection("P2", (0, 0, R), (0, 0, 1), 1100, "contact",
                                                  90)))
    near, far = check_points(pipe, [(0, 0, R), (0, 0, -R)], settings, [shell])
    for shot in near:  # f = 500 < f_min B = 1059,8 a protější stěna přes obraz
        assert shot.state == "limited" and shot.thickness == pytest.approx(12)
        assert {kind for kind, _ in shot.reasons} == {"distance", "overlap"}
        assert "1059,8 mm" in shot.reasons[0][1]
    assert [{kind for kind, _ in shot.reasons} for shot in far] == [{"overlap"}] * 2


def test_collisions_beam_and_free_detector(otvor):
    pipe = part("trubka")
    geo = PartGeometry(pipe)
    inside = Projection("P", (0, 0, -51.15), (0, 0, 1), 51.15, "contact", 90)
    housing = prepare(geo, RtSettings(cone_deg=360), inside)
    assert not housing.ok and housing.kind == "housing" and "Tělo zdroje naráží" in housing.text
    point = prepare(geo, RtSettings(cone_deg=360, housing_diameter_mm=0), inside)
    assert point.ok and point.center == pytest.approx((0, 0, -R))
    in_wall = prepare(geo, RtSettings(), Projection("P", (0, 0, R), (0, 0, -1), 3))
    assert not in_wall.ok and in_wall.kind == "source_inside"
    plate = PartGeometry(otvor)
    through = prepare(plate, RtSettings(), Projection("P", (0, 0, 20), (0, 0, 1), 500))
    assert not through.ok and through.kind == "no_exit"  # střed do otvoru, detektor na ploše
    deep = prepare(plate, RtSettings(), Projection("P", (0, 0, 20), (0, 0, 1), 500, "free", 0,
                                                    510))
    assert not deep.ok and deep.kind == "detector"
    [[shot]] = check_points(otvor, [(95, 0, 20)], RtSettings(cone_deg=10,
                                                             projections=(straight(),)))
    assert shot.state == "blocked" and "Mimo svazek – 10,8°" in shot.reasons[0][1]
    [[shot]] = check_points(otvor, [(50, 0, 20)], RtSettings(
        housing_diameter_mm=120, projections=(straight(distance_mm=1000,
                                                       detector_distance_mm=1020),)))
    assert shot.state == "ok"


def test_study_target_and_estimate(otvor):
    geo = PartGeometry(otvor)
    with pytest.raises(RtError, match="jen pro RT"):
        study_target(geo, {"method": "MT", "target": TOP})
    with pytest.raises(RtError, match="nemá oblast"):
        study_target(geo, {"method": "RT", "target": {"kind": "faces", "faces": []}})
    with pytest.raises(RtError, match="nemá projekci"):
        compute(otvor, {"method": "RT", "target": TOP}, RtSettings())
    samples, step, projections, seconds = estimate(
        otvor, {"method": "RT", "target": TOP}, RtSettings(projections=(straight(),)))
    assert samples > 100 and step > 0 and projections == 1 and seconds > 0


def test_self_check():
    ok, text = self_check(NDT)
    assert ok and "RT projekce: OK" in text
