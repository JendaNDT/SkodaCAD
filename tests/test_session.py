import json
import shutil

import pytest

from skodacad import DocumentError
from skodacad.session import ModelSession, format_parameter_value, parse_parameter_text


@pytest.fixture
def session(examples_dir, tmp_path):
    model = tmp_path / "priruba.json"
    shutil.copy(examples_dir / "priruba.json", model)
    s = ModelSession()
    s.open(model)
    return s


@pytest.mark.parametrize(
    ("text", "expected"),
    [("18", 18), ("12.5", 12.5), ("12,5", 12.5), (" -3 ", -3), ("2.0", 2.0),
     ("D - 40", "D - 40"), ("max(a, b)", "max(a, b)")],
)
def test_parse_parameter_text(text, expected):
    value = parse_parameter_text(text)
    assert value == expected
    assert type(value) is type(expected)


def test_parse_parameter_text_rejects_empty():
    with pytest.raises(DocumentError, match="prázdná"):
        parse_parameter_text("  ")


def test_format_parameter_value():
    assert format_parameter_value(8.0) == "8"
    assert format_parameter_value(12.5) == "12.5"
    assert format_parameter_value("D/2") == "D/2"


def test_open_builds_model(session):
    assert session.result.ok
    assert session.properties.volume_mm3 > 0
    assert not session.dirty
    assert session.title == "Plochá příruba (priruba.json) – ŠkodaCAD"


def test_set_parameter_rebuilds_and_marks_dirty(session):
    volume_before = session.properties.volume_mm3
    result = session.set_parameter("n", "8")
    assert result.ok
    assert session.document.parameters["n"] == 8
    assert session.properties.volume_mm3 < volume_before  # víc děr = méně materiálu
    assert session.dirty
    assert session.title.startswith("*")


def test_same_value_does_not_mark_dirty(session):
    session.set_parameter("n", "4")
    assert not session.dirty


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [("n", "neexistuje * 2", "neznámý parametr"),
     ("k", "k + 1", "v kruhu"),
     ("xyz", "1", "nemá parametr")],
)
def test_invalid_parameter_keeps_model_unchanged(session, name, text, message):
    before = dict(session.document.parameters)
    with pytest.raises(DocumentError, match=message):
        session.set_parameter(name, text)
    assert session.document.parameters == before
    assert not session.dirty


def test_failed_feature_is_reported_not_raised(session):
    result = session.set_parameter("s", "50")  # sražení větší než deska
    assert not result.ok
    assert result.first_error.id == "sraz_obvod"
    assert session.result.part is not None  # díl ve stavu před chybou


def test_save_writes_changed_parameter(session, tmp_path):
    session.set_parameter("D", "200")
    saved = session.save()
    assert not session.dirty
    assert json.loads(saved.read_text(encoding="utf-8"))["parameters"]["D"] == 200

    copy_path = session.save(tmp_path / "kopie.json")
    assert session.path == copy_path and copy_path.exists()


def test_export(session, tmp_path):
    path = session.export(tmp_path / "priruba.step")
    assert path.stat().st_size > 0


def test_empty_session_errors():
    s = ModelSession()
    assert s.title == "ŠkodaCAD"
    assert s.properties is None
    with pytest.raises(DocumentError):
        s.export("x.step")
    with pytest.raises(DocumentError):
        s.set_parameter("D", "1")
