"""RT v ModelSession, formát 21, pomocný proces a příkazová řádka (etapa 13, krok 13A.2)."""

import dataclasses
import json
import math
import shutil
import struct

import pytest

from conftest import EXAMPLES
from skodacad.cli import main
from skodacad.document import Document, DocumentError
from skodacad.ndt import RT_DISCLAIMER, RT_MAP
from skodacad.ndt.rt import COLORS, RtSettings
from skodacad.session import ModelSession

NDT = EXAMPLES / "ndt"
WELD = NDT / "cilove_objemy" / "tupy_svar_objem.json"
NOMINAL_30 = 20 / math.cos(math.radians(30))
QUICK = {"step_mm": 10, "image_step_mm": 20}  # testy nečekají na 6 000 paprsků náhledu


def opened(path=NDT / "otvor.json"):
    session = ModelSession()
    session.open(path)
    return session


def quick(session, sid="s2"):
    settings = dataclasses.replace(session.ndt_rt_settings(sid), **QUICK)
    assert session.set_ndt_rt_settings(sid, settings) is not None
    return session


def names(session, sid="s2"):
    return [p.name for p in session.ndt_rt_settings(sid).projections]


def test_settings_are_one_undo_step_and_only_for_rt_studies():
    session = opened()
    settings = session.ndt_rt_settings("s2")
    assert names(session) == ["P1", "P2"] and settings.test_class == "B"
    assert session.set_ndt_rt_settings("s2", settings) is None  # beze změny
    session.set_ndt_rt_settings("s2", dataclasses.replace(settings, test_class="A"))
    assert session.ndt_study("s2")["rt"]["class"] == "A" and session.dirty
    session.undo()
    assert session.ndt_study("s2")["rt"]["class"] == "B"
    with pytest.raises(DocumentError, match="jen RT"):
        session.set_ndt_rt_settings("s1", {})
    with pytest.raises(DocumentError, match="Třída zkoušky"):
        session.set_ndt_rt_settings("s2", {"class": "C"})
    session.set_ndt_method("s2", "UT")  # nastavení RT má jen RT studie
    assert "rt" not in session.ndt_study("s2")


def test_projections_add_copy_edit_remove_each_one_undo_step():
    session = opened()
    new = session.ndt_rt_projection_at("s2", (60, 5, 20))  # zdroj nad bodem horní plochy
    assert new.name == "P3" and new.aim == (60, 5, 20) and new.direction == (0, 0, 1)
    assert new.distance_mm == 500 and new.detector == "contact" and new.detector_angle_deg == 0
    assert names(session) == ["P1", "P2"]  # zatím neuložená
    session.add_ndt_rt_projection("s2", new)
    session.copy_ndt_rt_projection("s2", "P3", (0, 30, 0))
    copied = session.ndt_rt_settings("s2").projection("P4")
    assert copied.aim == (60, 35, 20) and copied.direction == new.direction
    session.set_ndt_rt_projection("s2", "P4", dataclasses.replace(copied, name="P9",
                                                                  distance_mm=700))
    assert names(session) == ["P1", "P2", "P3", "P9"]
    assert session.set_ndt_rt_projection("s2", "P9", session.ndt_rt_settings("s2").projection(
        "P9")) is None  # beze změny
    session.remove_ndt_rt_projection("s2", "P1")
    assert names(session) == ["P2", "P3", "P9"]
    with pytest.raises(DocumentError, match="dvakrát"):
        session.set_ndt_rt_projection("s2", "P9", dataclasses.replace(copied, name="P2"))
    with pytest.raises(DocumentError, match="ve studii není"):
        session.remove_ndt_rt_projection("s2", "P7")
    with pytest.raises(DocumentError, match="stejném místě"):
        session.copy_ndt_rt_projection("s2", "P2", (0, 0, 0))
    for expected in (["P1", "P2", "P3", "P9"], ["P1", "P2", "P3", "P4"], ["P1", "P2", "P3"],
                     ["P1", "P2"]):
        session.undo()
        assert names(session) == expected


