"""Základní přísná diagnostika, nikoli přejímka importu."""
from pathlib import Path

import pytest

from skodacad.step_probe import MAX_STEP_BYTES, StepProbeError, probe_step

ROOT = Path(__file__).parent / "fixtures"
STEP = ROOT / "step"


@pytest.mark.parametrize(("name", "unit", "maximum", "volume"), [
    ("01-jedno-teleso.step", "millimetre", (40, 30, 20), 24000),
    ("04-palce.step", "inch", (50.8, 25.4, 12.7), 16387.064),
    ("07-metry.step", "metre", (10, 13, 17), 2210),
])
def test_single_solid(name, unit, maximum, volume):
    facts = probe_step((STEP / name).read_bytes())
    assert facts.unit == unit
    assert facts.solids == 1
    assert facts.bounds_mm == pytest.approx((0, 0, 0, *maximum), abs=1e-6)
    assert facts.volume_mm3 == pytest.approx(volume, abs=1e-5)


@pytest.mark.parametrize(("path", "reason"), [
    (STEP / "02-dve-telesa.step", "jeden"),
    (STEP / "03-sestava.step", "sestavu"),
    (STEP / "05-otevrena-plocha.step", "těleso"),
    (STEP / "06-poskozeny.step", "poškozený"),
    (ROOT / "step-p33" / "obracena-plocha.step", "oprava"),
])
def test_reject_invalid_or_unsupported(path, reason):
    with pytest.raises(StepProbeError, match=reason):
        probe_step(path.read_bytes())


def test_size_limit():
    with pytest.raises(StepProbeError, match="16 MiB"):
        probe_step(b"x" * (MAX_STEP_BYTES + 1))


def test_other_length_unit_remains_unsupported():
    raw = (STEP / "07-metry.step").read_bytes()
    metre = b"LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.)"
    centimetre = b"LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.CENTI.,.METRE.)"
    assert metre in raw
    with pytest.raises(StepProbeError, match="jednotky|Jednotky"):
        probe_step(raw.replace(metre, centimetre))


def test_global_shape_fix_setting_is_restored():
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    assert reader is not None
    before = Interface_Static.CVal_s("FromSTEP.exec.op")
    probe_step((STEP / "01-jedno-teleso.step").read_bytes())
    assert Interface_Static.CVal_s("FromSTEP.exec.op") == before
    with pytest.raises(StepProbeError):
        probe_step((STEP / "06-poskozeny.step").read_bytes())
    assert Interface_Static.CVal_s("FromSTEP.exec.op") == before
