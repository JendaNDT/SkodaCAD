"""MT – přiložení jha a směry magnetizace (etapa 12, ``ndt/mt.py``).

Očekávané hodnoty jsou ručně spočítané v ``docs/ndt/21-navrh-etapa-12.md`` (oddíl 9)
a ``docs/ndt/05-referencni-dily.md``: místo pólu = průsečík kružnice o poloměru d/2 s povrchem,
účinná oblast (d − 50) × d/2, ve směru pole končí pokrytí 35 mm od okraje (poloměr pólu
10 + 25 mm u pólu), všechny orientace vad pokryjí dva směry pole aspoň 60° od sebe. Testy
jsou krátké (body a zúžené směry místo celých map) kvůli časovému limitu kroku *Testy*.
"""

import math

import pytest

from conftest import EXAMPLES
from skodacad.document import Document
from skodacad.ndt import MT_DISCLAIMER, MT_MAP
from skodacad.ndt import mt as module
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.mt import (
    MtError,
    MtSettings,
    Yoker,
    _missing,
    check_points,
    compute,
    covers,
    estimate,
    material_status,
    place_yoke,
    self_check,
    study_faces,
)
from skodacad.rebuild import rebuild

NDT = EXAMPLES / "ndt"
S = math.sqrt(0.5)
R = 57.15  # vnější poloměr trubky Ø 114,3
FIELD_ONLY = MtSettings(apply=False, inspect=False)


def part(name):
    return rebuild(Document.load(NDT / f"{name}.json")).part


@pytest.fixture(scope="module")
def deska():
    return part("deska")


def top_faces(deska):
    return [f for f in deska.faces()
            if abs(f.center().Z - 20) < 1e-6 and abs(f.normal_at().Z - 1) < 1e-6]


def poles(placed):
    return sorted(tuple(round(v, 2) for v in q) for q in placed.poles)


# --- nastavení a materiál --------------------------------------------------------------------


def test_settings_defaults_roundtrip_and_czech_errors():
    s = MtSettings()
    assert s.spacings == (100.0, 75.0)
    assert MtSettings.from_dict(s.to_dict()) == s
    assert "step_mm" not in s.to_dict() and "ferromagnetic" not in s.to_dict()
    assert MtSettings(min_spacing_mm=100).spacings == (100.0,)
    assert s.pt_settings().cleaning == "rinse"
    with pytest.raises(MtError, match="nezná"):
        MtSettings.from_dict({"roztec": 100})
    with pytest.raises(MtError, match="Rozteč pólů \\[mm\\] musí být číslo"):
        MtSettings(spacing_mm=5)
    with pytest.raises(MtError, match="Nejmenší rozteč"):
        MtSettings(min_spacing_mm=120)
    with pytest.raises(MtError, match="dvojnásobek oblasti u pólu"):
        MtSettings(min_spacing_mm=50)
    with pytest.raises(MtError, match="true nebo false"):
        MtSettings(apply="ano")
    assert any("zvoleno pro výpočet" in line for line in s.lines())
    assert any("ISO 17638" in line for line in s.lines())


@pytest.mark.parametrize(("material", "confirmed", "status"), [
    ("ocel", None, "ok"), ("Litina", None, "ok"), ("hliník", None, "no"),
    ("hliník", True, "no"), ("nerez", None, "confirm"), ("nerez", True, "confirmed"),
    ("", None, "confirm"), ("PLA", None, "no")])
def test_material_must_be_ferromagnetic(material, confirmed, status):
    assert material_status(material, confirmed)[0] == status


def test_non_ferromagnetic_or_unconfirmed_material_refuses_the_map(deska):
    with pytest.raises(MtError, match="hliník není feromagnetický"):
        compute(deska, top_faces(deska), FIELD_ONLY, "hliník")
    with pytest.raises(MtError, match="austenitická"):
        compute(deska, top_faces(deska), FIELD_ONLY, "nerez")
    settings = MtSettings(apply=False, inspect=False, ferromagnetic=True, step_mm=20,
                          center_step_mm=40)
    result = compute(deska, top_faces(deska), settings, "nerez", directions=(0,))
    assert "potvrzeno uživatelem" in result.material


