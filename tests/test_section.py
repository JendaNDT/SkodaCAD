"""Řez modelem: zbylý objem, obsah plochy řezu podle vzorců, rovina z plochy, 2D export."""

import math

import pytest

from conftest import box_features, face_at, make_doc
from skodacad import Document, rebuild
from skodacad.section import (
    SectionError,
    axis_plane,
    axis_range,
    cut,
    depth_range,
    describe,
    export_2d,
    face_plane,
    keep_triangles,
)


def plate_with_hole():
    """Deska 40 × 30 × 10 (z = 0 … 10) s průchozí dírou Ø8 uprostřed."""
    result = rebuild(make_doc(box_features(40, 30, 10) + [
        {"id": "ds", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 8}]},
        {"id": "d", "type": "extrude", "sketch": "ds", "operation": "cut", "through_all": True},
    ]))
    assert result.ok
    return result.part


def test_cut_through_hole_centre_keeps_half_and_shows_ligaments():
    part = plate_with_hole()
    section = cut(part, axis_plane("Y", 0))  # řez XZ středem díry, zbude zadní polovina
    assert section.part.is_valid
    assert section.part.volume == pytest.approx(part.volume / 2)
    assert section.area == pytest.approx((40 - 8) * 10)  # dva můstky vedle díry
    assert len(section.faces) == 2
    assert all(face.normal_at().Y == pytest.approx(-1) for face in section.faces)
    assert min(v.Y for v in section.part.vertices()) == pytest.approx(0)
    flipped = cut(part, axis_plane("Y", 0, flipped=True))  # zbude přední polovina
    assert max(v.Y for v in flipped.part.vertices()) == pytest.approx(0)
    assert describe(section.plane) == "Y = 0.00 mm"
    assert axis_range(part, "Z") == pytest.approx((0, 10), abs=1e-6)


def test_cut_beside_hole_and_horizontal_cut():
    part = plate_with_hole()
    beside = cut(part, axis_plane("X", 10))  # kolmo na X mimo díru: celý průřez 30 × 10
    assert beside.area == pytest.approx(30 * 10)
    assert beside.part.volume == pytest.approx((40 * 30 - math.pi * 16) * 10 - 10 * 30 * 10)
    level = cut(part, axis_plane("Z", 4))  # vodorovně: deska bez díry, zbude spodek 4 mm
    assert level.area == pytest.approx(40 * 30 - math.pi * 16)
    assert level.part.volume == pytest.approx((40 * 30 - math.pi * 16) * 4)


def test_cut_parallel_to_a_face_goes_into_the_depth():
    part = plate_with_hole()
    top = face_at(part, 15, 10, 10)
    assert depth_range(part, top) == pytest.approx((0, 10))
    section = cut(part, face_plane(top, 3))  # 3 mm pod horní plochou
    assert section.part.volume == pytest.approx((40 * 30 - math.pi * 16) * 7)
    assert section.area == pytest.approx(40 * 30 - math.pi * 16)
    layer = cut(part, face_plane(top, 3, flipped=True))  # zbude jen vrchní vrstva 3 mm
    assert layer.part.volume == pytest.approx((40 * 30 - math.pi * 16) * 3)
    with pytest.raises(SectionError, match="zakřivená"):
        face_plane(face_at(part, 4, 0, 5), 1)  # stěna díry


def test_plane_missing_the_part_and_no_part_are_czech():
    part = plate_with_hole()
    with pytest.raises(SectionError, match="míjí"):
        cut(part, axis_plane("Z", 50))
    with pytest.raises(SectionError, match="odřízla celý díl"):
        cut(part, axis_plane("Z", -5))
    with pytest.raises(SectionError, match="nemá těleso"):
        cut(None, axis_plane("Z", 0))
    with pytest.raises(SectionError, match="Neznámá osa"):
        axis_plane("W", 0)


def test_pipe_example_section_through_the_pit(examples_dir):
    part = rebuild(Document.load(examples_dir / "trubka.json")).part
    lengthwise = cut(part, axis_plane("Z", 0))  # podélně mimo jamku: 2 stěny 6 × 300
    assert lengthwise.area == pytest.approx(2 * 6 * 300)
    through_pit = cut(part, axis_plane("Y", 0))  # svisle přes jamku Ø20 hloubky 3,5
    assert through_pit.area == pytest.approx(2 * 6 * 300 - 20 * 3.5, rel=1e-6)


