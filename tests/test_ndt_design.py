"""Konstrukční návrh pro NDT – jádro (etapa 15, krok 15A.1): zadání, varianty, zámky
a podmínky, vyhodnocení na kopii modelu, pořadí, ověření krokem a zpráva
(``docs/ndt/26-navrh-etapa-15.md``)."""

import copy
import csv
import json
from pathlib import Path

import pytest

from conftest import EXAMPLES
from skodacad.document import VERSION, Document
from skodacad.ndt import DISCLAIMER, MT_DISCLAIMER, PT_DISCLAIMER
from skodacad.ndt.design import (
    BANNER,
    DESIGN_NOTE,
    INFORMATIVE,
    MAX_VARIANTS,
    TITLE,
    Design,
    DesignError,
    DesignResult,
    StudyOutcome,
    Variant,
    baseline,
    evaluate,
    rank_and_verify,
)
from skodacad.ndt.study import part_fingerprint
from skodacad.session import ModelSession

NDT = EXAMPLES / "ndt"
MT_QUICK = {"step_mm": 6, "center_step_mm": 12, "apply": False, "inspect": False}
POCKET_WALL = {"id": "m1", "name": "Stěna kapsy X", "kind": "parallel",
               "a": {"face": {"at": [20, 0, 30], "normal": [-1, 0, 0], "type": "plane"}},
               "b": {"face": {"at": [60, 0, 20], "normal": [1, 0, 0], "type": "plane"}}}
RIB_SPAN = {"id": "m1", "name": "Vnější rozteč žeber", "kind": "parallel",
            "a": {"face": {"at": [25, 0, 40], "normal": [1, 0, 0], "type": "plane"}},
            "b": {"face": {"at": [-25, 0, 40], "normal": [-1, 0, 0], "type": "plane"}}}


def model(name, change=None):
    """Ukázka jako slovník s úpravou ``change`` a otisky studií pro upravený recept."""
    data = json.loads((NDT / name).read_text(encoding="utf-8"))
    data["version"] = VERSION
    if change is not None:
        change(data)
    fingerprint = part_fingerprint(Document.from_dict(copy.deepcopy(data)))
    for study in data["ndt"]["studies"]:
        study["part"] = fingerprint
    return data


def pocket(data):
    data["measurements"] = [POCKET_WALL]
    for study in data["ndt"]["studies"]:
        if study["id"] == "s3":
            study["mt"] = dict(MT_QUICK)


def rib_gap(data):
    data["parameters"]["w"] = "m + 2*s"  # vnější rozteč žeber výrazem
    data["measurements"] = [RIB_SPAN]
    data["ndt"]["studies"].append(
        {"id": "s2", "name": "PT dna mezery", "method": "PT", "created": "2026-10-20",
         "target": {"kind": "faces", "faces": [
             {"face": {"at": [0, 0, 15], "normal": [0, 0, 1], "type": "plane"}}]},
         "pt": {"step_mm": 15}})


def test_design_note_matches_the_approved_proposal():
    text = (Path(__file__).parents[1] / "docs" / "ndt" / "26-navrh-etapa-15.md").read_text(
        encoding="utf-8")
    assert DESIGN_NOTE in " ".join(text.split())


