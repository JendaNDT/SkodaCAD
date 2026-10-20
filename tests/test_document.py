import json

import pytest

from skodacad import Document, DocumentError
from skodacad.materials import density_g_cm3


def test_json_round_trip_keeps_everything(tmp_path, examples_dir):
    original = Document.load(examples_dir / "priruba.json")
    path = tmp_path / "kopie.json"
    original.save(path)
    assert Document.load(path) == original
    assert "Plochá příruba" in path.read_text(encoding="utf-8")  # čeština bez \u escapů


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "JSON objekt"),
        ({"format": "jiny", "version": 1}, "není model ŠkodaCAD"),
        ({"format": "skodacad", "version": 99}, "Nepodporovaná verze"),
        ({"format": "skodacad", "version": 1, "units": "inch"}, "Jednotky"),
        (
            {"format": "skodacad", "version": 1, "features": [{"type": "sketch"}]},
            "nemá textové „id“",
        ),
        (
            {"format": "skodacad", "version": 1,
             "features": [{"id": "a", "type": "sketch"}, {"id": "a", "type": "extrude"}]},
            "dvakrát",
        ),
    ],
)
def test_invalid_documents_are_rejected(data, message):
    with pytest.raises(DocumentError, match=message):
        Document.from_dict(data)


def test_broken_json_reports_line(tmp_path):
    path = tmp_path / "rozbity.json"
    path.write_text('{"format": "skodacad",\n "version": 1,,}', encoding="utf-8")
    with pytest.raises(DocumentError, match="řádek 2"):
        Document.load(path)


def test_with_parameters_does_not_change_original(examples_dir):
    original = Document.load(examples_dir / "priruba.json")
    changed = original.with_parameters({"D": 200})
    assert changed.parameters["D"] == 200
    assert original.parameters["D"] == 165
    with pytest.raises(DocumentError, match="nemá parametr"):
        original.with_parameters({"neexistuje": 1})


def test_material_lookup_ignores_accents_and_case():
    assert density_g_cm3("Hliník") == density_g_cm3("hlinik") == 2.70
    assert density_g_cm3("PETG") == 1.27
    assert density_g_cm3("neznámý") is None


def test_version_1_files_still_load_and_save_as_current(tmp_path):
    from skodacad.document import VERSION

    document = Document.from_dict({"format": "skodacad", "version": 1, "features": []})
    path = tmp_path / "stary.json"
    document.save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == VERSION == 22
