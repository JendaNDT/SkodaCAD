"""P6.12 – úkos stěn (docs/p6-11-ukos-steny.md): objem podle vzorce, změřený sklon ploch,
odmítnutí, pojistky a zápis formátu 35.

Očekávané objemy jsou spočítané ze vzorců (průřez po výšce), ne převzaté z výsledku.
"""

from __future__ import annotations

import copy
import math

import pytest
from build123d import Box, Cylinder, Pos, fillet

from skodacad import draft
from skodacad.document import VERSION, Document, DocumentError
from skodacad.features import REPEATABLE_FEATURES, VOLUME_FEATURES, tree_summary
from skodacad.rebuild import rebuild
from skodacad.selectors import find_face

T5 = math.tan(math.radians(5))


def prism(a, b, t, s0, s1):
    """Objem hranolu a × b, jehož rozměry se zmenšují o 2·t·s (s = vzdálenost od neutrální
    roviny, kladná ve směru odebírání): ∫ (a − 2ts)(b − 2ts) ds."""
    def primitive(s):
        return a * b * s - t * (a + b) * s * s + 4 / 3 * t * t * s ** 3
    return primitive(s1) - primitive(s0)


def wall(at, normal, origin="deska"):
    return {"at": at, "normal": normal, "type": "plane", "origin": origin}


WALLS = [wall([20, 0, 10], [1, 0, 0]), wall([-20, 0, 10], [-1, 0, 0]),
         wall([0, 15, 10], [0, 1, 0]), wall([0, -15, 10], [0, -1, 0])]