def test_missing_orientations_need_two_directions_60_degrees_apart():
    assert _missing((), 30) == ((0.0, 180.0),)
    assert _missing((0.0,), 30) == ((-30.0, 30.0),)
    assert _missing((0.0, 90.0), 30) == ()
    assert _missing((0.0, 60.0), 30) == ()  # ISO 17638: odchylka od kolmých nejvýš 30°
    assert _missing((157.5, 0.0, 22.5), 30) == ((-7.5, 7.5),)
    assert _missing((67.5, 90.0, 112.5), 30) == ((82.5, 97.5),)


# --- přiložení jha ---------------------------------------------------------------------------


def test_poles_on_plate_and_edge_rule(deska):
    yoker = Yoker(PartGeometry(deska), MtSettings())
    along = yoker.place((0, 0, 20), (0, 0, 1), (1, 0, 0), 100)
    assert along.ok and poles(along) == [(-50.0, 0.0, 20.0), (50.0, 0.0, 20.0)]
    across = yoker.best((0, 0, 20), (0, 0, 1), (0, 1, 0))  # 100 + 2 · 10 > 100 mm šířky
    assert across.ok and across.spacing == 75
    assert yoker.place((0, 0, 20), (0, 0, 1), (0, 1, 0), 100).kind == "overhang"
    # pól celý na ploše: střed nejvýš 100 − d/2 − 10 od středu desky
    assert yoker.place((40, 0, 20), (0, 0, 1), (1, 0, 0), 100).ok
    assert not yoker.place((41, 0, 20), (0, 0, 1), (1, 0, 0), 100).ok
    assert yoker.place((52.5, 0, 20), (0, 0, 1), (1, 0, 0), 75).ok
    assert not yoker.place((53, 0, 20), (0, 0, 1), (1, 0, 0), 75).ok


def test_poles_over_weld_cap_and_across_fillet_corner():
    cap = Yoker(PartGeometry(part("tupy_svar")), MtSettings())
    placed = cap.place((0, 0, 14), (0, 0, 1), (1, 0, 0), 100)
    assert placed.ok and poles(placed) == [(-49.96, 0.0, 12.0), (49.96, 0.0, 12.0)]
    fillet = Yoker(PartGeometry(part("koutovy_svar")), MtSettings())
    placed = fillet.place((-8.5, 0, 13.5), (-S, 0, S), (S, 0, S), 100)
    # kružnice r = 50 kolem (−8,5; 13,5): základní deska z = 10 → x = −8,5 − √(50² − 3,5²)
    corner = math.sqrt(50 ** 2 - 3.5 ** 2)
    assert placed.ok and "nohy svírají 90°" in placed.text
    assert poles(placed) == [(round(-8.5 - corner, 2), 0.0, 10.0),
                             (-5.0, 0.0, round(13.5 + corner, 2))]


def test_pipe_circumferential_needs_smaller_spacing():
    yoker = Yoker(PartGeometry(part("trubka")), MtSettings())
    wide = yoker.place((0, 0, R), (0, 0, 1), (0, 1, 0), 100)
    # póly na tětivě 50 mm: nohy svírají 2 · 2 · asin(50 / 114,3) = 103,7°
    assert wide.kind == "legs" and "104°" in wide.text
    narrow = yoker.place((0, 0, R), (0, 0, 1), (0, 1, 0), 75)
    legs = 4 * math.degrees(math.asin(37.5 / (2 * R)))
    assert narrow.ok and f"{legs:.0f}°" in narrow.text  # 76,6°
    assert yoker.place((0, 0, R), (0, 0, 1), (1, 0, 0), 100).ok  # podél osy


def test_yoke_does_not_fit_into_pocket():
    placed = Yoker(PartGeometry(part("kapsa")), MtSettings()).best((0, 0, 15), (0, 0, 1),
                                                                   (1, 0, 0))
    assert not placed.ok and placed.kind == "wall"
    assert "Mezi místem a pólem je stěna" in placed.text and "Ani rozteč 75 mm" in placed.text


def test_place_yoke_returns_shapes_and_zone_outline(deska):
    placed = place_yoke(deska, (0, 0, 20), (0, 0, 1), 0.0)
    assert placed.ok and len(placed.shapes) == 5  # 2 botky, 2 nohy, tělo
    outline = placed.outline(MtSettings())
    assert len(outline) == 5 and outline[0] == outline[-1]
    assert {round(p[0], 6) for p in outline} == {-25.0, 25.0}  # (d − 50) / 2
    assert {round(p[1], 6) for p in outline} == {-25.0, 25.0}  # d / 4


