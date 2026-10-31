"""P6: význam stěny loftu, analytické objemy, měření a zpětná kompatibilita."""

import copy
import math

import pytest

from conftest import EXAMPLES, box_features
from skodacad import Document, rebuild
from skodacad.document import VERSION, DocumentError
from skodacad.measure import RayCaster
from skodacad.schema import new_feature
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

EXAMPLE = EXAMPLES / "loft_stena.json"


def cone_volume(shift, height=60):
    return math.pi * height * (60 * shift - shift**2)


@pytest.mark.parametrize("mode", ["normal", "sections"])
@pytest.mark.parametrize("wall", [3, 18])
def test_conical_wall_volume_and_normal_thickness(mode, wall):
    document = Document.load(EXAMPLE)
    document.features[-1]["wall_mode"] = mode
    document.features[-1]["wall"] = wall
    result = rebuild(document)
    assert result.ok, result.first_error
    part = result.part
    shift = wall * math.sqrt(1 + (20 / 60)**2) if mode == "normal" else wall
    assert part.is_valid and len(part.solids()) == 1
    assert part.volume == pytest.approx(cone_volume(shift), abs=2e-5)
    # Nezávislá rovnice kužele: na vnějším plášti r(z) = 40 − z/3.
    ray = RayCaster(part)
    for z in [10, 30, 50]:
        for angle in [0, 0.7, 2.2]:
            normal_length = math.sqrt(1 + 1 / 9)
            normal = (math.cos(angle) / normal_length, math.sin(angle) / normal_length,
                      1 / 3 / normal_length)
            point = ((40 - z / 3) * math.cos(angle), (40 - z / 3) * math.sin(angle), z)
            depth, oblique = ray.thickness(point, tuple(-n for n in normal))
            assert not oblique
            assert depth == pytest.approx(shift / normal_length, abs=2e-5)


def rectangular_loft(kind, mode):
    rounded = kind == "rounded"
    a = {"id": "a", "type": "sketch", "plane": "XY", "elements": [
        {"shape": "rectangle", "width": 80, "height": 50,
         "corner_radius": 6 if rounded else 0}]}
    b = copy.deepcopy(a)
    b.update(id="b", offset=40 if kind == "inclined" else 30)
    if kind == "inclined":
        b["elements"][0].update(width=40, height=30)
    return Document.from_dict({"format": "skodacad", "version": VERSION, "features": [a, b,
        {"id": "l", "type": "loft", "sketches": ["a", "b"], "ruled": True,
         "wall": 3, "wall_mode": mode}]})


@pytest.mark.parametrize("mode", ["normal", "sections"])
@pytest.mark.parametrize("kind", ["straight", "inclined", "rounded"])
def test_three_reference_profiles_have_analytic_volume_and_expected_wall(kind, mode):
    document = rectangular_loft(kind, mode)
    result = rebuild(document)
    assert result.ok, result.first_error
    if kind == "inclined":
        dx = 3 * math.sqrt(1.25) if mode == "normal" else 3
        dy = 3 * math.sqrt(1.0625) if mode == "normal" else 3

        def integral(a, b):
            return 4 * (a * b * 40 - (a / 4 + b / 2) * 40**2 / 2 + 40**3 / 24)
        expected = integral(40, 25) - integral(40 - dx, 25 - dy)
    else:
        expected = (80 * 50 - 74 * 44) * 30
        if kind == "rounded":
            expected -= (4 - math.pi) * (6**2 - 3**2) * 30
    assert result.part.volume == pytest.approx(expected, abs=2e-5)
    outer = copy.deepcopy(document)
    outer.features[-1].pop("wall")
    original = rebuild(outer).part
    ray = RayCaster(result.part)
    for face in original.faces():
        point = face.position_at(0.5, 0.5)
        normal = face.normal_at(point)
        if abs(normal.Z) > 0.999:
            continue  # otevřená čela nejsou stěny
        depth, oblique = ray.thickness(tuple(point), tuple(-normal))
        assert not oblique
        target = (3 * max(abs(normal.X), abs(normal.Y))
                  if kind == "inclined" and mode == "sections" else 3)
        assert depth == pytest.approx(target, abs=2e-5)


def test_legacy_hopper_and_explicit_sections_keep_identical_geometry(tmp_path):
    document = Document.load(EXAMPLES / "vysypka.json")
    original = rebuild(document)
    assert original.ok
    assert "wall_mode" not in document.features[-1]
    document.save(tmp_path / "old.json")
    assert Document.load(tmp_path / "old.json").to_dict()["version"] == 24
    assert original.part.volume == pytest.approx(908807.4817089331, abs=2e-5)
    document.features[-1]["wall_mode"] = "sections"
    explicit = rebuild(document)
    assert explicit.ok, explicit.first_error
    assert explicit.part.volume == pytest.approx(original.part.volume, abs=2e-5)


def test_hopper_normal_mode_reports_failure_keeps_previous_part_and_skips_rest():
    document = Document.load(EXAMPLES / "vysypka.json")
    document.features[-1]["wall_mode"] = "normal"
    document.features[:0] = box_features(10, 10, 5)
    document.features.append({"id": "after", "type": "fillet", "edges": "all", "radius": 1})
    result = rebuild(document)
    assert not result.ok and "V rovinách skic" in result.first_error.message
    assert result.part is result.parts_before["vysypka"]
    assert result.part.volume == pytest.approx(500)
    assert result.statuses[-1].status == "skipped"


