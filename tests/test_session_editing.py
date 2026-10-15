"""Úpravy modelu v ModelSession: nový díl, prvky, parametry, Zpět/Znovu."""

import math

import pytest

from skodacad import DocumentError
from skodacad.session import ModelSession


@pytest.fixture
def session():
    s = ModelSession()
    s.new_document("Zkušební díl")
    return s


def ids(session):
    return [f["id"] for f in session.document.features]


def test_new_document_is_empty(session):
    assert session.document.name == "Zkušební díl"
    assert session.document.features == []
    assert session.result.part is None
    assert not session.dirty
    assert not session.can_undo


def test_build_part_from_scratch(session):
    sketch = session.add_feature("sketch")
    extrude = session.add_feature("extrude")
    assert ids(session) == [sketch, extrude] == ["sketch1", "extrude1"]
    assert session.result.ok
    assert session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    assert session.dirty


def test_update_feature_rebuilds(session):
    session.add_feature("sketch")
    extrude = session.add_feature("extrude")
    feature = session.feature(extrude)
    feature["distance"] = "2 * 12.5"
    session.update_feature(extrude, feature)
    assert session.properties.size_mm[2] == pytest.approx(25)


def test_update_feature_cannot_change_id_or_type(session):
    sketch = session.add_feature("sketch")
    feature = session.feature(sketch)
    feature["type"] = "extrude"
    with pytest.raises(DocumentError, match="id ani typ"):
        session.update_feature(sketch, feature)


def test_failing_update_is_kept_and_reported(session):
    """Chybná hodnota prvku se uloží (jde opravit), strom ukáže chybu – stejně jako u CADu."""
    session.add_feature("sketch")
    extrude = session.add_feature("extrude")
    fillet = session.add_feature("fillet")
    feature = session.feature(fillet)
    feature["radius"] = 100
    result = session.update_feature(fillet, feature)
    assert result.first_error.id == fillet
    assert session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)  # díl před zaoblením
    assert extrude in ids(session)


def test_add_feature_after_selected(session):
    first = session.add_feature("sketch")
    session.add_feature("extrude")
    inserted = session.add_feature("sketch", after_id=first)
    assert ids(session) == ["sketch1", inserted, "extrude1"]


def test_delete_feature_refuses_used_sketch(session):
    sketch = session.add_feature("sketch")
    extrude = session.add_feature("extrude")
    with pytest.raises(DocumentError, match="používá Vysunutí"):
        session.delete_feature(sketch)
    session.delete_feature(extrude)
    session.delete_feature(sketch)
    assert ids(session) == []


def test_move_feature(session):
    session.add_feature("sketch")
    session.add_feature("extrude")
    session.add_feature("fillet")
    session.move_feature("fillet1", -1)
    assert ids(session) == ["sketch1", "fillet1", "extrude1"]
    assert session.result.first_error.id == "fillet1"  # zaoblení před tělesem nejde
    session.move_feature("fillet1", +1)
    session.move_feature("fillet1", +1)  # už je poslední – nic se nestane
    assert ids(session) == ["sketch1", "extrude1", "fillet1"]
    assert session.result.ok


def test_parameters_add_use_delete(session):
    session.add_parameter("sirka", "50")
    session.add_feature("sketch")
    sketch = session.feature("sketch1")
    sketch["elements"][0]["width"] = "sirka"
    session.update_feature("sketch1", sketch)
    session.add_feature("extrude")
    assert session.properties.size_mm[0] == pytest.approx(50)

    session.set_parameter("sirka", "60,5")
    assert session.properties.size_mm[0] == pytest.approx(60.5)

    with pytest.raises(DocumentError, match="se používá: Skica „Skica 1“"):
        session.delete_parameter("sirka")
    session.add_parameter("nepouzity", "1")
    session.delete_parameter("nepouzity")
    assert "nepouzity" not in session.document.parameters


