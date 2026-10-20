"""Plán dráhy UT sondy (etapa 10): ověřeno na referenčních dílech se změřeným nebo ručně
spočítaným výsledkem (docs/ndt/18-navrh-etapa-10.md, oddíl 8), ne existencí výsledku."""

import json
import math

import pytest
from build123d import Box, Pos

from conftest import EXAMPLES, face_at
from skodacad import Document, rebuild
from skodacad.ndt import UT_DISCLAIMER
from skodacad.ndt.coverage import PlanRegion, compute
from skodacad.ndt.devices import Probe, place
from skodacad.ndt.geometry import OVERLAP_TOL, PartGeometry
from skodacad.ndt.plan import (
    PLAN_NOTE,
    PassSpec,
    Plan,
    PlanError,
    Planner,
    PlanOptions,
    Zone,
    _overlap,
    strip_note,
    zones_from,
)
from skodacad.session import ModelSession
from test_ndt_volume_reference import PROBE, SLICE

# Výřez V svaru 10 mm, sonda 70° zprava bez odrazů, pojezd po celé horní pravé ploše krokem
# 5 mm: 14,7430 % (změřeno 18. 10. 2026; vzorec průřezu 15,18 %).
SLICE_FACE_PERCENT = 14.7430


def _route_points(planner, check, step=1.0):
    """Všechny body jízdy po povrchu (úseky a přesuny) po ``step`` mm."""
    points = []
    for item in check.steps:
        if item.kind == "air":
            continue
        length = math.dist(item.start, item.end)
        count = max(1, math.ceil(length / step))
        points += [tuple(a + (b - a) * k / count for a, b in zip(item.start, item.end,
                                                                strict=True))
                   for k in range(count + 1)]
    return points


# --- soubor a nastavení (bez geometrie) ---------------------------------------------------


def test_plan_and_zones_round_trip_and_reject_nonsense_in_czech():
    data = {"pattern": "auto", "row_step_mm": 5, "approach_mm": 20, "check_step_mm": 1,
            "passes": [{"face": {"at": [40, 0, 12], "normal": [0, 0, 1], "type": "plane"},
                        "angle_deg": 180, "beta": 70, "bounces": 0, "pattern": "toward",
                        "segments": [{"start": [37.5, -40, 12], "end": [22.1875, -40, 12]}]}],
            "part": "abc", "target": "def", "probe": "ghi", "edited": False}
    plan = Plan.from_dict(json.loads(json.dumps(data)))
    assert plan.to_dict() == data
    assert plan.segment_count == 1 and plan.passes[0].segments[0].length == pytest.approx(15.3125)
    zone = {"name": "štítek", "min": [60, -20, 12], "max": [90, 20, 20]}
    assert zones_from([zone])[0].to_dict() == zone and zones_from(None) == ()
    bad = [({**data, "row_step_mm": 0}, "rozteč"),
           ({**data, "colour": 1}, "neznámá položka"),
           ({**data, "passes": [{**data["passes"][0], "beta": 0.5}]}, "úhel β"),
           ({**data, "passes": [{**data["passes"][0], "segments": [{"start": [0, 0]}]}]},
            "úsek 1"),
           ({**data, "passes": [{**data["passes"][0], "face": {"at": [0, 0, 0]}}]}, "normal")]
    for broken, word in bad:
        with pytest.raises(PlanError, match=word):
            Plan.from_dict(broken)
    for broken, word in [({**zone, "max": [60, 20, 20]}, "větší"), ([1, 2], "objekt"),
                         ({**zone, "color": "red"}, "neznámá")]:
        with pytest.raises(PlanError, match=word):
            Zone.from_dict(broken)
    for options, word in [(PlanOptions(pattern="spiral"), "Vzor"),
                          (PlanOptions(row_step_mm=0.1), "Rozteč"),
                          (PlanOptions(check_step_mm=6), "Kontrolní krok nesmí"),
                          (PlanOptions(approach_mm=-1), "nájezdu")]:
        with pytest.raises(PlanError, match=word):
            options.checked()


