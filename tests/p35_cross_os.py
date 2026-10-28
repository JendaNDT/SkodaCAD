"""Vytvoření a kontrola přenositelných modelů pro CI na dvou operačních systémech.

Spuštění: python tests/p35_cross_os.py fetch-onshape|create|check SLOŽKA
"""
import argparse
import hashlib
import time
import urllib.request
from pathlib import Path

from skodacad.session import ModelSession
from skodacad.step_source import source_bytes
from skodacad.step_task import StepTask

FIXTURES = Path(__file__).parent / "fixtures" / "step"
CASES = {
    "01-jedno-teleso.step": ("c326fffbe82273617c8e009f9992f04080e615b6863f686a9bea9e7216cce812",
                              (40.0, 30.0, 20.0), 24000.0),
    "04-palce.step": ("1bbd9ecfdbbe43e829ac0a7a5a2d9f3985c14bec2898b99a2192e592da4448fe",
                       (50.8, 25.4, 12.7), 16387.064),
    "07-metry.step": ("c2cee005d3c3bcf18ef644e2493b7787a9f4625e6d43c6e08a8b43de820a8b73",
                       (10.0, 13.0, 17.0), 2210.0),
    "onshape-metry.step": ("31d3fd438c1bfe01951619a83a2744a442dfe05b46931c356e375ba89dce916d",
                           (20.0, 20.0, 20.0), 8000.0),
}
ONSHAPE_URL = ("https://gist.githubusercontent.com/MattFerraro/"
               "76adbd74042696895e7f9b0f87313a88/raw/"
               "a7d49498a42152d0453ceb3d125fe0d9570009c4/1cm%20cube.step")


def fetch_onshape(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ONSHAPE_URL, timeout=30) as response:  # noqa: S310
        raw = response.read(1024 * 1024)
    assert hashlib.sha256(raw).hexdigest() == CASES["onshape-metry.step"][0]
    (folder / "onshape-metry.step").write_bytes(raw)


def create(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, (digest, _, _) in CASES.items():
        source = folder / name if name == "onshape-metry.step" else FIXTURES / name
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        session = ModelSession()
        session.new_document()
        session.add_step_import(raw, name)
        assert session.result.ok, session.result.first_error
        session.save(folder / (name + ".json"))
        print(f"Created model with embedded source {name}.")


def check(folder: Path) -> None:
    for name, (digest, dimensions, volume) in CASES.items():
        session = ModelSession()
        session.open(folder / (name + ".json"))
        assert session.result.ok, session.result.first_error
        raw = source_bytes(session.document.features[0])
        assert hashlib.sha256(raw).hexdigest() == digest
        part = session.result.part
        assert len(part.solids()) == 1
        size = part.bounding_box().size
        assert all(abs(a - b) <= 1e-6 for a, b in zip(size, dimensions, strict=True))
        assert abs(part.volume - volume) <= 1e-5
        export_path = folder / (name + ".export.step")
        session.export(export_path)
        task = StepTask(export_path.read_bytes())
        try:
            deadline = time.monotonic() + 70
            while (outcome := task.poll()) is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert outcome is not None and not outcome.error
            assert outcome.facts.solids == 1
            bounds = outcome.facts.bounds_mm
            exported_size = (bounds[3] - bounds[0], bounds[4] - bounds[1],
                             bounds[5] - bounds[2])
            assert all(abs(a - b) <= 1e-6
                       for a, b in zip(exported_size, dimensions, strict=True))
            assert abs(outcome.facts.volume_mm3 - volume) <= 1e-5
        finally:
            task.cancel()
        print(f"Opened and exported {name}: {tuple(size)} mm, {part.volume:.6f} mm^3.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch-onshape", "create", "check"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    {"fetch-onshape": fetch_onshape, "create": create, "check": check}[args.action](args.folder)


if __name__ == "__main__":
    main()