def test_design_record_validation_and_round_trip():
    record = {"study": "s3",
              "parameters": [{"name": "a", "values": [40, 96, 100]},
                             {"name": "b", "from": 30, "to": 70, "step": 20}],
              "locked": {"measurements": ["m1"], "parameters": ["A"]},
              "conditions": [{"measurement": "m1", "min": 15, "reason": "pevnost"}],
              "mass_change_pct": 10, "options": {"verify": False, "ut": "check"}}
    design = Design.from_dict(record)
    assert design.parameters[1].values == (30, 50, 70)
    assert design.to_dict() == record and not design.informative
    assert Design.from_dict({"study": "s1", "parameters": [{"name": "a", "values": [1]}]}
                            ).informative
    bad = [
        ({"parameters": [{"name": "a", "values": [1]}]}, "cílovou studii"),
        ({"study": "s1", "parameters": []}, "aspoň jeden"),
        ({"study": "s1", "parameters": [{"name": "a", "values": [1], "from": 0}]}, "ne obojí"),
        ({"study": "s1", "parameters": [{"name": "a", "from": 0, "to": 100, "step": 5}]},
         "nejvýš 12"),
        ({"study": "s1", "parameters": [{"name": "a", "values": [1, 1]}]}, "opakují"),
        ({"study": "s1", "parameters": [{"name": "a", "values": [1]}],
          "locked": {"parameters": ["a"]}}, "měnit a zároveň zamknout"),
        ({"study": "s1", "parameters": [{"name": "a", "values": [1]}],
          "conditions": [{"measurement": "m1", "min": 5, "max": 1}]}, "větší než"),
        ({"study": "s1", "parameters": [{"name": "a", "values": [1]}],
          "options": {"ut": "nic"}}, "rebuild"),
    ]
    for data, message in bad:
        with pytest.raises(DesignError, match=message):
            Design.from_dict(data)


def test_design_check_against_model_and_combinations():
    data = model("kapsa.json", pocket)
    document = Document.from_dict(copy.deepcopy(data))
    design = Design.from_dict({"study": "s3", "parameters": [
        {"name": "a", "values": [40, 96, 100]}, {"name": "b", "values": [30, 40]}]})
    design.check(document)
    combos = design.combinations({"a": 40, "b": 30})
    assert len(combos) == 5 and {"a": 40, "b": 30} not in combos  # původní díl zvlášť
    for record, message in (
            ({"study": "s1", "parameters": [{"name": "a", "values": [50]}]}, "plán dráhy"),
            ({"study": "s9", "parameters": [{"name": "a", "values": [50]}]}, "s9"),
            ({"study": "s3", "parameters": [{"name": "zz", "values": [1]}]}, "zz"),
            ({"study": "s3", "parameters": [{"name": "a", "values": [50]}],
              "conditions": [{"measurement": "m7", "min": 1}]}, "m7")):
        with pytest.raises(DesignError, match=message):
            Design.from_dict(record).check(document)
    document.parameters["a"] = "b + 10"
    with pytest.raises(DesignError, match="výrazem"):
        design.check(document)
    many = Design.from_dict({"study": "s3", "parameters": [
        {"name": "a", "from": 40, "to": 95, "step": 5}, {"name": "b", "values": [30, 40, 50]}]})
    with pytest.raises(DesignError, match=f"nejvýš {MAX_VARIANTS}"):
        many.combinations({"a": 40, "b": 30})


@pytest.fixture(scope="module")
def gap():
    """Deska se dvěma žebry (díl 8): vnější rozteč m + 2s = 50 mm zamčená měřením
    i parametrem w; PT dna mezery s hrubou sítí."""
    data = model("pristup.json", rib_gap)
    design = Design.from_dict({"study": "s2", "parameters": [
        {"name": "m", "values": [30, 34, 40]}, {"name": "s", "values": [8, 10]}],
        "locked": {"measurements": ["m1"], "parameters": ["w"]},
        "options": {"rejected": False}})
    return data, design, baseline(data, design)


def test_locked_dimension_change_does_not_pass(gap):
    _data, design, base = gap
    assert base.measurements["m1"].value.value == pytest.approx(50)  # m + 2s
    wide = evaluate(base, design, 1, {"m": 40, "s": 10})
    assert wide.status == "rejected" and wide.target is None  # NDT se nepočítá
    assert any("zamčená kóta Vnější rozteč žeber" in r and "60,00 mm" in r
               for r in wide.reasons)
    assert any("zamčený parametr w" in r for r in wide.reasons)
    same = evaluate(base, design, 2, {"m": 34, "s": 8})  # 34 + 2 · 8 = 50
    assert same.status == "passed" and all(c.ok for c in same.checks)
    assert same.target.status == "done" and same.target.total == pytest.approx(34 * 100)
    original = evaluate(base, design, 0, {})
    note = rank_and_verify(base, design, [original, same])
    assert note.startswith("Pořadí") and same.verify is not None
    assert same.verify.steps.endswith("poloviční krok")


