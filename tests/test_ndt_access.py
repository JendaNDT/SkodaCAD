"""Návrh poloh UT sondy (etapa 09): ověřeno na referenčních dílech s ručně spočítaným nebo
změřeným výsledkem (docs/ndt/17-navrh-etapa-09.md, oddíl 6), ne existencí výsledku."""

import math
import time
from collections import Counter
from dataclasses import replace

import pytest

from conftest import EXAMPLES, face_at
from skodacad import Document, rebuild
from skodacad.ndt import UT_DISCLAIMER
from skodacad.ndt.access import (
    ALTERNATIVE_ANGLES,
    NOT_FOUND_NOTE,
    ORDER_NOTE,
    AccessError,
    AccessOptions,
    Analysis,
    Variant,
    VariantResult,
    finish,
    rank,
    union,
)
from skodacad.ndt.coverage import CoverageMap, compute
from skodacad.ndt.devices import Probe, aim, direction_angle, place, reuse_placements
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.volume_coverage import compute_volume
from skodacad.selectors import find_face
from test_ndt_volume_reference import PROBE, SLICE


@pytest.fixture(scope="module")
def parts():
    return {name: PartGeometry(rebuild(Document.load(EXAMPLES / "ndt" / f"{name}.json")).part)
            for name in ("deska", "zebro", "pristup")}


# --- pomůcky přiložení ------------------------------------------------------------------


@pytest.mark.parametrize("normal,vector", [((0, 0, 1), (-1, 0, 0)), ((0, 0, 1), (1, 1, 0)),
                                           ((1, 0, 0), (0, 0, 1)), ((0, 0, -1), (0, -1, 5))])
def test_direction_angle_points_the_probe_along_the_vector(parts, normal, vector):
    geo = parts["deska"]
    angle = direction_angle(normal, vector)
    projected = [v - normal[i] * sum(a * b for a, b in zip(vector, normal, strict=True))
                 for i, v in enumerate(vector)]
    length = math.hypot(*projected)
    point = {(0, 0, 1): (0, 0, 20), (1, 0, 0): (100, 0, 10), (0, 0, -1): (0, 0, 0)}[normal]
    frame = aim(geo, Probe.angle(), point, angle)
    assert frame.x_dir == pytest.approx([v / length for v in projected], abs=1e-9)
    assert direction_angle((0, 0, 1), (0, 0, -3)) is None


def test_aim_matches_placement_frame_and_memo_keeps_results(parts):
    geo = parts["zebro"]
    face = face_at(geo.part, 50, 0, 20)
    placed = place(geo, Probe.angle(), (50, 0, 20), angle=135, face=face)
    frame = aim(geo, Probe.angle(), (50, 0, 20), 135, face)
    assert (frame.origin, frame.x_dir, frame.y_dir, frame.z_dir) == (
        placed.origin, placed.x_dir, placed.y_dir, placed.z_dir)
    with reuse_placements(geo) as memo:
        again = place(geo, Probe.angle(), (50, 0, 20), angle=135, face=face)
        other = place(geo, Probe.angle(beam_angle=70, bounces=0), (50, 0, 20), angle=135,
                      face=face)
        assert len(memo) == 1
    assert again == placed
    assert other.probe.beam_angle == 70 and other.state == placed.state
    assert getattr(geo, "_placement_memo", None) is None