def test_plan_mode_over_whole_face_equals_face_mode():
    """Režim ``plan`` s polohami mřížky plochy a pásem přes celou plochu = pojezd po ploše."""
    from skodacad.ndt.coverage import _scan_positions

    geo = PartGeometry(rebuild(Document.load(EXAMPLES / "ndt" / "deska.json")).part)
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    target = [face_at(geo.part, 0, 0, 0)]
    face = compute(geo, placed, faces=target, scan_step=40, target_step=40)
    positions = _scan_positions(placed, "face", 40, 0)
    everything = PlanRegion((((-1e4, 0, 20), (1, 0, 0), 2e4, (0, 1, 0), 1e4),))
    plan = compute(geo, placed, faces=target, mode="plan", scan_step=40, target_step=40,
                   positions=positions, region=everything)
    assert plan.states == face.states and plan.percent("covered") == face.percent("covered")
    nowhere = PlanRegion((((0, 0, 20), (1, 0, 0), 0.0, (0, 1, 0), 0.0),))
    narrow = compute(geo, placed, faces=target, mode="plan", scan_step=40, target_step=40,
                     positions=positions, region=nowhere)
    assert narrow.percent("covered") <= plan.percent("covered")


# --- výřez V svaru (rychlý referenční díl) ------------------------------------------------


@pytest.fixture(scope="module")
def weld():
    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "cilove_objemy" / "tupy_svar_objem.json")
    session.set_ndt_volume_target("s1", SLICE)
    geo = session._ndt_geometry()
    return geo, face_at(geo.part, 50, 0, 12), face_at(geo.part, -50, 0, 12)


def weld_plan(weld, zones=(), **options):
    geo, right, _ = weld
    planner = Planner(geo, Probe.from_dict(PROBE), volume=SLICE, zones=zones,
                      options=PlanOptions(pattern="toward", **options))
    return planner, planner.run([PassSpec(right, (40.0, 0.0, 12.0), 180.0, 70.0, 0)])


@pytest.fixture(scope="module")
def slice_plan(weld):
    return weld_plan(weld)


def test_weld_plan_covers_like_whole_face_and_starts_at_the_cap(slice_plan):
    """Plán bez zón = pojezd po celé ploše (14,743 %); úseky začínají u x = 22 mm, kde čelo
    sondy naráží na převýšení (dohledáno půlením na 0,5 mm), 0 přestavení."""
    _, result = slice_plan
    assert result.check.valid and result.check.lifts == 0
    assert result.coverage.covered == pytest.approx(SLICE_FACE_PERCENT, abs=1e-3)
    starts = [min(s.start[0], s.end[0]) for s in result.plan.passes[0].segments]
    assert all(22.0 - 1e-9 <= x <= 22.5 for x in starts)
    assert all(abs(s.start[1]) <= 40 + 1e-9 for s in result.plan.passes[0].segments)
    assert [d.pattern for d in result.drafts if d.chosen] == ["toward"]
    text = "\n".join(result.summary())
    for needed in (UT_DISCLAIMER, PLAN_NOTE, strip_note(5), "Plán platí", "Robustnost"):
        assert needed in text