def test_export_section_as_dxf_and_svg(tmp_path):
    import ezdxf
    from ezdxf import bbox

    section = cut(plate_with_hole(), axis_plane("Y", 0))
    dxf = export_2d(section, tmp_path / "rez.dxf")
    extents = bbox.extents(ezdxf.readfile(dxf).modelspace())
    # pohled na řez z přední strany: vodorovně X (−20 … 20), svisle Z (0 … 10)
    assert (extents.extmin.x, extents.extmin.y) == pytest.approx((-20, 0), abs=1e-6)
    assert (extents.extmax.x, extents.extmax.y) == pytest.approx((20, 10), abs=1e-6)
    svg = export_2d(section, tmp_path / "rez.svg").read_text(encoding="utf-8")
    assert "<svg" in svg and "path" in svg
    with pytest.raises(SectionError, match=r"\.dxf nebo \.svg"):
        export_2d(section, tmp_path / "rez.pdf")


def test_map_triangles_on_the_kept_side():
    nodes = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 5), (1, 0, 5), (0, 1, 5)]
    triangles = [(0, 1, 2), (3, 4, 5)]
    assert keep_triangles(nodes, triangles, axis_plane("Z", 2)) == [(0, 1, 2)]
    assert keep_triangles(nodes, triangles, axis_plane("Z", 2, flipped=True)) == [(3, 4, 5)]


# --- řez v ModelSession: jen pohled, výběr z rozříznutého dílu funguje na celém dílu -------


def plate_session():
    from skodacad.session import ModelSession

    session = ModelSession()
    session.document = make_doc(box_features(40, 30, 10) + [
        {"id": "ds", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 8}]},
        {"id": "d", "type": "extrude", "sketch": "ds", "operation": "cut", "through_all": True},
    ], {})
    session.rebuild()
    return session


def test_session_section_is_only_a_view(tmp_path):
    from skodacad.document import DocumentError

    session = plate_session()
    full = session.result.part
    assert session.display_part is full and session.section is None
    before = session.document.to_dict()
    section = session.set_section_axis("Y")  # bez polohy: uprostřed dílu
    assert session.section_range() == pytest.approx((-15, 15), abs=1e-6)
    assert section.area == pytest.approx((40 - 8) * 10)
    assert session.display_part is section.part
    assert session.document.to_dict() == before and not session.dirty  # model beze změny
    session.set_section_position(10)  # mimo díru, zbude zadní pruh y > 10
    assert session.section.area == pytest.approx(40 * 10)
    assert session.section.part.volume == pytest.approx(40 * 5 * 10)
    session.flip_section()  # zbude přední část y < 10
    assert session.section.part.volume == pytest.approx(full.volume - 40 * 5 * 10)
    session.set_section_position(99)
    assert session.section is None and "míjí" in session.section_error
    assert session.display_part is full  # při chybě ukázat celý díl
    with pytest.raises(DocumentError, match="míjí"):
        session.export_section(tmp_path / "rez.dxf")
    session.set_section_position(0)
    assert session.export_section(tmp_path / "rez.svg").exists()
    session.clear_section()
    assert session.display_part is full and session.section is None


def test_section_parallel_to_clicked_face():
    from skodacad.document import DocumentError

    session = plate_session()
    top = face_at(session.result.part, 15, 10, 10)
    section = session.set_section_face([top.wrapped], (15, 10, 10))
    assert session.section_range() == pytest.approx((0, 10))
    assert section.part.volume == pytest.approx((40 * 30 - math.pi * 16) * 5)  # v půlce
    with pytest.raises(DocumentError, match="zakřivená"):
        session.set_section_face([face_at(session.result.part, 4, 0, 5).wrapped])
    with pytest.raises(DocumentError, match="právě jednu"):
        session.set_section_face([])


def test_selection_on_cut_part_works_on_the_whole_part():
    from skodacad.document import DocumentError

    session = plate_session()
    session.set_section_axis("Y", 0)
    cut_part = session.display_part
    edge = min(cut_part.edges(), key=lambda e: e.distance_to((0, 15, 10)))  # zadní horní
    fillet = session.add_from_selection("fillet", [edge.wrapped])
    assert session.feature(fillet)["edges"] == {"between": ["top", "back"]}
    assert session.result.ok  # zaoblení se postavilo na celém díle
    mid = session.add_measurement([face_at(session.display_part, 15, 10, 0).wrapped],
                                  "thickness", (15, 10, 0))
    assert [m.value.value for m in session.measurements if m.id == mid] == [pytest.approx(10)]
    on_cut = face_at(session.display_part, 15, 0, 5)  # plocha řezu (vznikla jen řezem)
    with pytest.raises(DocumentError, match="vznikla jen řezem"):
        session.add_from_selection("sketch", [on_cut.wrapped], (15, 0, 5))
    # měřit na ploše řezu jde (jen uložit ne): tloušťka od řezu dozadu přes celou desku
    values = session.measure_selection([on_cut.wrapped], (15, 0, 5))
    assert values[0].kind == "thickness" and values[0].value == pytest.approx(15)
