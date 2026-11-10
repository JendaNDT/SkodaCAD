"""P7.81 – krátký popis hran „obvod horní plochy“ (docs/p7-81-obvod-plochy.md)."""

from __future__ import annotations

import pytest
from build123d import Box, Cylinder, Pos, fillet

from skodacad.selectors import outline_name

BOX = Pos(0, 0, 10) * Box(40, 30, 20)  # z od 0 do 20


def edges_at(part, **where):
    axis, value = next(iter(where.items()))
    return [e for e in part.edges() if abs(getattr(e.center(), axis) - value) < 1e-6]


@pytest.mark.parametrize("where,expected", [
    ({"Z": 20}, "obvod horní plochy"),
    ({"Z": 0}, "obvod spodní plochy"),
    ({"Y": -15}, "obvod přední plochy"),
    ({"Y": 15}, "obvod zadní plochy"),
    ({"X": 20}, "obvod pravé plochy"),
    ({"X": -20}, "obvod levé plochy"),
])
def test_box_face_outlines_are_named_by_direction(where, expected):
    assert outline_name(BOX, edges_at(BOX, **where)) == expected


def test_outline_of_a_rounded_plate_includes_the_arcs():
    rounded = fillet([e for e in BOX.edges() if abs(e.tangent_at(0.5).Z) > 0.99], 4)
    top = edges_at(rounded, Z=20)
    assert len(top) == 8 and outline_name(rounded, top) == "obvod horní plochy"


def test_edges_of_a_face_with_a_hole_are_named_all_edges_unless_only_the_outline_is_selected():
    holed = BOX - Pos(0, 0, 20) * Cylinder(3, 40)
    top = edges_at(holed, Z=20)
    assert len(top) == 5
    assert outline_name(holed, top) == "všechny hrany horní plochy"
    assert outline_name(holed, [e for e in top if e.geom_type.name == "LINE"]) \
        == "obvod horní plochy"


def test_part_of_an_outline_or_no_edges_has_no_short_name():
    top = edges_at(BOX, Z=20)
    assert outline_name(BOX, top[:3]) is None
    assert outline_name(BOX, []) is None
    assert outline_name(BOX, top + edges_at(BOX, Z=0)) is None
