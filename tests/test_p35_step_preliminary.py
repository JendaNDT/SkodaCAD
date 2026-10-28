"""Předběžná zkouška zdroje a převodu; nenahrazuje přejímku celé aplikace."""
import json
import time
from pathlib import Path

import pytest
from build123d import export_step

from skodacad.step_source import source_bytes, source_record
from skodacad.step_task import StepTask
from skodacad.worker import _shape_from

FIXTURES = Path(__file__).parent / "fixtures" / "step"


def check_in_child(raw):
    task = StepTask(raw)
    try:
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            result = task.poll()
            if result is not None:
                assert not result.error, result.error
                return result
            time.sleep(0.02)
        raise AssertionError("Kontrola STEP neodpověděla")
    finally:
        task.cancel()


@pytest.mark.parametrize("name", ["01-jedno-teleso.step", "04-palce.step", "07-metry.step"])
def test_embedded_source_and_export_reimport(name, tmp_path):
    original = (FIXTURES / name).read_bytes()
    record = source_record(original, name)
    path = tmp_path / "jiny-pocitac" / "model.json"
    path.parent.mkdir()
    path.write_text(json.dumps(record), encoding="utf-8")
    # Nové otevření používá jen uložené bajty, nikoliv cestu k původnímu souboru.
    restored = source_bytes(json.loads(path.read_text(encoding="utf-8")))
    assert restored == original
    first = check_in_child(restored)
    shape = _shape_from(("Part", first.shape_bytes))
    exported = tmp_path / "vystup.step"
    export_step(shape, exported)
    second = check_in_child(exported.read_bytes())
    assert second.facts.solids == first.facts.solids == 1
    assert second.facts.bounds_mm == pytest.approx(first.facts.bounds_mm, abs=1e-6)
    assert second.facts.volume_mm3 == pytest.approx(first.facts.volume_mm3, abs=1e-5)