@pytest.fixture(scope="module")
def walls():
    """Kapsa (díl 2): MT dna kapsy, podmínka stěna X ≥ 15 mm (pevnost)."""
    data = model("kapsa.json", pocket)
    design = Design.from_dict({"study": "s3", "parameters": [
        {"name": "a", "values": [90, 100]}],
        "conditions": [{"measurement": "m1", "min": 15, "reason": "pevnost stěny"}],
        "options": {"rejected": False, "verify": False}})
    return data, design, baseline(data, design)


def test_condition_on_pocket_wall(walls):
    _data, design, base = walls
    assert base.steps["s3"] == {"mt": {"step_mm": 6, "center_step_mm": 12}}
    thin = evaluate(base, design, 2, {"a": 100})  # stěna (120 − 100)/2 = 10 mm
    assert thin.status == "rejected"
    assert thin.reasons == ["podmínka Stěna kapsy X (pevnost stěny): 10,00 mm "
                            "(požadováno ≥ 15 mm)"]
    edge = evaluate(base, design, 1, {"a": 90})  # 15 mm – právě na mezi
    assert edge.status == "passed" and edge.target.total == pytest.approx(90 * 30)
    assert edge.volume == pytest.approx(120 * 80 * 40 - 90 * 30 * 25)


def test_original_variant_matches_the_panel_with_locked_steps(walls):
    data, design, base = walls
    original = evaluate(base, design, 0, {})
    session = ModelSession()
    session.document = Document.from_dict(copy.deepcopy(data))
    session.rebuild()
    session.set_ndt_mt_settings("s3", {**MT_QUICK})
    panel = session.compute_ndt_mt("s3")
    assert [s[3] for s in original.target.states] == pytest.approx(
        [100 * sum(s.area for s in panel.samples if s.state == state) /
         sum(s.area for s in panel.samples) for state, *_ in original.target.states])
    assert original.target.steps == "síť 6 mm, středy jha 12 mm"


def test_variant_that_cannot_be_evaluated():
    data = model("cilove_objemy/tupy_svar_objem.json")
    design = Design.from_dict({"study": "s2", "parameters": [{"name": "h", "values": [0, 1]}],
                               "options": {"verify": False}})
    base = baseline(data, design)
    flat = evaluate(base, design, 1, {"h": 0})
    assert flat.status == "failed" and "nulovou plochu" in flat.reasons[0]
    low = evaluate(base, design, 2, {"h": 1})  # cíl má převýšení 2,0 mm napevno
    assert low.status == "failed" and "chybí 1700 mm³" in low.reasons[-1]



def test_ut_variant_rebuilds_the_saved_plan_and_mass_limit_rejects():
    """Deska se žebrem (díl 3): úhlová sonda 45° s rezervou 5 mm míří od žebra k dnu. Výstupní
    bod musí být aspoň s/2 + 12 + 5 mm od osy, dno pod ním se tedy zasáhne až od x = s/2 − 3:
    silnější žebro (50 místo 10 mm) pokrytí dna ubere. Hmotnost +240 000 mm³ (+52,2 %)."""
    session = ModelSession()
    session.open(NDT / "zebro.json")
    session.set_ndt_device("s1", {"kind": "angle", "length": 40, "width": 20, "front": 12,
                                  "beam_angle": 45, "height": 25, "bounces": 0,
                                  "max_gap": 0.5, "reserve": 5})
    session.compute_ndt_plan("s1", passes=[{
        "face": {"at": [50, 0, 20], "normal": [0, 0, 1], "type": "plane"},
        "point": [50, 0, 20], "angle_deg": 180, "beta": 45, "bounces": 0}],
        options={"row_step_mm": 25})
    data = session.document.to_dict()
    design = Design.from_dict({"study": "s1", "parameters": [{"name": "s", "values": [50]}],
                               "mass_change_pct": 10, "options": {"verify": False}})
    base = baseline(data, design)
    assert "rozteč řádků 25 mm" in base.steps_text["s1"]
    original = evaluate(base, design, 0, {})
    thick = evaluate(base, design, 1, {"s": 50})
    assert original.status == "passed" and original.target.good_pct > 0
    assert thick.status == "rejected"
    assert thick.reasons == ["změna hmotnosti: +52,2 % (požadováno nejvýš ± 10 %)"]
    assert thick.target.good_pct < original.target.good_pct  # informativně spočítáno
    assert thick.volume - original.volume == pytest.approx(40 * 100 * 60)