def test_coverage_is_identical_with_shared_placements(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    target = [face_at(geo.part, 0, 0, 0)]
    plain = compute(geo, placed, faces=target, scan_step=40, target_step=40)
    with reuse_placements(geo):
        shared = compute(geo, placed, faces=target, scan_step=40, target_step=40)
        again = compute(geo, placed, faces=target, scan_step=40, target_step=40)
    assert plain.states == shared.states == again.states
    assert plain.percent("covered") == again.percent("covered")


def test_options_are_checked_in_czech():
    with pytest.raises(AccessError, match="30°, 45° nebo 90°"):
        AccessOptions(direction_step_deg=20).checked()
    with pytest.raises(AccessError, match="Odrazy"):
        AccessOptions(bounces=(3,)).checked()
    with pytest.raises(AccessError, match="Krok analýzy"):
        AccessOptions(step_mm=0).checked()
    with pytest.raises(AccessError, match="Úhel β"):
        AccessOptions(angles=(90,)).checked()
    assert AccessOptions(angles=(60, 60.0, 45)).checked().angles == (60.0, 45.0)


# --- sjednocení a pořadí -----------------------------------------------------------------


def _map(states, areas=(1.0, 1.0, 2.0, 4.0)):
    n = len(states)
    return CoverageMap([], [], [(float(i), 0.0, 0.0) for i in range(n)], list(areas[:n]),
                       list(states), [None] * n, [""] * n, 10, 5, 0, {"probe": {}}, 1.0)


def test_union_is_sample_by_sample_without_renormalisation():
    a = _map(["covered", "uncovered", "uncertain", "uncovered"])
    b = _map(["uncovered", "uncertain", "covered", "uncovered"])
    merged = union([a, b], ["A", "B"])
    assert merged.states == ["covered", "uncertain", "covered", "uncovered"]
    assert merged.percent("covered") == pytest.approx(100 * 3 / 8)
    assert merged.percent("covered") >= max(a.percent("covered"), b.percent("covered"))
    assert merged.areas == a.areas and merged.assumptions["combination"] == ["A", "B"]
    with pytest.raises(AccessError, match="stejnou mřížku"):
        union([a, _map(["covered"] * 3)])


def _result(states, beta=70.0, bounces=1, valid=5, name="x"):
    coverage = replace(_map(states), valid_positions=valid)
    return VariantResult(Variant(name, {}, 0.0, "0°", beta, bounces), coverage, None, None,
                         None, "", 1.0)


def test_rank_prefers_room_within_one_point_and_greedy_combination():
    wide = _result(["covered", "uncovered", "uncovered", "covered"], valid=40, name="wide")
    tight = _result(["covered", "covered", "uncovered", "covered"], valid=3, name="tight")
    side = _result(["uncovered", "uncovered", "covered", "uncovered"], valid=10, name="side")
    # 62,5 % proti 75 % – rozdíl nad 1 p. b. rozhoduje pokrytí
    assert [r.variant.face for r in rank([wide, tight, side], 70)] == ["tight", "wide", "side"]
    near = _result(["covered", "covered", "uncovered", "covered"], valid=40, bounces=0,
                   name="near")
    assert rank([tight, near], 70)[0].variant.face == "near"
    from skodacad.ndt.access import Preparation
    prep = Preparation([], [], [], [], 1, 10, {"study_beta": 70.0, "step_mm": 10,
                                                "direction_step_deg": 45, "bounces": [0, 1],
                                                "spread_deg": 0}, 1.0)
    result = finish(prep, [tight, side, wide])
    assert [result.variants[i].variant.face for i in result.combination] == ["tight", "side"]
    assert result.gains == pytest.approx([75.0, 25.0])
    assert result.combined == pytest.approx(100.0)
    assert "Kombinace #1 + #3: 100 %" in result.combination_text()


# --- referenční díly ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def gap_analysis(parts):
    """Obtížný přístup: úhlová sonda 40 × 20 v mezeře 30 mm, cíl dno desky."""
    geo = parts["pristup"]
    gap = face_at(geo.part, 0, 0, 15)
    analysis = Analysis(geo, Probe.angle(beam_angle=60), faces=[face_at(geo.part, 0, 0, 0)],
                        contact_faces=[gap], options=AccessOptions(step_mm=10, bounces=(0,),
                                                                  direction_step_deg=90))
    return analysis.run()


def test_gap_across_is_rejected_for_collision_and_along_is_found(gap_analysis):
    across = [r for r in gap_analysis.rejected if r.kind == "access"]
    assert {r.direction for r in across} >= {"0°", "180°"}
    assert all("koliduje" in r.reason for r in across)
    assert gap_analysis.variants, "podél mezery musí najít alternativu"
    assert {r.variant.direction for r in gap_analysis.variants} <= {"90°", "270°"}
    best = gap_analysis.variants[0]
    assert best.covered > 0 and best.best is not None
    assert best.variant.short_face == "+Z (0; 0; 15)"
    # 30 − 20 = 10 mm napříč: v ose mezery volno 5 mm, u x = ±5 sonda stěnu žebra dotýká
    assert best.clearance == pytest.approx(0, abs=1e-6)
    contact = Counter(c.state for c in gap_analysis.preparation.contact)
    assert contact["none"] > 0, "krajní polohy mezery musí vyjít jako problémové"
    text = "\n".join(gap_analysis.summary())
    assert UT_DISCLAIMER in text and ORDER_NOTE in text and NOT_FOUND_NOTE in text


@pytest.mark.parametrize("alternatives,found", [(False, False), (True, True)])
def test_rib_root_with_reserve_honestly_not_found_unless_other_angles(parts, alternatives,
                                                                      found):
    """Žebro, rezerva 5 mm: 45° potřebuje výstup ≥ 22 mm, půlkrok je jen 20 mm; mezní úhel
    47,7°, 60° dá 34,64 mm (docs/ndt/05-referencni-dily.md, díl 3)."""
    geo = parts["zebro"]
    analysis = Analysis(geo, Probe.angle(reserve=5), points=[(0.0, 0.0, 0.0)],
                        contact_faces=[face_at(geo.part, 50, 0, 20),
                                       face_at(geo.part, -50, 0, 20)],
                        options=AccessOptions(step_mm=20, bounces=(0,), direction_step_deg=90,
                                              angles=(
                            ALTERNATIVE_ANGLES if alternatives else ())))
    result = analysis.run()
    if not found:
        assert result.combination == [] and result.union is None
        assert all(r.covered == 0 for r in result.variants)
        assert "nic geometricky nepokryje" in "\n".join(result.summary()) or not result.variants
    else:
        best = result.variants[0]
        assert best.covered == 100 and best.variant.beta in (60.0, 70.0)
        assert "předpokládá úhel" in best.note.lower()
        assert all(r.variant.beta != 45 or r.covered == 0 for r in result.variants)


def test_nothing_found_is_said_honestly(parts, tmp_path):
    geo = parts["deska"]
    analysis = Analysis(geo, Probe.angle(length=250), faces=[face_at(geo.part, 0, 0, 0)],
                        options=AccessOptions(step_mm=20, bounces=(0,),
                                              direction_step_deg=90))
    result = analysis.run()
    assert result.variants == [] and result.combination == []
    kinds = Counter(r.kind for r in result.rejected)
    assert kinds["access"] > 0 or kinds["small"] > 0
    text = "\n".join(result.summary())
    assert "nenašel" in text and NOT_FOUND_NOTE in text
    csv = result.write_csv(tmp_path / "polohy.csv").read_text(encoding="utf-8-sig")
    assert UT_DISCLAIMER in csv and ORDER_NOTE in csv and "vyřazeno" in csv


@pytest.fixture(scope="module")
def weld():
    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "cilove_objemy" / "tupy_svar_objem.json")
    session.set_ndt_volume_target("s1", SLICE)
    session.set_ndt_device("s1", PROBE)
    geo = session._ndt_geometry()
    top = face_at(geo.part, 80, 0, 12)
    analysis = Analysis(geo, Probe.from_dict(PROBE), volume=SLICE, contact_faces=[top],
                        options=AccessOptions(step_mm=10, direction_step_deg=90))
    return geo, top, analysis.run()