def test_projection_over_weld_turns_the_film_along_the_weld():
    session = opened(WELD)
    new = session.ndt_rt_projection_at("s2", (0, 10, 14))  # temeno převýšení
    assert new.aim == pytest.approx((0, 10, 14)) and new.direction == pytest.approx((0, 0, 1))
    assert new.detector_angle_deg == pytest.approx(90)  # delší strana podél osy svaru (Y)
    assert new.name == "P2"
    cells, step, projections, seconds = session.ndt_rt_estimate("s2")  # bez pomalého ořezu
    assert (cells, step, projections) == (8 * 6 * 40, 2.5, 1)  # 20 × 15 × 100 mm po 2,5 mm
    assert 15 < seconds < 40


def test_format_21_saves_rt_and_rejects_it_in_other_studies(tmp_path):
    session = quick(opened())
    path = session.save(tmp_path / "otvor.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 23 and data["ndt"]["studies"][1]["rt"]["step_mm"] == 10
    assert "rt" not in data["ndt"]["studies"][0]
    assert Document.load(path).to_dict() == data  # načtení a uložení beze změny
    data["ndt"]["studies"][0]["rt"] = {"class": "B"}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DocumentError, match="nastavení RT"):
        Document.load(path)
    data["ndt"]["studies"][0].pop("rt")
    data["ndt"]["studies"][1]["rt"]["trida"] = "A"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DocumentError, match="nezná"):
        Document.load(path)


def test_map_is_a_view_invalidated_by_part_change(tmp_path):
    session = quick(opened())
    before = session.document.to_dict()
    samples, step, projections, seconds = session.ndt_rt_estimate("s2")
    assert samples > 100 and step == 10 and projections == 2 and seconds > 0
    result = session.compute_ndt_rt("s2")
    assert session.ndt_rt_map is result and session.ndt_rt_study() == "s2"
    assert session.document.to_dict() == before
    p1, p2 = result.projections
    assert (p1.f, p1.b) == pytest.approx((500, 20))
    assert (p2.f, p2.b) == pytest.approx((500, NOMINAL_30), abs=0.01)
    assert result.percent("ok") > 80
    nodes, triangles, colors = session.ndt_rt_mesh("p1")
    assert len(nodes) == len(colors) == 3 * len(triangles) > 0
    lines = session.ndt_rt_describe((60, 0, 20))
    assert lines[0].startswith("Promítne se") and any(line.startswith("P2:") for line in lines)
    image = session.ndt_rt_image("P1")
    assert image is not None and image.max_mm == pytest.approx(20 / math.cos(math.atan(
        math.hypot(50, 120) / 520)), abs=0.5)  # roh filmu 10 × 24 cm
    assert session.ndt_rt_image("P7") is None
    csv = session.export_ndt_rt(tmp_path / "rt.csv")
    assert csv.read_text(encoding="utf-8-sig").startswith(RT_MAP)
    only = session.compute_ndt_rt("s2", projections=["P2"])
    assert [p.setup.name for p in only.projections] == ["P2"]
    session.set_parameter("t", "30")
    assert session.ndt_rt_map is None  # jen pohled
    with pytest.raises(DocumentError, match="nejdřív ji potvrď"):
        session.compute_ndt_rt("s2")
    with pytest.raises(DocumentError, match="jen pro RT"):
        session.compute_ndt_rt("s1")


