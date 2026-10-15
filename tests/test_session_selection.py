"""Prvky z výběru ve 3D přes ModelSession: kliknutá hrana/plocha → zaoblení, skica …"""

import math

import pytest
from build123d import Vector

from conftest import edge_at, face_at
from skodacad import DocumentError
from skodacad.session import ModelSession

BOX = 40 * 30 * 10  # výchozí nový díl: obdélník 40 × 30 vysunutý o 10 (z = 0 … 10)


@pytest.fixture
def session():
    s = ModelSession()
    s.new_document("Výběr")
    s.add_feature("sketch")
    s.add_feature("extrude")
    assert s.properties.volume_mm3 == pytest.approx(BOX)
    return s


def part(session):
    return session.result.part


def click_edges(session, *points):
    return [edge_at(part(session), *p).wrapped for p in points]


def click_face(session, *point):
    return [face_at(part(session), *point).wrapped]


def corner_loss(radius, length):
    """Objem, který zaoblení ostré pravoúhlé hrany ubere."""
    return (radius ** 2 - math.pi * radius ** 2 / 4) * length


def test_fillet_from_clicked_edge(session):
    new_id = session.add_from_selection("fillet", click_edges(session, (20, -15, 5)))
    feature = session.feature(new_id)
    assert feature["edges"] == {"between": ["front", "right"]}
    assert session.properties.volume_mm3 == pytest.approx(BOX - corner_loss(2, 10))
    assert not part(session).is_inside(Vector(19.8, -14.8, 5))
    session.undo()
    assert session.properties.volume_mm3 == pytest.approx(BOX)


def test_chamfer_of_all_clicked_top_edges(session):
    top_edges = click_edges(session, (0, -15, 10), (0, 15, 10), (-20, 0, 10), (20, 0, 10))
    new_id = session.add_from_selection("chamfer", top_edges)
    assert session.feature(new_id)["edges"] == {"face": "top"}
    d = 1  # výchozí sražení: hranoly podél hran, v rozích se překrývají (d³/3)
    assert session.properties.volume_mm3 == pytest.approx(BOX - d ** 2 * (40 + 30) + 4 * d ** 3 / 3)


def test_sketch_on_clicked_face_then_hole(session):
    new_id = session.add_from_selection("sketch", click_face(session, 5, 5, 10),
                                        point=(5, 5, 10))
    sketch = session.feature(new_id)
    assert sketch["plane"] == "top" and "offset" not in sketch
    assert sketch["elements"][0]["center"] == [5, 5]
    extrude_id = session.add_feature("extrude", after_id=new_id)
    extrude = session.feature(extrude_id)
    extrude.update(operation="cut", distance=4)
    session.update_feature(extrude_id, extrude)
    assert session.properties.volume_mm3 == pytest.approx(BOX - math.pi * 5 ** 2 * 4)
    assert not part(session).is_inside(Vector(5, 5, 8))


def test_shell_open_at_clicked_face(session):
    new_id = session.add_from_selection("shell", click_face(session, 0, 0, 10))
    assert session.feature(new_id)["open_faces"] == ["top"]
    assert session.properties.volume_mm3 == pytest.approx(BOX - 36 * 26 * 8)


def test_add_clicked_edge_to_existing_fillet(session):
    fillet = session.add_from_selection("fillet", click_edges(session, (20, -15, 5)))
    # Zadní levá svislá hrana a horní přední hrana (zaoblení ji už zkrátilo).
    session.apply_selection(fillet, click_edges(session, (-20, 15, 5)))
    edges = session.feature(fillet)["edges"]
    assert edges == [{"between": ["front", "right"]}, {"between": ["back", "left"]}]
    assert session.properties.volume_mm3 == pytest.approx(BOX - 2 * corner_loss(2, 10))
    session.apply_selection(fillet, click_edges(session, (0, -15, 10)))
    assert len(session.feature(fillet)["edges"]) == 3
    assert session.result.ok
    # Nahradit: jen nově vybraná hrana (spodní zadní), původní zaoblení zmizí.
    session.apply_selection(fillet, click_edges(session, (0, 15, 0)), replace=True)
    assert session.feature(fillet)["edges"] == {"between": ["bottom", "back"]}
    assert session.properties.volume_mm3 == pytest.approx(BOX - corner_loss(2, 40))