def test_weld_prefers_full_skip_and_names_the_direction(weld):
    """Výřez V svaru, 70° zprava: bez odrazu jen kořen (vzorec 15,18 %), s odrazem skoro vše
    (99,91 % při kroku 5 mm i 10 mm, změřeno 18. 10. 2026)."""
    _, _, result = weld
    best = result.variants[0]
    assert best.variant.bounces == 1 and best.variant.direction == "k cíli (180°)"
    assert best.covered == pytest.approx(99.91, abs=0.05)
    direct = next(r for r in result.variants
                  if r.variant.bounces == 0 and r.variant.direction == "k cíli (180°)")
    assert direct.covered < 20
    assert result.combination[0] == 0 and result.combined >= best.covered
    assert "odraz" in best.note.lower()
    away = [r for r in result.rejected if r.direction.startswith("od cíle")]
    assert away, "směr od svaru musí být vyřazený s důvodem"


def test_weld_variant_recomputed_independently_gives_same_number(weld):
    geo, top, result = weld
    best = next(r for r in result.variants  # přímý paprsek: přepočet je nejlevnější
                if r.variant.bounces == 0 and r.variant.direction == "k cíli (180°)")
    face, at = find_face(geo.part, best.best_reference["face"])
    assert face.is_same(top)
    probe = Probe.from_dict({**PROBE, "bounces": best.variant.bounces})
    placed = place(geo, probe, (at.X, at.Y, at.Z), angle=best.variant.angle_deg, face=face)
    assert placed.ok
    again = compute_volume(geo, placed, target=SLICE, scan_step=10,
                           angle_deg=best.variant.angle_deg)
    assert again.states == best.coverage.states
    assert again.percent("covered") == pytest.approx(best.covered, abs=1e-9)


# --- ModelSession, pomocný proces a příkazová řádka (09A.2) -----------------------------

QUICK = {"step_mm": 40, "direction_step_deg": 90, "bounces": (0,), "angles": (60,)}


