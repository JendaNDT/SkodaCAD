"""Zátěžové vstupy P8.1 mají skutečnou analyticky kontrolovanou geometrii."""

import locale
import math
import subprocess
import sys
from pathlib import Path

import pytest

from benchmark_p8 import history_data, make_assembly, make_constraints
from skodacad import Document, rebuild
from skodacad.assembly_session import AssemblySession


def test_history_has_two_distinct_real_blind_cuts_and_correct_volume():
    document = Document.from_dict(history_data(2))
    before = document.to_dict()
    result = rebuild(document)
    assert result.ok and len(result.statuses) == 6 and result.part.is_valid
    assert result.part.volume == pytest.approx(16*20*10 - 6*math.pi)
    circles = {tuple(round(x, 6) for x in edge.arc_center) for edge in result.part.edges()
               if edge.geom_type.name == "CIRCLE"}
    assert circles == {(-2., 0., 10.), (2., 0., 10.), (-2., 0., 7.), (2., 0., 7.)}
    assert document.to_dict() == before


def test_instance_reference_has_correct_copies_and_live_placement_expression(tmp_path):
    path = make_assembly(tmp_path, 3)
    source = (tmp_path / "box.json").read_bytes()
    session = AssemblySession()
    session.open(path)
    result = session.result
    assert result.complete and len(result.instances) == 3
    assert result.volume_mm3 == pytest.approx(3000)
    assert [i.part.bounding_box().center().X for i in result.instances] == pytest.approx(
        [0, 20, 40])
    preview = session.preview_parameters({"pitch": 21})
    assert [i.part.bounding_box().center().X for i in preview.result.instances] == pytest.approx(
        [0, 21, 42])
    assert session.result is result and not session.can_undo
    assert (tmp_path / "box.json").read_bytes() == source


@pytest.fixture(params=[None, "C"])
def text_locale(request):
    """Český recept musí fungovat i s ASCII výchozím kódováním souborů."""
    original = locale.setlocale(locale.LC_CTYPE)
    try:
        if request.param is not None:
            locale.setlocale(locale.LC_CTYPE, request.param)
        yield
    finally:
        locale.setlocale(locale.LC_CTYPE, original)


def test_constraint_groups_keep_all_seven_constraints_and_independent_offsets(tmp_path,
                                                                            text_locale):
    path = make_constraints(tmp_path, 2)
    session = AssemblySession()
    session.open(path)
    result = session.result
    assert result.complete and len(result.instances) == 12 and len(result.constraints) == 14
    a = next(i.part for i in result.instances if i.ids == ("g0_vicko",))
    b = next(i.part for i in result.instances if i.ids == ("g1_vicko",))
    assert b.bounding_box().center().X - a.bounding_box().center().X == pytest.approx(150)
    preview = session.preview_parameters({"mezera": 12.5})
    lifted = [i.part.bounding_box().max.Z for i in preview.result.instances
              if i.ids in (("g0_vicko",), ("g1_vicko",))]
    assert lifted == pytest.approx([a.bounding_box().max.Z+12.5, b.bounding_box().max.Z+12.5])
    assert preview.result.complete and session.result is result


def test_measurement_cli_refuses_to_overwrite_existing_evidence(tmp_path):
    report = tmp_path / "baseline.json"
    report.write_text("Původní evidence", encoding="utf-8")
    script = Path(__file__).with_name("benchmark_p8.py")
    done = subprocess.run([sys.executable, str(script), "--output", str(report),
                           "--cases", "startup"], capture_output=True, timeout=15)
    assert done.returncode == 2 and report.read_text(encoding="utf-8") == "Původní evidence"
    assert not report.with_suffix("").exists()
