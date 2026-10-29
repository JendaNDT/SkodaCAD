"""P4.2: ortogonální projekce a řez v měřítku listu."""
import math

import pytest
from build123d import Align, Box, Compound, Cylinder, Edge, GeomType, Pos, Rot

from skodacad.drawing_geometry import (
    DrawingGeometryError,
    _remove_visible_from_hidden,
    project_section,
    project_view,
)


def box():
    return Box(40, 30, 20, align=(Align.MIN,) * 3)


def plate_with_offset_hole():
    return box() - Pos(7, 8, 0) * Cylinder(3, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))


def bounds(edges):
    box = Compound(children=list(edges)).bounding_box()
    return (box.min.X, box.min.Y, box.max.X, box.max.Y)


@pytest.mark.parametrize(("view", "expected"), [
    ("front", (0, 0, 40, 20)),
    ("top", (0, 0, 40, 30)),
    ("right", (0, 0, 30, 20)),
])
def test_box_orthographic_views_and_scale(view, expected):
    one = project_view(box(), view)
    half = project_view(box(), view, scale=0.5)
    assert bounds(one.visible) == pytest.approx(expected, abs=1e-6)
    assert bounds(half.visible) == pytest.approx(tuple(x * 0.5 for x in expected), abs=1e-6)
    assert not one.hidden  # zadní hrany kvádru splývají s viditelnými


def test_partially_overlapping_hidden_edge_keeps_only_uncovered_portion():
    visible = Edge.make_line((5, 0, 0), (15, 0, 0))
    hidden = Edge.make_line((0, 0, 0), (10, 0, 0))
    result = _remove_visible_from_hidden([visible], [hidden])
    assert len(result) == 1
    assert bounds(result) == pytest.approx((0, 0, 5, 0), abs=1e-6)


def test_asymmetric_hole_is_at_the_right_position_in_top_view():
    result = project_view(plate_with_offset_hole(), "top")
    circles = [edge for edge in result.visible if edge.geom_type == GeomType.CIRCLE]
    assert len(circles) == 1
    assert (circles[0].arc_center.X, circles[0].arc_center.Y) == pytest.approx((7, 8), abs=1e-6)
    assert circles[0].radius == pytest.approx(3, abs=1e-6)
    front = project_view(plate_with_offset_hole(), "front")
    # The hole axis is perpendicular to Z: its boundaries are hidden in the front view.
    verticals = [edge for edge in front.hidden if edge.geom_type == GeomType.LINE
                 and abs(edge.start_point().X - edge.end_point().X) < 1e-6
                 and abs(edge.length - 20) < 1e-6]
    assert any(abs(edge.start_point().X - 4) < 1e-6 for edge in verticals)
    assert any(abs(edge.start_point().X - 10) < 1e-6 for edge in verticals)


def test_section_shows_geometry_behind_plane_and_does_not_hatch_hole():
    result = project_section(plate_with_offset_hole(), "Y", 8, hatch_spacing_mm=3)
    assert bounds(result.visible) == pytest.approx((0, 0, 40, 20), abs=1e-6)
    assert result.hatching
    for line in result.hatching:
        start, end = line.start_point(), line.end_point()
        assert max(start.X, end.X) <= 4 + 1e-6 or min(start.X, end.X) >= 10 - 1e-6
    visible_verticals = [edge for edge in result.visible if edge.geom_type == GeomType.LINE
                         and abs(edge.start_point().X - edge.end_point().X) < 1e-6]
    assert any(abs(edge.start_point().X - 4) < 1e-6 for edge in visible_verticals)
    assert any(abs(edge.start_point().X - 10) < 1e-6 for edge in visible_verticals)


def recipe_part(*features):
    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    result = rebuild(Document(features=[
        {"id": "s", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": 100, "height": 60}]},
        {"id": "deska", "type": "extrude", "sketch": "s", "distance": 10}, *features]))
    assert result.ok
    return result.part


def plate_with_through_hole():
    # Deska z návrhu výkresu P4.1: 100 × 60 × 10, otvor Ø20 skrz, jako z okna aplikace.
    return recipe_part(
        {"id": "k", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "circle", "diameter": 20}]},
        {"id": "otvor", "type": "extrude", "sketch": "k", "operation": "cut",
         "through_all": True})


def straight_lines(edges):
    """Svislé úsečky jako (x, dolní y, horní y) a vodorovné jako (y, levé x, pravé x),
    zaokrouhlené na 1e-6 mm (+ 0.0 sjednotí -0.0)."""
    def mm(*values):
        return tuple(round(value, 6) + 0.0 for value in values)

    vertical, horizontal = [], []
    for edge in edges:
        if edge.geom_type != GeomType.LINE:
            continue
        a, b = edge.start_point(), edge.end_point()
        if abs(a.X - b.X) < 1e-6:
            vertical.append(mm(a.X, min(a.Y, b.Y), max(a.Y, b.Y)))
        elif abs(a.Y - b.Y) < 1e-6:
            horizontal.append(mm(a.Y, min(a.X, b.X), max(a.X, b.X)))
    return sorted(vertical), sorted(horizontal)


@pytest.mark.parametrize("view", ["front", "right"])
def test_hole_seam_is_not_drawn_as_a_hidden_edge(view):
    # Šev válcové plochy není hrana dílu: z boku má otvor jen dvě obrysové čáry,
    # nikoli třetí čáru v ose (dřív v pohledu zprava).
    result = project_view(plate_with_through_hole(), view)
    vertical, horizontal = straight_lines(result.hidden)
    assert len(result.hidden) == 2 and not horizontal
    assert vertical == [(-10, 0, 10), (10, 0, 10)]