def test_every_route_point_is_collision_free_and_recompute_is_identical(weld, slice_plan,
                                                                        tmp_path):
    """Podmínka dokončení etapy: každý bod trasy bez kolize (nezávislé přiložení po 1 mm,
    bez paměti plánovače) a pokrytí souhlasí s nezávislým přepočtem uloženého plánu."""
    geo, right, _ = weld
    planner, result = slice_plan
    fresh = PartGeometry(geo.part)
    probe = Probe.from_dict(PROBE)
    points = _route_points(planner, result.check)
    assert len(points) > 100
    assert all(place(fresh, probe, p, angle=180.0, face=right).ok for p in points)
    saved = Plan.from_dict(json.loads(json.dumps(result.plan.to_dict())))
    again = Planner(fresh, probe, volume=SLICE, options=PlanOptions.for_plan(saved))
    recomputed = again.evaluate(saved, [right])
    assert recomputed.coverage.coverage.states == result.coverage.coverage.states
    assert recomputed.coverage.covered == result.coverage.covered
    csv = result.write_csv(tmp_path / "plan.csv").read_text(encoding="utf-8-sig")
    assert UT_DISCLAIMER in csv and "boční rezerva" in csv
    assert csv.count("\n") > len(result.check.positions) + len(result.check.steps)
    # přehrávání: před první polohou nic, po poslední celé pokrytí
    assert "covered" not in result.coverage.until(-1)
    assert result.coverage.until(len(result.check.positions)) == result.coverage.coverage.states


def test_useless_segments_go_without_losing_coverage(weld, slice_plan):
    """Řádky y = ±10 mm míjejí výřez svaru (y ±5 mm) – síto dosahu je velkorysé, ale
    pokrytí ukáže, že nic nezasáhnou; po smazání vyjde totéž číslo s kratší dráhou."""
    from dataclasses import replace

    _, right, _ = weld
    planner, result = slice_plan
    hits = result.coverage.segment_hits(result.check)
    assert sum(hits.values()) == sum(f is not None for f in result.coverage.first_position)
    useless = result.useless_segments()
    assert useless and "bez přínosu" in "\n".join(result.summary())
    keep = [s for i, s in enumerate(result.plan.passes[0].segments) if (0, i) not in useless]
    pruned = replace(result.plan, passes=(replace(result.plan.passes[0], segments=tuple(keep)),))
    again = planner.evaluate(pruned, [right])
    assert again.coverage.covered == pytest.approx(result.coverage.covered, abs=1e-9)
    assert again.check.length("scan") < result.check.length("scan")
    assert not again.useless_segments()


def test_forbidden_zone_shortens_rows_and_route_never_enters_it(weld, slice_plan):
    """Upínka za sondou (x 58–62 mm): tělo sondy dlouhé 40 mm do ní vjede, když je výstupní
    bod dál než x = 30 mm – řádky skončí u 30 mm a žádný bod trasy zónu nezasáhne."""
    geo, right, _ = weld
    zone = Zone("upínka", (58.0, -1.0, 12.0), (62.0, 1.0, 40.0))
    planner, result = weld_plan(weld, zones=(zone,))
    assert result.check.valid
    ends = [max(s.start[0], s.end[0]) for s in result.plan.passes[0].segments]
    assert all(e <= 30.5 for e in ends), ends
    probe = Probe.from_dict(PROBE)
    solid = zone.solid()
    for point in _route_points(planner, result.check):
        placed = place(geo, probe, point, angle=180.0, face=right)
        assert placed.ok
        assert _overlap(placed.body.wrapped, solid.wrapped) <= OVERLAP_TOL
    assert result.coverage.covered <= slice_plan[1].coverage.covered + 1e-9


def test_two_passes_join_sample_by_sample_with_one_change(weld):
    """Zprava i zleva bez odrazu (etapa 09: obě strany 15,22 %): sjednocení vzorek po
    vzorku, mezi průchody jedno přestavení."""
    geo, right, left = weld
    planner = Planner(geo, Probe.from_dict(PROBE), volume=SLICE,
                      options=PlanOptions(pattern="along"))
    result = planner.run([PassSpec(right, (40.0, 0.0, 12.0), 180.0, 70.0, 0),
                          PassSpec(left, (-40.0, 0.0, 12.0), 0.0, 70.0, 0)])
    assert len(result.plan.passes) == 2 and result.check.pass_changes == 1
    assert [s.kind for s in result.check.steps].count("air") == 1
    assert result.coverage.covered == pytest.approx(15.22, abs=0.05)
    assert result.coverage.covered >= SLICE_FACE_PERCENT


