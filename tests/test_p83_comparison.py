"""Odmítnutí neplatných důkazů zrychlení, na skutečných uložených bězích."""
import json
from pathlib import Path

import pytest

from compare_p83 import compare

BASELINES = Path(__file__).resolve().parents[1] / "docs/baselines"


@pytest.fixture
def reports():
    return [json.loads((BASELINES / f"p8-3-macos-arm64-{phase}.json").read_text(
        encoding="utf-8")) for phase in ("before", "after")]


def test_comparison_accepts_equal_geometry_and_bounded_source_change(reports):
    result = compare(*reports)
    assert result["status"] == "ok"
    assert result["metrics"]["open-build-tree-render"]["after_over_before"] > 0


@pytest.mark.parametrize("corruption", [
    "input", "status", "source", "accounting", "calls", "geometry"])
def test_comparison_rejects_invalid_speed_evidence(reports, corruption):
    after = reports[1]
    result = after["results"][1]
    metric = result["metrics"][0]
    if corruption == "input":
        result["input_sha256"]["assembly.json"] = "jiný vstup"
    elif corruption == "status":
        result["exit"] = 1
    elif corruption == "source":
        after["hashes"]["tests/profile_p8.py"] = "jiný měřič"
    elif corruption == "accounting":
        metric["traces"][0]["spans"]["operation_other"]["self_s"] += .1
    elif corruption == "calls":
        metric["traces"][0]["spans"]["source_read"]["calls"] -= 1
    else:
        metric["correctness"]["volume_mm3"] += 1
    with pytest.raises(ValueError):
        compare(*reports)