# --- směrové pokrytí v bodech ----------------------------------------------------------------


def test_plate_points_two_directions_or_missing_band(deska):
    a, b, c = check_points(deska, [(0, 0, 20), (0, 45, 20), (95, 0, 20)], [(0, 0, 1)] * 3,
                           FIELD_ONLY)
    assert a.state == "ok" and a.missing == ()
    assert b.state == "limited" and b.angles == (0.0, 22.5, 157.5)
    assert b.missing == ((-7.5, 7.5),)  # vady podél osy X
    assert c.state == "limited" and c.angles == (67.5, 90.0, 112.5)
    assert c.missing == ((82.5, 97.5),)  # vady podél osy Y
    assert c.directions[0] == "no_site" and "nemá kam dosednout" in c.failures[0]


def test_pipe_axial_edge_rule_at_35_mm_from_end():
    near, far = check_points(part("trubka"), [(114, 0, R), (116, 0, R)], [(0, 0, 1)] * 2,
                             FIELD_ONLY, directions=(0,))
    assert near.directions[0] == "ok"  # 150 − 35 = 115 mm
    assert far.directions[0] == "no_site"


def test_pocket_bottom_is_not_covered_because_of_wall():
    samples = check_points(part("kapsa"), [(0, 0, 15), (15, 10, 15)], [(0, 0, 1)] * 2,
                           FIELD_ONLY, directions=(0, 4))
    for sample in samples:
        assert sample.state == "blocked" and sample.field == "blocked"
        assert any(kind == "field_blocked" for kind, _ in sample.reasons)
    assert samples[0].directions[0] == "wall"


def test_off_plane_place_must_belong_to_material_under_the_yoke():
    settings = MtSettings()
    shape = part("kapsa")  # jho na horní ploše vedle kapsy, dno o 25 mm níž
    kapsa = PartGeometry(shape)
    beside = place_yoke(shape, (0, -22.86, 40), (0, 0, 1), 0.0, geo=kapsa)
    assert beside.ok and beside.spacing == 100
    assert covers(beside, (-15, 0, 15), (0, 0, 1), settings) == 0.0  # oblast dno zasáhne,
    assert covers(beside, (-15, 0, 15), (0, 0, 1), settings, kapsa) is None  # tok ale ne
    shape = part("koutovy_svar")  # jho na pásnici podél svaru, svar nad ní
    svar = PartGeometry(shape)
    along = place_yoke(shape, (26, 0, 10), (0, 0, 1), 90.0, geo=svar)  # tělo jha těsně u stojiny
    assert along.ok and along.spacing == 75
    assert covers(along, (8.5, 0, 13.5), (S, 0, S), settings, svar) == pytest.approx(90)
    shape = part("trubka")  # vypouklá trubka: spojnice vede materiálem
    trubka = PartGeometry(shape)
    axial = place_yoke(shape, (0, 0, R), (0, 0, 1), 0.0, geo=trubka)
    phi = math.asin(20 / R)
    point, normal = (10, R * math.sin(phi), R * math.cos(phi)), (0, math.sin(phi), math.cos(phi))
    assert axial.ok and R - point[2] > 2  # mimo rovinu středu
    assert covers(axial, point, normal, settings, trubka) == pytest.approx(0, abs=1e-6)


def test_fillet_weld_across_everywhere_along_only_in_the_middle():
    middle, side = check_points(part("koutovy_svar"), [(-8.5, 0, 13.5), (-8.5, 30, 13.5)],
                                [(-S, 0, S)] * 2, FIELD_ONLY, directions=(0, 4))
    assert middle.directions[0] == "ok" and middle.directions[4] == "ok"  # podél: rozteč 75
    assert side.directions[0] == "ok" and side.directions[4] == "no_site"


def test_uncertain_placement_is_never_counted_as_covered(deska, monkeypatch):
    monkeypatch.setattr(module, "overlap", lambda *a, **k: None)  # průnik nespočítán
    [sample] = check_points(deska, [(0, 0, 20)], [(0, 0, 1)], FIELD_ONLY, directions=(0,))
    assert sample.state == "uncertain" and sample.angles == ()
    assert sample.uncertain_angles == (0.0,) and sample.directions[0] == "uncertain"


