"""MT v ModelSession, formát 20, pomocný proces a příkazová řádka (etapa 12, krok 12A.2)."""

import json
import shutil

import pytest

from conftest import EXAMPLES
from skodacad.cli import main
from skodacad.document import Document, DocumentError
from skodacad.ndt import MT_DISCLAIMER, MT_MAP
from skodacad.ndt.mt import MtSettings
from skodacad.session import ModelSession

NDT = EXAMPLES / "ndt"
QUICK = {"step_mm": 25, "center_step_mm": 50, "apply": False, "inspect": False}


def opened(name="deska"):
    session = ModelSession()
    session.open(NDT / f"{name}.json")
    return session


def quick(session, sid="s2"):
    assert session.set_ndt_mt_settings(sid, QUICK) is not None
    return session


def test_settings_are_one_undo_step_and_only_for_mt_studies():
    session = opened()
    assert session.ndt_mt_settings("s2") == MtSettings()
    quick(session)
    assert session.ndt_study("s2")["mt"]["center_step_mm"] == 50 and session.dirty
    assert session.set_ndt_mt_settings("s2", QUICK) is None  # beze změny
    session.undo()
    assert "mt" not in session.ndt_study("s2")
    with pytest.raises(DocumentError, match="jen MT"):
        session.set_ndt_mt_settings("s1", QUICK)
    with pytest.raises(DocumentError, match="Rozteč pólů"):
        session.set_ndt_mt_settings("s2", {"spacing_mm": 5})
    quick(session)
    session.set_ndt_method("s2", "UT")  # nastavení MT má jen MT studie
    assert "mt" not in session.ndt_study("s2")


def test_format_20_saves_mt_and_rejects_it_in_other_studies(tmp_path):
    session = quick(opened())
    path = session.save(tmp_path / "deska.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 22 and data["ndt"]["studies"][1]["mt"]["step_mm"] == 25
    data["ndt"]["studies"][0]["mt"] = {"spacing_mm": 100}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DocumentError, match="nastavení MT"):
        Document.load(path)
    data["ndt"]["studies"][0].pop("mt")
    data["ndt"]["studies"][1]["mt"] = {"roztec": 100}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DocumentError, match="nezná"):
        Document.load(path)


def test_map_and_yoke_are_views_invalidated_by_part_change(tmp_path):
    session = quick(opened())
    before = session.document.to_dict()
    placed = session.place_ndt_yoke("s2", (0, 0, 20), 0.0)
    assert placed.ok and placed.spacing == 100 and session.ndt_yoke is placed
    across = session.place_ndt_yoke("s2", (0, 0, 20), 90.0)
    assert across.ok and across.spacing == 75  # deska je široká jen 100 mm
    result = session.compute_ndt_mt("s2")
    assert session.ndt_mt_map is result and session.ndt_mt_study() == "s2"
    assert session.document.to_dict() == before
    assert result.percent("ok", "d0") > 0
    nodes, triangles, colors = session.ndt_mt_mesh("d0")
    assert len(nodes) == len(colors) == 3 * len(triangles)
    assert any("Pole" in line or "Pokryto" in line or "Jen část" in line
               for line in session.ndt_mt_describe((0, 0, 20)))
    csv = session.export_ndt_mt(tmp_path / "mt.csv")
    assert csv.read_text(encoding="utf-8-sig").startswith(MT_MAP)
    found = session.ndt_mt_yoke_at((0, 30, 20), "d0")  # jho, které místo pokryje polem 0°
    assert found is not None and found.ok and session.ndt_yoke is found
    assert session.document.to_dict() == before
    session.set_parameter("t", "30")
    assert session.ndt_mt_map is None and session.ndt_yoke is None  # jen pohled
    with pytest.raises(DocumentError, match="nejdřív ji potvrď"):
        session.compute_ndt_mt("s2")
    with pytest.raises(DocumentError, match="jen pro MT"):
        session.compute_ndt_mt("s1")


def test_material_must_be_ferromagnetic_or_confirmed():
    session = quick(opened())
    session.set_info(material="hliník")
    session.confirm_ndt_study("s2")  # materiál patří do receptu – studie byla zastaralá
    with pytest.raises(DocumentError, match="hliník není feromagnetický"):
        session.ndt_mt_estimate("s2")
    session.set_info(material="nerez")
    session.confirm_ndt_study("s2")
    with pytest.raises(DocumentError, match="austenitická"):
        session.compute_ndt_mt("s2")
    session.set_ndt_mt_settings("s2", {**QUICK, "ferromagnetic": True})
    samples, step, centers, center_step, seconds = session.ndt_mt_estimate("s2")
    assert samples > 0 and step == 25 and centers > 0 and center_step == 50 and seconds > 0


def test_background_runner_computes_map_with_progress():
    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(NDT / "deska.json")
        assert session.wait(60)
        quick(session)
        assert session.wait(60)
        assert session.start_ndt_mt("s2") is None and session.mt_pending
        assert session.wait(300)
        assert not session.mt_pending and session.ndt_mt_map is not None
        assert session.ndt_mt_study() == "s2"
    finally:
        runner.close()


def test_cli_prints_summary_with_disclaimer_and_writes_csv(tmp_path, capsys):
    model = tmp_path / "deska.json"
    shutil.copy(NDT / "deska.json", model)
    code = main(["magneticka", str(model), "--studie", "s2", "--krok", "25",
                 "--krok-stredu", "50", "--bez-naneseni", "--bez-prohlidky",
                 "--csv", str(tmp_path / "mt.csv"), "--ulozit"])
    out = capsys.readouterr().out
    assert code == 0 and MT_MAP in out and MT_DISCLAIMER in out
    assert (tmp_path / "mt.csv").exists()
    assert json.loads(model.read_text(encoding="utf-8"))["ndt"]["studies"][1]["mt"][
        "center_step_mm"] == 50
    assert main(["magneticka", str(model), "--studie", "s1"]) == 2  # UT studie
    assert main(["build", str(NDT / "deska.json"), "-o", str(tmp_path),
                 "--format", "step"]) == 0
    assert f"({MT_DISCLAIMER})" in capsys.readouterr().out