PLATE = [
    {"id": "obrys", "type": "sketch", "plane": "XY",
     "elements": [{"shape": "rectangle", "width": 40, "height": 30}]},
    {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": "H"},
]


def model(*features, parameters=None, version=VERSION, plate=True) -> Document:
    return Document.from_dict({
        "format": "skodacad", "version": version, "units": "mm",
        "parameters": {"H": 20, **(parameters or {})},
        "features": (PLATE if plate else []) + [copy.deepcopy(f) for f in features],
    })


def ukos(faces=None, pull="+Z", angle=5, neutral=0, fid="ukos"):
    return {"id": fid, "type": "draft", "faces": copy.deepcopy(faces or WALLS), "pull": pull,
            "angle": angle, "neutral": neutral}


def built(document):
    result = rebuild(document)
    assert result.ok, result.first_error
    return result


def drafted(spec, z, neutral=0.0, angle=5.0):
    """Odkaz na zkosenou stěnu: bod ve výšce z a skloněná vnější normála (find_face hledá
    rovinu podle přesné normály, proto se nehledá původní svislá)."""
    t, a = math.tan(math.radians(angle)), math.radians(angle)
    n = spec["normal"]
    at = [spec["at"][0] - n[0] * (z - neutral) * t, spec["at"][1] - n[1] * (z - neutral) * t, z]
    return {"at": at, "normal": [n[0] * math.cos(a), n[1] * math.cos(a), math.sin(a)],
            "type": "plane"}


def slope(part, spec):
    """Složka vnější normály plochy ve směru Z – změřená na hotovém dílu."""
    face, point = find_face(part, {k: v for k, v in spec.items() if k != "origin"})
    return face.normal_at(point).Z


# --- objem a sklon -----------------------------------------------------------------------


def test_four_walls_pull_up_volume_and_measured_slope():
    result = built(model(ukos()))
    part = result.part
    assert part.is_valid and len(part.solids()) == 1
    assert part.volume == pytest.approx(prism(40, 30, T5, 0, 20), abs=1e-6)
    assert part.volume < 24000
    bbox = part.bounding_box()
    assert (bbox.size.X, bbox.size.Y, bbox.size.Z) == pytest.approx((40, 30, 20), abs=1e-9)
    # dno zůstává 40 × 30 (neutrální rovina z = 0), horní hrana je užší o 2·20·tg 5°
    top = part.faces().sort_by(lambda f: f.center().Z)[-1]
    assert top.bounding_box().size.X == pytest.approx(40 - 2 * 20 * T5, abs=1e-9)
    for spec in WALLS:  # vnější normála míří ke směru tažení: sin 5°
        assert slope(part, drafted(spec, 10)) == pytest.approx(math.sin(math.radians(5)),
                                                               abs=1e-9)


def test_pull_down_flips_the_sign():
    part = built(model(ukos(pull="-Z"))).part
    assert part.volume == pytest.approx(prism(40, 30, -T5, 0, 20), abs=1e-6)
    assert part.volume > 24000  # stěny se směrem nahoru rozšíří
    assert part.bounding_box().size.X == pytest.approx(40 + 2 * 20 * T5, abs=1e-9)


def test_negative_angle_equals_opposite_pull():
    assert built(model(ukos(angle=-5))).part.volume == pytest.approx(
        built(model(ukos(pull="-Z", angle=5))).part.volume, abs=1e-6)


def test_neutral_plane_in_the_middle_keeps_the_section():
    part = built(model(ukos(neutral=10))).part
    assert part.volume == pytest.approx(prism(40, 30, T5, -10, 10), abs=1e-6)
    # v neutrální rovině (z = 10) stěna zůstává na místě, o 10 mm výš je užší, níž širší
    for z, x in ((10, 20.0), (20, 20 - 10 * T5), (0, 20 + 10 * T5)):
        face, point = find_face(part, drafted(WALLS[0], z, neutral=10))
        assert point.X == pytest.approx(x, abs=1e-9)


def test_angle_and_neutral_follow_parameters():
    document = model(ukos(angle="A", neutral="N"), parameters={"A": 5, "N": 10})
    assert built(document).part.volume == pytest.approx(prism(40, 30, T5, -10, 10), abs=1e-6)
    document.parameters["A"] = 2
    t2 = math.tan(math.radians(2))
    assert built(document).part.volume == pytest.approx(prism(40, 30, t2, -10, 10), abs=1e-6)


def test_neutral_given_by_a_plane_face_of_the_part():
    top = wall([0, 0, 20], [0, 0, 1])
    top["type"] = "plane"
    part = built(model(ukos(neutral=top, angle=-5))).part
    # neutrální rovina = horní plocha (z = 20); záporný úhel: dno se rozšíří o stejnou míru
    expected = prism(40, 30, -T5, -20, 0)
    assert part.volume == pytest.approx(expected, abs=1e-6)
    assert part.faces().sort_by(lambda f: f.center().Z)[-1].bounding_box().size.X == \
        pytest.approx(40, abs=1e-9)


def test_only_two_opposite_walls():
    part = built(model(ukos(faces=WALLS[:2]))).part
    assert part.volume == pytest.approx(30 * (40 * 20 - T5 * 20 * 20), abs=1e-6)


# --- válec, kapsa, tečný řetěz -----------------------------------------------------------


def test_cylinder_becomes_a_cone_with_the_exact_half_angle():
    document = Document.from_dict({
        "format": "skodacad", "version": VERSION, "units": "mm", "parameters": {},
        "features": [
            {"id": "obrys", "type": "sketch", "plane": "XY",
             "elements": [{"shape": "circle", "diameter": 20}]},
            {"id": "valec", "type": "extrude", "sketch": "obrys", "distance": 30},
            {"id": "ukos", "type": "draft", "pull": "+Z", "angle": 3, "neutral": 0,
             "faces": [{"at": [10, 0, 15], "normal": [1, 0, 0], "type": "cylinder",
                        "origin": "valec"}]}]})
    t3 = math.tan(math.radians(3))
    part = built(document).part
    expected = math.pi * (100 * 30 - 10 * t3 * 900 + t3 * t3 * 27000 / 3)
    assert part.volume == pytest.approx(expected, abs=1e-6)
    cone, = [f for f in part.faces() if f.geom_type.name == "CONE"]
    assert cone.is_valid


def test_pocket_walls_widen_toward_the_pull_direction():
    block = [
        {"id": "obrys", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": 60, "height": 50}]},
        {"id": "blok", "type": "extrude", "sketch": "obrys", "distance": 20},
        {"id": "kapsa_skica", "type": "sketch", "plane": "top",
         "elements": [{"shape": "rectangle", "width": 30, "height": 20}]},
        {"id": "kapsa", "type": "extrude", "sketch": "kapsa_skica", "operation": "cut",
         "distance": 10},
    ]
    faces = [wall([15, 0, 15], [-1, 0, 0], "kapsa"), wall([-15, 0, 15], [1, 0, 0], "kapsa"),
             wall([0, 10, 15], [0, -1, 0], "kapsa"), wall([0, -10, 15], [0, 1, 0], "kapsa")]
    document = Document.from_dict({
        "format": "skodacad", "version": VERSION, "units": "mm", "parameters": {},
        "features": block + [ukos(faces, neutral=20)]})
    part = built(document).part
    # neutrální rovina = ústí kapsy (z = 20): kapsa se ke dnu zužuje
    assert part.volume == pytest.approx(60000 - prism(30, 20, T5, 0, 10), abs=1e-6)
    assert slope(part, drafted(faces[0], 15, neutral=20)) == pytest.approx(
        math.sin(math.radians(5)), abs=1e-9)


def test_one_wall_drafts_the_whole_tangent_chain_of_rounded_corners():
    document = model(
        {"id": "zaobleni", "type": "fillet", "edges": {"parallel": "Z", "type": "line"},
         "radius": 4},
        ukos(faces=[wall([20, 0, 10], [1, 0, 0], "deska")]))
    part = built(document).part
    t, h, r = T5, 20, 4
    expected = (40 * 30 * h - 70 * t * h * h + 4 / 3 * t * t * h ** 3
                - (4 - math.pi) * (r * r * h - r * t * h * h + t * t * h ** 3 / 3))
    assert part.volume == pytest.approx(expected, abs=1e-5)  # všech 8 stěn zkosených


# --- odmítnutí ---------------------------------------------------------------------------


def error_of(document):
    result = rebuild(document)
    assert not result.ok
    return result.first_error.message


def test_angle_outside_the_limit_is_rejected():
    for angle in (0, 31, -45):
        message = error_of(model(ukos(angle=angle)))
        assert "nenulový a nejvýš ±30°" in message


def test_horizontal_face_is_rejected_with_advice():
    top = wall([0, 0, 20], [0, 0, 1])
    assert "kolmá na směr tažení" in error_of(model(ukos(faces=[top])))


def test_duplicate_face_is_rejected():
    assert "dvakrát" in error_of(model(ukos(faces=[WALLS[0], WALLS[0]])))


def test_wrong_origin_is_rejected():
    faces = [{**WALLS[0], "origin": "obrys"}]
    assert "pochází" in error_of(model(ukos(faces=faces)))


def test_neutral_face_must_be_perpendicular_to_the_pull():
    assert "kolmá na směr tažení" in error_of(model(ukos(neutral=wall([20, 0, 10], [1, 0, 0]))))


def test_too_steep_angle_for_a_tall_part_is_rejected_by_the_kernel():
    message = error_of(model(ukos(angle=28), parameters={"H": 60}))
    assert "Zmenši úhel" in message


def test_floor_fillet_blocks_the_draft_with_advice():
    block = Pos(0, 0, 10) * Box(60, 50, 20) - Pos(0, 0, 15) * Box(30, 20, 10)
    floor = block.edges().filter_by(
        lambda e: abs(e.center().Z - 10) < 1e-6 and abs(e.center().X) < 16
        and abs(e.center().Y) < 11)
    rounded = fillet(floor, 2)
    pocket_wall = [f for f in rounded.faces() if f.geom_type.name == "PLANE"
                   and abs(f.normal_at().Z) < 1e-6 and abs(f.center().X) < 20
                   and abs(f.center().Y) < 20][0]
    with pytest.raises(draft.DraftError, match="před zaoblením"):
        draft.apply(rounded, [pocket_wall], "+Z", 5, 20.0)
    # stejná kapsa bez zaoblení dna jde
    plain = [f for f in block.faces() if f.geom_type.name == "PLANE"
             and abs(f.normal_at().Z) < 1e-6 and abs(f.center().X) < 20
             and abs(f.center().Y) < 20]
    assert draft.apply(block, plain, "+Z", 5, 20.0).is_valid


# --- služba přímo ------------------------------------------------------------------------


def side_walls(part):
    return [f for f in part.faces() if f.geom_type.name == "PLANE"
            and abs(f.normal_at().Z) < 0.5]


def test_angle_is_absolute_not_added_to_an_existing_slope():
    box = Pos(0, 0, 10) * Box(40, 30, 20)
    first = draft.apply(box, side_walls(box), "+Z", -4, 0.0)
    second = draft.apply(first, side_walls(first), "+Z", 2, 0.0)
    for face in side_walls(second):
        assert face.normal_at().Z == pytest.approx(math.sin(math.radians(2)), abs=1e-9)


def test_horizontal_pull_direction_in_the_service():
    box = Pos(20, 0, 0) * Box(40, 30, 20)  # x od 0 do 40
    faces = [f for f in box.faces() if abs(f.normal_at().X) < 1e-6]
    part = draft.apply(box, faces, "+X", 5, 0.0)
    assert part.volume == pytest.approx(prism(30, 20, T5, 0, 40), abs=1e-5)


def test_cylinder_with_axis_off_the_pull_is_rejected():
    cylinder = Pos(0, 0, 15) * Cylinder(10, 30)
    wall_face = [f for f in cylinder.faces() if f.geom_type.name == "CYLINDER"]
    with pytest.raises(draft.DraftError, match="osu mimo směr tažení"):
        draft.apply(cylinder, wall_face, "+X", 3, 0.0)


def test_sphere_is_rejected():
    from build123d import Sphere

    sphere = Sphere(10)
    with pytest.raises(draft.DraftError, match="není rovina ani válec"):
        draft.apply(sphere, list(sphere.faces()), "+Z", 3, 0.0)


# --- formát 35, strom a registr ----------------------------------------------------------


def test_format_35_only_with_the_draft_feature():
    assert model(ukos()).to_dict()["version"] == 35
    assert model().to_dict()["version"] == 24  # starší díly beze změny formátu


def test_draft_needs_format_35():
    with pytest.raises(DocumentError, match="verze 35"):
        model(ukos(), version=34)


def test_structure_errors_are_czech():
    for bad, text in (
        ({**ukos(), "faces": []}, "aspoň jednu plochu"),
        ({**ukos(), "pull": "Z"}, "Směr tažení"),
        ({**ukos(), "faces": [{"at": [0, 0, 0]}]}, "„at“ a „normal“"),
        ({**ukos(), "faces": [{**WALLS[0], "origin": ""}]}, "původ plochy"),
        ({**ukos(), "faces": [{**WALLS[0], "type": "sphere"}]}, "plane nebo cylinder"),
        ({**ukos(), "extra": 1}, "neznámý klíč"),
        ({**ukos(), "angle": True}, "Úhel úkosu"),
        ({**ukos(), "neutral": True}, "Neutrální rovina"),
    ):
        with pytest.raises(DocumentError, match=text):
            model(bad)


def test_round_trip_keeps_the_result():
    document = model(ukos(angle="A"), parameters={"A": 5})
    again = Document.from_dict(document.to_dict())
    assert built(again).part.volume == pytest.approx(built(document).part.volume, abs=1e-9)


def test_registry_summary_and_no_repetition():
    assert "draft" in VOLUME_FEATURES and "draft" not in REPEATABLE_FEATURES
    assert tree_summary(ukos(angle=5), {}) == "5°"
    assert tree_summary(ukos(angle="A"), {"A": 3}) == "3°"


def test_example_box_with_draft_matches_the_formula():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "examples" / "ukos_krabicka.json"
    document = Document.from_dict(json.loads(path.read_text(encoding="utf-8")))
    part = built(document).part
    t = math.tan(math.radians(3))
    assert part.volume == pytest.approx(prism(60, 40, -t, 0, 20) - prism(50, 30, t, 0, 15),
                                        abs=1e-6)
    assert document.to_dict()["version"] == 35
    document.parameters["UHEL"] = 1  # parametr mění oba úkosy
    t1 = math.tan(math.radians(1))
    assert built(document).part.volume == pytest.approx(
        prism(60, 40, -t1, 0, 20) - prism(50, 30, t1, 0, 15), abs=1e-6)


# --- výběr ploch ve 3D přes ModelSession -------------------------------------------------


def session_with_plate(tmp_path):
    from skodacad.session import ModelSession

    path = tmp_path / "deska.json"
    model().save(path)
    session = ModelSession()
    session.open(path)
    return session


SIDES = ((20, 0), (-20, 0), (0, 15), (0, -15))  # středy stěn desky v rovině XY


def side_faces(session, which=(0, 1, 2, 3)):
    """Stěny podle polohy (po úkosu už nejsou svislé, proto se hledají nejbližší)."""
    walls = [f for f in session.result.part.faces()
             if f.geom_type.name == "PLANE" and abs(f.normal_at().Z) < 0.5]
    found = []
    for index in which:
        x, y = SIDES[index]
        found.append(min(walls, key=lambda f: math.hypot(f.center().X - x, f.center().Y - y)))
    return [face.wrapped for face in found]


def test_session_creates_draft_from_selected_faces_with_origin_and_neutral(tmp_path):
    session = session_with_plate(tmp_path)
    feature_id = session.add_from_selection("draft", side_faces(session))
    feature = session.feature(feature_id)
    assert feature["type"] == "draft" and feature["pull"] == "+Z"
    assert len(feature["faces"]) == 4
    assert all(spec["origin"] == "deska" and spec["type"] == "plane" for spec in feature["faces"])
    assert feature["neutral"] == 0  # dno vybraných stěn (z = 0), rozměr u dna zůstane
    session.rebuild()
    assert session.result.ok
    assert session.result.part.volume == pytest.approx(prism(40, 30, math.tan(math.radians(3)),
                                                              0, 20), abs=1e-6)
    session.undo()
    assert all(f["type"] != "draft" for f in session.document.features)  # jeden krok Zpět


def test_session_adds_more_faces_and_highlights_them(tmp_path):
    session = session_with_plate(tmp_path)
    feature_id = session.add_from_selection("draft", side_faces(session, (0, 1)))
    session.rebuild()
    assert len(session.feature(feature_id)["faces"]) == 2
    session.apply_selection(feature_id, side_faces(session, (2, 3)))  # zbylé dvě stěny
    session.rebuild()
    assert len(session.feature(feature_id)["faces"]) == 4
    assert session.result.ok
    assert len(session.feature_highlight(feature_id)) == 4


def test_session_rejects_edges_and_counts_draftable_faces(tmp_path):
    session = session_with_plate(tmp_path)
    edge = session.result.part.edges()[0].wrapped
    with pytest.raises(DocumentError, match="bez hran"):
        session.add_from_selection("draft", [edge])
    with pytest.raises(DocumentError, match="bez hran"):
        session.add_from_selection("draft", [])
    info = session.selection_info(side_faces(session))
    assert info.faces == 4 and info.edges == 0 and info.draftable_faces == 4
