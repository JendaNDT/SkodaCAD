"""Měření ve 3D: vzdálenosti, úhly, průměry a tloušťka stěny podle vzorců."""

import math

import pytest
from build123d import Axis, GeomType

from conftest import box_features, edge_at, face_at, make_doc
from skodacad import Document, rebuild
from skodacad.document import DocumentError
from skodacad.measure import evaluate, measure, new_measurement


def build_ok(features, parameters=None):
    result = rebuild(make_doc(features, parameters))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    return result.part


def values(items, point=None, part=None):
    faces = [i for i in items if i.__class__.__name__ == "Face"]
    edges = [i for i in items if i.__class__.__name__ == "Edge"]
    return {v.kind: v for v in measure(faces, edges, point, part)}


def holes(x1="x1", x2="x2"):
    """Deska 40 × 30 × t (z = 0 … t) se dvěma průchozími dírami Ø6 v [x1, 3] a [x2, 3]."""
    return box_features(40, 30, "t") + [
        {"id": "ds", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 6, "center": [x1, 3]},
                      {"shape": "circle", "diameter": 6, "center": [x2, 3]}]},
        {"id": "dira", "type": "extrude", "sketch": "ds", "operation": "cut", "through_all": True},
    ]


PARAMS = {"t": 10, "x1": -10, "x2": 5}


def test_plate_thickness_between_parallel_faces_and_at_a_point():
    part = build_ok(holes(), PARAMS)
    top, bottom = face_at(part, 0, -10, 10), face_at(part, 0, -10, 0)
    found = values([top, bottom])
    assert found["parallel"].label == "Vzdálenost rovnoběžných ploch"
    assert found["parallel"].value == pytest.approx(10)
    assert found["distance"].value == pytest.approx(10)
    assert "angle" not in found
    single = values([top], (12, -8, 10), part)
    assert single["thickness"].value == pytest.approx(10)
    assert single["thickness"].points == ((12, -8, 10), pytest.approx((12, -8, 0)))
    assert single["area"].value == pytest.approx(40 * 30 - 2 * math.pi * 9)
    assert next(iter(single)) == "thickness"  # u rovinné plochy je tloušťka první


def test_hole_pitch_axis_distance_and_diameter():
    part = build_ok(holes(), PARAMS)
    left, right = face_at(part, -13, 3, 5), face_at(part, 8, 3, 5)
    assert left.geom_type == right.geom_type == GeomType.CYLINDER
    pitch = values([left, right])["parallel"]
    assert pitch.label == "Rozteč os" and pitch.value == pytest.approx(15)
    assert values([left, right])["distance"].value == pytest.approx(15 - 6)  # mezi stěnami
    front = face_at(part, 0, -15, 5)
    axis = values([right, front])["parallel"]
    assert axis.label == "Vzdálenost osy od plochy" and axis.value == pytest.approx(3 + 15)
    hole = values([left], (-13, 3, 5), part)
    assert next(iter(hole)) == "diameter" and hole["diameter"].value == pytest.approx(6)
    assert hole["thickness"].value == pytest.approx(-13 + 20)  # od díry k levé stěně
    # kružnice na horní ploše: průměr, obvod, vzdálenost středů
    circle_l, circle_r = edge_at(part, -13, 3, 10), edge_at(part, 8, 3, 10)
    edge = values([circle_l])
    assert edge["diameter"].value == pytest.approx(6)
    assert edge["length"].value == pytest.approx(2 * math.pi * 3)
    pair = values([circle_l, circle_r])
    assert pair["centers"].value == pytest.approx(15)
    assert pair["centers"].points == (pytest.approx((-10, 3, 10)), pytest.approx((5, 3, 10)))


CHAMFERED = box_features(40, 30, 20) + [
    {"id": "c", "type": "chamfer", "edges": {"between": ["top", "front"]}, "distance": 10},
]


