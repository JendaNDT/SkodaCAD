"""Vytvoření a kontrola přenositelných modelů pro CI na dvou operačních systémech.

Spuštění: python tests/p35_cross_os.py create|check SLOŽKA
"""
import argparse
import hashlib
import time
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
}


def create(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, (digest, _, _) in CASES.items():
        raw = (FIXTURES / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        session = ModelSession()
        session.new_document()
        session.add_step_import(raw, name)
        assert session.result.ok, session.result.first_error
        session.save(folder / (name + ".json"))
        print(f"Vytvořen model s vloženým zdrojem {name}.")


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
        print(f"Otevřen a exportován {name}: {tuple(size)} mm, {part.volume:.6f} mm³.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "check"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    (create if args.action == "create" else check)(args.folder)


if __name__ == "__main__":
    main()
