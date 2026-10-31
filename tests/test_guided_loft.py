"""Řízený přechod: objemy, průřezy, intervalové meze, zachování stavu a přenos."""

import copy
import importlib
import math

import pytest
from build123d import Plane, Vector, import_step, section
from numpy.polynomial import polynomial as poly

from conftest import EXAMPLES, box_features
from native_ownership import check_accepted_inputs
from skodacad import Document, rebuild
from skodacad.document import VERSION, DocumentError
from skodacad.export import export
from skodacad.guided_loft import _positive, default_guides
from skodacad.schema import new_feature
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

EXAMPLE = EXAMPLES / "rizeny_prechod.json"


def expected_volume(bx, by, height=60):
    # Nezávislý integrál ve standardní mocninné bázi; implementace používá Bernsteinovy koef.
    coefficients = poly.polymul([20, -8+4*bx, -4*bx], [15, -6+4*by, -4*by])
    return 4*height*sum(c/(i+1) for i, c in enumerate(coefficients))


@pytest.mark.parametrize("bx,by", [(0, 0), (7, 5), (-2, -1), (12, 0)])
@pytest.mark.parametrize("bent", [False, True])
def test_volume_cross_sections_and_actual_surface_match_analytic_reference(bx, by, bent):
    doc = Document.load(EXAMPLE)
    doc.parameters.update(Bx=bx, By=by)
    feature = doc.features[-1]
    if bent:
        for g in feature["guides"]:
            sx, sy = g["corner"]["x"], g["corner"]["y"]
            g["controls"] = [[sx*4*bx/3+10, sy*4*by/3+8],
                             [sx*4*bx/3-8, sy*4*by/3-5]]
    original = copy.deepcopy(doc.to_dict())
    result = rebuild(doc)
    assert result.ok, result.first_error
    part = result.part
    assert part.is_valid and len(part.solids()) == 1
    assert part.volume == pytest.approx(expected_volume(bx, by), abs=2e-5)
    for t in (.13, .31, .5, .73, .87):
        a, b = 20-8*t+4*bx*t*(1-t), 15-6*t+4*by*t*(1-t)
        center_x = 3*(1-t)**2*t*10 - 3*(1-t)*t*t*8 if bent else 0
        center_y = 3*(1-t)**2*t*8 - 3*(1-t)*t*t*5 if bent else 0
        assert section(part, section_by=Plane(origin=(0, 0, t*60))).area == pytest.approx(
            4*a*b, abs=2e-5)
        for x, y in ((a, b*.4), (-a, -b*.4), (a*.4, b), (-a*.4, -b)):
            p = Vector(center_x+x, center_y+y, t*60)
            assert min(f.distance_to(p) for f in part.faces()) < 1e-6
    assert doc.to_dict() == original


def test_native_sketches_are_read_only_even_during_sewing(monkeypatch):
    module = importlib.import_module("skodacad.rebuild")
    run = module._run_feature
    monkeypatch.setattr(module, "_run_feature", lambda ctx, f: check_accepted_inputs(run, ctx, f))
    assert rebuild(Document.load(EXAMPLE)).ok


def test_translated_profiles_and_permuted_guide_order_keep_semantic_corners():
    doc = Document.load(EXAMPLE)
    for i, f in enumerate(doc.features[:2]):
        f["elements"][0]["center"] = [100+17*i, -70-8*i]
        f["offset"] = 10+60*i
    doc.features[-1]["guides"].reverse()
    result = rebuild(doc)
    assert result.ok, result.first_error
    assert result.part.volume == pytest.approx(77760, abs=2e-5)
    t = .5
    p = Vector(100+17*t+23, -70-8*t, 10+60*t)
    assert min(f.distance_to(p) for f in result.part.faces()) < 1e-6


def test_subdivision_accepts_positive_mixed_coefficients_and_refuses_touch_or_uncertainty():
    assert _positive([1, -.1, 1], 1e-10)  # skutečné minimum 0,45; hrubá obálka je záporná
    assert not _positive([1, -1, 1], 1e-10)  # dotyk nuly přesně mezi vzorky
    assert not _positive([1e-12]*7, 1e-10)  # neprokázaná kladnost není přijetí


def test_subdivision_budget_is_a_hard_limit(monkeypatch):
    from skodacad import guided_loft

    monkeypatch.setattr(guided_loft, "MAX_NODES", 1)
    assert guided_loft._positive([1, 1, 1], 1e-10)
    assert not guided_loft._positive([1, -.1, 1], 1e-10)