def test_angles_on_chamfered_block():
    part = build_ok(CHAMFERED)
    top, front = face_at(part, 0, 5, 20), face_at(part, 0, -15, 2)
    slope = face_at(part, 0, -10, 15)
    assert values([top, slope])["angle"].value == pytest.approx(45)
    assert values([slope, front])["angle"].value == pytest.approx(45)
    assert values([top, front])["angle"].value == pytest.approx(90)
    assert values([top, front])["angle"].label == "Úhel mezi plochami"
    slanted = edge_at(part, 20, -10, 15)  # šikmá hrana na pravém boku
    upright = edge_at(part, 20, -15, 5)  # svislá hrana vpravo vpředu
    assert values([slanted, top])["angle"].value == pytest.approx(45)
    assert values([slanted, top])["angle"].label == "Úhel hrany a plochy"
    assert values([slanted, upright])["angle"].value == pytest.approx(45)
    back_edge = edge_at(part, 20, 15, 10)  # svislá hrana vzadu – rovnoběžná se svislou vpředu
    gap = values([upright, back_edge])["parallel"]
    assert gap.label == "Vzdálenost rovnoběžných hran" and gap.value == pytest.approx(30)


def test_wall_thickness_of_tube_shell_and_corroded_plate():
    tube = build_ok([  # trubka Ø60 × 5
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [{"shape": "circle",
                                                                   "diameter": 60}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 100},
        {"id": "v", "type": "sketch", "plane": "top", "elements": [{"shape": "circle",
                                                                    "diameter": 50}]},
        {"id": "r", "type": "extrude", "sketch": "v", "operation": "cut", "through_all": True},
    ])
    outer, inner = face_at(tube, 30, 0, 50), face_at(tube, 25, 0, 50)
    assert values([outer], (0, 30, 40), tube)["thickness"].value == pytest.approx(5)
    assert values([inner], (0, -25, 40), tube)["thickness"].value == pytest.approx(5)
    assert values([outer], (0, 30, 40), tube)["diameter"].value == pytest.approx(60)
    assert values([outer, inner])["parallel"].value == pytest.approx(0)  # soustředné

    shell = build_ok(box_features(40, 30, 20) + [
        {"id": "sk", "type": "shell", "thickness": 2, "open_faces": ["top"]}])
    side = face_at(shell, 20, 0, 10)
    assert values([side], (20, 0, 10), shell)["thickness"].value == pytest.approx(2)
    assert values([face_at(shell, 0, 0, 0)], (5, 5, 0), shell)["thickness"].value == \
        pytest.approx(2)

    # deska 10 mm, zespodu vyžraná jamka hloubky 6 (jako koroze): nad ní zbývají 4 mm
    plate = build_ok(box_features(40, 30, 10) + [
        {"id": "j", "type": "sketch", "plane": "bottom",
         "elements": [{"shape": "circle", "diameter": 10}]},
        {"id": "r", "type": "extrude", "sketch": "j", "operation": "cut", "distance": 6},
    ])
    top = face_at(plate, 15, 10, 10)
    assert values([top], (0, 0, 10), plate)["thickness"].value == pytest.approx(4)
    assert values([top], (15, 0, 10), plate)["thickness"].value == pytest.approx(10)


def test_more_than_two_items_measure_nothing():
    part = build_ok(box_features(10, 10, 10))
    assert measure(list(part.faces())[:3], []) == []


def saved(part):
    """Uložená měření: tloušťka v bodě, tloušťka mezi plochami, rozteč děr (plochy i hrany)."""
    left, right = face_at(part, -13, 3, 5), face_at(part, 8, 3, 5)
    records = []
    for faces, edges, kind, point in (
        ([face_at(part, 0, -10, 10)], [], "thickness", (12, -8, 10)),
        ([face_at(part, 0, -10, 10), face_at(part, 0, -10, 0)], [], "parallel", None),
        ([left, right], [], "parallel", None),
        ([], [edge_at(part, -13, 3, 10), edge_at(part, 8, 3, 10)], "centers", None),
        ([left], [], "diameter", (-13, 3, 5)),
    ):
        records.append(new_measurement(part, faces, edges, kind, point, records))
    return records


