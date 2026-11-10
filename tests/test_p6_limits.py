"""P6.16 – meze P6 zapsané testy (docs/p6-16-zaobleni-vice-hran-a-kruhy.md).

Drží zjištění průzkumu: víc nezávislých hran po sobě přesně, skořepina před zaoblením,
zaoblení na hotové skořepině a kruhový přechod se třemi skicami.
"""

from __future__ import annotations

import math

import pytest
from build123d import Box, GeomType, Pos, offset

from skodacad import variable_fillet as vf
from skodacad.document import Document
from skodacad.features import BuildContext, FeatureError, build_shell
from skodacad.rebuild import rebuild


def volume(part) -> float:
    return sum(solid.volume for solid in part.solids())


def removed(length: float, r1: float, r2: float) -> float:
    return (1 - math.pi / 4) * length / 3 * (r1 * r1 + r1 * r2 + r2 * r2)


BLOCK = Pos(0, 0, 10) * Box(60, 40, 20)  # svislé hrany v (±30, ±20), z od 0 do 20
CORNERS = [(30, 20), (-30, 20), (30, -20), (-30, -20)]


def round_edge(part, history, x, y, r1, r2):
    edge = next(e for e in part.edges()
                if e.geom_type == GeomType.LINE and abs(e.tangent_at(0.5).Z) > 1 - 1e-9
                and abs(e.center().X - x) < 1e-6 and abs(e.center().Y - y) < 1e-6)
    reference = vf.reference(part, edge, history)
    return vf.apply(part, edge, r1, r2, reference["direction"], False, reference["normals"])


def four_corners(r1=2.0, r2=6.0):
    part, history = BLOCK, [("telo", BLOCK)]
    for index, (x, y) in enumerate(CORNERS, start=1):
        part = round_edge(part, history, x, y, r1, r2)
        history.append((f"vf{index}", part))
    return part


def test_four_independent_vertical_edges_remove_exactly_four_times_the_formula():
    result = four_corners()
    assert volume(BLOCK) - volume(result) == pytest.approx(4 * removed(20, 2, 6), abs=1e-5)
    assert result.is_valid and len(result.solids()) == 1
    assert len(result.faces()) == len(BLOCK.faces()) + 4


def test_edges_whose_roundings_overlap_are_rejected():
    plate = Pos(0, 0, 10) * Box(11, 40, 20)
    history = [("telo", plate)]
    first = round_edge(plate, history, 5.5, 20, 6, 6)
    history.append(("vf1", first))
    with pytest.raises(vf.VariableFilletError):
        round_edge(first, history, -5.5, 20, 6, 6)


def test_edge_next_to_an_already_rounded_edge_at_a_shared_vertex_is_rejected():
    top_edge = next(e for e in BLOCK.edges()
                    if e.geom_type == GeomType.LINE and abs(e.center().Z - 20) < 1e-6
                    and abs(e.tangent_at(0.5).X) > 1 - 1e-9 and abs(e.center().Y - 20) < 1e-6)
    reference = vf.reference(BLOCK, top_edge, [("telo", BLOCK)])
    first = vf.apply(BLOCK, top_edge, 2, 6, reference["direction"], False, reference["normals"])
    with pytest.raises(vf.VariableFilletError, match="Oba konce hrany"):
        round_edge(first, [("telo", BLOCK), ("vf1", first)], 30, 20, 2, 6)


def test_shell_after_variable_rounding_is_rejected_so_shell_comes_first():
    rounded = four_corners()
    context = BuildContext(params={}, part=rounded)
    with pytest.raises(FeatureError, match="Skořepina"):
        build_shell(context, {"id": "s", "type": "shell", "thickness": 2,
                              "open_faces": ["top"]})


def test_rounding_on_a_finished_shell_fits_r6_but_not_r7():
    top = max(BLOCK.faces(), key=lambda f: f.center().Z)
    hollow = offset(BLOCK, amount=-2.0, openings=[top])
    history = [("telo", hollow)]
    result = round_edge(hollow, history, 30, 20, 2, 6)
    assert volume(hollow) - volume(result) == pytest.approx(removed(20, 2, 6), abs=1e-5)
    with pytest.raises(vf.VariableFilletError):
        round_edge(hollow, history, 30, 20, 2, 7)


def circle(number, z, diameter):
    return {"id": f"k{number}", "type": "sketch", "plane": "XY", "offset": z,
            "elements": [{"shape": "circle", "diameter": diameter}]}


def test_loft_of_three_circles_matches_the_analytic_rotation_body():
    # r(t) = 20 + 20·t·(1 − t) na výšce 60 mm: V = 60·π·∫ r(t)² dt = 32 800·π
    data = {"format": "skodacad", "version": 36, "name": "kruhy", "parameters": {},
            "features": [circle(1, 0, 40), circle(2, 30, 50), circle(3, 60, 40),
                         {"id": "l", "type": "loft", "sketches": ["k1", "k2", "k3"],
                          "wall_mode": "normal"}]}
    result = rebuild(Document.from_dict(data))
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert volume(result.part) == pytest.approx(32800 * math.pi, abs=1e-2)
    assert result.part.is_valid
