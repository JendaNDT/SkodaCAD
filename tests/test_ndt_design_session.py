"""NDT etapa 15A.2: uložení zadání, session, CLI a výpočet ve vedlejším procesu."""

import copy
import json

import pytest

from conftest import EXAMPLES
from skodacad.cli import main
from skodacad.document import VERSION, Document, DocumentError
from skodacad.ndt.design import Design
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

EXAMPLE = EXAMPLES / "ndt" / "navrh_kapsa.json"


def test_format_22_and_backwards_compatibility(tmp_path):
    assert VERSION == 27
    document = Document.load(EXAMPLE)
    design = Design.from_dict(document.ndt["design"])
    assert design.study == "s3"
    assert [p.name for p in design.parameters] == ["a"]
    output = tmp_path / "kopie.json"
    document.save(output)
    assert Document.load(output) == document
    assert json.loads(output.read_text(encoding="utf-8"))["version"] == 24

    old = document.to_dict()
    old["version"] = 21
    del old["ndt"]["design"]
    assert Document.from_dict(old).ndt.get("design") is None

    bad = copy.deepcopy(document.to_dict())
    bad["ndt"]["design"]["study"] = "neexistuje"
    with pytest.raises(DocumentError, match="neexistuje"):
        Document.from_dict(bad)
    bad = copy.deepcopy(document.to_dict())
    bad["ndt"]["design"]["parameters"] = [{"name": "nic", "values": [10]}]
    with pytest.raises(DocumentError, match="nic"):
        Document.from_dict(bad)


def test_session_settings_undo_and_separate_variant(tmp_path):
    session = ModelSession()
    session.open(EXAMPLE)
    settings = session.ndt_design_settings()
    assert settings is not None
    assert session.ndt_design is None

    original = EXAMPLE.read_bytes()
    updated = settings.to_dict()
    updated["parameters"] = [{"name": "a", "values": [40, 90]}]
    session.set_ndt_design(updated)
    assert session.dirty
    assert session.ndt_design_settings().parameters[0].values == (40.0, 90.0)
    session.undo()
    assert session.ndt_design_settings().parameters[0].values == (40.0, 60.0, 80.0,
                                                                  90.0, 100.0)
    assert EXAMPLE.read_bytes() == original

    options = {"study": "s3", "parameters": [{"name": "a", "values": [90, 100]}],
               "conditions": [{"measurement": "m1", "min": 15, "reason": "stěna"}],
               "options": {"verify": False, "rejected": False}}
    count, seconds = session.ndt_design_estimate(options)
    assert count == 2 and seconds > 0
    before = copy.deepcopy(session.document.to_dict())
    result = session.compute_ndt_design(options)
    assert result.complete and len(result.variants) == 3
    assert session.document.to_dict() == before
    assert session.dirty  # Zpět ponechává dokument označený jako upravený
    passed = next(v for v in result.variants if v.values.get("a") == 90)
    rejected = next(v for v in result.variants if v.values.get("a") == 100)
    assert passed.status == "passed"
    assert rejected.status == "rejected"
    with pytest.raises(DocumentError, match="jen variantu"):
        session.apply_ndt_design_variant(rejected.index)

    folder = tmp_path / "zprava"
    names = sorted(p.name for p in session.export_ndt_design(folder))
    assert names == ["navrh.html", "varianty.csv"]
    target = tmp_path / "vetsi-kapsa.json"
    session.save_ndt_design_variant(passed.index, target)
    assert Document.load(target).parameters["a"] == 90
    assert session.document.to_dict() == before
    assert EXAMPLE.read_bytes() == original
    with pytest.raises(DocumentError, match="existuje"):
        session.save_ndt_design_variant(passed.index, target)

    session.apply_ndt_design_variant(passed.index)
    assert session.document.parameters["a"] == 90
    assert session.ndt_design is None
    session.undo()
    assert session.document.parameters["a"] == 40


def test_cli_design_keeps_source_untouched(tmp_path, capsys):
    original = EXAMPLE.read_bytes()
    folder = tmp_path / "export"
    code = main(["navrh", str(EXAMPLE), "--parametr", "a=90",
                 "--slozka", str(folder), "--bez-overeni", "--bez-neproslych"])
    out = capsys.readouterr()
    assert code == 0
    assert "Konstrukční" in out.out or "konstrukční" in out.out
    assert (folder / "navrh.html").is_file()
    assert (folder / "varianty.csv").is_file()
    assert EXAMPLE.read_bytes() == original
    assert main(["navrh", str(EXAMPLE), "--parametr", "neplatne"]) == 2


def test_background_returns_variants_and_does_not_change_document():
    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(EXAMPLE)
        assert session.wait(150)
        before = copy.deepcopy(session.document.to_dict())
        settings = {"study": "s3", "parameters": [{"name": "a", "values": [90]}],
                    "conditions": [{"measurement": "m1", "min": 15}],
                    "options": {"verify": False, "rejected": False}}
        assert session.start_ndt_design(settings) is None
        assert session.design_pending and session.computing
        assert session.wait(240), session.failure
        result = session.ndt_design
        assert result is not None and result.complete
        assert len(result.variants) == 2
        assert session.document.to_dict() == before
        assert session.ndt_design_progress == ""

        session.start_ndt_design(settings)
        assert session.cancel()
        assert session.document.to_dict() == before
        assert not session.design_pending
    finally:
        runner.close()
