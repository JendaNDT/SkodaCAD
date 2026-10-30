"""Vytvoření a kontrola přenositelných modelů pro CI na dvou operačních systémech.

Spuštění: python tests/p35_cross_os.py fetch-onshape|create|check SLOŽKA

Kromě modelů s vloženým STEP vznikne i sestava v podsložce (P5.2, A18): odkazuje na
modely o úroveň výš (``../…``), na druhém systému se musí otevřít úplná, se stejnými
otisky zdrojů, objemem a obálkami kopií.
"""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from skodacad.assembly_session import AssemblySession
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
    create_assembly(folder)


def create_assembly(folder: Path) -> None:
    (folder / "sestavy").mkdir(exist_ok=True)
    assembly = AssemblySession()
    assembly.new(folder / "sestavy" / "sestava.json", "Přenos sestavy")
    first = folder / "01-jedno-teleso.step.json"
    one = assembly.insert(first)
    two = assembly.insert(first, position=(100, 0, 0), rotation=(0, 0, 90))
    assembly.insert(folder / "04-palce.step.json", position=(0, 0, 50), rotation=(90, 0, 30))
    # Vazba (formát 30) na základní roviny – splněná, nic se neposune (P5.3).
    assembly.add_constraint("flush", {"component": one, "plane": "XY"},
                            {"component": two, "plane": "XY"})
    assembly.save()
    result = assembly.result
    assert result.complete and not result.warnings, result.problems
    saved = json.loads((folder / "sestavy" / "sestava.json").read_text(encoding="utf-8"))
    assert saved["version"] == 30 and len(saved["constraints"]) == 1
    expected = {"volume": result.volume_mm3,
                "bounds": [list(instance.part.bounding_box().min)
                           + list(instance.part.bounding_box().max)
                           for instance in result.instances]}
    (folder / "sestavy" / "ocekavani.json").write_text(json.dumps(expected), encoding="utf-8")
    print(f"Created assembly with {len(result.instances)} components.")


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
    check_assembly(folder)


def check_assembly(folder: Path) -> None:
    expected = json.loads((folder / "sestavy" / "ocekavani.json").read_text(encoding="utf-8"))
    assembly = AssemblySession()
    result = assembly.open(folder / "sestavy" / "sestava.json")
    assert result.complete, result.problems
    assert not result.warnings, result.warnings  # otisky zdrojů stejné na obou systémech
    assert [c.state for c in result.constraints] == ["ok"] and not assembly.dirty
    assert [c.path for c in assembly.assembly.components] == [
        "../01-jedno-teleso.step.json", "../01-jedno-teleso.step.json", "../04-palce.step.json"]
    assert abs(result.volume_mm3 - expected["volume"]) <= 1e-5
    for instance, bounds in zip(result.instances, expected["bounds"], strict=True):
        box = instance.part.bounding_box()
        assert all(abs(a - b) <= 1e-6
                   for a, b in zip([*box.min, *box.max], bounds, strict=True))
    print(f"Opened assembly: {len(result.instances)} components, {result.volume_mm3:.6f} mm^3.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch-onshape", "create", "check"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    {"fetch-onshape": fetch_onshape, "create": create, "check": check}[args.action](args.folder)


if __name__ == "__main__":
    main()
