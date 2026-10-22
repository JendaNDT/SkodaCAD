"""P1.2A: geometrická kompatibilita ukázek a načítání verzí 1–22."""

import importlib

import pytest

from conftest import EXAMPLES, box_features, make_doc
from native_ownership import check_accepted_inputs
from skodacad import Document, rebuild
from skodacad.document import VERSION
from skodacad.features import FEATURE_TYPES

# Změřeno před změnou jádra na main 15b8bf4. Kompatibilita, nikoli analytický důkaz.
EXAMPLE_BASELINE = {
    "cep.json": (
        24339.35340053283,
        (-40.0000001, -10.0000001, -10.0000001, 40.0000001, 10.0000001, 10.0000001),
        1,
    ),
    "deska.json": (137645.18793644223, (-60.0, -40.0, 0.0, 60.0, 40.0, 15.0), 1),
    "drzak_loziska.json": (17941.511798902062, (-30.0, -15.0, 0.0, 30.0, 15.0, 12.0), 1),
    "hridel.json": (120665.82493081209, (-20.0, -20.0, 0.0, 20.0, 20.0, 135.0), 1),
    "koleno.json": (
        122007.29273345615,
        (-24.150000100000007, -24.1500001, 0.0, 150.0, 24.1500001, 174.1500001),
        1,
    ),
    "krabicka.json": (
        21045.40254638561,
        (-40.0, -25.0, -4.440892098500626e-16, 40.0, 25.0, 30.0),
        1,
    ),
    "kryt.json": (43037.40731626589, (-80.0, -40.0, 0.0, 80.0, 40.0, 4.0), 1),
    "ndt/cilove_objemy/koutovy_svar_objem.json": (
        284900.0,
        (-100.0, -50.0, 0.0, 100.0, 50.0, 90.0),
        1,
    ),
    "ndt/cilove_objemy/tupy_svar_objem.json": (
        363900.00000000006,
        (-150.0, -50.0, -1.0000000000000002, 150.0, 50.0, 14.0),
        1,
    ),
    "ndt/deska.json": (399999.9999999999, (-100.0, -50.0, 0.0, 100.0, 50.0, 20.0), 1),
    "ndt/kapsa.json": (354000.0, (-60.0, -40.0, 0.0, 60.0, 40.0, 40.0), 1),
    "ndt/koutovy_svar.json": (284900.0, (-100.0, -50.0, 0.0, 100.0, 50.0, 90.0), 1),
    "ndt/navrh_kapsa.json": (354000.0, (-60.0, -40.0, 0.0, 60.0, 40.0, 40.0), 1),
    "ndt/otvor.json": (393716.81469282036, (-100.0, -50.0, 0.0, 100.0, 50.0, 20.0), 1),
    "ndt/pristup.json": (399999.99999999994, (-100.0, -50.0, 0.0, 100.0, 50.0, 65.0), 1),
    "ndt/sterbina.json": (178634.51332235383, (-50.0, -30.0, 0.0, 50.0, 30.0, 30.0), 1),
    "ndt/trubka.json": (612422.0718907946, (-150.0, -57.15, -57.15, 150.0, 57.15, 57.15), 1),
    "ndt/tupy_svar.json": (
        363900.00000000006,
        (-150.0, -50.0, -1.0000000000000002, 150.0, 50.0, 14.0),
        1,
    ),
    "ndt/zebro.json": (459999.9999999999, (-100.0, -50.0, 0.0, 100.0, 50.0, 80.0), 1),
    "paka.json": (22717.983559116663, (-20.0, -20.0, 0.0, 90.0, 20.0, 8.0), 1),
    "prilozka.json": (16454.601595447726, (-15.0, -15.0, 0.0, 95.0, 15.000000000000002, 6.0), 1),
    "priruba.json": (311092.5473303001, (-82.5, -82.5, 0.0, 82.5, 82.5, 18.0), 1),
    "ram.json": (
        555617.6907911104,
        (-20.0, -20.0, -10.000000000000002, 820.0, 520.0, 10.000000000000002),
        1,
    ),
    "sloupky.json": (21532.396389495134, (-50.0, -35.0, 0.0, 50.0, 35.0, 9.0), 1),
    "trubka.json": (
        611391.5647100897,
        (-150.0000001, -57.1500001, -57.1500001, 150.0000001, 57.1500001, 57.1500001),
        1,
    ),
    "vysypka.json": (
        908807.4817089331,
        (-200.0000001, -200.0000001, -1e-07, 200.0000001, 200.0000001, 300.0000001),
        1,
    ),
}


@pytest.mark.parametrize("name", sorted(EXAMPLE_BASELINE))
def test_all_recursive_examples_keep_baseline_geometry_and_round_trip(name, tmp_path, monkeypatch):
    module = importlib.import_module("skodacad.rebuild")
    real_run = module._run_feature

    def audit(ctx, feature):
        return check_accepted_inputs(real_run, ctx, feature)

    monkeypatch.setattr(module, "_run_feature", audit)
    path = EXAMPLES / name
    original_bytes = path.read_bytes()
    document = Document.load(path)
    result = rebuild(document)
    assert result.ok, result.first_error
    volume, bounds, solids = EXAMPLE_BASELINE[name]
    assert result.part.is_valid and len(result.part.solids()) == solids
    assert result.part.volume == pytest.approx(volume, rel=1e-9, abs=1e-9)
    box = result.part.bounding_box()
    assert (*box.min, *box.max) == pytest.approx(bounds, abs=1e-6)
    destination = tmp_path / path.name
    document.save(destination)
    restored = Document.load(destination)
    assert restored == document and restored.to_dict()["version"] == VERSION == 22
    assert rebuild(restored).ok
    assert path.read_bytes() == original_bytes


def test_native_input_audit_examples_cover_all_registered_builders():
    exercised = {feature["type"] for path in EXAMPLES.rglob("*.json")
                 for feature in Document.load(path).features}
    assert exercised == set(FEATURE_TYPES)


@pytest.mark.parametrize("version", range(1, 23))
def test_simple_legacy_recipe_loads_without_new_persisted_fields(version, tmp_path):
    source = make_doc(box_features()).to_dict()
    source["version"] = version
    document = Document.from_dict(source)
    result = rebuild(document)
    assert result.ok and result.part.volume == pytest.approx(24000)
    assert len(result.part.solids()) == 1
    path = tmp_path / "saved.json"
    document.save(path)
    saved = Document.load(path).to_dict()
    assert saved["version"] == VERSION == 22
    assert not any("message" in feature for feature in saved["features"])
