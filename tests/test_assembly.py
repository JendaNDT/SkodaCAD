"""Sestavy – formát 29 (P5.1 S1–S12, matice A01–A22 z docs/p5-1-navrh-formatu-sestav.md)."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from conftest import EXAMPLES
from skodacad import assembly_build
from skodacad.assembly import Assembly, AssemblyError, check_path
from skodacad.assembly_build import (
    Cache,
    angles_of,
    build,
    location,
    rotation_matrix,
    turned,
)
from skodacad.assembly_session import AssemblySession
from skodacad.cli import main
from skodacad.document import VERSION, Document, DocumentError

SAMPLE = EXAMPLES / "sestavy" / "krabicka_s_vickem.json"


def part_data(width=30, depth=20, height=10, center=(15, 10), material="ocel",
              name="Kvádr") -> dict:
    """Kvádr width × depth × height; výchozí leží v rohu u počátku (0…30, 0…20, 0…10)."""
    return {"format": "skodacad", "version": 24, "name": name, "material": material,
            "parameters": {}, "features": [
                {"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "rectangle", "width": width, "height": depth,
                               "center": list(center)}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": height}]}


def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def component(cid: str, path: str, position=(0, 0, 0), rotation=(0, 0, 0), **extra) -> dict:
    return {"id": cid, "source": {"path": path},
            "placement": {"position": list(position), "rotation": list(rotation)}, **extra}


def assembly_data(components: list[dict], parameters: dict | None = None, **extra) -> dict:
    return {"format": "skodacad", "kind": "assembly", "version": 29, "name": "Zkouška",
            "units": "mm", "parameters": parameters or {}, "components": components, **extra}


def rounded(bounds) -> tuple:
    low, high = bounds
    return tuple(round(v, 6) + 0.0 for v in (*low, *high))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Složka projektu: díl kvádru a sestava se dvěma jeho kopiemi."""
    write(tmp_path / "dily" / "kvadr.json", part_data())
    write(tmp_path / "sestava.json", assembly_data([
        component("a", "dily/kvadr.json", fixed=True),
        component("b", "dily/kvadr.json", position=(100, 0, 0)),
    ]))
    return tmp_path