def pinched(a=.371234, c=-1e-8):
    """Poloviční šířka 100*((t-a)^2+c): krajní čela kladná, nebezpečí uvnitř."""
    doc = Document.load(EXAMPLE)
    doc.parameters.update(Bx=0, By=0)
    powers = [100*(a*a+c), -200*a, 100]
    poles = [powers[0], powers[0]+powers[1]/3,
             powers[0]+2*powers[1]/3+powers[2]/3, sum(powers)]
    for i in (0, 1):
        doc.features[i]["elements"][0].update(width=2*poles[i*3], height=10)
    for g in doc.features[-1]["guides"]:
        sx = g["corner"]["x"]
        g["controls"] = [[sx*(poles[k]-(poles[0]+(poles[3]-poles[0])*k/3)), 0]
                         for k in (1, 2)]
    return doc


def test_narrow_crossing_between_sampled_sections_is_refused_before_kernel(monkeypatch):
    from skodacad import guided_loft

    doc = pinched()
    # Pevná síť po 0,05 závadu mine; intervalová kontrola ji musí odmítnout.
    assert all(100*((t-.371234)**2-1e-8) > 0 for t in [i/20 for i in range(21)])
    monkeypatch.setattr(guided_loft.Face, "make_bezier_surface",
                        lambda *_a, **_k: pytest.fail("Neplatná síť se nesmí předat jádru."))
    result = rebuild(doc)
    assert not result.ok and "konvexitu" in result.first_error.message


def test_true_positive_pinched_shape_is_not_rejected_just_for_control_polygon():
    doc = pinched(a=.4, c=.03)
    result = rebuild(doc)
    assert result.ok, result.first_error
    assert result.part.volume == pytest.approx(20*60*100*(1/3-.4+.4**2+.03), abs=2e-5)


@pytest.mark.parametrize("kind", ["circle", "rounded", "rotated", "tilted", "height"])
def test_unsupported_profiles_are_refused_with_help(kind):
    doc = Document.load(EXAMPLE)
    if kind == "circle":
        doc.features[0]["elements"] = [{"shape": "circle", "diameter": 30}]
    elif kind == "rounded":
        doc.features[0]["elements"][0]["corner_radius"] = 3
    elif kind == "rotated":
        doc.features[0]["elements"][0]["angle"] = 25
    elif kind == "tilted":
        doc.features[0]["plane"] = "XZ"
    else:
        doc.features[1]["offset"] = 0
    result = rebuild(doc)
    assert not result.ok, kind
    assert result.first_error.id == "rizeny" and result.part is None


@pytest.mark.parametrize("change", [
    {"guides": None}, {"guides": []}, {"sketches": ["dole", "dole"]}, {"wall": 0},
    {"wall_mode": "normal"}, {"ruled": False},
])
def test_structural_errors_fail_read_and_direct_rebuild(change):
    doc = Document.load(EXAMPLE)
    doc.features[-1].update(change)
    with pytest.raises(DocumentError):
        Document.from_dict(doc.to_dict())
    assert not rebuild(doc).ok


@pytest.mark.parametrize("bad", [True, None, float("nan"), float("inf"), 10**1000, "", [], {}])
def test_invalid_coordinate_never_crashes_reader(bad):
    doc = Document.load(EXAMPLE)
    doc.features[-1]["guides"][0]["controls"][0][0] = bad
    with pytest.raises(DocumentError):
        Document.from_dict(doc.to_dict())
    assert not rebuild(doc).ok


def test_duplicate_missing_or_unknown_corner_fields_are_refused():
    for change in ({"x": True, "y": 1}, {"x": 0, "y": 1}, {"x": 1}, {"x": -1, "y": 1}):
        doc = Document.load(EXAMPLE)
        doc.features[-1]["guides"][0]["corner"] = change
        with pytest.raises(DocumentError):
            Document.from_dict(doc.to_dict())
    doc = Document.load(EXAMPLE)
    doc.features[-1]["guides"][0]["unknown"] = 1
    with pytest.raises(DocumentError):
        Document.from_dict(doc.to_dict())


def test_failure_preserves_previous_body_and_skips_rest():
    doc = pinched()
    doc.features[:0] = box_features(10, 10, 2)
    doc.features[-1]["operation"] = "add"
    doc.features.append({"id": "after", "type": "fillet", "edges": "all", "radius": .2})
    result = rebuild(doc)
    assert not result.ok and result.part is result.parts_before["rizeny"]
    assert result.part.volume == pytest.approx(200)
    assert result.statuses[-1].status == "skipped"