# --- nájezd pod převisem a úzká mezera --------------------------------------------------


@pytest.fixture(scope="module")
def roof():
    """Deska 120 × 60 × 20 se střechou ve výšce 50 mm nad x ∈ ⟨−20; 40⟩: přímá sonda (25 mm)
    pod ni zajede, ale s nájezdem 20 mm se pod ní spustit ani zvednout nedá."""
    part = (Pos(0, 0, 10) * Box(120, 60, 20) + Pos(45, 0, 37.5) * Box(10, 60, 35)
            + Pos(15, 0, 52.5) * Box(70, 60, 5))
    geo = PartGeometry(part)
    points = [(x, 0.0, 10.0) for x in (-40.0, -30.0, -20.0, -10.0, 0.0)]
    return geo, face_at(part, 0, 0, 20), points


def roof_plan(roof, angle, approach):
    geo, top, points = roof
    planner = Planner(geo, Probe.straight(10), points=points,
                      options=PlanOptions(pattern="toward", approach_mm=approach))
    plan, faces, _, _ = planner.build([PassSpec(top, (-20.0, 0.0, 20.0), angle, 0.0, 0)])
    return planner, plan, planner.check(plan, faces, margins=False)


def test_under_roof_probe_is_lowered_outside_and_slides_in(roof):
    geo, top, _ = roof
    tall = Probe.straight(10, height=45)
    for angle in (180.0, 0.0):  # první úsek začíná pod střechou / poslední tam končí
        planner, plan, check = roof_plan(roof, angle, 20)
        assert check.valid, check.problems
        ends = [s for s in check.steps if s.kind == "air"]
        lowered = check.steps[0].start
        lifted = check.steps[-1].end
        for point in [lowered, lifted, *(s.start for s in ends), *(s.end for s in ends)]:
            assert point[0] < -20, point  # mimo střechu
            body = place(geo, tall, point, angle=angle, face=top).body
            assert _overlap(geo.part.wrapped, body.wrapped) <= OVERLAP_TOL
        assert any(s.kind == "slide" and s.length > 20 for s in check.steps)
    _, _, free = roof_plan(roof, 180.0, 0)
    assert free.valid and not any(s.kind == "slide" and s.length > 6 for s in free.steps)


def test_narrow_gap_route_only_along_and_in_the_middle_strip():
    """Obtížný přístup: sonda 40 × 20 v mezeře 30 mm se vejde jen podélně (vůle 10 mm)."""
    geo = PartGeometry(rebuild(Document.load(EXAMPLES / "ndt" / "pristup.json")).part)
    floor = face_at(geo.part, 0, 0, 15)
    probe = Probe.angle(beam_angle=45, bounces=0)
    planner = Planner(geo, probe, faces=[floor], options=PlanOptions(pattern="toward",
                                                                     row_step_mm=5))
    across, _, _, dropped = planner.build([PassSpec(floor, (0.0, 0.0, 15.0), 0.0, 45.0, 0)])
    assert not across.passes and "nevejde" in " ".join(dropped)
    along, faces, _, _ = planner.build([PassSpec(floor, (0.0, 0.0, 15.0), 90.0, 45.0, 0)])
    segments = along.passes[0].segments
    assert segments and all(abs(s.start[0]) <= 5 + 1e-6 and abs(s.end[0]) <= 5 + 1e-6
                            for s in segments)
    assert planner.check(along, faces, margins=False).valid


# --- soubor (formát 18), ModelSession, pomocný proces a příkazová řádka (10A.2) ---------

QUICK = {"row_step_mm": 20, "check_step_mm": 5}