def test_display_compound_filters_copy_by_ids_without_changing_full_result(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    result = session.result
    before = session.assembly.to_dict()
    for ids, low, high in ((("a",), (0, 0, 0), (30, 20, 10)),
                           (("b",), (100, 0, 0), (130, 20, 10))):
        shown = result.compound(ids)
        assert shown.is_valid and len(shown.solids()) == 1
        assert shown.volume == pytest.approx(30*20*10)
        assert tuple(shown.bounding_box().min) == pytest.approx(low)
        assert tuple(shown.bounding_box().max) == pytest.approx(high)
    assert not result.compound(("neexistuje",)).solids()
    chosen = result.compound(visible_ids={("b",)})
    assert len(chosen.solids()) == 1 and chosen.volume == pytest.approx(6000)
    assert tuple(chosen.bounding_box().min) == pytest.approx((100, 0, 0))
    assert not result.compound(visible_ids=set()).solids()
    assert not result.compound(("a",), visible_ids={("b",)}).solids()
    assert result.volume_mm3 == pytest.approx(12000)
    assert len(result.compound().solids()) == 2
    assert session.assembly.to_dict() == before and not session.can_undo


# --- A01–A06: soubor a jeho kontrola --------------------------------------------------


def test_a01_part_files_never_get_assembly_version():
    assert VERSION == 34
    parts = [path for path in EXAMPLES.rglob("*.json")
             if json.loads(path.read_text(encoding="utf-8")).get("kind") is None]
    assert len(parts) > 20
    for path in parts:
        document = Document.load(path)
        saved = document.to_dict()["version"]
        if any(f["type"] == "guided_loft" for f in document.features):
            assert saved == 34, path
        elif any(f["type"] == "loft" and "wall_mode" in f for f in document.features):
            assert saved == 33, path
        elif any(f["type"] == "variable_fillet" for f in document.features):
            assert saved == 32, path
        else:
            assert saved <= 28, path
    # Díl zapsaný ve verzi 29–31 (verze je nadmnožina) se načte jako dosud.
    for version in (29, 30, 31, 32, 33, 34):
        assert Document.from_dict(part_data() | {"version": version}).features


def test_a02_open_and_save_without_changes_keeps_identical_file(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    session.save()  # poprvé doplní otisky zdrojů (S5)
    first = (project / "sestava.json").read_bytes()
    session = AssemblySession()
    session.open(project / "sestava.json")
    assert not session.dirty
    session.save()
    assert (project / "sestava.json").read_bytes() == first
    saved = json.loads(first)
    assert saved["version"] == 29 and saved["kind"] == "assembly"
    assert len(saved["components"][0]["source"]["fingerprint"]) == 16


def test_a03_assembly_needs_version_29_and_known_kind():
    with pytest.raises(AssemblyError, match="od formátu verze 29"):
        Assembly.from_dict(assembly_data([]) | {"version": 28})
    with pytest.raises(AssemblyError, match="novější verze"):
        Assembly.from_dict(assembly_data([]) | {"version": 32})
    with pytest.raises(DocumentError, match="Neznámý druh souboru"):
        Document.from_dict(part_data() | {"kind": "drawing"})


def test_a04_assembly_and_part_are_not_interchangeable(capsys):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with pytest.raises(DocumentError, match="je sestava, ne díl"):
        Document.from_dict(data)
    # Dřív by se sestava s nízkou verzí otevřela jako prázdný díl – i ta se odmítne.
    with pytest.raises(DocumentError, match="je sestava"):
        Document.from_dict(data | {"version": 1})
    with pytest.raises(AssemblyError, match="je díl, ne sestava"):
        Assembly.from_dict(part_data())
    assert main(["build", str(SAMPLE)]) == 2
    assert "je sestava" in capsys.readouterr().err


@pytest.mark.parametrize("change, message", [
    (lambda d: d["components"][0].pop("id"), "nemá textové „id“"),
    (lambda d: d["components"].append(dict(d["components"][0])), "dvakrát"),
    (lambda d: d.update(barva="modrá"), "neznámý klíč „barva“"),
    (lambda d: d["components"][0].update(scale=2), "neznámý klíč „scale“"),
    (lambda d: d["components"][0]["source"].update(kopie="x"), "neznámý klíč „kopie“"),
    (lambda d: d["components"][0]["placement"].update(mirror=True), "neznámý klíč „mirror“"),
    (lambda d: d.update(units="cm"), "musí být v mm"),
    (lambda d: d["components"][0]["source"].update(fingerprint="XYZ"), "16 znaků"),
    (lambda d: d["components"][0].update(fixed="ano"), "true nebo false"),
    (lambda d: d["components"][0]["placement"].update(position=[0, 0]), "trojice"),
    (lambda d: d["components"][0]["placement"].update(rotation=[True, 0, 0]), "číslo nebo výraz"),
    (lambda d: d["components"][0].pop("source"), "chybí „source“"),
])
def test_a05_structure_errors_are_czech(change, message):
    data = assembly_data([component("a", "dily/kvadr.json")])
    change(data)
    with pytest.raises(AssemblyError, match=message):
        Assembly.from_dict(data)


@pytest.mark.parametrize("text, ok", [
    ("dily/deska.json", True), ("../dily/deska.json", True), ("C:/dily/deska.json", False),
    ("/home/jan/deska.json", False), ("dily\\deska.json", False),
    ("\\\\server\\deska.json", False), ("dily//deska.json", False), ("./deska.json", False),
    ("dily/../deska.json", False), ("..", False), ("", False),
])
def test_a06_path_rules(text, ok):
    if ok:
        assert check_path(text) == text
    else:
        with pytest.raises(AssemblyError):
            check_path(text)


# --- A07–A10: chybějící a vadné komponenty, cykly, meze ------------------------------------


def test_a07_missing_file_keeps_record_and_rest_of_assembly(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    session.save()
    before = json.loads((project / "sestava.json").read_text(encoding="utf-8"))
    (project / "dily" / "kvadr.json").rename(project / "dily" / "jinam.json")
    write(project / "dily" / "druhy.json", part_data(width=10))
    session.insert(project / "dily" / "druhy.json", position=(0, 50, 0))
    result = session.result
    assert [s.state for s in result.statuses] == ["missing", "missing", "ok"]
    assert "se nenašel" in result.status("a").reason
    assert not result.complete and len(result.instances) == 1
    session.save()
    after = json.loads((project / "sestava.json").read_text(encoding="utf-8"))
    assert after["components"][:2] == before["components"]  # záznam beze změny


def test_a08_unreadable_and_broken_sources(tmp_path):
    (tmp_path / "rozbity.json").write_text("{nejde", encoding="utf-8")
    write(tmp_path / "cizi.json", {"format": "jiny"})
    write(tmp_path / "novy.json", part_data() | {"version": 99})
    broken = part_data()
    broken["features"][1]["sketch"] = "neni"
    write(tmp_path / "chyba.json", broken)
    write(tmp_path / "s.json", assembly_data([
        component("json", "rozbity.json"), component("cizi", "cizi.json"),
        component("novy", "novy.json"), component("chyba", "chyba.json")]))
    result = build(Assembly.load(tmp_path / "s.json"), tmp_path / "s.json")
    states = {s.ids[0]: (s.state, s.reason) for s in result.statuses}
    assert states["json"] == ("unreadable", "soubor není platný JSON.")
    assert states["cizi"] == ("unreadable", "soubor není model ŠkodaCAD.")
    assert states["novy"][0] == "unreadable" and "novější" in states["novy"][1]
    assert states["chyba"][0] == "error" and states["chyba"][1]
    assert not result.instances and not result.complete


def test_a09_cycles_are_reported_and_loading_ends(tmp_path):
    write(tmp_path / "a.json", assembly_data([component("b", "pod/b.json")]))
    write(tmp_path / "pod" / "b.json", assembly_data([component("zpet", "../a.json")]))
    result = build(Assembly.load(tmp_path / "a.json"), tmp_path / "a.json")
    assert result.status(("b", "zpet")).state == "cycle"
    assert "a.json → b.json → a.json" in result.status(("b", "zpet")).reason
    write(tmp_path / "sama.json", assembly_data([component("ja", "sama.json")]))
    alone = build(Assembly.load(tmp_path / "sama.json"), tmp_path / "sama.json")
    assert alone.status("ja").state == "cycle"


def test_a10_depth_and_count_limits(tmp_path, monkeypatch):
    write(tmp_path / "kvadr.json", part_data())
    write(tmp_path / "u9.json", assembly_data([component("dil", "kvadr.json")]))
    for level in range(8, 0, -1):
        write(tmp_path / f"u{level}.json",
              assembly_data([component(f"u{level + 1}", f"u{level + 1}.json")]))
    deep = build(Assembly.load(tmp_path / "u1.json"), tmp_path / "u1.json")
    blocked = [s for s in deep.statuses if s.state != "ok"]
    assert len(blocked) == 1 and "nejvýš 8" in blocked[0].reason
    assert len(blocked[0].ids) == 8 and not deep.instances

    with pytest.raises(AssemblyError, match="nejvýš 1000"):
        Assembly.from_dict(assembly_data([component(f"k{i}", "kvadr.json")
                                          for i in range(1001)]))
    monkeypatch.setattr(assembly_build, "MAX_COMPONENTS", 5)
    write(tmp_path / "tri.json", assembly_data([component(f"k{i}", "kvadr.json")
                                                for i in range(3)]))
    write(tmp_path / "dvakrat.json", assembly_data([component("p", "tri.json"),
                                                    component("q", "tri.json")]))
    many = build(Assembly.load(tmp_path / "dvakrat.json"), tmp_path / "dvakrat.json")
    assert "nejvýš 5" in many.error and not many.instances and not many.complete


# --- A11–A13: polohy a kopie --------------------------------------------------------


def test_a11_fixed_axes_order_and_expressions(tmp_path):
    write(tmp_path / "kvadr.json", part_data())
    write(tmp_path / "s.json", assembly_data(
        [component("a", "kvadr.json", rotation=(90, 0, 90)),
         component("b", "kvadr.json", position=["d", "d/2", 0])], parameters={"d": 40}))
    result = build(Assembly.load(tmp_path / "s.json"), tmp_path / "s.json")
    turned_part = result.instances[0].part.bounding_box()
    # Ručně: X 90° (x, y, z) → (x, −z, y), pak Z 90° → (z, x, y).
    assert rounded((turned_part.min, turned_part.max)) == (0, 0, 0, 10, 30, 20)
    moved = result.instances[1].part.bounding_box()
    assert rounded((moved.min, moved.max)) == (40, 20, 0, 70, 40, 10)
    # Výchozí pořadí build123d by dalo jinou polohu – proto se matice skládá výslovně.
    from build123d import Location

    default = Document.from_dict(part_data())
    from skodacad.rebuild import rebuild

    other = rebuild(default).part.moved(Location((0, 0, 0), (90, 0, 90))).bounding_box()
    assert rounded((other.min, other.max)) != (0, 0, 0, 10, 30, 20)


def test_a12_right_angles_are_exact_and_stored_as_whole_numbers(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    session.turn("b", "x", 90)
    session.turn("b", "z", 90)
    assert session.assembly.component("b").rotation == [90, 0, 90]
    assert all(type(v) is int for v in session.assembly.component("b").rotation)
    box = session.result.instances[1].part.bounding_box()
    assert (box.min.X, box.min.Y, box.min.Z) == (100.0, 0.0, 0.0)  # přesně, ne 4e-15
    assert (box.max.X, box.max.Y, box.max.Z) == (110.0, 30.0, 20.0)
    session.turn("b", "y", -90)
    session.turn("b", "y", 90)
    assert session.assembly.component("b").rotation == [90, 0, 90]


def test_rotation_round_trip_for_general_angles():
    for angles in ([10, 20, 30], [-45, 60, 170], [0, 90, 35], [12.5, -90, 0], [180, 0, 180]):
        back = angles_of(rotation_matrix(angles))
        for row_a, row_b in zip(rotation_matrix(angles), rotation_matrix(back), strict=True):
            assert row_a == pytest.approx(row_b, abs=1e-12)
    assert turned([0, 0, 0], "z", 90) == [0, 0, 90]
    assert tuple(location((1, 2, 3), (0, 0, 0)).position) == (1, 2, 3)


def test_a13_copies_share_shape_and_never_touch_source_file(project):
    source = project / "dily" / "kvadr.json"
    original = source.read_bytes()
    session = AssemblySession()
    session.open(project / "sestava.json")
    a, b = session.result.instances
    assert a.part.wrapped.TShape() == b.part.wrapped.TShape()
    session.set_placement("b", position=[0, 0, 50], rotation=[0, 45, 0])
    a2, b2 = session.result.instances
    assert rounded((a2.part.bounding_box().min, a2.part.bounding_box().max)) == \
        rounded((a.part.bounding_box().min, a.part.bounding_box().max))
    assert b2.part.bounding_box().min.Z == pytest.approx(50 - 30 * math.sin(math.pi / 4))
    session.save()
    assert source.read_bytes() == original


# --- A14–A18: změny zdroje, součty, podsestavy, přenos ------------------------------------


def test_a14_changed_source_is_used_and_reported_until_saved(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    session.save()
    assert session.result.volume_mm3 == pytest.approx(2 * 30 * 20 * 10)
    write(project / "dily" / "kvadr.json", part_data(height=20))
    result = session.rebuild()
    assert result.volume_mm3 == pytest.approx(2 * 30 * 20 * 20)
    assert result.status("a").changed and "změnil" in result.warnings[0]
    session.save()
    assert not session.result.warnings


def test_a15_relink_warns_about_other_recipe_and_is_one_undo_step(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    session.save()
    write(project / "dily" / "jiny.json", part_data(width=5))
    write(project / "dily" / "stejny.json", part_data())
    assert "jiný recept" in session.relink_warning("a", project / "dily" / "jiny.json")
    assert session.relink_warning("a", project / "dily" / "stejny.json") == ""
    session.relink("a", project / "dily" / "jiny.json")
    assert session.assembly.component("a").path == "dily/jiny.json"
    session.undo()
    assert session.assembly.component("a").path == "dily/kvadr.json" and not session.can_undo
    (project / "dily" / "zly.json").write_text("{", encoding="utf-8")
    with pytest.raises(AssemblyError, match="nejde použít"):
        session.relink("a", project / "dily" / "zly.json")


def test_a16_sample_volume_and_mass_are_sum_of_parts(capsys):
    result = build(Assembly.load(SAMPLE), SAMPLE)
    assert result.complete and len(result.instances) == 6

    def rounded_rect(w, h, r):
        return w * h - (4 - math.pi) * r * r

    lid = rounded_rect(80, 50, 6) * 2 + (rounded_rect(75.4, 45.4, 3.7)
                                         - rounded_rect(72.4, 42.4, 2.2)) * 4
    foot = math.pi * 5 ** 2 * 3
    box = Document.load(EXAMPLES / "krabicka.json")
    from skodacad.rebuild import rebuild

    box_volume = rebuild(box).part.volume
    assert result.instances[1].volume_mm3 == pytest.approx(lid, rel=1e-9)
    assert result.volume_mm3 == pytest.approx(box_volume + lid + 4 * foot, rel=1e-9)
    assert result.mass_kg == pytest.approx(result.volume_mm3 * 1.27e-6, rel=1e-9)  # PETG
    assert rounded(result.bounds()) == pytest.approx((-40, -25, -3, 40, 25, 32), abs=1e-6)
    lid_box = result.instances[1].part.bounding_box()
    assert (lid_box.min.Z, lid_box.max.Z) == (26.0, 32.0)  # lem v krabičce, deska navrchu
    assert main(["sestava", str(SAMPLE)]) == 0
    assert "Objem: 31309.29 mm³" in capsys.readouterr().out


def test_a16_incomplete_assembly_is_marked(project, capsys):
    (project / "dily" / "kvadr.json").unlink()
    result = build(Assembly.load(project / "sestava.json"), project / "sestava.json")
    assert not result.complete and result.volume_mm3 == 0
    assert main(["sestava", str(project / "sestava.json")]) == 1
    assert "NEÚPLNÁ" in capsys.readouterr().out


def test_a17_subassembly_composes_both_placements(tmp_path):
    write(tmp_path / "noha.json", part_data(width=10, depth=10, height=3, center=(0, 0)))
    write(tmp_path / "pod" / "pod.json", assembly_data([
        component("noha", "../noha.json", position=(10, 0, 0))]))
    write(tmp_path / "s.json", assembly_data([
        component("pod", "pod/pod.json", position=(100, 0, 0), rotation=(0, 0, 90))]))
    result = build(Assembly.load(tmp_path / "s.json"), tmp_path / "s.json")
    assert result.status("pod").kind == "assembly"
    assert result.instances[0].ids == ("pod", "noha")
    assert rounded(result.bounds()) == pytest.approx((95, 5, 0, 105, 15, 3), abs=1e-9)


def test_a18_project_folder_can_move(project, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("jinde") / "projekt"
    shutil.copytree(project, elsewhere)
    here = build(Assembly.load(project / "sestava.json"), project / "sestava.json")
    there = build(Assembly.load(elsewhere / "sestava.json"), elsewhere / "sestava.json")
    assert there.complete and there.volume_mm3 == here.volume_mm3
    assert there.instances[0].file == (elsewhere / "dily" / "kvadr.json").resolve()


def test_a19_different_letter_case_is_found_with_warning(project):
    data = json.loads((project / "sestava.json").read_text(encoding="utf-8"))
    data["components"][1]["source"]["path"] = "Dily/Kvadr.json"
    write(project / "sestava.json", data)
    result = build(Assembly.load(project / "sestava.json"), project / "sestava.json")
    assert result.status("b").state == "ok"
    assert "velikost písmen" in result.status("b").warnings[0]


# --- A20–A22: úpravy, pevná komponenta, ukázka ------------------------------------------


def test_a20_every_change_is_one_undo_step_and_unchanged_is_none(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    new = session.insert(project / "dily" / "kvadr.json", position=(0, 100, 0))
    assert new == "kvadr_1" and session.insert(project / "dily" / "kvadr.json") == "kvadr_2"
    session.move_by(new, (5, 0, 0))
    session.rename(new, "Třetí")
    session.remove("kvadr_2")
    assert len(session._undo) == 5
    session.set_placement(new, position=[5, 100, 0])  # stejné hodnoty = žádný krok
    session.rename(new, "Třetí")
    assert len(session._undo) == 5
    for _ in range(5):
        session.undo()
    assert [c.id for c in session.assembly.components] == ["a", "b"] and not session.can_undo
    session.redo()
    assert session.assembly.components[-1].id == "kvadr_1" and session.can_redo
    assert session.dirty


def test_a21_first_component_is_fixed_and_cannot_be_dragged(tmp_path):
    write(tmp_path / "kvadr.json", part_data())
    session = AssemblySession()
    session.new(tmp_path / "nova.json", "Nová")
    assert json.loads((tmp_path / "nova.json").read_text(encoding="utf-8"))["components"] == []
    first = session.insert(tmp_path / "kvadr.json")
    second = session.insert(tmp_path / "kvadr.json")
    assert session.assembly.component(first).fixed
    assert not session.assembly.component(second).fixed
    with pytest.raises(AssemblyError, match="je pevná"):
        session.move_by(first, (1, 0, 0))
    session.set_placement(first, position=[1, 0, 0])  # výslovně číslem jde
    session.move_by(second, (0, 0, 15))
    assert session.assembly.component(second).position == [0, 0, 15]


def test_insert_refuses_self_cycles_and_other_drives(project, monkeypatch):
    session = AssemblySession()
    session.open(project / "sestava.json")
    with pytest.raises(AssemblyError, match="do sebe samé"):
        session.insert(project / "sestava.json")
    write(project / "obal.json", assembly_data([component("s", "sestava.json")]))
    with pytest.raises(AssemblyError, match="cyklus"):
        session.insert(project / "obal.json")
    (project / "zly.json").write_text("[]", encoding="utf-8")
    with pytest.raises(AssemblyError, match="nejde vložit"):
        session.insert(project / "zly.json")

    def other_drive(path, start):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr("skodacad.assembly_session.os.path.relpath", other_drive)
    with pytest.raises(AssemblyError, match="jiném disku"):
        session.insert(project / "dily" / "kvadr.json")
    assert len(session.assembly.components) == 2


def test_save_as_elsewhere_keeps_components_pointing_to_same_files(project):
    session = AssemblySession()
    session.open(project / "sestava.json")
    (project / "sestavy").mkdir()
    session.save(project / "sestavy" / "kopie.json")
    data = json.loads((project / "sestavy" / "kopie.json").read_text(encoding="utf-8"))
    assert data["components"][0]["source"]["path"] == "../dily/kvadr.json"
    assert session.result.complete


def test_a22_sample_and_its_parts_are_in_examples():
    assert SAMPLE.is_file()
    assembly = Assembly.load(SAMPLE)
    assert [c.path for c in assembly.components][:2] == ["../krabicka.json", "dily/vicko.json"]
    assert sum(c.path == "dily/nozicka.json" for c in assembly.components) == 4
    assert assembly.components[0].fixed
    result = build(assembly, SAMPLE, Cache())
    assert result.complete and not result.warnings


def test_deferred_cache_waits_for_background_parts(project):
    """Okno staví díly v pomocném procesu: sestavení nejdřív jen ohlásí, co čeká."""
    from skodacad.assembly_build import Built, build_part

    cache = Cache(builder=None)
    file = project / "sestava.json"
    first = build(Assembly.load(file), file, cache)
    assert [s.state for s in first.statuses] == ["pending", "pending"]
    assert not first.complete and len(cache.waiting) == 1  # obě kopie = jeden díl
    (source,) = cache.waiting.values()
    cache.store(source, build_part(source.document))
    assert not cache.waiting
    done = build(Assembly.load(file), file, cache)
    assert done.complete and done.volume_mm3 == pytest.approx(2 * 6000)
    broken = Built.from_result(source.document, None)
    assert broken.problem and broken.part is None


def test_save_with_copied_parts_makes_a_standalone_project(project, tmp_path_factory):
    """Uložení ukázky: díly se zkopírují do dily/ vedle sestavy, cizí soubor se nepřepíše."""
    session = AssemblySession()
    session.open(project / "sestava.json")
    write(project / "jiny" / "kvadr.json", part_data(width=5))
    session.insert(project / "jiny" / "kvadr.json", position=(0, 80, 0))
    elsewhere = tmp_path_factory.mktemp("projekt")
    write(elsewhere / "dily" / "kvadr.json", part_data(width=7))  # cizí soubor stejného jména
    session.save(elsewhere / "kopie.json", copy_parts=True)
    data = json.loads((elsewhere / "kopie.json").read_text(encoding="utf-8"))
    paths = [c["source"]["path"] for c in data["components"]]
    assert paths == ["dily/kvadr_2.json", "dily/kvadr_2.json", "dily/kvadr_3.json"]
    assert json.loads((elsewhere / "dily" / "kvadr.json").read_text())["features"][0][
        "elements"][0]["width"] == 7  # cizí soubor zůstal
    assert session.result.complete and session.result.volume_mm3 == pytest.approx(
        2 * 6000 + 5 * 20 * 10)
    assert session.path == (elsewhere / "kopie.json").resolve()