def test_apply_and_inspect_come_from_pt_checks():
    session_part = part("sterbina")
    [wall] = check_points(session_part, [(-25.5, 0.0, 15.0)], [(1, 0, 0)],
                          MtSettings(), directions=(0,))
    assert wall.inspect == "blocked" and wall.state == "blocked"
    assert any(kind.startswith("inspect_") for kind, _ in wall.reasons)


# --- mapa ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plate_maps(deska):
    # krok středů 25 mm: uzly mřížky leží i na ose desky (y = 0) – pruh platných poloh podél Y
    # je široký jen 5 mm a mřížka, která ho mine, by pokrytí podhodnotila
    settings = MtSettings(apply=False, inspect=False, step_mm=5, center_step_mm=25)
    return {k: compute(deska, top_faces(deska), settings, "ocel", directions=(k,))
            for k in (0, 4)}


def test_plate_direction_maps_follow_hand_calculation(plate_maps):
    # podél X: x ∈ ⟨−65; 65⟩ = 65 %; podél Y jen rozteč 75: y ∈ ⟨−15; 15⟩ = 30 %
    assert plate_maps[0].percent("ok", "d0") == pytest.approx(65, abs=1.0)
    assert plate_maps[4].percent("ok", "d4") == pytest.approx(30, abs=1.0)


def test_plate_diagonal_map_is_never_above_hand_calculation(deska):
    settings = MtSettings(apply=False, inspect=False, step_mm=5, center_step_mm=10,
                          min_spacing_mm=100)
    result = compute(deska, top_faces(deska), settings, "ocel", directions=(2,))
    # sjednocení otočených čtverců 50 × 50 = osmiúhelník 11 899 mm² = 59,5 %; mřížka středů
    # může pokrytí jen podhodnotit (zubatý okraj do poloviny kroku středů)
    assert 54.0 <= result.percent("ok", "d2") <= 59.5


def test_map_summary_csv_mesh_and_click(plate_maps, tmp_path):
    result = plate_maps[0]
    summary = result.summary()
    assert summary[:2] == [MT_MAP, MT_DISCLAIMER]
    assert any("Směry pole" in line for line in summary)
    assert any("ISO 17638" in line for line in summary)
    path = result.write_csv(tmp_path / "mt.csv")
    rows = path.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == MT_MAP and rows[1] == MT_DISCLAIMER
    header = next(i for i, row in enumerate(rows) if row.startswith("x [mm]"))
    assert len(rows) - header - 1 == len(result.samples)
    nodes, triangles, colors = result.mesh("d0")
    assert len(nodes) == len(colors) == 3 * len(triangles) == 3 * len(result.samples)
    index = result.nearest((90, 0, 20))
    text = " ".join(result.describe(index))
    assert "Nepokryto" in text or "Jen část" in text
    assert "0° = průmět osy +X" in text


def test_same_input_gives_same_states(deska):
    settings = MtSettings(apply=False, inspect=False, step_mm=25, center_step_mm=50)
    first = compute(deska, top_faces(deska), settings, "ocel", directions=(0,))
    second = compute(deska, top_faces(deska), settings, "ocel", directions=(0,))
    assert [s.directions for s in first.samples] == [s.directions for s in second.samples]
    assert [s.state for s in first.samples] == [s.state for s in second.samples]


def test_study_faces_and_estimate(deska):
    geo = PartGeometry(deska)
    study = Document.load(NDT / "deska.json").ndt["studies"][1]
    assert study["method"] == "MT"
    faces = study_faces(geo, study)
    assert len(faces) == 1
    samples, step, centers, center_step, seconds = estimate(
        deska, faces, MtSettings(step_mm=20, center_step_mm=40), "ocel")
    assert samples > 0 and step == 20 and centers > 0 and center_step == 40 and seconds > 0
    with pytest.raises(MtError, match="MT \\(magnetickou práškovou\\)"):
        study_faces(geo, {**study, "method": "PT"})
    with pytest.raises(MtError, match="MT posuzuje povrch"):
        study_faces(geo, {**study, "target": {"kind": "volume"}})


def test_self_check():
    ok, text = self_check(NDT)
    assert ok, text