def rib_session(runner=None):
    """Deska se žebrem: studie s1 (cíl dno), sonda přiložená na horní ploše vpravo ke žebru."""
    session = ModelSession(runner)
    session.open(EXAMPLES / "ndt" / "zebro.json")
    if runner is not None:
        session.wait(120)
    part = session.result.part
    session.place_ndt_probe("s1", [face_at(part, 50, 0, 20).wrapped], (50, 0, 20), 180)
    return session


@pytest.fixture(scope="module")
def rib():
    session = rib_session()
    return session, session.compute_ndt_plan("s1", options=QUICK)


def test_plan_is_stored_with_prints_and_recomputed_identically_after_reopening(rib, tmp_path):
    session, result = rib
    assert session.dirty and result.check.valid and result.coverage.covered > 0
    plan = session.ndt_plan("s1")
    assert plan == result.plan and not plan.edited
    assert {k: getattr(plan, k) for k in ("part", "target", "probe")} == \
        session._plan_prints("s1")
    assert session.ndt_plan_state("s1") == ("ok", "Plán platí.")
    path = session.save(tmp_path / "zebro.json")
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 22
    again = ModelSession()
    again.open(path)
    assert again.ndt_plan("s1") == plan
    assert again.ndt_plan_state("s1")[0] == "unchecked"
    checked = again.check_ndt_plan("s1", QUICK)
    assert checked.coverage.coverage.states == result.coverage.coverage.states
    assert again.ndt_plan_state("s1")[0] == "ok" and not again.dirty


def test_session_plays_positions_back_and_exports_csv(rib, tmp_path):
    session, result = rib
    placed = session.show_ndt_plan_position(len(result.check.positions) - 1)
    assert placed.ok
    assert placed.origin == pytest.approx(result.check.positions[-1].point, abs=1e-6)
    text = session.export_ndt_plan(tmp_path / "plan.csv").read_text(encoding="utf-8-sig")
    assert UT_DISCLAIMER in text and PLAN_NOTE in text


def test_changed_part_makes_plan_stale_until_confirmed_and_edits_undo(rib):
    """Mění sdílené sezení (díl, plán) – musí běžet po testech, které ho jen čtou."""
    session, result = rib
    session.set_parameter("A", "220")  # delší deska: plán se sám neposune
    state, text = session.ndt_plan_state("s1")
    assert state == "stale" and "díl" in text
    session.confirm_ndt_study("s1")  # studie napřed (jako u návrhu poloh), plán zvlášť
    assert session.ndt_plan_state("s1")[0] == "stale"
    session.check_ndt_plan("s1", QUICK, coverage=False, confirm=True)
    assert session.ndt_plan_state("s1")[0] == "ok"
    before = session.ndt_plan("s1")
    first = before.passes[0].segments[0]
    session.reverse_ndt_plan_segment("s1", 0, 0)
    reversed_plan = session.ndt_plan("s1")
    assert reversed_plan.edited and reversed_plan.passes[0].segments[0] == first.reversed()
    assert session.ndt_plan_state("s1")[0] == "unchecked"
    session.remove_ndt_plan_segment("s1", 0, 1)
    assert len(session.ndt_plan("s1").passes[0].segments) == len(before.passes[0].segments) - 1
    session.undo()
    session.undo()
    assert session.ndt_plan("s1") == before
    with pytest.raises(Exception, match="Nejdřív plán ověř"):  # bez spočítaného pokrytí
        session.remove_ndt_useless_segments("s1")
    with pytest.raises(Exception, match="nemá úsek 99"):
        session.remove_ndt_plan_segment("s1", 0, 98)
    with pytest.raises(Exception, match="na kraji"):
        session.move_ndt_plan_segment("s1", 0, 0, -1)
    session.set_ndt_plan_segment("s1", 0, 0, first.start, first.start)  # jedna poloha
    assert session.ndt_plan("s1").passes[0].segments[0].length == 0
    session.add_ndt_plan_segment("s1", 10)
    assert session.ndt_plan("s1").passes[0].segments[-1].length == pytest.approx(10)
    session.remove_ndt_plan("s1")
    assert session.ndt_plan("s1") is None and session.ndt_plan_state("s1")[0] == "none"


