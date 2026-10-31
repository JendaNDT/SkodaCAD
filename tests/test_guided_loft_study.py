"""Nezávislé fyzikální reference pro průzkum vodítek; aplikaci zatím nerozšiřuje."""

import runpy
from fractions import Fraction
from pathlib import Path

import pytest

STUDY = runpy.run_path(str(Path(__file__).resolve().parents[1] / "docs/p6-6-pruzkum-voditek.py"))


@pytest.mark.parametrize("case,expected", [
    ("rovny", 60 * (1200 + 432 + 720) / 3),
    # 4*H ∫(20+20t−28t²)(15+14t−20t²) dt, nezávislé racionální vyčíslení.
    ("vybouleny", 240 * sum(Fraction(c, i + 1)
                            for i, c in enumerate((300, 580, -540, -792, 560)))),
])
def test_guide_reference_volume_matches_independent_integral(case, expected):
    controls = STUDY["inputs"](case)["guides_cubic_poles_mm"]
    volume, minimum = STUDY["analytic"](controls)
    assert volume == pytest.approx(float(expected), abs=2e-6)
    assert minimum > 0


def test_convexity_checks_between_the_two_valid_end_profiles():
    controls = STUDY["inputs"]("krizeni")["guides_cubic_poles_mm"]
    for end in (0, -1):
        # Obě koncová čela zůstávají konvexní; kontrola jen čel závadu neodhalí.
        corners = [rail[end] for rail in controls]
        for i in range(4):
            a, b, c = (corners[(i + j) % 4] for j in range(3))
            assert (b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0]) > 0
    _, minimum = STUDY["analytic"](controls)
    assert minimum < -1000
