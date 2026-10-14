"""Chyby v modelu: srozumitelná česká zpráva, díl zůstane ve stavu před chybou."""

import pytest

from conftest import box_features, make_doc
from skodacad import DocumentError, rebuild


def statuses(result):
    return [(s.id, s.status) for s in result.statuses]


def test_too_large_fillet_keeps_previous_part_and_skips_rest():
    doc = make_doc(box_features(20, 30, 40) + [
        {"id": "f", "type": "fillet", "edges": "all", "radius": 50},
        {"id": "c", "type": "chamfer", "edges": "all", "distance": 1},
    ])
    result = rebuild(doc)
    assert statuses(result) == [("s", "ok"), ("e", "ok"), ("f", "error"), ("c", "skipped")]
    assert "Zaoblení R50 se nepodařilo" in result.first_error.message
    assert result.part.volume == pytest.approx(20 * 30 * 40)


@pytest.mark.parametrize(
    ("feature", "message"),
    [
        ({"id": "x", "type": "neznamy"}, "Neznámý typ prvku"),
        ({"id": "x", "type": "extrude", "sketch": "chybi", "distance": 5}, "neexistuje"),
        ({"id": "x", "type": "fillet", "edges": {"face": "top", "type": "circle"}, "radius": 1},
         "nenašel žádnou hranu"),
        ({"id": "x", "type": "fillet", "edges": {"strana": "top"}, "radius": 1},
         "Neznámý klíč"),
        ({"id": "x", "type": "chamfer", "edges": "all"}, "Chybí povinná hodnota „distance“"),
        ({"id": "x", "type": "chamfer", "edges": "all", "distance": -1}, "větší než 0"),
        ({"id": "x", "type": "chamfer", "edges": "all", "distance": "zz"}, "neznámý parametr"),
        ({"id": "x", "type": "sketch", "plane": "nahore", "elements": []}, "Neznámá rovina"),
    ],
)
def test_feature_errors_have_czech_messages(feature, message):
    result = rebuild(make_doc(box_features() + [feature]))
    assert result.first_error is not None
    assert result.first_error.id == "x"
    assert message in result.first_error.message


def test_cut_that_misses_the_part_is_reported():
    doc = make_doc(box_features(20, 20, 10) + [
        {"id": "h", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 5}]},
        {"id": "c", "type": "extrude", "sketch": "h", "operation": "cut", "distance": 5,
         "direction": "normal"},
    ])
    result = rebuild(doc)
    assert "neodebral žádný materiál" in result.first_error.message


def test_second_new_body_is_rejected():
    doc = make_doc(box_features() + [
        {"id": "e2", "type": "extrude", "sketch": "s", "distance": 5, "operation": "new"},
    ])
    assert "díl už existuje" in rebuild(doc).first_error.message


def test_sketch_on_face_without_part():
    doc = make_doc([
        {"id": "s", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 5}]},
    ])
    assert "nejdřív vytvoř těleso" in rebuild(doc).first_error.message


def test_bad_parameter_is_document_error():
    with pytest.raises(DocumentError, match="Parametr „a“"):
        rebuild(make_doc(box_features("a"), parameters={"a": "b * 2"}))