def outcome(good, limited=0.0, uncertain=0.0, total=1000.0, method="PT"):
    blocked = 100 - good - limited - uncertain
    states = (("ok", "Přístupné", "ok", good, total * good / 100),
              ("limited", "Omezené", "limited", limited, total * limited / 100),
              ("blocked", "Nepřístupné", "blocked", blocked, total * blocked / 100),
              ("uncertain", "Nelze spolehlivě vyhodnotit", "uncertain", uncertain,
               total * uncertain / 100))
    return StudyOutcome("s2", "PT dna", method, states=states, total=total)


def test_ranking_conclusion_and_report(tmp_path):
    design = Design.from_dict({"study": "s2",
                               "parameters": [{"name": "a", "values": [50, 60, 70, 80]}],
                               "conditions": [{"measurement": "m1", "min": 15}]})
    variants = [Variant(0, {}, target=outcome(50), volume=1000.0),
                Variant(1, {"a": 50}, target=outcome(60, uncertain=5), volume=990.0),
                Variant(2, {"a": 60}, target=outcome(60), volume=980.0),
                Variant(3, {"a": 70}, status="rejected", reasons=["podmínka m1: 10 mm"],
                        target=outcome(90), volume=950.0),
                Variant(4, {"a": 80}, status="failed", reasons=["prvek Kapsa: chyba"])]
    result = DesignResult(design, "Kapsa", "kapsa.json", "abc", "ocel", "2026-10-20 12:00",
                          "ŠkodaCAD 0.1.0, vývojová verze", "Python", {"a": 40},
                          {"s2": "síť 8 mm"}, variants)
    assert [v.label for v in result.ranked()] == ["Původní", "V2", "V1", "V3", "V4"]
    assert result.better(variants[2]) and not result.better(variants[4])
    assert result.conclusion().startswith("Nejlepší prošlá varianta V2 (a: 40 → 60)")
    variants[1].target = variants[2].target = outcome(40)
    assert "nezlepšil" in result.conclusion() and "neprošlá varianta V3" in result.conclusion()
    variants[2].target = outcome(50, limited=10)  # při shodě rozhoduje „omezeně“
    assert result.better(variants[2]) and "V2" in result.conclusion()
    variants[1].target = outcome(50, total=1500)  # oblast +50 %
    assert "V1" in result.region_warning()
    page = result.html()
    for text in (TITLE, BANNER, DESIGN_NOTE, DISCLAIMER, PT_DISCLAIMER):
        assert text in page
    assert MT_DISCLAIMER not in page
    for word in ("vyhovuje", "pevnostně v pořádku"):
        assert word not in page.lower()
    names = sorted(p.name for p in result.write_folder(tmp_path / "navrh"))
    assert names == ["navrh.html", "varianty.csv"]
    rows = list(csv.reader((tmp_path / "navrh" / "varianty.csv").open(encoding="utf-8-sig"),
                           delimiter=";"))
    assert [r[0] for r in rows[:4]] == [TITLE, BANNER, DESIGN_NOTE, DISCLAIMER]
    table = rows[[r[0] if r else "" for r in rows].index("varianta") + 1:]
    assert [r[0] for r in table] == ["Původní", "V2", "V1", "V3", "V4"]
    assert table[3][2].startswith("neprošla – podmínka m1")
    informative = DesignResult(Design.from_dict({"study": "s2", "parameters": [
        {"name": "a", "values": [50]}]}), "Kapsa", "", "", "", "", "", "", {"a": 40}, {},
        variants[:2])
    assert INFORMATIVE in informative.row(variants[1])["status"]
