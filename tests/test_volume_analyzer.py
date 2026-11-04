"""A complete volume check shares one fresh OCCT analysis with its subshape checks."""
import pytest
from build123d import Box, Compound, Pos, Shell, Solid
from OCP.BRepCheck import BRepCheck_Analyzer

from skodacad import geometry_validation as validation


def test_every_solid_is_checked_in_the_current_whole_shape_analysis(monkeypatch):
    constructed, checked = [], []

    class ObservedAnalyzer:
        def __init__(self, shape):
            constructed.append(shape)
            self.native = BRepCheck_Analyzer(shape)

        def SetParallel(self, value):  # noqa: N802 -- mirrors the OCCT API
            self.native.SetParallel(value)

        def IsValid(self, *shapes):  # noqa: N802 -- mirrors the OCCT API
            checked.append(shapes)
            return self.native.IsValid(*shapes)

    monkeypatch.setattr(validation, "BRepCheck_Analyzer", ObservedAnalyzer)
    part = Compound([Box(2, 3, 4), Pos(10, 0, 0)*Box(5, 6, 7)])
    facts = validation.inspect_volume(part)
    assert facts.solids == 2 and facts.volume == pytest.approx(234)
    assert len(constructed) == 1 and constructed[0].IsSame(part.wrapped)
    assert checked[0] == ()
    assert len(checked) == 3
    for solid in part.solids():
        assert any(args and args[0].IsSame(solid.wrapped) for args in checked)


def test_later_native_change_to_same_python_object_is_checked_again():
    part = Box(20, 30, 40)
    assert validation.inspect_volume(part).volume == pytest.approx(24000)
    open_solid = Solid(Shell([face for face in part.faces() if face.center().Z < 19]))
    part.wrapped = open_solid.wrapped
    with pytest.raises(validation.GeometryValidationError):
        validation.inspect_volume(part)


def test_subshape_rejection_is_not_replaced_by_only_the_whole_shape_result(monkeypatch):
    class RejectSubshape:
        def __init__(self, _shape):
            pass

        def SetParallel(self, _value):  # noqa: N802
            pass

        def IsValid(self, *shapes):  # noqa: N802
            return not shapes

    monkeypatch.setattr(validation, "BRepCheck_Analyzer", RejectSubshape)
    with pytest.raises(validation.GeometryValidationError, match="neplatnou objemovou složku"):
        validation.inspect_volume(Box(2, 3, 4))


def test_unavailable_subshape_analysis_fails_closed(monkeypatch):
    class BrokenAnalyzer:
        def __init__(self, _shape):
            raise RuntimeError("unavailable kernel analysis")

    monkeypatch.setattr(validation, "BRepCheck_Analyzer", BrokenAnalyzer)
    with pytest.raises(validation.GeometryValidationError, match="spolehlivě ověřit"):
        validation.inspect_volume(Box(2, 3, 4))
