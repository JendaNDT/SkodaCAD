"""Vazby v sestavě – formát 30 (P5.3 M1–M12, matice B01–B19 z docs/p5-3-navrh-vazeb.md)."""

from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path

import pytest

from conftest import EXAMPLES
from skodacad.assembly import Assembly, AssemblyError, fingerprint
from skodacad.assembly_build import build
from skodacad.assembly_session import AssemblySession
from skodacad.cli import main

SAMPLE = EXAMPLES / "sestavy" / "krabicka_s_vazbami.json"

RIM = {"component": "krabicka",
       "face": {"at": [0, 24, 30], "normal": [0, 0, 1], "type": "plane"}}  # okraj krabičky
RING = {"component": "vicko",
        "face": {"at": [0, 24, 2], "normal": [0, 0, 1], "type": "plane"}}  # deska víčka u lemu
BOX_X = {"component": "krabicka",
         "face": {"at": [40, 0, 15], "normal": [1, 0, 0], "type": "plane"}}
LID_X = {"component": "vicko", "face": {"at": [40, 0, 1], "normal": [1, 0, 0], "type": "plane"}}
BOX_FRONT = {"component": "krabicka",
             "face": {"at": [20, -25, 15], "normal": [0, -1, 0], "type": "plane"}}
LID_BACK = {"component": "vicko",
            "face": {"at": [20, 25, 1], "normal": [0, 1, 0], "type": "plane"}}
BOTTOM = {"component": "krabicka",
          "face": {"at": [0, 0, 0], "normal": [0, 0, -1], "type": "plane"}}


def foot_top(cid: str) -> dict:
    return {"component": cid, "face": {"at": [0, 0, 3], "normal": [0, 0, 1], "type": "plane"}}


def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def component(cid: str, path: str, position=(0, 0, 0), rotation=(0, 0, 0), **extra) -> dict:
    return {"id": cid, "source": {"path": path},
            "placement": {"position": list(position), "rotation": list(rotation)}, **extra}


def constraint(cid: str, kind: str, a: dict, b: dict, **extra) -> dict:
    return {"id": cid, "type": kind, "a": a, "b": b, **extra}


def assembly_data(components: list[dict], constraints: list[dict] | None = None,
                  parameters: dict | None = None) -> dict:
    data = {"format": "skodacad", "kind": "assembly", "version": 30 if constraints else 29,
            "name": "Zkouška", "units": "mm", "parameters": parameters or {},
            "components": components}
    if constraints:
        data["constraints"] = constraints
    return data


