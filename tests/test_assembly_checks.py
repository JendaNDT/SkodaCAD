"""Kontroly sestavy – formát 31 (P5.4 K1–K12, matice C01–C19 z docs/p5-4-navrh-kontrol.md)."""

from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path

import pytest

from conftest import EXAMPLES
from skodacad.assembly import Assembly, AssemblyError
from skodacad.assembly_build import build
from skodacad.assembly_check import ascii_name, bill, check, export_step, write_bill
from skodacad.assembly_session import AssemblySession
from skodacad.cli import main

SCREW = EXAMPLES / "sestavy" / "deska_se_sroubem.json"
LID = EXAMPLES / "sestavy" / "krabicka_s_vazbami.json"
THREAD = math.pi * (1.5 ** 2 - 1.25 ** 2) * 6  # šroub Ø 3 v díře Ø 2,5, deska 6 mm


def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def block(size=20, name="Kvádr") -> dict:
    return {"format": "skodacad", "version": 24, "name": name, "material": "ocel",
            "parameters": {}, "features": [
                {"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "rectangle", "width": size, "height": size,
                               "center": [size / 2, size / 2]}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": size}]}


def component(cid: str, path: str, position=(0, 0, 0), **extra) -> dict:
    return {"id": cid, "source": {"path": path},
            "placement": {"position": list(position), "rotation": [0, 0, 0]}, **extra}


def assembly(components: list[dict], checks: dict | None = None) -> dict:
    data = {"format": "skodacad", "kind": "assembly", "version": 31 if checks else 29,
            "name": "Zkouška", "units": "mm", "parameters": {}, "components": components}
    if checks:
        data["checks"] = checks
    return data


@pytest.fixture
def blocks(tmp_path: Path):
    """Dva kvádry 20 mm; ``dx`` = posun druhého v ose X."""
    write(tmp_path / "kvadr.json", block())

    def make(dx: float, checks: dict | None = None, name: str = "s.json") -> Path:
        return write(tmp_path / name, assembly(
            [component("a", "kvadr.json", fixed=True), component("b", "kvadr.json", (dx, 0, 0))],
            checks))

    return make


@pytest.fixture
def screw(tmp_path: Path) -> Path:
    """Kopie ukázky deska se šroubem (díly v podsložce dily/)."""
    shutil.copytree(EXAMPLES / "sestavy" / "dily", tmp_path / "dily")
    shutil.copy(SCREW, tmp_path / "s.json")
    return tmp_path / "s.json"


def run(path: Path, clearance: float | None = None):
    loaded = Assembly.load(path)
    if clearance is not None:
        loaded.checks.clearance = clearance
    result = build(loaded, path)
    return check(result, loaded.checks), result


# --- C01–C03: soubor ---------------------------------------------------------------------


def test_c01_assemblies_without_checks_keep_their_version():
    for path in (EXAMPLES / "sestavy" / "krabicka_s_vickem.json", LID):
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded = Assembly.load(path)
        assert loaded.checks.empty and "checks" not in loaded.to_dict()
        assert loaded.to_dict()["version"] == data["version"]


def test_c02_checks_survive_save_and_open(screw):
    session = AssemblySession()
    session.open(screw)
    session.set_clearance(0.25)
    session.save()
    saved = json.loads(screw.read_text(encoding="utf-8"))
    assert saved["version"] == 31
    assert saved["checks"] == {"clearance": 0.25, "accepted": [
        {"a": ["deska"], "b": ["sroub_1"], "volume": 12.959,
         "note": "závit M3 – díra je jen vrták pod závit (2,5 mm)"}]}
    reopened = AssemblySession()
    reopened.open(screw)
    assert reopened.assembly == session.assembly and not reopened.dirty


@pytest.mark.parametrize(("change", "message"), [
    (lambda d: d.update(version=32), "novější verze"),
    (lambda d: d.update(version=30), "až ve formátu verze 31"),
    (lambda d: d["checks"].update(extra=1), "neznámý klíč „extra“"),
    (lambda d: d["checks"]["accepted"][0].update(why="x"), "neznámý klíč „why“"),
    (lambda d: d["checks"].update(clearance=-1), "kladné číslo"),
    (lambda d: d["checks"].update(clearance=True), "kladné číslo"),
    (lambda d: d["checks"]["accepted"][0].update(a="deska"), "cesta id"),
    (lambda d: d["checks"]["accepted"][0].update(a=[]), "cesta id"),
    (lambda d: d["checks"]["accepted"][0].update(b=["deska"]), "dvěma různými"),
    (lambda d: d["checks"]["accepted"][0].update(volume=-2), "nezáporný objem"),
    (lambda d: d["checks"]["accepted"].append(dict(d["checks"]["accepted"][0])), "dvakrát"),
])
def test_c03_bad_checks_are_refused_in_czech(change, message):
    data = json.loads(SCREW.read_text(encoding="utf-8"))
    change(data)
    with pytest.raises(AssemblyError, match=message):
        Assembly.from_dict(data)


# --- C04–C08: kolize, dotyk, vůle --------------------------------------------------------


def test_c04_overlap_volume_and_centre_follow_the_formula(blocks):
    outcome, _ = run(blocks(15))
    [finding] = outcome.findings
    assert finding.kind == "collision" and finding.a == ("a",) and finding.b == ("b",)
    assert finding.volume == pytest.approx(5 * 20 * 20)
    assert finding.center == pytest.approx((17.5, 10, 10))
    assert not outcome.clean and outcome.pairs == 1 and outcome.candidates == 1


def test_c05_touching_blocks_are_not_a_collision(blocks):
    outcome, _ = run(blocks(20))
    assert outcome.findings == [] and outcome.touches == 1 and outcome.clean


def test_c06_small_clearance_is_reported_below_the_limit_only(blocks):
    outcome, _ = run(blocks(20.3))
    [finding] = outcome.findings
    assert finding.kind == "clearance" and finding.distance == pytest.approx(0.3)
    assert "vůle 0,3 mm" in finding.text
    outcome, _ = run(blocks(20.3), clearance=0.2)
    assert outcome.findings == [] and outcome.candidates == 0  # obálky dál než 0,2 mm


def test_c07_example_box_has_only_touches():
    outcome, result = run(LID)
    assert outcome.pairs == 15 and outcome.candidates == 5
    assert outcome.findings == [] and outcome.touches == 5 and outcome.clean
    assert result.complete


def test_c08_screw_in_tap_hole_collides_and_can_be_accepted(screw):
    session = AssemblySession()
    session.open(screw)
    session.unaccept_collision(["deska"], ["sroub_1"])
    outcome = session.check()
    [finding] = outcome.findings
    assert finding.kind == "collision" and finding.volume == pytest.approx(THREAD, rel=1e-6)
    steps = len(session._undo)
    session.accept_collision(finding.a, finding.b, finding.volume, "závit M3")
    assert len(session._undo) == steps + 1
    view = session.last_check()  # bez nového výpočtu
    assert [f.kind for f in view.findings] == ["accepted"] and view.clean
    assert view.findings[0].note == "závit M3"
    session.undo()
    assert [f.kind for f in session.last_check().findings] == ["collision"]


# --- C09–C14: přijetí, smazání, podsestava, neúplná, nespočítaný průnik ---------------------


def test_c09_accepted_collision_with_changed_volume_collides_again(screw):
    plate = json.loads((screw.parent / "dily" / "deska_m3.json").read_text(encoding="utf-8"))
    plate["parameters"]["t"] = 8  # šroub M3 × 10 je hlouběji v materiálu
    write(screw.parent / "dily" / "deska_m3.json", plate)
    outcome, _ = run(screw)
    [finding] = outcome.findings
    assert finding.kind == "changed" and "objem se změnil z 12,959 mm³" in finding.reason
    assert finding.volume == pytest.approx(math.pi * (1.5 ** 2 - 1.25 ** 2) * 8, rel=1e-6)
    assert not outcome.clean


def test_c10_accepted_collision_that_disappeared_is_reported(blocks):
    path = blocks(25, checks={"accepted": [{"a": ["a"], "b": ["b"], "volume": 2000}]})
    outcome, _ = run(path)
    assert outcome.findings == [] and outcome.clean
    assert len(outcome.gone) == 1 and any("už není" in line for line in outcome.summary())


def test_c11_removing_component_removes_its_accepted_collisions(screw):
    session = AssemblySession()
    session.open(screw)
    session.remove("sroub_1")
    assert session.assembly.checks.accepted == [] and not session.assembly.constraints
    assert session.assembly.to_dict()["version"] == 31  # mez vůle 0,3 zůstala
    session.undo()
    assert len(session.assembly.checks.accepted) == 1


def test_c12_copy_inside_subassembly_is_checked_with_its_path(tmp_path, blocks):
    blocks(0)  # zapíše kvadr.json
    write(tmp_path / "pod.json", assembly([component("k", "kvadr.json", (0, 0, 0))]))
    path = write(tmp_path / "hlavni.json", assembly(
        [component("a", "kvadr.json", fixed=True), component("pod", "pod.json", (10, 0, 0))]))
    outcome, _ = run(path)
    [finding] = outcome.findings
    assert finding.b == ("pod", "k") and finding.b_label == "pod / k"
    assert finding.volume == pytest.approx(10 * 20 * 20)


def test_c13_incomplete_assembly_refuses_check_bill_and_step(blocks, tmp_path):
    path = blocks(15)
    (tmp_path / "kvadr.json").unlink()
    session = AssemblySession()
    session.open(path)
    for action in (session.check, lambda: session.write_bill(tmp_path / "k.csv"),
                   lambda: session.export_step(tmp_path / "s.step")):
        with pytest.raises(AssemblyError, match="úplné sestavy"):
            action()
    assert not (tmp_path / "k.csv").exists() and not (tmp_path / "s.step").exists()


def test_c14_intersection_that_cannot_be_computed_is_never_clean(blocks):
    path = blocks(15)
    loaded = Assembly.load(path)
    result = build(loaded, path)
    outcome = check(result, loaded.checks, intersect=lambda a, b: (None, None))
    assert [f.kind for f in outcome.findings] == ["unknown"] and not outcome.clean
    assert "nelze vyloučit" in outcome.findings[0].reason


# --- C15–C18: kusovník a STEP -------------------------------------------------------------


def test_c15_bill_of_example_box(tmp_path):
    result = build(Assembly.load(LID), LID)
    rows = bill(result, LID)
    assert [(r.name, r.path, r.count, r.material) for r in rows] == [
        ("Krabička pro 3D tisk", "../krabicka.json", 1, "PETG"),
        ("Víčko krabičky", "dily/vicko.json", 1, "PETG"),
        ("Nožička", "dily/nozicka.json", 4, "PETG")]
    foot = rows[2]
    assert foot.volume_mm3 == pytest.approx(math.pi * 5 ** 2 * 3)
    assert foot.components == ["nozicka_1", "nozicka_2", "nozicka_3", "nozicka_4"]
    assert sum(r.total_kg for r in rows) == pytest.approx(result.mass_kg)
    path = write(tmp_path / "ndt.json", json.loads(
        (EXAMPLES / "ndt" / "deska.json").read_text(encoding="utf-8")))
    single = write(tmp_path / "s.json", assembly([component("d", "ndt.json")]))
    [row] = bill(build(Assembly.load(single), single), single)
    assert row.ndt >= 1 and path.name == "ndt.json"


def test_c16_bill_csv_is_czech_excel_friendly(tmp_path):
    result = build(Assembly.load(LID), LID)
    path = write_bill(bill(result, LID), tmp_path / "kusovnik.csv", "Krabička")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM – Excel pozná UTF-8
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert rows[0] == ["Kusovník – Krabička"] and "jen pro samotný díl" in rows[1][0]
    assert rows[5][:4] == ["3", "Nožička", "dily/nozicka.json", "4"]
    assert rows[5][6] == f"{rows_total(result, 'nozicka'):.2f}".replace(".", ",")
    assert rows[-1][0] == "Celkem" and rows[-1][3] == "6"
    assert rows[-1][6] == f"{result.mass_kg * 1000:.2f}".replace(".", ",")


def rows_total(result, stem: str) -> float:
    return sum(i.mass_kg for i in result.instances if i.file.stem == stem) * 1000


def step_tree(path: Path) -> tuple[str, list[tuple[str, str, list]]]:
    """Strom STEP zpět přes XCAF: (kořen, [(kopie, výrobek, podstrom)])."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    assert reader.ReadFile(str(path)) == IFSelect_RetDone and reader.Transfer(document)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())

    def name(label) -> str:
        attr = TDataStd_Name()
        return attr.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(),
                                                                attr) else ""

    def walk(label) -> list:
        children, out = Sequence_TDF_Label(), []
        tool.GetComponents_s(label, children)
        for index in range(children.Length()):
            child, product = children.Value(index + 1), TDF_Label()
            tool.GetReferredShape_s(child, product)
            out.append((name(child), name(product),
                        walk(product) if tool.IsAssembly_s(product) else []))
        return out

    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    assert roots.Length() == 1
    return name(roots.Value(1)), walk(roots.Value(1))


def test_c17_step_export_keeps_tree_names_volume_and_bounds(tmp_path):
    from build123d import import_step

    result = build(Assembly.load(LID), LID)
    path = export_step(result, tmp_path / "sestava.step", "Krabička s víčkem a vazbami")
    root, tree = step_tree(path)
    assert root == "Krabicka s vickem a vazbami"
    assert [(child, product) for child, product, _ in tree] == [
        ("krabicka", "krabicka"), ("vicko", "vicko"),
        *[(f"nozicka_{i}", "nozicka") for i in range(1, 5)]]
    assert path.read_text(errors="replace").count("PRODUCT('nozicka'") == 1  # díl jednou
    back = import_step(str(path))
    assert back.volume == pytest.approx(result.volume_mm3, rel=1e-6)
    low, high = result.bounds()
    box = back.bounding_box()
    assert tuple(box.min) == pytest.approx(low, abs=1e-4)
    assert tuple(box.max) == pytest.approx(high, abs=1e-4)
    assert ascii_name("Šroub M3 × 10 – „víčko“") == 'Sroub M3 x 10 - "vicko"'


def test_c18_subassembly_is_a_nested_assembly_in_step(tmp_path, blocks):
    blocks(0)
    write(tmp_path / "pod.json", assembly([component("k1", "kvadr.json"),
                                           component("k2", "kvadr.json", (30, 0, 0))]))
    path = write(tmp_path / "hlavni.json", assembly(
        [component("a", "kvadr.json", fixed=True), component("pod", "pod.json", (0, 50, 0))]))
    result = build(Assembly.load(path), path)
    out = export_step(result, tmp_path / "s.step", "Hlavní")
    root, tree = step_tree(out)
    assert root == "Hlavni"
    assert tree == [("a", "kvadr", []),
                    ("pod", "pod", [("k1", "kvadr", []), ("k2", "kvadr", [])])]
    from build123d import import_step

    back = import_step(str(out))
    assert back.volume == pytest.approx(3 * 8000) and back.bounding_box().max.Y == 70


# --- C19: příkazová řádka ------------------------------------------------------------------


def test_c19_cli_check_bill_and_export(tmp_path, blocks, capsys):
    out_csv, out_step = tmp_path / "k.csv", tmp_path / "s.step"
    assert main(["sestava", str(SCREW), "--kontrola", "--kusovnik", str(out_csv),
                 "--export", str(out_step)]) == 0
    text = capsys.readouterr().out
    assert "Přijatá kolize: Deska × Šroub M3 × 10: průnik 12,959 mm³" in text
    assert "Kusovník (2 řádky, 2 kusy)" in text and out_csv.is_file() and out_step.is_file()
    assert main(["sestava", str(blocks(15)), "--kontrola"]) == 1
    assert "Kolize: a × b: průnik 2000 mm³" in capsys.readouterr().out
    assert main(["sestava", str(blocks(20.3, name="v.json")), "--kontrola", "--vule", "0,5"]) == 0
    assert "Malá vůle: a × b: vůle 0,3 mm" in capsys.readouterr().out
