"""P3.3: průzkum ohlášené opravy orientace při převodu STEP, ne importní služba."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

CASES = Path(__file__).parent / "fixtures" / "step-p33"

# Každé čtení v samostatném procesu: nastavení OCCT je globální.
PROBE = r'''
import io, json, sys
from build123d import Shape
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_ItemsByEntity, IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Reader

reader = STEPControl_Reader()
assert Interface_Static.SetCVal_s("FromSTEP.exec.op", sys.argv[2])
assert reader.ReadFile(sys.argv[1]) == IFSelect_RetDone
load = io.BytesIO()
reader.PrintCheckLoad(load, False, IFSelect_ItemsByEntity)
assert reader.TransferRoots() == 1
shape = Shape.cast(reader.OneShape())
transfer = io.BytesIO()
reader.PrintCheckTransfer(transfer, False, IFSelect_ItemsByEntity)
print(json.dumps({"load": load.getvalue().decode("utf-8", errors="replace"),
                  "report": transfer.getvalue().decode("utf-8", errors="replace"),
                  "valid": BRepCheck_Analyzer(shape.wrapped).IsValid(),
                  "solids": len(shape.solids()), "faces": len(shape.faces()),
                  "volume": shape.volume, "size": list(shape.bounding_box().size)}))
'''


def probe(name, mode):
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(CASES / name), mode],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def test_fixture_identity_and_introduced_change():
    source = (CASES / "puvodni-kvadr.step").read_bytes()
    modified = (CASES / "obracena-plocha.step").read_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "c326fffbe82273617c8e009f9992f04080e615b6863f686a9bea9e7216cce812"
    )
    assert hashlib.sha256(modified).hexdigest() == (
        "16ff0b22432178a0afa401b7cb1d45a6a10441a8a534d37a53b751b60bfc8de3"
    )
    before = b"#17 = ADVANCED_FACE('',(#18),#32,.F.);"
    after = b"#17 = ADVANCED_FACE('',(#18),#32,.T.);"
    assert source.count(before) == 1
    assert modified == source.replace(before, after)


@pytest.mark.parametrize("mode", ["FixShape", ""])
def test_orientation_correction_is_reported_even_without_shape_fix(mode):
    valid = probe("puvodni-kvadr.step", mode)
    altered = probe("obracena-plocha.step", mode)
    assert not valid["load"] and not valid["report"]
    assert not altered["load"]
    assert "Faces were incorrectly oriented in the shell, corrected" in altered["report"]
    for result in (valid, altered):
        assert result["valid"] and result["solids"] == 1 and result["faces"] == 6
        assert result["size"] == pytest.approx([40, 30, 20], abs=1e-6)
        assert result["volume"] == pytest.approx(24000, abs=1e-5)