def test_zones_are_checked_saved_and_block_the_plan(tmp_path):
    session = rib_session()
    with pytest.raises(Exception, match="větší než „min“"):
        session.set_ndt_zones("s1", [{"name": "chyba", "min": [0, 0, 0], "max": [0, 1, 1]}])
    result = session.compute_ndt_plan("s1", options=QUICK)
    segment = result.plan.passes[0].segments[0]
    middle = tuple((a + b) / 2 for a, b in zip(segment.start, segment.end, strict=True))
    zone = {"name": "štítek", "min": [middle[0] - 2, middle[1] - 2, 20],
            "max": [middle[0] + 2, middle[1] + 2, 22]}
    assert session.ndt_placement_zone == ""
    session.set_ndt_zones("s1", [zone])
    assert session.ndt_zones("s1")[0].to_dict() == zone
    part = session.result.part
    session.place_ndt_probe("s1", [face_at(part, *middle).wrapped], middle, 180)
    assert "zakázané zóny „štítek“" in session.ndt_placement_zone  # jen upozorní
    assert session.ndt_placement.ok
    checked = session.check_ndt_plan("s1", coverage=False)
    assert not checked.check.valid and "v zakázané zóně" in " ".join(checked.check.problems)
    assert session.ndt_plan_state("s1")[0] == "invalid"
    data = session.document.to_dict()
    data["ndt"]["studies"][0]["plan"]["row_step_mm"] = -1
    with pytest.raises(Exception, match="rozteč"):
        Document.from_dict(data)


@pytest.fixture(scope="module")
def runner():
    from skodacad.worker import BackgroundRebuilder

    rebuilder = BackgroundRebuilder()
    yield rebuilder
    rebuilder.close()


def test_background_build_stores_plan_and_check_matches(rib, runner):
    import time

    _, direct = rib
    session = rib_session(runner)
    assert session.start_ndt_plan("s1", options=QUICK) is None and session.plan_pending
    seen = set()
    end = time.monotonic() + 300
    while session.computing and time.monotonic() < end:
        session.poll()
        seen.add(session.ndt_plan_progress)
        time.sleep(0.05)
    assert not session.failure, session.failure
    assert session.ndt_plan("s1").passes == direct.plan.passes
    assert any(text.startswith("Kontrola dráhy") for text in seen)
    session.wait(120)  # přepočet po uložení plánu do studie
    assert session.start_ndt_plan_check("s1", QUICK) is None
    assert session.wait(300) and not session.failure
    assert session.ndt_plan_result.coverage.covered == direct.coverage.covered


def test_cli_plans_saves_and_rechecks(tmp_path, capsys):
    import shutil

    from skodacad.cli import main

    model = tmp_path / "deska.json"
    shutil.copy(EXAMPLES / "ndt" / "deska.json", model)
    code = main(["draha", str(model), "--studie", "s1", "--plocha", "0,0,20",
                 "--roztec", "40", "--kontrola", "5", "--zona=-100,-60,20:-80,60,40",
                 "--ulozit", "--csv", str(tmp_path / "plan.csv")])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert UT_DISCLAIMER in out.out and PLAN_NOTE in out.out and "Odhad" in out.err
    saved = json.loads(model.read_text(encoding="utf-8"))["ndt"]["studies"][0]
    assert saved["plan"]["passes"] and saved["zones"][0]["min"] == [-100, -60, 20]
    assert (tmp_path / "plan.csv").exists()
    assert main(["draha", str(model), "--studie", "s1", "--prepocet", "--kontrola", "5"]) == 0
    assert "Plán platí" in capsys.readouterr().out
    assert main(["draha", str(model), "--studie", "s1"]) == 2
    assert "Zadej, odkud plánovat" in capsys.readouterr().err