@pytest.mark.parametrize(
    ("name", "message"),
    [("1abc", "nejde použít"), ("s mezerou", "nejde použít"), ("pi", "nelze použít")],
)
def test_invalid_parameter_names(session, name, message):
    with pytest.raises(DocumentError, match=message):
        session.add_parameter(name, "1")
    assert session.document.parameters == {}


def test_parameter_used_in_other_parameter_cannot_be_deleted(session):
    session.add_parameter("D", "100")
    session.add_parameter("k", "D - 20")
    with pytest.raises(DocumentError, match="parametr „k“"):
        session.delete_parameter("D")


def test_set_info(session):
    session.set_info(name="Držák", material="Hliník", description="pro 3D tisk")
    assert (session.document.name, session.document.material) == ("Držák", "Hliník")
    with pytest.raises(DocumentError, match="neznám"):
        session.set_info(material="dřevo")


def test_undo_redo(session):
    session.add_feature("sketch")
    session.add_feature("extrude")
    volume = session.properties.volume_mm3
    session.add_feature("shell")
    assert session.properties.volume_mm3 < volume

    session.undo()
    assert ids(session) == ["sketch1", "extrude1"]
    assert session.properties.volume_mm3 == pytest.approx(volume)
    assert session.can_redo

    session.redo()
    assert ids(session) == ["sketch1", "extrude1", "shell1"]

    for _ in range(3):
        session.undo()
    assert ids(session) == [] and not session.can_undo
    assert session.undo() is None  # víc už nejde

    session.add_feature("sketch")
    assert not session.can_redo  # nová úprava zahodí „Znovu“


def test_invalid_change_does_not_create_undo_step(session):
    session.add_parameter("a", "1")
    with pytest.raises(DocumentError):
        session.set_parameter("a", "neznamy + 1")
    session.undo()
    assert session.document.parameters == {}


def test_open_clears_history(session, examples_dir):
    session.add_feature("sketch")
    session.open_template(examples_dir / "priruba.json")
    assert not session.can_undo and not session.can_redo


def test_flange_from_scratch_matches_formula(session):
    """Celá příruba poskládaná jen přes ModelSession – stejně jako v okně."""
    session.add_parameter("D", "165")
    session.add_parameter("t", "18")
    session.add_feature("sketch")
    sketch = session.feature("sketch1")
    sketch["elements"] = [{"shape": "circle", "diameter": "D"},
                          {"shape": "circle", "diameter": 62, "mode": "subtract"}]
    session.update_feature("sketch1", sketch)
    session.add_feature("extrude")
    extrude = session.feature("extrude1")
    extrude["distance"] = "t"
    session.update_feature("extrude1", extrude)
    assert session.result.ok
    assert session.properties.volume_mm3 == pytest.approx(math.pi / 4 * (165**2 - 62**2) * 18)


def test_profile_point_names_are_not_parameters(session):
    from skodacad.schema import new_shape

    session.add_parameter("A", "5")  # stejné jméno jako bod obrysu
    session.add_parameter("vyska", "30")
    sketch = session.add_feature("sketch")
    feature = session.feature(sketch)
    profile = new_shape("profile")
    profile["constraints"][-1]["value"] = "vyska"
    feature["elements"] = [profile]
    session.update_feature(sketch, feature)
    with pytest.raises(DocumentError, match="používá"):
        session.delete_parameter("vyska")
    session.delete_parameter("A")
    assert "A" not in session.document.parameters


def test_delete_feature_refuses_feature_used_by_pattern(session):
    session.add_feature("sketch")
    session.add_feature("extrude")
    hole = session.add_feature("hole", values={"positions": [[-10, 0]]})
    pattern = session.add_feature("pattern")
    assert session.result.ok
    with pytest.raises(DocumentError, match="používá Pole"):
        session.delete_feature(hole)
    session.delete_feature(pattern)
    session.delete_feature(hole)