def test_drawing_preview_png_and_collision_are_views():
    session = quick(opened())
    drawing = session.ndt_rt_drawing("s2", "P2")
    _body, state, source, aim, text, rays = drawing
    assert state == "ok" and source == pytest.approx((250, 0, 453.0127), abs=1e-4)
    assert aim == (0, 0, 20) and text == "P2: f 500 mm" and len(rays) == 8
    assert session.ndt_rt_drawing("s2", "P2") is drawing  # pamatuje se
    assert session.ndt_rt_drawing("s1", "P1") is None  # UT studie
    p2 = session.ndt_rt_settings("s2").projection("P2")
    normal, tilt, turn, label = session.ndt_rt_angles(p2.aim, p2.direction)
    assert label == "osa +Z" and (tilt, turn) == pytest.approx((30, 0))  # bod uprostřed otvoru
    assert session.ndt_rt_angles((60, 0, 20), (0, 0, 1))[3] == "kolmice k ploše"
    before = session.document.to_dict()
    session.compute_ndt_rt("s2")
    width, height, data = session.ndt_rt_preview("P1", 2)
    assert (width, height, len(data)) == (24, 10, 3 * 24 * 10)  # 240 × 100 mm po 20 mm, 2 body
    assert data[:3] == bytes((255, 255, 255))  # roh filmu mimo desku: bez materiálu
    assert session.document.to_dict() == before  # kresba ani náhled model nemění
    p1 = session.ndt_rt_settings("s2").projection("P1")
    session.add_ndt_rt_projection("s2", dataclasses.replace(p1, name="P5",
                                                            detector_distance_mm=510))
    _body, state, _source, _aim, text, rays = session.ndt_rt_drawing("s2", "P5")
    assert state == "collision" and text.endswith("detektor naráží do dílu")
    assert len(rays) == 8  # deska, která naráží (z = 10 v desce), se nakreslí červeně
    assert "naráží do dílu" in session.ndt_rt_setup_text("s2", "P5")


def test_png_export_and_weld_volume_mesh(tmp_path):
    session = quick(opened())
    session.compute_ndt_rt("s2")
    path = session.export_ndt_rt_png("P1", tmp_path / "p1.png")
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (960, 400)  # 12 × 5 buněk po 80 bodech
    with pytest.raises(DocumentError, match="Náhled projekce není"):
        session.export_ndt_rt_png("P7", tmp_path / "p7.png")
    weld = opened(WELD)
    weld.set_ndt_rt_settings("s2", dataclasses.replace(weld.ndt_rt_settings("s2"), step_mm=5,
                                                       image_step_mm=20))
    weld.compute_ndt_rt("s2")
    nodes, triangles, colors = weld.ndt_rt_mesh(None)  # povrch svaru obarvený podle buněk
    assert len(nodes) == len(colors) > 0 and set(colors) == {COLORS["ok"]}


def test_study_without_projection_explains_what_to_do():
    session = opened()
    session.set_ndt_rt_settings("s2", RtSettings())
    with pytest.raises(DocumentError, match="nemá projekci"):
        session.start_ndt_rt("s2")


def test_background_runner_computes_map_with_progress():
    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(NDT / "otvor.json")
        assert session.wait(60)
        quick(session)
        assert session.wait(60)
        assert session.start_ndt_rt("s2") is None and session.rt_pending
        assert session.wait(120)
        assert not session.rt_pending and session.ndt_rt_map is not None
        assert session.ndt_rt_study() == "s2" and len(session.ndt_rt_map.projections) == 2
    finally:
        runner.close()


def test_cli_prints_summary_with_disclaimer_and_saves_changes(tmp_path, capsys):
    model = tmp_path / "otvor.json"
    shutil.copy(NDT / "otvor.json", model)
    code = main(["radiografie", str(model), "--studie", "s2", "--krok", "10",
                 "--krok-nahledu", "20", "--trida", "A", "--projekce", "P1",
                 "--vzdalenost", "700", "--csv", str(tmp_path / "rt.csv"), "--ulozit"])
    out = capsys.readouterr().out
    assert code == 0 and RT_MAP in out and RT_DISCLAIMER in out
    assert "P1: " in out and "P2: " not in out
    assert (tmp_path / "rt.csv").exists()
    saved = json.loads(model.read_text(encoding="utf-8"))["ndt"]["studies"][1]["rt"]
    assert saved["class"] == "A" and saved["image_step_mm"] == 20
    p1, p2 = saved["projections"]
    assert p1["distance_mm"] == 700 and p1["detector_distance_mm"] == 720  # film zůstal
    assert p2["distance_mm"] == 500
    assert main(["radiografie", str(model), "--studie", "s1"]) == 2  # UT studie
    assert main(["radiografie", str(model), "--studie", "s2", "--projekce", "P7"]) == 2
    assert main(["build", str(NDT / "otvor.json"), "-o", str(tmp_path),
                 "--format", "step"]) == 0
    assert f"({RT_DISCLAIMER})" in capsys.readouterr().out