def block(width, depth, height, center=(0, 0), hole=None, name="Kvádr") -> dict:
    """Kvádr na rovině XY (výška do +Z), volitelně s průchozí dírou ``hole`` = (x, y, d)."""
    features = [{"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "rectangle", "width": width, "height": depth,
                               "center": list(center)}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": height}]
    if hole is not None:
        x, y, diameter = hole
        features += [{"id": "d", "type": "sketch", "plane": "top",
                      "elements": [{"shape": "circle", "diameter": diameter, "center": [x, y]}]},
                     {"id": "o", "type": "extrude", "sketch": "d", "operation": "cut",
                      "distance": height}]
    return {"format": "skodacad", "version": 24, "name": name, "material": "ocel",
            "parameters": {}, "features": features}


def pin(diameter=10, length=30) -> dict:
    return {"format": "skodacad", "version": 24, "name": "Čep", "material": "ocel",
            "parameters": {}, "features": [
                {"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "circle", "diameter": diameter, "center": [0, 0]}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": length}]}


@pytest.fixture
def box_project(tmp_path: Path) -> Path:
    """Krabička, víčko a nožička z ukázek; sestavy se zapisují do ``sestavy/``."""
    shutil.copy(EXAMPLES / "krabicka.json", tmp_path / "krabicka.json")
    shutil.copytree(EXAMPLES / "sestavy" / "dily", tmp_path / "sestavy" / "dily")
    return tmp_path


def box_assembly(folder: Path, lid=((7, -4, 50), (180, 0, 0)), constraints=(),
                 extra=(), parameters=None, name="sestava.json", **box) -> Path:
    components = [component("krabicka", "../krabicka.json", fixed=True, **box),
                  component("vicko", "dily/vicko.json", *lid), *extra]
    return write(folder / "sestavy" / name,
                 assembly_data(components, list(constraints), parameters))


def bounds_of(result, cid: str) -> tuple:
    instance = next(i for i in result.instances if i.ids[-1] == cid)
    box = instance.part.bounding_box()
    return tuple(round(v, 6) + 0.0 for v in (*box.min, *box.max))


def placement(session: AssemblySession, cid: str) -> tuple[list, list]:
    found = session.assembly.component(cid)
    return found.position, found.rotation


# --- B01–B04: soubor ------------------------------------------------------------------


def test_b01_assemblies_without_constraints_stay_version_29(tmp_path):
    plain = EXAMPLES / "sestavy" / "krabicka_s_vickem.json"
    assembly = Assembly.load(plain)
    assert not assembly.constraints
    assert assembly.to_dict()["version"] == 29 and "constraints" not in assembly.to_dict()
    assert Assembly.from_dict(assembly.to_dict()) == assembly
    # Otisk podsestavy bez vazeb je stejný jako ve formátu 29.
    with_empty = copy.deepcopy(assembly)
    with_empty.constraints = []
    assert fingerprint(with_empty) == fingerprint(assembly)
    constrained = Assembly.load(SAMPLE)
    assert constrained.to_dict()["version"] == 30
    assert fingerprint(constrained) != fingerprint(assembly)


def test_b02_save_and_open_keeps_constraints_and_placements(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    session = AssemblySession()
    session.open(path)
    assert session.result.complete and not session.dirty
    session.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    original = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert saved["version"] == 30
    assert saved["constraints"] == original["constraints"]
    assert ([c["placement"] for c in saved["components"]]
            == [c["placement"] for c in original["components"]])
    reopened = AssemblySession()
    reopened.open(path)
    assert reopened.assembly == session.assembly and not reopened.dirty


@pytest.mark.parametrize(("change", "message"), [
    (lambda d: d.update(version=31), "novější verze"),
    (lambda d: d.update(version=29), "až ve formátu verze 30"),
    (lambda d: d["constraints"][0].update(gap=1), "neznámý klíč „gap“"),
    (lambda d: d["constraints"][0].update(type="angle"), "neznámý druh „angle“"),
    (lambda d: d["constraints"][0]["a"].update(edge={}), "neznámý klíč „edge“"),
    (lambda d: d["constraints"][0]["a"]["face"].update(radius=3), "neznámý klíč „radius“"),
    (lambda d: d["constraints"][0]["a"]["face"].pop("type"), "„at“, „normal“ i „type“"),
    (lambda d: d["constraints"][0]["a"]["face"].update(type="cone"), "„plane“"),
    (lambda d: d["constraints"][0]["a"]["face"].update(normal=[0, 0, 0]), "nulový směr"),
    (lambda d: d["constraints"][0]["a"]["face"].update(at=[0, "x", 0]), "trojice čísel"),
    (lambda d: d["constraints"][0].update(a={"component": "krabicka", "plane": "AB"}),
     "jedna z XY, XZ, YZ"),
    (lambda d: d["constraints"][0].update(a={"component": "krabicka", "axis": "Z"}),
     "dvě rovinné plochy"),
    (lambda d: d["constraints"][0].update(type="coaxial"), "dvě válcové plochy"),
    (lambda d: d["constraints"][0].update(b=copy.deepcopy(d["constraints"][0]["a"])),
     "dvě různé komponenty"),
    (lambda d: d["constraints"][0].pop("value"), "potřebuje hodnotu"),
    (lambda d: d["constraints"][1].update(value=3), "jen vzdálenost"),
    (lambda d: d["constraints"][1].update(id="v1"), "dvakrát"),
    (lambda d: d["constraints"][0]["a"].update(plane="XY"), "právě jedno"),
])
def test_b03_bad_constraints_are_refused_in_czech(change, message):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    change(data)
    with pytest.raises(AssemblyError, match=message):
        Assembly.from_dict(data)


def test_b04_missing_component_or_face_keeps_placement(box_project):
    lost = constraint("v9", "mate", BOTTOM, foot_top("nozicka_9"))
    gone = constraint("v8", "mate", RIM, {"component": "vicko", "face": {
        "at": [0, 24, 2], "normal": [0.6, 0.8, 0], "type": "plane"}})  # šikmá plocha není
    path = box_assembly(box_project, constraints=[lost, gone])
    result = build(Assembly.load(path), path)
    assert not result.complete and not result.solved
    assert result.constraint("v9").state == "missing"
    assert "nozicka_9" in result.constraint("v9").reason
    assert result.constraint("v8").state == "missing"
    assert "už na dílu není" in result.constraint("v8").reason
    assert any("odkaz nenalezen" in line for line in result.problems)
    assert bounds_of(result, "vicko")[2] == 44  # 50 − 6, poloha beze změny
    session = AssemblySession()
    session.open(path)
    assert not session.dirty and placement(session, "vicko") == ([7, -4, 50], [180, 0, 0])
    with pytest.raises(AssemblyError, match="už na dílu není"):
        session.add_constraint("mate", RIM, gone["b"])
    assert not session.can_undo


# --- B05–B08: druhy vazeb -----------------------------------------------------------


def test_b05_mate_puts_lid_on_rim_and_leaves_three_freedoms(box_project):
    path = box_assembly(box_project, constraints=[constraint("v1", "mate", RIM, RING)])
    result = build(Assembly.load(path), path)
    assert result.complete
    # Okraj v z = 30 (výška krabičky), deska víčka 2 mm, lem 4 mm dolů do krabičky.
    assert result.solved[("vicko",)] == ([7, -4, 32], [180, 0, 0])
    assert bounds_of(result, "vicko")[2::3] == (26, 32)
    status = result.status("vicko")
    assert status.freedom == (2, 1) and status.freedom_text == "volná: 2 posuny, 1 otočení"
    assert result.status("krabicka").freedom_text == "pevná"
    assert result.constraint("v1").residual < 1e-9


def test_b06_mate_and_two_flushes_fully_determine_lid_from_tilted_start(box_project):
    path = box_assembly(box_project, lid=((7, -4, 50), (180, 8, 12)), constraints=[
        constraint("v1", "mate", RIM, RING), constraint("v2", "flush", BOX_X, LID_X),
        constraint("v3", "flush", BOX_FRONT, LID_BACK)])
    session = AssemblySession()
    session.open(path)
    assert placement(session, "vicko") == ([0, 0, 32], [180, 0, 0])  # jako ručně v ukázce
    assert session.result.status("vicko").freedom_text == "plně určená"
    assert session.dirty and "„vicko“" in session.notice


def test_b07_distance_follows_parameter_expression(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    session = AssemblySession()
    session.open(path)
    assert placement(session, "vicko")[0] == [0, 0, 32]
    session.set_parameters({"mezera": 15})
    assert placement(session, "vicko")[0] == [0, 0, 47]
    assert bounds_of(session.result, "vicko")[2::3] == (41, 47)
    assert session.can_undo and not session.notice
    session.undo()
    assert placement(session, "vicko")[0] == [0, 0, 32] and not session.can_undo
    session.remove_constraint("v4")  # dotyk nožičky nahradí vzdálenost výrazem
    session.add_constraint("distance", BOTTOM, foot_top("nozicka_1"), value="2 * mezera + 1")
    assert placement(session, "nozicka_1")[0] == [-32, -17, -4]


def test_b08_coaxial_cylinder_faces_and_part_axes(tmp_path):
    write(tmp_path / "deska.json", block(60, 40, 10, hole=(20, 0, 10), name="Deska"))
    write(tmp_path / "cep.json", pin())
    hole = {"component": "deska",
            "face": {"at": [25, 0, 5], "normal": [-1, 0, 0], "type": "cylinder"}}
    pin_face = {"component": "cep",
                "face": {"at": [5, 0, 15], "normal": [1, 0, 0], "type": "cylinder"}}
    path = write(tmp_path / "s.json", assembly_data(
        [component("deska", "deska.json", fixed=True),
         component("cep", "cep.json", (5, 3, 20), (10, 0, 0))],
        [constraint("v1", "coaxial", hole, pin_face)]))
    result = build(Assembly.load(path), path)
    assert result.complete
    low_x, low_y, _z, high_x, high_y, _ = bounds_of(result, "cep")
    assert (low_x, low_y, high_x, high_y) == (15, -5, 25, 5)  # osa čepu = osa díry
    assert result.status("cep").freedom_text == "volná: 1 posun, 1 otočení"
    # Osa dílu: osa Z čepu na ose Z desky.
    path = write(tmp_path / "s2.json", assembly_data(
        [component("deska", "deska.json", fixed=True),
         component("cep", "cep.json", (5, 3, 20), (10, 0, 0))],
        [constraint("v1", "coaxial", {"component": "deska", "axis": "Z"},
                    {"component": "cep", "axis": "Z"})]))
    result = build(Assembly.load(path), path)
    low_x, low_y, _z, high_x, high_y, _ = bounds_of(result, "cep")
    assert (low_x, low_y, high_x, high_y) == (-5, -5, 5, 5)
    assert result.status("cep").freedom == (1, 1)


# --- B09–B15: spor, pevné a výrazové polohy, ruční úpravy ---------------------------


def test_b09_conflicting_constraint_is_refused_without_undo_step(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    session = AssemblySession()
    session.open(path)
    before = session.assembly.to_dict()
    with pytest.raises(AssemblyError, match="si odporují.*Víčko na okraji.*zbytek 3,54"):
        session.add_constraint("distance", RIM, RING, value=5, name="Pět milimetrů")
    assert session.assembly.to_dict() == before and not session.can_undo
    assert session.result.complete


def test_b10_conflict_after_part_change_keeps_saved_placements(tmp_path):
    write(tmp_path / "a.json", block(10, 10, 10, name="Sloupek A"))
    write(tmp_path / "b.json", block(10, 10, 10, name="Sloupek B"))
    write(tmp_path / "deska.json", block(120, 20, 2, center=(50, 0), name="Deska"))
    top = {"at": [0, 0, 10], "normal": [0, 0, 1], "type": "plane"}
    under = {"component": "deska", "face": {"at": [0, 0, 0], "normal": [0, 0, -1],
                                            "type": "plane"}}
    path = write(tmp_path / "s.json", assembly_data(
        [component("a", "a.json", fixed=True), component("b", "b.json", (100, 0, 0), fixed=True),
         component("deska", "deska.json", (0, 0, 10))],
        [constraint("v1", "mate", {"component": "a", "face": top}, under),
         constraint("v2", "mate", {"component": "b", "face": top}, under)]))
    session = AssemblySession()
    session.open(path)
    assert session.result.complete and not session.dirty
    write(tmp_path / "b.json", block(10, 10, 12, name="Sloupek B"))  # o 2 mm vyšší
    session.rebuild()
    result = session.result
    assert not result.complete and not session.dirty and not session.notice
    assert {c.state for c in result.constraints} == {"conflict"}
    assert result.status("deska").freedom_text == "ve sporu"
    assert placement(session, "deska") == ([0, 0, 10], [0, 0, 0])
    assert any("ve sporu" in line for line in result.problems)
    # Úprava, která spor nemění, jde dál; spor sám ji nezablokuje.
    session.rename("deska", "Krycí deska")
    assert session.can_undo


def test_b11_upside_down_foot_is_flipped(box_project):
    foot = component("nozicka_1", "dily/nozicka.json", (-30, -15, -10), (180, 0, 0))
    path = box_assembly(box_project, extra=[foot],
                        constraints=[constraint("v1", "mate", BOTTOM, foot_top("nozicka_1"))])
    result = build(Assembly.load(path), path)
    assert result.complete
    position, rotation = result.solved[("nozicka_1",)]
    assert rotation == [0, 0, 0] and position[2] == -3
    assert bounds_of(result, "nozicka_1")[2::3] == (-3, 0)


def test_b12_fixed_component_never_moves(box_project):
    lid = (((0, 0, 40), (180, 0, 0)))
    path = box_assembly(box_project, lid=lid, constraints=[constraint("v1", "mate", RIM, RING)])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["components"][1]["fixed"] = True
    write(path, data)
    result = build(Assembly.load(path), path)
    assert result.constraint("v1").state == "conflict" and not result.solved
    assert "obě komponenty jsou pevné" in result.constraint("v1").reason
    assert bounds_of(result, "krabicka")[2::3] == (0, 30)
    # Pevné víčko, volná krabička: posune se krabička, víčko zůstane.
    data["components"][0]["fixed"] = False
    write(path, data)
    result = build(Assembly.load(path), path)
    assert result.solved == {("krabicka",): ([0, 0, 8], [0, 0, 0])}  # okraj 30 → 38
    assert result.status("vicko").freedom_text == "pevná"


def test_b13_expression_placement_is_never_moved(box_project):
    path = box_assembly(box_project, lid=((0, 0, "H + 3"), (180, 0, 0)), parameters={"H": 30})
    session = AssemblySession()
    session.open(path)
    with pytest.raises(AssemblyError, match="zadaná výrazem.*nahraď výraz číslem"):
        session.add_constraint("mate", RIM, RING)
    assert not session.can_undo
    session.set_placement("vicko", position=[0, 0, "H + 2"])
    session.add_constraint("mate", RIM, RING)  # výraz vazbu splňuje – přijme se, nic se nehne
    assert placement(session, "vicko")[0] == [0, 0, "H + 2"]
    status = session.result.status("vicko")
    assert status.freedom_text == "poloha výrazem – vazby s ní nehýbou"


def test_b14_group_without_fixed_component_keeps_its_first_component(box_project):
    path = box_assembly(box_project, constraints=[constraint("v1", "mate", RIM, RING)],
                        position=(5, 5, 5))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["components"][0].pop("fixed")
    write(path, data)
    result = build(Assembly.load(path), path)
    assert set(result.solved) == {("vicko",)}
    assert result.solved[("vicko",)][0] == [7, -4, 37]
    assert result.status("krabicka").freedom_text == "drží polohu skupiny vazeb"
    assert result.status("vicko").freedom == (2, 1)


def test_b15_manual_move_changes_only_free_motions(box_project):
    path = box_assembly(box_project, lid=((7, -4, 32), (180, 0, 0)),
                        constraints=[constraint("v1", "mate", RIM, RING)])
    session = AssemblySession()
    session.open(path)
    assert not session.dirty
    session.move_by("vicko", (5, 0, 10))
    assert placement(session, "vicko") == ([12, -4, 32], [180, 0, 0])  # z se vrátí
    session.turn("vicko", "z", 90)
    assert placement(session, "vicko") == ([12, -4, 32], [180, 0, 90])
    session.undo()
    session.undo()
    assert placement(session, "vicko") == ([7, -4, 32], [180, 0, 0]) and not session.can_undo
    # Plně určené víčko: posun se vrátí celý – žádný krok Zpět.
    session.add_constraint("flush", BOX_X, LID_X)
    session.add_constraint("flush", BOX_FRONT, LID_BACK)
    steps = len(session._undo)
    session.move_by("vicko", (3, 3, 3))
    assert placement(session, "vicko")[0] == [0, 0, 32] and len(session._undo) == steps


# --- B16–B19: změna dílu, mazání, rychlost, podsestava -------------------------------


def test_b16_taller_box_moves_lid_and_marks_assembly_unsaved(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    box = json.loads((box_project / "krabicka.json").read_text(encoding="utf-8"))
    box["parameters"]["H"] = 40
    write(box_project / "krabicka.json", box)
    session = AssemblySession()
    session.open(path)
    assert placement(session, "vicko")[0] == [0, 0, 42]
    assert session.dirty and "po změně dílu přepočítaly" in session.notice
    assert "„Víčko“" in session.notice and not session.can_undo
    assert session.result.complete


def test_b17_removing_component_removes_its_constraints(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    session = AssemblySession()
    session.open(path)
    session.remove("vicko")
    assert [c.id for c in session.assembly.constraints] == ["v4", "v5", "v6", "v7"]
    assert session.result.complete
    session.undo()
    assert len(session.assembly.constraints) == 7 and not session.can_undo
    session.remove_constraint("v1")
    assert "v1" not in [c.id for c in session.assembly.constraints]
    session.undo()
    session.set_constraint("v1", value=4)
    assert placement(session, "vicko")[0] == [0, 0, 36]
    with pytest.raises(AssemblyError, match="hodnotu má jen vzdálenost"):
        session.set_constraint("v2", value=1)


def test_b18_forty_independent_groups_are_solved_separately(box_project):
    lids = [component(f"v{i}", "dily/vicko.json", (i, 2, 40), (180, 3, 4)) for i in range(40)]
    links = []
    for i in range(40):
        cid = f"v{i}"
        links += [constraint(f"a{i}", "mate", RIM, RING | {"component": cid}),
                  constraint(f"b{i}", "flush", BOX_X, LID_X | {"component": cid}),
                  constraint(f"c{i}", "flush", BOX_FRONT, LID_BACK | {"component": cid})]
    path = write(box_project / "sestavy" / "s.json", assembly_data(
        [component("krabicka", "../krabicka.json", fixed=True), *lids], links))
    assembly = Assembly.load(path)
    build(assembly, path)  # díly v mezipaměti procesu se tu nepočítají do času
    start = time.perf_counter()
    result = build(assembly, path)
    took = time.perf_counter() - start
    assert result.complete and len(result.solved) == 40
    assert all(position == [0, 0, 32] and rotation == [180, 0, 0]
               for position, rotation in result.solved.values())
    assert took < 20, took  # v cloudu řádově sekundy (hledání ploch), ne minuty


def test_b19_face_of_subassembly_in_its_own_coordinates(box_project):
    sub = box_assembly(box_project, name="podsestava.json", position=(0, 0, 10),
                       lid=((0, 0, 50), (180, 0, 0)),
                       constraints=[constraint("v1", "mate", RIM, RING)])
    foot = component("nozicka", "dily/nozicka.json", (95, 3, -20))
    path = write(box_project / "sestavy" / "s.json", assembly_data(
        [component("sub", "podsestava.json", (100, 0, 0), fixed=True), foot],
        [constraint("v1", "mate", {"component": "sub", "face": {
            "at": [0, 0, 10], "normal": [0, 0, -1], "type": "plane"}}, foot_top("nozicka"))]))
    result = build(Assembly.load(path), path)
    assert result.complete
    assert result.solved[("nozicka",)] == ([95, 3, 7], [0, 0, 0])  # dno krabičky z = 10
    # Vazba uvnitř podsestavy se splní při sestavení, soubor podsestavy se nemění.
    assert bounds_of(result, "vicko")[2::3] == (36, 42)
    assert any("uvnitř podsestavy" in w for w in result.status("sub").warnings)
    assert Assembly.load(sub).component("vicko").position == [0, 0, 50]


# --- okno bez okna: odkaz z kliknutí, výchozí vzdálenost, příkazová řádka -------------


def test_reference_from_clicked_face_is_in_part_coordinates(box_project):
    path = box_project / "sestavy" / "s.json"
    shutil.copy(SAMPLE, path)
    session = AssemblySession()
    session.open(path)
    lid = next(i for i in session.result.instances if i.ids == ("vicko",))
    ring = next(f for f in lid.part.faces() if f.geom_type.name == "PLANE"
                and abs(f.normal_at().Z + 1) < 1e-9 and abs(f.center().Z - 30) < 1e-9)
    reference = session.reference_at(ring, (10, 24, 30))
    assert reference == {"component": "vicko", "face": {
        "at": [10, -24, 2], "normal": [0, 0, 1], "type": "plane"}}
    assert session.constraint_kinds(RIM, reference) == ["mate", "flush", "distance"]
    assert session.constraint_kinds({"component": "a", "axis": "Z"},
                                    {"component": "b", "axis": "X"}) == ["coaxial"]
    assert session.constraint_kinds(RIM, {"component": "a", "axis": "Z"}) == []
    assert session.gap(RIM, reference) == 0
    assert session.gap(BOTTOM, foot_top("nozicka_1")) == 0
    session.set_parameters({"mezera": 2.5})
    assert session.gap(RIM, RING) == 2.5


def test_cli_lists_constraints_and_freedom(box_project, capsys):
    assert main(["sestava", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "Vazby (7):" in out and "✓ Víčko na okraji  vzdálenost: krabicka ↔ vicko" in out
    assert "(díl, plně určená)" in out and "volná: 2 posuny, 1 otočení" in out
    path = box_assembly(box_project, constraints=[constraint("v1", "mate", RIM, RING),
                                                  constraint("v2", "distance", RIM, RING,
                                                             value=5)])
    assert main(["sestava", str(path)]) == 1
    out = capsys.readouterr().out
    assert "ve sporu" in out and "NEÚPLNÁ" in out
    path = box_assembly(box_project, name="posun.json",
                        constraints=[constraint("v1", "mate", RIM, RING)])
    assert main(["sestava", str(path)]) == 0
    assert "liší od zapsaných" in capsys.readouterr().out


def test_constraints_wait_for_parts_computed_in_background(box_project):
    """Okno počítá díly v pomocném procesu: do té doby vazby čekají a polohy se nemění."""
    from skodacad.assembly_build import Cache, build_part

    path = box_assembly(box_project, constraints=[constraint("v1", "mate", RIM, RING)])
    session = AssemblySession(Cache(builder=None))
    session.open(path)
    assert session.result.constraint("v1").state == "pending" and not session.dirty
    assert placement(session, "vicko")[0] == [7, -4, 50]
    with pytest.raises(AssemblyError, match="ještě počítá"):
        session.add_constraint("flush", BOX_X, LID_X)
    for source in list(session.cache.waiting.values()):
        session.cache.store(source, build_part(source.document))
    session.rebuild()
    assert placement(session, "vicko")[0] == [7, -4, 32] and session.dirty
    assert session.result.complete
