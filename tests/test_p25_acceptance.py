"""Doplněné případy přejímky P2.5, nezávislé na podobě dialogu."""

import copy

import pytest
from build123d import GeomType, Sphere

from conftest import EXAMPLES
from skodacad.direct_edit import DirectEditError, move_face, set_diameter
from skodacad.document import DocumentError
from skodacad.session import ModelSession


@pytest.mark.parametrize("operation", [move_face, set_diameter])
def test_q19_sphere_is_rejected_without_geometry_change(operation):
    part = Sphere(10)
    face = part.faces()[0]
    volume = part.volume
    with pytest.raises(DirectEditError, match="umí jen"):
        operation(part, face, face.position_at(0.5, 0.5), 2)
    assert part.is_valid and part.volume == pytest.approx(volume)


@pytest.mark.parametrize(("example", "geometry"), [("koleno", GeomType.TORUS),
                                                       ("vysypka", GeomType.BSPLINE)])
@pytest.mark.parametrize("kind", ["move_face", "face_diameter"])
def test_q19_sweep_and_loft_faces_are_rejected_in_preview(example, geometry, kind):
    session = ModelSession()
    session.open(EXAMPLES / f"{example}.json")
    original = copy.deepcopy(session.document)
    face = next(f for f in session.result.part.faces() if f.geom_type == geometry)
    with pytest.raises(DocumentError, match="rovinnou plochu"):
        session.preview_direct_edit(kind, [face], None, 2)
    assert session.document == original and session.result.ok