@pytest.mark.parametrize("failure", ["exception", "unchanged"])
def test_normal_never_falls_back_to_profile_offsets(monkeypatch, failure):
    import skodacad.features as features

    calls = []

    def failed_offset(obj, **kwargs):
        calls.append(obj._dim)
        if failure == "exception":
            raise RuntimeError("simulované selhání jádra")
        return obj

    monkeypatch.setattr(features, "offset", failed_offset)
    result = rebuild(Document.load(EXAMPLE))
    assert not result.ok and "kolmo ke stěně" in result.first_error.message
    assert calls == [3]


def test_sections_never_tries_a_normal_offset(monkeypatch):
    import skodacad.features as features

    original_offset = features.offset
    calls = []

    def only_profiles(obj, **kwargs):
        calls.append(obj._dim)
        assert obj._dim == 2
        return original_offset(obj, **kwargs)

    monkeypatch.setattr(features, "offset", only_profiles)
    document = Document.load(EXAMPLE)
    document.features[-1]["wall_mode"] = "sections"
    result = rebuild(document)
    assert result.ok, result.first_error
    assert calls == [2, 2]
    assert result.part.volume == pytest.approx(cone_volume(3), abs=2e-5)


@pytest.mark.parametrize("mode", ["normal", "sections"])
def test_impossible_wall_is_not_accepted(mode):
    document = Document.load(EXAMPLE)
    document.features[-1].update(wall=50, wall_mode=mode)
    result = rebuild(document)
    assert not result.ok and "tloušťku" in result.first_error.message


@pytest.mark.parametrize("wall", [19, 20])
def test_inverted_offset_near_the_small_end_is_rejected(wall):
    document = Document.load(EXAMPLE)
    document.features[-1]["wall"] = wall
    result = rebuild(document)
    assert not result.ok and "kolmo ke stěně" in result.first_error.message


def test_valid_but_thinner_kernel_result_is_rejected(monkeypatch):
    import skodacad.features as features

    thinner = Document.load(EXAMPLE)
    thinner.features[-1]["wall"] = 1
    wrong = rebuild(thinner).part
    monkeypatch.setattr(features, "offset", lambda *a, **kw: wrong)
    result = rebuild(Document.load(EXAMPLE))
    assert not result.ok and "V rovinách skic" in result.first_error.message


@pytest.mark.parametrize("bad", [None, False, "auto", {}, []])
def test_invalid_mode_is_rejected_on_read_and_in_the_core(bad):
    document = Document.load(EXAMPLE)
    data = document.to_dict()
    data["features"][-1]["wall_mode"] = bad
    with pytest.raises(DocumentError, match="normal.*sections"):
        Document.from_dict(data)
    document.features[-1]["wall_mode"] = bad
    result = rebuild(document)
    assert not result.ok and "wall_mode" in result.first_error.message


def test_version_and_missing_mode_are_distinct():
    document = Document.load(EXAMPLE)
    assert VERSION == 33 and document.to_dict()["version"] == 33
    data = document.to_dict()
    data["version"] = 32
    with pytest.raises(DocumentError, match="33"):
        Document.from_dict(data)
    del data["features"][-1]["wall_mode"]
    old = Document.from_dict(data)
    assert old.to_dict()["version"] == 24
    old.features.append({"id": "r", "type": "variable_fillet"})
    assert old.to_dict()["version"] == 32
    old.features[-2]["wall_mode"] = "sections"
    assert old.to_dict()["version"] == 33
    assert new_feature("loft", [])["wall_mode"] == "normal"


def test_session_parameters_history_and_save_reopen(tmp_path):
    session = ModelSession()
    session.open(EXAMPLE)
    feature = session.feature("prechod")
    feature["wall_mode"] = "sections"
    session.update_feature("prechod", feature)
    assert session.result.part.volume == pytest.approx(cone_volume(3), abs=2e-5)
    session.undo()
    assert session.feature("prechod")["wall_mode"] == "normal"
    session.redo()
    session.set_parameter("H", "120")
    assert session.result.part.volume == pytest.approx(cone_volume(3, height=120), abs=2e-5)
    session.save(tmp_path / "loft.json")
    reopened = ModelSession()
    reopened.open(tmp_path / "loft.json")
    assert reopened.document == session.document and reopened.result.ok
    assert reopened.document.to_dict()["version"] == 33
    assert reopened.result.part.volume == pytest.approx(session.result.part.volume, abs=2e-5)


def test_modes_cross_the_worker_boundary():
    runner = BackgroundRebuilder()
    try:
        for mode in ("normal", "sections"):
            document = Document.load(EXAMPLE)
            document.features[-1]["wall_mode"] = mode
            job = runner.submit(document.to_dict())
            finished = runner.wait(timeout=30)
            assert finished is not None and finished.job == job and not finished.error
            assert finished.result.ok
            assert finished.result.part.volume == pytest.approx(
                rebuild(document).part.volume, abs=2e-5)
    finally:
        runner.close()
