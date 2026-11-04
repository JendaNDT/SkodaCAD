"""Bounded assembly presentation ownership, real AIS styles and model invalidation."""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QMessageBox

from test_assembly_gui import app as app
from test_assembly_gui import dialogs as dialogs
from test_assembly_gui import main_window as main_window
from test_assembly_gui import opened as opened
from test_assembly_gui import pick
from test_assembly_gui import project as project
from test_viewer_surface import viewer as viewer


def test_restore_reuses_full_ais_with_current_transparency_and_one_finished_frame(viewer):
    from build123d import Box, Compound, Location

    viewer._context = Mock()
    a = Box(10, 10, 10)
    b = a.moved(Location((30, 0, 0)))
    viewer.show_part(Compound([a, b]), transparent=[(a, .35)])
    full = viewer._ais
    assert viewer.retain_part()
    assert viewer._ais is None and viewer._retained_part[0] is full
    viewer._context.Erase.assert_called_with(full, False)
    viewer._context.Deactivate.assert_called_with(full)
    viewer._context.ClearSelected.assert_called_with(False)
    viewer.show_part(b)
    filtered = viewer._ais
    events = []
    viewer.selection_changed.connect(lambda shapes: events.append((shapes, viewer._ais)))
    viewer._view.reset_mock()
    assert viewer.restore_part(fit=True, transparent=[(b, .7)])
    assert viewer._ais is full and viewer._retained_part is None
    assert events == [([], full)] and viewer._view.Redraw.call_count == 1
    viewer._context.Remove.assert_called_with(filtered, False)
    assert viewer._context.Activate.call_count >= 2
    aspects = full.CustomAspectsMap()
    assert aspects.Find(a.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency() == 0
    amount = aspects.Find(b.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency()
    assert amount == pytest.approx(.7)
    assert len(Compound(full.Shape()).solids()) == 2
    assert Compound(full.Shape()).volume == pytest.approx(2000)


def test_retention_is_bounded_and_clear_preserves_the_current_part(viewer):
    from build123d import Box

    viewer._context = Mock()
    viewer.show_part(Box(10, 10, 10))
    first = viewer._ais
    viewer.retain_part()
    viewer.show_part(Box(20, 10, 10))
    second = viewer._ais
    viewer.retain_part()
    viewer._context.Remove.assert_called_with(first, False)
    assert viewer._retained_part[0] is second
    viewer.show_part(Box(30, 10, 10))
    current = viewer._ais
    viewer.clear_retained_part()
    assert viewer._retained_part is None and viewer._ais is current
    viewer._context.Remove.assert_called_with(second, False)
    assert not viewer.restore_part()


def test_pending_surface_does_not_retain_or_lose_its_request(viewer):
    from build123d import Box

    viewer._view = None
    part = Box(10, 10, 10)
    viewer.show_part(part, fit=True)
    pending = viewer._pending
    assert not viewer.retain_part() and not viewer.restore_part()
    assert viewer._pending is pending and pending[0] is part


@pytest.mark.parametrize("failure", ["invalid-appearance", "fit"])
def test_failed_restore_has_no_untracked_retained_ais(viewer, failure):
    from build123d import Box

    viewer._context = Mock()
    part = Box(10, 10, 10)
    viewer.show_part(part)
    full = viewer._ais
    viewer.retain_part()
    viewer.show_part(Box(20, 10, 10))
    current = viewer._ais
    if failure == "invalid-appearance":
        with pytest.raises(ValueError):
            viewer.restore_part(transparent=[(part, 2)])
        assert viewer._ais is current and viewer._retained_part[0] is full
    else:
        viewer._view.FitAll.side_effect = RuntimeError("fit failed")
        with pytest.raises(RuntimeError, match="fit failed"):
            viewer.restore_part(fit=True)
        assert viewer._ais is None and viewer._retained_part is None
        viewer._context.Remove.assert_called_with(full, False)
        assert viewer._redraw_depth == 0


def install_retention(viewer, monkeypatch):
    state = {"part": None, "retains": 0, "restores": 0, "clears": 0}

    def retain():
        assert state["part"] is None
        state["part"] = viewer.parts[-1][0]
        state["retains"] += 1
        return True

    def restore(fit=False, transparent=None):
        if state["part"] is None:
            return False
        part, state["part"] = state["part"], None
        state["restores"] += 1
        viewer.show_part(part, fit=fit, transparent=transparent)
        return True

    def clear():
        state["part"] = None
        state["clears"] += 1

    monkeypatch.setattr(viewer, "retain_part", retain, raising=False)
    monkeypatch.setattr(viewer, "restore_part", restore, raising=False)
    monkeypatch.setattr(viewer, "clear_retained_part", clear, raising=False)
    return state


def test_window_restores_same_full_geometry_after_multiple_filters(opened, monkeypatch):
    state = install_retention(opened.viewer, monkeypatch)
    full = opened.viewer.parts[-1][0]
    recipe = opened.session.assembly.to_dict()
    result = opened.session.result
    pick(opened, "vicko")
    opened.set_component_transparency(("vicko",), 35)
    opened.isolate_selected()
    pick(opened, "nozicka_1")
    opened.isolate_selected()
    opened.show_all()
    assert state["retains"] == state["restores"] == 1 and state["part"] is None
    assert opened.viewer.parts[-1][0] is full and len(full.solids()) == 6
    assert opened.session.result is result and opened.session.assembly.to_dict() == recipe
    assert opened.viewer.transparencies[0][1] == .35


def test_edit_and_undo_invalidate_retained_geometry_even_with_the_same_ids(opened, monkeypatch):
    state = install_retention(opened.viewer, monkeypatch)
    old = opened.viewer.parts[-1][0]
    pick(opened, "vicko")
    opened.isolate_selected()
    assert state["part"] is old
    opened.position_edits[0].setText("100")
    opened.apply_form()
    assert state["part"] is None and state["clears"] >= 1
    opened.show_all()
    moved = opened.viewer.parts[-1][0]
    assert moved is not old and moved.bounding_box().max.X > old.bounding_box().max.X + 50
    opened.isolate_selected()
    assert state["part"] is moved
    opened.undo()
    assert state["part"] is None
    opened.show_all()
    shown = opened.viewer.parts[-1][0]
    assert shown.bounding_box().max.X == pytest.approx(old.bounding_box().max.X)


def test_cancelled_close_preserves_retained_geometry_and_accepted_close_releases_it(
        opened, dialogs, monkeypatch):
    state = install_retention(opened.viewer, monkeypatch)
    pick(opened, "vicko")
    opened.isolate_selected()
    retained = state["part"]
    opened.session.dirty = True
    dialogs["question"] = QMessageBox.StandardButton.Cancel
    assert not opened.close()
    assert state["part"] is retained and state["clears"] == 0
    dialogs["question"] = QMessageBox.StandardButton.Discard
    assert opened.close()
    assert state["part"] is None and state["clears"] == 1
