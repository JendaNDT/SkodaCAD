"""Referenční vstupy P3.1: nezávisle vypočtené míry a struktura STEP."""

import hashlib
from pathlib import Path

import pytest
from build123d import import_step
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader

FIXTURES = Path(__file__).parent / "fixtures" / "step"

CASES = [
    ("01-jedno-teleso.step", 1, 1, 6, (0, 0, 0), (40, 30, 20), 24000),
    ("02-dve-telesa.step", 2, 2, 12, (0, 0, 0), (35, 20, 30), 6750),
    ("03-sestava.step", 1, 2, 12, (0, 0, 0), (35, 20, 30), 6750),
    ("04-palce.step", 1, 1, 6, (0, 0, 0), (50.8, 25.4, 12.7), 16387.064),
    ("05-otevrena-plocha.step", 1, 0, 1, (-20, -10, 0), (40, 20, 0), 0),
]

HASHES = {
    "01-jedno-teleso.step": "c326fffbe82273617c8e009f9992f04080e615b6863f686a9bea9e7216cce812",
    "02-dve-telesa.step": "11a3cc83a880c00dc2ba5bea1a8a1173dfdc1f7cd4ea4eeaa21adadc7497e943",
    "03-sestava.step": "1f1993250b6a555730367ff7089e9e2b6350dc7b5927a5d132decfd9034784ba",
    "04-palce.step": "1bbd9ecfdbbe43e829ac0a7a5a2d9f3985c14bec2898b99a2192e592da4448fe",
    "05-otevrena-plocha.step": "23f564aa265d7ebd65ae278eed335557c9f6394f2fe7f8610ec47606c67541fd",
    "06-poskozeny.step": "dfe370bd414a9418d4f20746e02eb5dc0e3e3efacf2304ef1368e5218ad2a2a6",
}


@pytest.mark.parametrize("name,roots,solids,faces,minimum,size,volume", CASES)
def test_reference_geometry(name, roots, solids, faces, minimum, size, volume):
    path = FIXTURES / name
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.NbRootsForTransfer() == roots
    shape = import_step(path)
    assert BRepCheck_Analyzer(shape.wrapped).IsValid()
    assert len(shape.solids()) == solids
    assert len(shape.faces()) == faces
    bbox = shape.bounding_box()
    assert tuple(bbox.min) == pytest.approx(minimum, abs=1e-6)
    assert tuple(bbox.size) == pytest.approx(size, abs=1e-6)
    assert shape.volume == pytest.approx(volume, abs=1e-5)


def test_distinguishes_assembly_free_shapes_and_inches():
    assembly = (FIXTURES / "03-sestava.step").read_text(encoding="ascii")
    separate = (FIXTURES / "02-dve-telesa.step").read_text(encoding="ascii")
    inches = (FIXTURES / "04-palce.step").read_text(encoding="ascii")
    assert assembly.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE") == 2
    assert "NEXT_ASSEMBLY_USAGE_OCCURRENCE" not in separate
    assert "CONVERSION_BASED_UNIT('INCH'" in inches
    shape = import_step(FIXTURES / "03-sestava.step")
    assert sorted(child.label for child in shape.children) == ["Deska", "Kostka"]
    assert [len(child.solids()) for child in shape.children] == [1, 1]
    for name in ("02-dve-telesa.step", "03-sestava.step"):
        solids = sorted(import_step(FIXTURES / name).solids(), key=lambda s: s.bounding_box().min.X)
        assert tuple(solids[0].bounding_box().min) == pytest.approx((0, 0, 0), abs=1e-6)
        assert tuple(solids[0].bounding_box().size) == pytest.approx((10, 20, 30), abs=1e-6)
        assert solids[0].volume == pytest.approx(6000, abs=1e-5)
        assert tuple(solids[1].bounding_box().min) == pytest.approx((30, 0, 0), abs=1e-6)
        assert tuple(solids[1].bounding_box().size) == pytest.approx((5, 10, 15), abs=1e-6)
        assert solids[1].volume == pytest.approx(750, abs=1e-5)


def test_truncated_file_is_rejected_by_step_reader():
    path = FIXTURES / "06-poskozeny.step"
    original = (FIXTURES / "01-jedno-teleso.step").read_bytes()
    assert path.read_bytes() == original[:len(original) // 2]
    assert STEPControl_Reader().ReadFile(str(path)) != IFSelect_RetDone


@pytest.mark.parametrize("name,expected", HASHES.items())
def test_fixture_sha256(name, expected):
    assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected
