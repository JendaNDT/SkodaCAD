"""Předběžný NDT audit – jádro zprávy (etapa 14, krok 14A.1): převod výsledků metod na
problémová místa a zpráva na referenčních dílech (``docs/ndt/25-navrh-etapa-14.md``)."""

import csv
import dataclasses
import json
import math

import pytest

from conftest import EXAMPLES
from skodacad import __version__
from skodacad.buildinfo import build_text, libraries_text
from skodacad.document import Document
from skodacad.ndt import DISCLAIMER, MT_DISCLAIMER, PT_DISCLAIMER, RT_DISCLAIMER, UT_DISCLAIMER
from skodacad.ndt.audit import (
    NOTE,
    TITLE,
    AuditEntry,
    AuditError,
    AuditResult,
    Spot,
    _clusters,
    find_places,
    layer_of,
)
from skodacad.ndt.coverage import CoverageMap
from skodacad.session import ModelSession
from skodacad.thickness_map import MapSettings
from skodacad.thickness_map import compute as thickness

NDT = EXAMPLES / "ndt"
PLATE = 200 * 100 - math.pi * 10**2  # horní plocha desky s otvorem Ø 20 [mm²]


@pytest.fixture(scope="module")
def maps():
    """Rychlé mapy referenčních dílů: RT deska s otvorem, MT kapsa, PT štěrbina, tloušťka."""
    s = ModelSession()
    s.open(NDT / "otvor.json")
    s.set_ndt_rt_settings("s2", dataclasses.replace(s.ndt_rt_settings("s2"), step_mm=10,
                                                    image_step_mm=20))
    k = ModelSession()
    k.open(NDT / "kapsa.json")
    k.set_ndt_mt_settings("s3", {"step_mm": 6, "center_step_mm": 12, "apply": False,
                                 "inspect": False})
    p = ModelSession()
    p.open(NDT / "sterbina.json")
    p.set_ndt_pt_settings("s2", {"step_mm": 8})
    return {"rt": (s.ndt_study("s2"), s.compute_ndt_rt("s2")),
            "mt": (k.ndt_study("s3"), k.compute_ndt_mt("s3")),
            "pt": (p.ndt_study("s2"), p.compute_ndt_pt("s2")),
            "tl": thickness(s.result.part, MapSettings(limit=21, step=10))}


def done(sid, method, pair, name="studie"):
    record, result = pair
    return AuditEntry(sid, name, method, "done", source="pokus", record=record, result=result)


def test_rt_plate_edges_off_the_film_are_two_places(maps):
    entry = done("s2", "RT", maps["rt"])
    places = entry.places
    assert len(places) == 2 and {p.group for p in places} == {"blocked"}
    assert sorted(round(p.center[1]) for p in places) == [-49, 49]  # dlouhé okraje desky
    assert all(abs(p.center[0]) < 1 for p in places)
    assert all(p.reasons == (("mimo detektor", pytest.approx(100)),) for p in places)
    assert sum(p.share for p in places) == pytest.approx(entry.layer.percent("blocked"))
    assert [p.id for p in places] == ["S2-01", "S2-02"]


def test_mt_pocket_bottom_is_one_place_with_one_reason(maps):
    [place] = done("s3", "MT", maps["mt"]).places
    assert place.label == "Nepokryto" and place.amount == pytest.approx(1200)  # dno 40 × 30
    assert place.reasons == (("jho se nevejde v žádném směru", pytest.approx(100)),)
    assert place.center == pytest.approx((0, 0, 15), abs=1e-6)


def test_pt_slit_walls_are_one_place_with_all_reasons(maps):
    [place] = done("s2", "PT", maps["pt"]).places
    assert place.label == "Nepřístupné" and place.amount == pytest.approx(1600)  # 2 × 40 × 20
    labels = dict(place.reasons)
    assert labels["nástroj se nevejde"] == pytest.approx(100)
    assert "nástřik nejde" in labels and place.example  # celá věta nejčastějšího důvodu


def test_thickness_below_limit_top_and_bottom(maps):
    entry = AuditEntry("tl", "Mapa tloušťky stěny", "TL", "done", result=maps["tl"])
    below = [p for p in entry.places if p.group == "blocked"]
    assert len(below) == 2  # horní a spodní plocha, 20 mm od sebe > 1,6 × 10 mm
    assert sum(p.amount for p in below) == pytest.approx(2 * PLATE, rel=1e-3)
    assert below[0].reasons[0][0] == "tloušťka pod mezí 21,00 mm"
    with pytest.raises(AuditError, match="nemá nastavenou mez"):
        layer_of(dataclasses.replace(maps["tl"], settings=MapSettings()))


