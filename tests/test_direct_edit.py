"""P2.3 – přímé úpravy ploch: matice Q01–Q22 (P2.1) a W01–W16 (P2.2).

Očekávání jsou spočítaná ze vzorců (objem, rozměry, poloha upravené plochy), ne
převzatá z výsledku. Odmítnutí kontroluje českou zprávu, stav prvku a nezměněný díl.
"""

from __future__ import annotations

import copy
import json
import math

import pytest
from build123d import Box, GeomType, Part, Pos

from skodacad.assistant import system_prompt
from skodacad.direct_edit import DirectEditError, face_origin, move_face, set_diameter
from skodacad.document import VERSION, Document, DocumentError
from skodacad.ndt.study import part_fingerprint
from skodacad.rebuild import rebuild
from skodacad.selectors import find_face
from skodacad.session import ModelSession

BOX = 40 * 30 * 20
TOP = {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}


def model(*features, parameters=None, measurements=None) -> Document:
    """Kvádr 40 × 30 × 20 (z 0…20) a další prvky."""
    plate = [
        {"id": "obrys", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": 40, "height": 30}]},
        {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": "H"},
    ]
    return Document.from_dict({
        "format": "skodacad", "version": VERSION, "units": "mm",
        "parameters": {"H": 20, **(parameters or {})},
        "features": plate + [copy.deepcopy(f) for f in features],
        "measurements": measurements or [],
    })


def move(face, distance, origin="deska", fid="uprava"):
    return {"id": fid, "type": "move_face", "face": face, "origin": origin,
            "distance": distance}


def diameter(face, value, origin, fid="uprava"):
    return {"id": fid, "type": "face_diameter", "face": face, "origin": origin,
            "diameter": value}


def sketch(fid, plane, *elements):
    return {"id": fid, "type": "sketch", "plane": plane, "elements": list(elements)}


def circle(d, center=(0, 0)):
    return {"shape": "circle", "diameter": d, "center": list(center)}


def rect(w, h, center=(0, 0)):
    return {"shape": "rectangle", "width": w, "height": h, "center": list(center)}


def through_hole(d=10, center=(0, 0)):
    return [sketch("dira_skica", "XY", circle(d, center)),
            {"id": "dira", "type": "extrude", "sketch": "dira_skica", "operation": "cut",
             "through_all": True}]


HOLE = {"at": [5, 0, 10], "normal": [-1, 0, 0], "type": "cylinder"}


def ok(document: Document):
    result = rebuild(document)
    assert result.ok, [s.message for s in result.statuses if s.status != "ok"]
    return result


def failed(document: Document, words: str):
    """Úprava odmítnuta: chyba prvku „uprava“, následné prvky přeskočené, díl beze změny."""
    result = rebuild(document)
    status = next(s for s in result.statuses if s.id == "uprava")
    assert status.status == "error" and words in status.message, status.message
    assert all(s.status == "skipped" for s in result.statuses
               if result.statuses.index(s) > result.statuses.index(status))
    assert result.part is result.parts_before["uprava"]
    return result


def size(part: Part):
    box = part.bounding_box()
    return pytest.approx((box.size.X, box.size.Y, box.size.Z), abs=1e-6)


# --- Q01–Q22: geometrie (P2.1) ----------------------------------------------------------


@pytest.mark.parametrize(("distance", "height"), [(5, 25), (-5, 15)])
def test_q01_box_top_face_moves(distance, height):
    result = ok(model(move(TOP, distance)))
    assert result.part.volume == pytest.approx(40 * 30 * height)
    assert size(result.part) == (40, 30, height)
    top = max(result.part.faces().filter_by(GeomType.PLANE), key=lambda f: f.center().Z)
    assert top.center().Z == pytest.approx(height)


@pytest.mark.parametrize("distance", [-20, -25])
def test_q02_face_moved_through_the_part_is_rejected(distance):
    result = failed(model(move(TOP, distance), sketch("dalsi", "top", circle(5))), "Zkus")
    assert result.part.volume == pytest.approx(BOX)


@pytest.mark.parametrize(("new", "radius"), [(8, 4), (12, 6)])
def test_q03_through_hole_diameter(new, radius):
    result = ok(model(*through_hole(), diameter(HOLE, new, "dira")))
    assert result.part.volume == pytest.approx(BOX - math.pi * radius**2 * 20)
    holes = [f for f in result.part.faces() if f.geom_type == GeomType.CYLINDER]
    assert len(holes) == 1 and holes[0].radius == pytest.approx(radius)
    box = holes[0].bounding_box()  # osa zůstala ve středu kvádru
    assert (box.min + box.max).X / 2 == pytest.approx(0, abs=1e-6)
    assert (box.min + box.max).Y / 2 == pytest.approx(0, abs=1e-6)


def test_q04_blind_hole_keeps_depth():
    features = [sketch("s", "top", circle(10)),
                {"id": "dira", "type": "extrude", "sketch": "s", "operation": "cut",
                 "distance": 8},
                diameter({"at": [5, 0, 16], "normal": [-1, 0, 0], "type": "cylinder"}, 12,
                         "dira")]
    result = ok(model(*features))
    assert result.part.volume == pytest.approx(BOX - math.pi * 36 * 8)
    bottom = [f for f in result.part.faces() if f.geom_type == GeomType.PLANE
              and abs(f.center().Z - 12) < 1e-6]
    assert len(bottom) == 1


def test_q05_boss_diameter_keeps_height():
    features = [sketch("s", "top", circle(10)),
                {"id": "cep", "type": "extrude", "sketch": "s", "operation": "add",
                 "distance": 10},
                diameter({"at": [5, 0, 25], "normal": [1, 0, 0], "type": "cylinder"}, 12, "cep")]
    result = ok(model(*features))
    assert result.part.volume == pytest.approx(BOX + math.pi * 36 * 10)
    assert size(result.part) == (40, 30, 30)


@pytest.mark.parametrize(("center", "new"), [((0, 0), 32), ((14, 0), 14)])
def test_q06_hole_breaking_the_wall_is_rejected(center, new):
    face = {"at": [center[0] + 5, 0, 10], "normal": [-1, 0, 0], "type": "cylinder"}
    failed(model(*through_hole(10, center), diameter(face, new, "dira")), "Zkus")


def trapezoid(*more):
    features = [sketch("lich", "XZ", {"shape": "polygon",
                                      "points": [[-20, 0], [20, 0], [10, 20], [-10, 20]]}),
                {"id": "hranol", "type": "extrude", "sketch": "lich", "distance": 30,
                 "direction": "both"}]
    return Document.from_dict({"format": "skodacad", "version": VERSION, "units": "mm",
                               "features": features + list(more)})


def test_q07_slanted_face_moves_along_its_normal():
    n = 1 / math.sqrt(5)
    face = {"at": [15, 0, 10], "normal": [2 * n, 0, n], "type": "plane"}
    result = ok(trapezoid(move(face, 3, "hranol")))
    assert result.part.volume == pytest.approx(18000 + 3 * math.sqrt(500) * 30)
    bottom = min(result.part.faces().filter_by(GeomType.PLANE), key=lambda f: f.center().Z)
    assert bottom.bounding_box().max.X == pytest.approx(20 + 3 / (2 * n))  # boky v rovinách


def test_q07_trapezoid_top_extends_slanted_sides():
    result = ok(trapezoid(move({"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}, 5,
                               "hranol")))
    assert result.part.volume == pytest.approx((40 + 15) / 2 * 25 * 30)


def test_q08_sharp_neighbouring_fillets_keep_radius():
    fillet = {"id": "r3", "type": "fillet", "radius": 3,
              "edges": {"parallel": "Z", "type": "line"}}
    before = ok(model(fillet)).part.volume
    result = ok(model(fillet, move(TOP, 5)))
    assert result.part.volume == pytest.approx(before * 25 / 20)
    rounds = [f for f in result.part.faces() if f.geom_type == GeomType.CYLINDER]
    assert len(rounds) == 4 and all(f.radius == pytest.approx(3) for f in rounds)


def test_q09_tangent_neighbour_is_rejected_before_the_kernel():
    fillet = {"id": "r3", "type": "fillet", "radius": 3, "edges": {"face": "top"}}
    failed(model(fillet, move({"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}, 5)),
           "hladce navazuje")
    round_hole = {"id": "r1", "type": "fillet", "radius": 1,
                  "edges": {"face": "top", "type": "circle"}}
    failed(model(*through_hole(), round_hole, diameter(HOLE, 11, "dira")), "hladce navazuje")


def test_q10_chamfered_hole():
    chamfer = {"id": "sraz", "type": "chamfer", "distance": 1,
               "edges": {"face": "top", "type": "circle"}}
    result = ok(model(*through_hole(), chamfer, diameter(HOLE, 11, "dira")))
    cone = math.pi * 0.5 / 3 * (5.5**2 + 5.5 * 6 + 6**2)
    assert result.part.volume == pytest.approx(BOX - math.pi * 5.5**2 * 19.5 - cone)
    failed(model(*through_hole(), chamfer, diameter(HOLE, 12, "dira")), "zanikla")


STEP = [sketch("schod", "top", rect(20, 30, (10, 0))),
        {"id": "vyrez", "type": "extrude", "sketch": "schod", "operation": "cut", "distance": 10}]
LOW = {"at": [10, 0, 10], "normal": [0, 0, 1], "type": "plane"}


def test_q11_step_face():
    result = ok(model(*STEP, move(LOW, 3, "vyrez")))
    assert result.part.volume == pytest.approx(BOX - 20 * 30 * 7)
    failed(model(*STEP, move(LOW, 10, "vyrez")), "Zkus")
    failed(model(*STEP, move(LOW, 15, "vyrez")), "Zkus")


@pytest.mark.parametrize(("distance", "depth"), [(2, 3), (-3, 8)])
def test_q12_pocket_bottom(distance, depth):
    features = [sketch("kapsa_s", "top", rect(20, 10)),
                {"id": "kapsa", "type": "extrude", "sketch": "kapsa_s", "operation": "cut",
                 "distance": 5},
                move({"at": [0, 0, 15], "normal": [0, 0, 1], "type": "plane"}, distance,
                     "kapsa")]
    assert ok(model(*features)).part.volume == pytest.approx(BOX - 200 * depth)


FORK = [sketch("zuby", "top", rect(10, 30, (-15, 0)), rect(10, 30, (15, 0))),
        {"id": "zub", "type": "extrude", "sketch": "zuby", "operation": "add", "distance": 20}]
INNER = {"at": [-10, 0, 30], "normal": [1, 0, 0], "type": "plane"}


def test_q13_fork_inner_wall():
    result = ok(model(*FORK, move(INNER, 10, "zub")))
    assert result.part.volume == pytest.approx(BOX + 2 * 10 * 30 * 20 + 10 * 30 * 20)
    failed(model(*FORK, move(INNER, 22, "zub")), "Zkus")


PIN = [sketch("cep_s", "top", circle(12, (-10, 0))),
       {"id": "cep", "type": "extrude", "sketch": "cep_s", "operation": "add", "distance": 10}]
PIN_TOP = {"at": [-10, 0, 30], "normal": [0, 0, 1], "type": "plane"}
PLATE_TOP = {"at": [10, 10, 20], "normal": [0, 0, 1], "type": "plane"}


def test_q14_pin_stays_in_place_when_its_face_moves():
    result = ok(model(*PIN, move(PLATE_TOP, 5)))
    assert result.part.volume == pytest.approx(40 * 30 * 25 + math.pi * 36 * 5)
    assert size(result.part) == (40, 30, 30)


FLANGE = Document.load(__import__("pathlib").Path(__file__).parents[1] / "examples"
                       / "priruba.json")


def flange(*features) -> Document:
    data = FLANGE.to_dict()
    data["features"] += [copy.deepcopy(f) for f in features]
    return Document.from_dict(data)


def test_q15_flange_one_bolt_hole():
    v0 = ok(flange()).part.volume
    c = 62.5 / math.sqrt(2)
    face = {"at": [c + 9, c, 9], "normal": [-1, 0, 0], "type": "cylinder"}
    result = ok(flange(diameter(face, 20, "diry")))
    assert result.part.volume == pytest.approx(v0 - math.pi * (10**2 - 9**2) * 18)
    radii = [round(f.radius, 6) for f in result.part.faces() if f.geom_type == GeomType.CYLINDER]
    assert radii.count(9) == 3 and radii.count(10) == 1


def test_q16_flange_faces():
    base = ok(flange()).part
    v0 = base.volume
    bottom = min(base.faces().filter_by(GeomType.PLANE), key=lambda f: f.center().Z)
    low = {"at": [70, 0, 0], "normal": [0, 0, -1], "type": "plane"}
    thin = ok(flange(move(low, -3, "deska")))
    assert thin.part.volume == pytest.approx(v0 - 3 * bottom.area)
    assert thin.part.bounding_box().size.Z == pytest.approx(15)
    up = {"at": [70, 0, 18], "normal": [0, 0, 1], "type": "plane"}
    thick = ok(flange(move(up, 3, "deska")))
    expected = (v0 + math.pi * (80.5**2 + 80.5 * 77.5 + 77.5**2)
                - math.pi * (32**2 + 32 * 35 + 35**2) - 4 * math.pi * 81 * 3)
    assert thick.part.volume == pytest.approx(expected)
    result = rebuild(flange(move(up, -3, "deska")))
    assert result.statuses[-1].status == "error"


@pytest.mark.parametrize(("feature", "words"), [
    (move(TOP, 0), "různé od 0"),
    (move(TOP, "1/0"), ""),
    (move(TOP, "neznamy + 1"), ""),
    (diameter(HOLE, 10, "dira"), "nic nemění"),
    (diameter(HOLE, -4, "dira"), "kladné"),
])
def test_q17_values_without_effect_or_invalid(feature, words):
    features = through_hole() if feature["type"] == "face_diameter" else []
    result = rebuild(model(*features, feature))
    status = result.statuses[-1]
    assert status.status == "error" and words in status.message


def test_q18_face_of_another_part_is_rejected():
    part, other = Box(40, 30, 20), Box(40, 30, 20)
    top = max(other.faces(), key=lambda f: f.center().Z)
    with pytest.raises(DirectEditError, match="nepatří"):
        move_face(part, top, top.center(), 5)


def test_q19_unsupported_faces():
    chamfer = {"id": "sraz", "type": "chamfer", "distance": 1,
               "edges": {"face": "top", "type": "circle"}}
    cone = {"at": [5.5, 0, 19.5], "normal": [-1, 0, 1], "type": "cone"}
    result = rebuild(model(*through_hole(), chamfer, diameter(cone, 12, "sraz")))
    assert result.statuses[-1].status == "error" and "musí být plocha" in \
        result.statuses[-1].message
    thread = {"id": "zavit", "type": "hole", "kind": "tapped", "size": "M6", "plane": "top",
              "positions": [[0, 0]], "through_all": True, "modeled_thread": True}
    built = ok(model(thread)).part
    core = next(f for f in built.faces() if f.geom_type == GeomType.CYLINDER)
    with pytest.raises(DirectEditError):
        set_diameter(built, core, core.position_at(0.5, 0.5), 6)
    facet = next(f for f in built.faces() if f.geom_type == GeomType.PLANE
                 and abs(f.normal_at().Z) < 0.99 and f.area < 50)
    with pytest.raises(DirectEditError):
        move_face(built, facet, facet.center(), 0.1)


def test_q20_other_bodies_stay_unchanged():
    second = [sketch("druhy", "XY", rect(10, 10, (60, 0))),
              {"id": "kostka", "type": "extrude", "sketch": "druhy", "operation": "add",
               "distance": 10}]
    result = ok(model(*second, move(TOP, 5)))
    volumes = sorted(s.volume for s in result.part.solids())
    assert volumes == pytest.approx([1000, 40 * 30 * 25])


def test_q21_following_features_use_edited_part():
    hole = [sketch("d6", "top", circle(6)),
            {"id": "vrt", "type": "extrude", "sketch": "d6", "operation": "cut",
             "through_all": True}]
    result = ok(model(move(TOP, 5), *hole))
    assert result.part.volume == pytest.approx(40 * 30 * 25 - math.pi * 9 * 25)
    rounded = ok(model(move(TOP, 5), {"id": "r", "type": "fillet", "radius": 2,
                                      "edges": {"face": "top"}}))
    assert rounded.part.bounding_box().size.Z == pytest.approx(25)


def test_q22_parameter_change_before_the_edit_follows_or_stops():
    assert ok(model(move(PLATE_TOP, -3), parameters={"H": 25})).part.volume == \
        pytest.approx(40 * 30 * 22)
    failed(model(*PIN, move(PIN_TOP, 2, "cep"), parameters={"H": 35}), "pochází z prvku")


# --- W01–W16: zápis a pojistka (P2.2) --------------------------------------------------


def test_w01_w02_old_files_open_and_save_as_23(tmp_path):
    for version in range(1, 23):
        data = model().to_dict() | {"version": version}
        document = Document.from_dict(data)
        assert rebuild(document).part.volume == pytest.approx(BOX)
    path = tmp_path / "stary.json"
    model().save(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == VERSION == 23 and Document.load(path) == model()


def test_w03_both_types_survive_save_and_open(tmp_path):
    document = model(*through_hole(), move(TOP, 5, fid="posun"),
                     diameter({"at": [5, 0, 10], "normal": [-1, 0, 0], "type": "cylinder"},
                              12, "dira"))
    path = tmp_path / "upravy.json"
    document.save(path)
    again = Document.load(path)
    assert again == document
    assert rebuild(again).part.volume == pytest.approx(40 * 30 * 25 - math.pi * 36 * 25)


def test_w04_newer_version_is_refused():
    with pytest.raises(DocumentError, match="novější"):
        Document.from_dict(model().to_dict() | {"version": 24})


@pytest.mark.parametrize(("face", "words"), [
    (None, "Chybí povinná hodnota"),
    ({"at": [0, 0, 20], "normal": [0, 0, 1], "type": "cylinder"}, "musí být plocha"),
    ({"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane", "barva": 1}, "Neznámý klíč"),
])
def test_w05_w06_bad_face_reference(face, words):
    feature = move(face, 5)
    if face is None:
        del feature["face"]
    status = rebuild(model(feature)).statuses[-1]
    assert status.status == "error" and words in status.message


def test_w06_diameter_needs_a_cylinder():
    status = rebuild(model(diameter(TOP, 12, "deska"))).statuses[-1]
    assert status.status == "error" and "cylinder" in status.message


def test_w08_missing_origin():
    feature = move(TOP, 5)
    del feature["origin"]
    failed(model(feature), "chybí původ plochy")


def test_w09_origin_not_before_the_edit():
    failed(model(move(TOP, 5, "neexistuje")), "není (smazaný")
    later = model(move(TOP, 5, "pozdeji"), sketch("pozdeji", "top", circle(4)))
    failed(later, "není (smazaný")


def test_w10_swapped_face_stops_with_czech_error():
    failed(model(move(PIN_TOP, 2, "cep")), "není (smazaný")  # čep smazán
    failed(model(*PIN, move(PIN_TOP, 2, "cep"), parameters={"H": 35}),
           "pochází z prvku „deska“")  # jen parametr: nejbližší je teď deska


def holes_in_a_row(count, spacing):
    """Díra Ø6 ve středu a její kopie v řadě po ose X (všechny celé uvnitř kvádru)."""
    return [*through_hole(6),
            {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "linear",
             "count": count, "direction": "X", "spacing": spacing}]


def test_w10_moved_pattern_copy_is_not_replaced_by_the_original():
    copy_hole = {"at": [11, 0, 10], "normal": [-1, 0, 0], "type": "cylinder"}
    edited = ok(model(*holes_in_a_row(2, 8), diameter(copy_hole, 4, "pole")))
    assert edited.part.volume == pytest.approx(BOX - math.pi * 9 * 20 - math.pi * 4 * 20)
    failed(model(*holes_in_a_row(2, -8), diameter(copy_hole, 4, "pole")),
           "pochází z prvku „dira“")
    failed(model(*through_hole(6), diameter(copy_hole, 4, "pole")), "není (smazaný")


def test_w12_known_limit_copy_of_the_same_pattern():
    """Přiznaná mez H3 (M1): jiná kopie téhož pole má stejný původ – úprava proběhne."""
    third = {"at": [19, 0, 10], "normal": [-1, 0, 0], "type": "cylinder"}
    assert ok(model(*holes_in_a_row(3, 8), diameter(third, 4, "pole")))
    result = ok(model(*holes_in_a_row(2, 8), diameter(third, 4, "pole")))  # třetí zmizela
    assert result.part.volume == pytest.approx(BOX - math.pi * 9 * 20 - math.pi * 4 * 20)


def test_w13_two_edits_of_the_same_face():
    second = {"at": [0, 0, 25], "normal": [0, 0, 1], "type": "plane"}
    result = ok(model(move(TOP, 5, fid="prvni"), move(second, 2, "prvni", fid="druha")))
    assert result.part.volume == pytest.approx(40 * 30 * 27)
    part = ok(model()).part
    face, point = find_face(part, TOP)
    assert face_origin([("obrys", None), ("deska", part)], face, point) == "deska"


def test_w14_pattern_cannot_repeat_a_direct_edit():
    pattern = {"id": "pole", "type": "pattern", "features": ["uprava"], "kind": "linear",
               "count": 2, "direction": "X", "spacing": 5}
    status = rebuild(model(move(TOP, 5), pattern)).statuses[-1]
    assert status.status == "error" and "přímá úprava plochy" in status.message


def test_w15_ndt_study_goes_stale_and_measurement_follows():
    thickness = {"id": "m1", "name": "Tloušťka", "kind": "thickness",
                 "a": {"face": {"at": [10, 10, 20], "normal": [0, 0, 1], "type": "plane"}}}
    before, after = model(measurements=[thickness]), model(move(TOP, 5),
                                                           measurements=[thickness])
    assert part_fingerprint(before) != part_fingerprint(after)
    value = rebuild(after).measurements[0].value
    assert value is not None and value.value == pytest.approx(25)


def test_w16_ai_prompt_knows_the_new_format():
    prompt = system_prompt()
    assert "move_face" in prompt and "face_diameter" in prompt and '"version": 23' in prompt


def test_q23_session_undo_redo_and_reopen(tmp_path):
    path = tmp_path / "model.json"
    model(move(TOP, 5)).save(path)
    session = ModelSession()
    session.open(path)
    assert session.result.part.volume == pytest.approx(30000)
    feature = session.feature("uprava") | {"distance": -5}
    session.update_feature("uprava", feature)
    assert session.result.part.volume == pytest.approx(18000)
    session.undo()
    assert session.result.part.volume == pytest.approx(30000)
    session.redo()
    saved = session.save(tmp_path / "kopie.json")
    reopened = ModelSession()
    reopened.open(saved)
    assert reopened.result.part.volume == pytest.approx(18000)


def test_moved_face_of_a_part_from_an_external_solid():
    """Úprava funguje i na díle bez historie (budoucí STEP, G1) – přímé volání jádra."""
    part = Part(Box(40, 30, 20).wrapped).moved(Pos(0, 0, 10))
    top = max(part.faces(), key=lambda f: f.center().Z)
    assert move_face(part, top, top.center(), 5).volume == pytest.approx(30000)