def test_top_view_of_through_hole_has_circle_and_no_hidden_lines():
    result = project_view(plate_with_through_hole(), "top")
    assert not result.hidden
    circles = [edge for edge in result.visible if edge.geom_type == GeomType.CIRCLE]
    assert [edge.radius for edge in circles] == pytest.approx([10], abs=1e-6)


def test_pipe_seams_are_not_drawn():
    from pathlib import Path

    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    path = Path(__file__).parents[1] / "examples" / "ndt" / "trubka.json"
    result = project_view(rebuild(Document.load(path)).part, "front")
    vertical, horizontal = straight_lines(result.hidden)
    # Trubka 114,3 × 6 podél X: skrytá je jen vnitřní stěna (r = 51,15), švy ne.
    assert len(result.hidden) == 2 and not vertical
    assert horizontal == [(-51.15, -150, 150), (51.15, -150, 150)]


def test_tangent_edges_of_fillets_stay_visible():
    part = recipe_part({"id": "r", "type": "fillet", "edges": {"parallel": "Z"}, "radius": 5})
    vertical, _ = straight_lines(project_view(part, "front").visible)
    # Obrys zaoblení (±50) i tečné hrany mezi zaoblením a čelní plochou (±45).
    assert [line[0] for line in vertical] == pytest.approx([-50, -45, 45, 50], abs=1e-6)


def test_projection_does_not_change_edges_of_the_model_part():
    from OCP.BRep import BRep_Tool

    part = plate_with_through_hole()
    hole = next(face for face in part.faces() if face.geom_type == GeomType.CYLINDER)
    seam = next(edge for edge in hole.edges()
                if BRep_Tool.IsClosed_s(edge.wrapped, hole.wrapped))
    before = BRep_Tool.Continuity_s(seam.wrapped, hole.wrapped, hole.wrapped)
    project_view(part, "right")
    # Plynulost se zapisuje jen do kopie – 3D okno kreslí hrany původního dílu.
    assert BRep_Tool.Continuity_s(seam.wrapped, hole.wrapped, hole.wrapped) == before


def test_section_flipped_direction_and_sheet_scale():
    front = project_section(box(), "Y", 15)
    opposite = project_section(box(), "Y", 15, flipped=True)
    half = project_section(box(), "Y", 15, scale=0.5)
    assert bounds(front.visible) == pytest.approx((0, 0, 40, 20), abs=1e-6)
    assert bounds(opposite.visible) == pytest.approx((-40, 0, 0, 20), abs=1e-6)
    assert bounds(half.visible) == pytest.approx((0, 0, 20, 10), abs=1e-6)
    assert len(half.hatching) < len(front.hatching)  # paper spacing stays 3 mm
    for result in (front, half):
        offsets = sorted(line.start_point().Y - line.start_point().X for line in result.hatching)
        assert all(b - a == pytest.approx(3 * math.sqrt(2), abs=1e-6)
                   for a, b in zip(offsets, offsets[1:], strict=False))


def test_section_includes_step_of_hole_behind_the_cut():
    # Cut through a stepped bore: the smaller circle lies behind the section plane.
    big = Pos(10, 20, 10) * Rot(90, 0, 0) * Cylinder(
        3, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    small = Pos(10, 30, 10) * Rot(90, 0, 0) * Cylinder(
        1, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    result = project_section(box() - big - small, "Y", 15)
    circles = [edge for edge in result.visible if edge.geom_type == GeomType.CIRCLE]
    assert sorted(edge.radius for edge in circles) == pytest.approx([1, 3], abs=1e-6)
    assert all((edge.arc_center.X, edge.arc_center.Y) == pytest.approx((10, 10), abs=1e-6)
               for edge in circles)


def test_hatching_is_clipped_around_a_circular_hole():
    result = project_section(plate_with_offset_hole(), "Z", 10, hatch_spacing_mm=1)
    assert result.hatching
    for line in result.hatching:
        a, b = line.start_point(), line.end_point()
        dx, dy = b.X - a.X, b.Y - a.Y
        t = max(0.0, min(1.0, ((7 - a.X) * dx + (8 - a.Y) * dy) / (dx * dx + dy * dy)))
        distance = math.hypot(a.X + t * dx - 7, a.Y + t * dy - 8)
        assert distance >= 3 - 1e-6


@pytest.mark.parametrize("scale", [0, -1, math.inf, math.nan, True])
def test_invalid_scale_is_rejected(scale):
    with pytest.raises(DrawingGeometryError, match="Měřítko"):
        project_view(box(), "front", scale=scale)


def test_invalid_inputs_and_hatch_limit_are_reported():
    with pytest.raises(DrawingGeometryError, match="objemový díl"):
        project_view(None, "front")
    with pytest.raises(DrawingGeometryError, match="Neznámý pohled"):
        project_view(box(), "wrong")
    with pytest.raises(DrawingGeometryError, match="míjí"):
        project_section(box(), "Y", -20)
    with pytest.raises(DrawingGeometryError, match="Poloha"):
        project_section(box(), "Y", math.nan)
    with pytest.raises(DrawingGeometryError, match="příliš mnoho šraf"):
        project_section(box(), "Y", 15, hatch_spacing_mm=0.001)


def test_imported_step_part_can_be_projected():
    from pathlib import Path

    from skodacad.session import ModelSession

    source = Path(__file__).parent / "fixtures" / "step" / "07-metry.step"
    session = ModelSession()
    session.new_document()
    session.add_step_import(source.read_bytes(), source.name)
    assert session.result.ok
    projection = project_view(session.result.part, "top")
    assert bounds(projection.visible) == pytest.approx((0, 0, 10, 13), abs=1e-6)