def test_ut_coverage_and_clusters():
    centers = [(0, 0, 0), (10, 0, 0), (20, 0, 0), (100, 0, 0), (50, 50, 0), (0, 50, 0)]
    states = ["uncovered", "uncovered", "uncovered", "uncovered", "uncertain", "covered"]
    reasons = ["", "", "", "", "Zásah jen v numerické toleranci.", ""]
    result = CoverageMap([], [], centers, [10.0] * 6, states, [None] * 6, reasons, 9, 9, 0,
                         {"target_step_mm": 10.0}, 0.1)
    places = find_places(layer_of(result), "s1", "UT", "UT")
    assert [(p.label, p.amount) for p in places] == [
        ("Geometricky nepokryto", 30.0), ("Geometricky nepokryto", 10.0),
        ("Nelze spolehlivě vyhodnotit", 10.0)]  # červená podle velikosti, pak šedá
    assert places[2].reasons == (("Zásah jen v numerické toleranci.", pytest.approx(100)),)
    assert places[0].low == (0, 0, 0) and places[0].high == (20, 0, 0)
    spots = [Spot((0, 0, 0), 1, "x"), Spot((16, 0, 0), 1, "x"), Spot((32.1, 0, 0), 1, "x"),
             Spot(None, 1, "x")]
    assert sorted(len(c) for c in _clusters(spots, 16.0)) == [1, 1, 2]  # bez bodu zvlášť
    with pytest.raises(AuditError, match="neumí shrnout"):
        layer_of(object())


def test_report_html_csv_and_folder(maps, tmp_path):
    entries = [done("s2", "RT", maps["rt"], "RT desky"), done("s3", "MT", maps["mt"], "MT kapsy"),
               done("s4", "PT", maps["pt"], "PT štěrbiny"),
               AuditEntry("s1", "UT okolí otvoru", "UT", "skipped",
                          reason="studie nemá plán dráhy ani spočítaný výsledek"),
               AuditEntry("s5", "PT zastaralá", "PT", "unavailable",
                          reason="studie je zastaralá – nejdřív ji potvrď")]
    result = AuditResult("Deska s otvorem", "otvor.json", "30081f12af1d9d7b", "ocel",
                         "2026-10-20 14:30", build_text(), libraries_text(), entries,
                         operator="J. N.")
    assert result.methods() == ["UT", "PT", "MT", "RT"]
    page = result.html()
    for text in (TITLE, DISCLAIMER, UT_DISCLAIMER, PT_DISCLAIMER, MT_DISCLAIMER, RT_DISCLAIMER,
                 NOTE, "Zpracoval(a): J. N.", "neprovedeno", "nedostupné",
                 "studie je zastaralá – nejdřív ji potvrď", build_text()):
        assert text in page
    for word in ("vyhovuje", "protokol o zkoušce", "zkušební protokol"):
        assert word not in page.lower()
    assert page.count("data:image/png;base64,") == 2  # náhledy RT, projekce P1 a P2
    record = json.dumps(maps["rt"][0], ensure_ascii=False, indent=2)
    assert record.replace('"', "&quot;") in page  # celý záznam studie
    places = result.places()
    assert places[0].group == "blocked" and all(p.id in page for p in places)
    paths = result.write_folder(tmp_path / "audit")
    names = sorted(p.name for p in paths)
    assert names == ["mista.csv", "studie-s2-rt.csv", "studie-s3-mt.csv", "studie-s4-pt.csv",
                     "zprava.html"]
    rows = list(csv.reader((tmp_path / "audit" / "mista.csv").open(encoding="utf-8-sig"),
                           delimiter=";"))
    assert [r[0] for r in rows[:7]] == [TITLE, DISCLAIMER, UT_DISCLAIMER, PT_DISCLAIMER,
                                        MT_DISCLAIMER, RT_DISCLAIMER, NOTE]
    table = rows[[r[0] for r in rows].index("označení") + 1:]
    assert len(table) == len(places)
    assert all(row[18] and row[1] and row[20].startswith("zpráva, oddíl studie")
               for row in table)  # u každého místa důvod, studie a odkaz na nastavení


def test_study_record_from_report_repeats_the_same_result(maps):
    record, first = maps["rt"]
    document = Document.load(NDT / "otvor.json").to_dict()
    document["ndt"]["studies"][1] = json.loads(json.dumps(record))  # jako ze zprávy
    session = ModelSession()
    session.document = Document.from_dict(document)
    session.rebuild()
    again = session.compute_ndt_rt("s2")
    assert [s.state for s in again.samples] == [s.state for s in first.samples]


def test_build_text_names_version_and_libraries():
    assert build_text().startswith(f"ŠkodaCAD {__version__}, ")
    assert "Open CASCADE" in libraries_text() and "build123d" in libraries_text()