def rib_session(runner=None):
    """Deska se žebrem, studie s1 (cíl: dno), kontaktní plocha horní vpravo."""
    from skodacad.session import ModelSession

    session = ModelSession(runner)
    session.open(EXAMPLES / "ndt" / "zebro.json")
    if runner is not None:
        session.wait(120)
    contact = session.ndt_access_contact([face_at(session.result.part, 50, 0, 20).wrapped])
    return session, contact


@pytest.fixture(scope="module")
def rib():
    session, contact = rib_session()
    result = session.compute_ndt_access("s1", QUICK, contact)
    return session, contact, result


def test_session_analysis_is_a_view_and_keeps_through_variant_use(rib, tmp_path):
    session, _, result = rib
    assert session.ndt_access is result and not session.dirty
    assert result.preparation.assumptions["study_id"] == "s1"
    assert {r.variant.beta for r in result.variants} == {45.0, 60.0}
    rank_60 = next(i for i, r in enumerate(result.variants)
                   if r.variant.beta == 60 and r.best is not None)
    shown = session.show_ndt_access_variant(rank_60)
    assert shown.ok and shown.probe.beam_angle == 60 and session.ndt_probe_preview is not None
    assert session.ndt_probe("s1").beam_angle == 45 and not session.dirty  # jen pohled
    assert session.ndt_beam is not None
    session.apply_ndt_access_variant(rank_60)
    assert session.ndt_probe("s1").beam_angle == 60 and session.dirty
    assert session.ndt_probe_preview is None and session.ndt_placement.ok
    assert session.ndt_access is result, "úhel studie analýzu nezneplatní"
    text = session.export_ndt_access(tmp_path / "polohy.csv").read_text(encoding="utf-8-sig")
    assert UT_DISCLAIMER in text and ORDER_NOTE in text and "vyhodnoceno" in text
    session.undo()
    assert session.ndt_probe("s1").beam_angle == 45
    session.set_ndt_device("s1", Probe.angle(length=30))  # jiné rozměry = jiná přístupnost
    assert session.ndt_access is None


def test_session_estimate(rib):
    session, contact, _ = rib
    estimate = session.ndt_access_estimate("s1", QUICK, contact)
    assert estimate.ok and estimate.faces == 1 and "Odhad" in estimate.text


def test_session_rejects_non_ut_study(tmp_path):
    from skodacad import DocumentError
    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "koutovy_svar.json")  # studie PT
    with pytest.raises(DocumentError, match="UT studii"):
        session.ndt_access_estimate("s1")


@pytest.fixture(scope="module")
def runner():
    from skodacad.worker import BackgroundRebuilder

    rebuilder = BackgroundRebuilder()
    yield rebuilder
    rebuilder.close()


def test_background_analysis_streams_progress_and_matches_direct(rib, runner):
    _, _, direct = rib
    session, contact = rib_session(runner)
    assert session.start_ndt_access("s1", QUICK, contact) is None and session.access_pending
    seen, remaining = set(), []
    end = time.monotonic() + 300
    while session.computing and time.monotonic() < end:
        session.poll()
        seen.add(session.ndt_access_progress.split(":")[0])
        remaining.append(session.ndt_access_progress)
        time.sleep(0.05)
    assert not session.computing and not session.failure
    result = session.ndt_access
    assert result is not None and result.complete
    assert "1. a 2. kolo" in seen and "3. kolo" in seen
    assert any("zbývá asi" in text for text in remaining)
    assert [r.covered for r in result.variants] == [r.covered for r in direct.variants]


def test_background_stop_keeps_finished_variants(runner):
    session, contact = rib_session(runner)
    session.start_ndt_access("s1", QUICK, contact)
    end = time.monotonic() + 300
    while time.monotonic() < end:
        session.poll()
        if session._access_pending and session._access_pending["results"]:
            break
        time.sleep(0.05)
    assert session.cancel()
    result = session.ndt_access
    assert result is not None and not result.complete and result.variants
    assert "Neúplná analýza" in "\n".join(result.summary())
    assert not session.dirty


def test_cli_prints_summary_with_disclaimer(tmp_path, capsys):
    from skodacad.cli import main

    code = main(["polohy", str(EXAMPLES / "ndt" / "deska.json"), "--studie", "s1",
                 "--krok", "50", "--smery", "90", "--odrazy", "0",
                 "--csv", str(tmp_path / "polohy.csv")])
    out = capsys.readouterr()
    assert code == 0
    assert UT_DISCLAIMER in out.out and ORDER_NOTE in out.out and "Odhad" in out.err
    assert (tmp_path / "polohy.csv").exists()
    assert main(["polohy", str(EXAMPLES / "ndt" / "zebro.json"), "--studie", "s1",
                 "--odrazy", "x"]) == 2