def test_edge_already_in_feature_is_reported(session):
    # Zaoblení s příliš velkým poloměrem selže → díl zůstane, jeho hrany jdou kliknout.
    fillet = session.add_feature("fillet")
    feature = session.feature(fillet)
    feature.update(edges={"face": "top"}, radius=50)
    session.update_feature(fillet, feature)
    assert session.result.first_error.id == fillet
    with pytest.raises(DocumentError, match="už prvek obsahuje"):
        session.apply_selection(fillet, click_edges(session, (0, -15, 10)))
    session.apply_selection(fillet, click_edges(session, (20, -15, 5)))
    assert session.feature(fillet)["edges"] == [{"face": "top"}, {"between": ["front", "right"]}]


def test_edge_removed_by_feature_cannot_be_added(session):
    fillet = session.add_from_selection("fillet", click_edges(session, (20, -15, 5)))
    # Bod u bývalého rohu teď leží na hraně zaoblení, která dřív neexistovala.
    with pytest.raises(DocumentError, match="neexistuje"):
        session.apply_selection(fillet, click_edges(session, (20, -14, 5)))


def test_move_existing_sketch_to_clicked_face(session):
    sketch = session.add_feature("sketch")  # na horní ploše
    session.apply_selection(sketch, click_face(session, 0, -15, 5))
    assert session.feature(sketch)["plane"] == "front"
    with pytest.raises(DocumentError, match="nepočítá"):
        session.apply_selection("sketch1", click_face(session, 0, -15, 5))  # první skica


@pytest.mark.parametrize(("kind", "pick", "message"), [
    ("fillet", "face", "aspoň jednu hranu"),
    ("sketch", "edge", "právě jednu rovinnou plochu"),
    ("shell", "edge", "plochy, které má skořepina otevřít"),
])
def test_wrong_selection_explains_what_to_pick(session, kind, pick, message):
    shapes = (click_face(session, 0, 0, 10) if pick == "face"
              else click_edges(session, (20, -15, 5)))
    with pytest.raises(DocumentError, match=message):
        session.add_from_selection(kind, shapes)
    assert len(session.document.features) == 2  # model beze změny


def test_no_selection_features_on_broken_or_empty_model(session):
    shapes = click_edges(session, (20, -15, 5))
    fillet = session.add_feature("fillet")
    feature = session.feature(fillet)
    feature["radius"] = 50  # nejde → chyba v modelu
    session.update_feature(fillet, feature)
    with pytest.raises(DocumentError, match="nejdřív ji oprav"):
        session.add_from_selection("chamfer", shapes)
    session.new_document()
    with pytest.raises(DocumentError, match="nemá těleso"):
        session.add_from_selection("chamfer", shapes)


def test_selection_info_text(session):
    assert session.selection_info([]).text == ""
    single = session.selection_info(click_face(session, 0, 0, 10))
    assert (single.faces, single.edges) == (1, 0) and "rovinná" in single.text
    several = session.selection_info(
        click_face(session, 0, 0, 10) + click_face(session, 0, 0, 0)
        + click_edges(session, (20, -15, 5), (-20, 15, 5), (0, 15, 0)))
    assert several.text == "Vybráno: 2 plochy, 3 hrany"
    assert several.flat_faces == 2


def test_feature_highlight_shows_what_feature_uses(session):
    assert len(session.feature_highlight("sketch1")) == 1  # plocha obdélníku
    assert len(session.feature_highlight("extrude1")) == 1  # jeho skica
    fillet = session.add_from_selection("fillet", click_edges(session, (20, -15, 5)))
    assert len(session.feature_highlight(fillet)) == 1
    shell = session.add_from_selection("shell", click_face(session, 0, 0, 10))
    assert len(session.feature_highlight(shell)) == 1
    assert session.feature_highlight("neni") == []


def test_hole_at_clicked_point_and_another_one(session):
    hole = session.add_from_selection("hole", click_face(session, 5, 5, 10), point=(5, 5, 10))
    feature = session.feature(hole)
    assert (feature["plane"], feature["positions"], feature["size"]) == ("top", [[5, 5]], "M6")
    one = math.pi * 2.5 ** 2 * 10  # výchozí hloubka 12 > tloušťka 10 → díra vyjde ven
    assert session.properties.volume_mm3 == pytest.approx(BOX - one)
    assert not part(session).is_inside(Vector(5, 5, 8))
    # Další díra na stejné ploše kliknutím; na jiné ploše to vysvětlí.
    session.apply_selection(hole, click_face(session, -12, 0, 10), point=(-12, 0, 10))
    assert session.feature(hole)["positions"] == [[5, 5], [-12, 0]]
    assert session.properties.volume_mm3 == pytest.approx(BOX - 2 * one)
    with pytest.raises(DocumentError, match="jiné ploše"):
        session.apply_selection(hole, click_face(session, 0, -15, 5), point=(0, -15, 5))