@pytest.mark.parametrize("operation", ["add", "cut"])
def test_add_and_cut_have_expected_boolean_effect(operation):
    doc = Document.load(EXAMPLE)
    doc.features[:0] = box_features(100, 100, 80 if operation == "cut" else 10)
    doc.features[2]["offset"], doc.features[3]["offset"] = 10, 70
    doc.features[-1]["operation"] = operation
    result = rebuild(doc)
    assert result.ok, result.first_error
    expected = 800000-77760 if operation == "cut" else 100000+77760
    assert result.part.volume == pytest.approx(expected, abs=2e-5)


def test_format_default_history_overlay_and_save_reopen(tmp_path):
    doc = Document.load(EXAMPLE)
    assert VERSION == 34 and doc.to_dict()["version"] == 34
    data = doc.to_dict()
    data["version"] = 33
    with pytest.raises(DocumentError, match="34"):
        Document.from_dict(data)
    feature = new_feature("guided_loft", doc.features[:2])
    assert feature["sketches"] == ["dole", "nahore"] and feature["guides"] == default_guides()
    session = ModelSession()
    session.open(EXAMPLE)
    display = session.guided_loft_display("rizeny", 2)
    assert display["selected"] == 2 and len(display["guides"]) == 4
    assert display["guides"][0]["curve"][0] == pytest.approx((20, 15, 0))
    assert display["guides"][0]["curve"][-1] == pytest.approx((12, 9, 60))
    assert not session.dirty and not session.can_undo
    session.set_parameter("Bx", "4")
    assert session.result.part.volume == pytest.approx(expected_volume(4, 5), abs=2e-5)
    session.undo()
    assert session.result.part.volume == pytest.approx(77760, abs=2e-5)
    session.redo()
    session.set_parameter("H", "120")
    assert session.result.part.volume == pytest.approx(expected_volume(4, 5, 120), abs=2e-5)
    session.save(tmp_path/"guided.json")
    session.open(tmp_path/"guided.json")
    assert session.result.ok and session.document.to_dict()["version"] == 34
    session.open(EXAMPLES/"loft_stena.json")
    assert session.document.to_dict()["version"] == 33
    assert session.guided_loft_display("prechod") is None


def test_step_round_trip_and_worker_transfer(tmp_path):
    direct = rebuild(Document.load(EXAMPLE))
    path = tmp_path/"guided.step"
    export(direct.part, path)
    restored = import_step(path)
    assert restored.is_valid and restored.volume == pytest.approx(77760, abs=2e-5)
    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(EXAMPLE)
        assert session.guided_loft_display("rizeny") is None
        assert session.wait(30) and session.result.ok
        assert session.result.part.volume == pytest.approx(77760, abs=2e-5)
        assert session.guided_loft_display("rizeny") is not None
        session.set_parameter("Bx", "4")
        assert session.guided_loft_display("rizeny") is None
        assert session.wait(30) and session.result.ok
        assert session.result.part.volume == pytest.approx(expected_volume(4, 5), abs=2e-5)
    finally:
        runner.close()


def test_large_coordinate_precision_is_refused_and_bad_expression_keeps_state():
    doc = Document.load(EXAMPLE)
    for f in doc.features[:2]:
        f["elements"][0]["center"] = [1e10, 1e10]
    result = rebuild(doc)
    assert not result.ok and "blíž k počátku" in result.first_error.message
    doc = Document.load(EXAMPLE)
    doc.features[-1]["guides"][0]["controls"][0][0] = "1/0"
    result = rebuild(doc)
    assert not result.ok and result.part is None


def test_guided_feature_can_be_repeated_and_later_modified():
    doc = Document.load(EXAMPLE)
    doc.features.append({"id": "copies", "type": "pattern", "kind": "linear",
                         "features": ["rizeny"], "count": 2, "spacing": 80, "direction": "X"})
    result = rebuild(doc)
    assert result.ok, result.first_error
    assert len(result.part.solids()) == 2 and result.part.volume == pytest.approx(155520, abs=2e-5)
    doc.features.pop()
    doc.features.append({"id": "hole", "type": "hole", "kind": "clearance", "size": "M3",
                         "diameter": 4,
                         "plane": "top", "positions": [[0, 0]], "through_all": True})
    result = rebuild(doc)
    assert result.ok, result.first_error
    assert result.part.volume == pytest.approx(77760 - math.pi*4*60, abs=2e-5)