def test_saved_measurements_follow_parameters():
    document = make_doc(holes(), PARAMS)
    part = rebuild(document).part
    document.measurements = saved(part)
    assert [m["id"] for m in document.measurements] == ["m1", "m2", "m3", "m4", "m5"]
    assert [m["name"] for m in document.measurements] == [
        "Tloušťka stěny", "Vzdálenost rovnoběžných ploch", "Rozteč os", "Vzdálenost středů",
        "Průměr"]
    reloaded = Document.from_dict(document.to_dict())  # projde uložením do JSON
    for t, x1, x2 in ((10, -10, 5), (25, -12, 9)):
        result = rebuild(reloaded, {"t": t, "x1": x1, "x2": x2})
        got = [m.value.value if m.value else m.error for m in result.measurements]
        assert got == pytest.approx([t, t, x2 - x1, x2 - x1, 6])


def test_saved_measurement_errors_are_czech():
    document = make_doc(holes(), PARAMS)
    document.measurements = saved(rebuild(document).part)
    document.measurements.append({"id": "m9", "kind": "objem", "a": {"face": {"at": [0, 0, 0]}}})
    del document.features[-2:]  # bez děr
    results = rebuild(document).measurements
    assert results[0].value.value == pytest.approx(10)  # deska zůstala
    assert "už na dílu není" in results[2].error  # díry zmizely
    assert "neznámý druh měření „objem“" in results[5].error
    assert "✕" in results[2].text
    assert evaluate(None, document.measurements[0]).error == "žádný díl není – není co měřit"


def test_document_checks_measurements():
    base = {"format": "skodacad", "version": 9, "features": []}
    with pytest.raises(DocumentError, match="dvakrát"):
        Document.from_dict({**base, "measurements": [{"id": "m1", "kind": "angle"}] * 2})
    with pytest.raises(DocumentError, match="kind"):
        Document.from_dict({**base, "measurements": [{"id": "m1"}]})
    with pytest.raises(DocumentError, match="seznam"):
        Document.from_dict({**base, "measurements": {}})
    assert Document.from_dict({**base, "version": 8}).measurements == []


def test_top_face_is_found_after_the_plate_gets_thicker():
    part = build_ok(holes(), PARAMS)
    top = part.faces().sort_by(Axis.Z)[-1]
    [record] = [new_measurement(part, [top], [], "thickness", (0, -10, 10))]
    thicker = build_ok(holes(), {**PARAMS, "t": 30})
    assert evaluate(thicker, record).value.value == pytest.approx(30)


def test_session_saves_renames_and_removes_measurements_with_undo():
    from skodacad.session import ModelSession

    session = ModelSession()
    session.document = make_doc(holes(), PARAMS)
    session.rebuild()
    part = session.result.part
    top = face_at(part, 0, -10, 10)
    shown = session.measure_selection([top.wrapped], (12, -8, 10))
    assert shown[0].text == "Tloušťka stěny: 10.00 mm"
    mid = session.add_measurement([top.wrapped], "thickness", (12, -8, 10))
    assert [m.text for m in session.measurements] == ["Tloušťka stěny: 10.00 mm"]
    session.rename_measurement(mid, "  Stěna u okraje ")
    session.set_parameter("t", "12")
    assert [m.text for m in session.measurements] == ["Stěna u okraje: 12.00 mm"]
    session.remove_measurement(mid)
    assert session.measurements == [] and session.document.measurements == []
    session.undo()
    assert [m.text for m in session.measurements] == ["Stěna u okraje: 12.00 mm"]
    with pytest.raises(DocumentError, match="nesmí být prázdný"):
        session.rename_measurement(mid, " ")
    with pytest.raises(DocumentError, match="v modelu není"):
        session.remove_measurement("m7")
    with pytest.raises(DocumentError, match="jednu nebo dvě"):
        session.add_measurement([f.wrapped for f in part.faces()[:3]], "distance")
    fresh = face_at(session.result.part, 0, -10, 12)  # po přepočtu je díl nový
    with pytest.raises(DocumentError, match="nejde uložit"):  # u jedné plochy není vzdálenost
        session.add_measurement([fresh.wrapped], "distance")


def test_measurements_travel_from_the_background_process():
    import pickle

    from skodacad.worker import decode_result, encode_result

    document = make_doc(holes(), PARAMS)
    document.measurements = saved(rebuild(document).part)
    result = rebuild(document)
    copied = decode_result(pickle.loads(pickle.dumps(encode_result(result))))  # jako rourou
    assert copied.measurements == result.measurements
    assert copied.measurements[2].text == "Rozteč os: 15.00 mm"
