"""P7.57: skicář jako režim hlavního okna (rám 2d) – plátno místo 3D, paleta Skica,
vazby v levé kartě, karta Výběr, pilulka; Hotovo = jeden krok Zpět, Zrušit nic nemění."""

import copy
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QPointF, QTimer  # noqa: E402

from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.sketch_mode import applicable, selection_title  # noqa: E402
from test_gui import FakeViewer  # noqa: E402


@pytest.fixture
def plate(examples_dir, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = tmp_path / "deska.json"
    shutil.copy(examples_dir / "deska.json", model)
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert window.open_model(model)
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    yield window
    if window.feature_preview is not None:
        window.cancel_feature_preview()
    window.session.dirty = False
    window.close()


def in_mode(window, work):
    """Spustí ``work(mode)`` uvnitř běžícího režimu skicáře (okno čeká v jeho smyčce)."""
    seen = {}

    def run():
        mode = window._sketch_mode
        seen["mode"] = mode
        try:
            work(mode, seen)
        except Exception as exc:  # noqa: BLE001 – chyba se ukáže v testu, smyčka skončí
            seen["error"] = exc
            mode.dialog.reject()

    QTimer.singleShot(0, run)
    return seen


def draw_rectangle(dialog):
    dialog.set_tool("line")
    for x, y in ((0, 0), (40, 0), (40, 20), (0, 20), (0, 0)):
        dialog.click(x, y)
    dialog.finish_drawing()
    dialog.set_tool("select")


def test_new_sketch_runs_in_the_main_window_and_done_starts_preview(plate):
    w = plate
    before = {a: a.isEnabled() for a in (w.save_action, w.undo_action, w.section_action)}

    def work(mode, seen):
        dialog = mode.dialog
        seen["canvas"] = dialog.canvas.parent() is w.viewer and dialog.canvas.isVisible()
        seen["palettes"] = (w.sketch_palette_card.isVisible(), w.palette_card.isHidden(),
                            w.view_card.isHidden())
        seen["page"] = w.ribbon.page
        seen["locked"] = not w.save_action.isEnabled() and not w.section_action.isEnabled()
        seen["shortcuts"] = dialog.tool_actions["line"] in w.actions()
        seen["empty"] = w.status_pill.state.text()
        draw_rectangle(dialog)
        seen["list"] = w.sketch_group.isAncestorOf(dialog.constraint_list)
        seen["title"] = w.sketch_group_title.text()
        seen["pill"] = (w.status_pill.focus, w.status_pill.message)
        seen["heading"] = (w.workspace.heading("editor"), w.workspace.menu_buttons["editor"].text())
        mode.palette.done.click()

    seen = in_mode(w, work)
    w.profile_sketch_action.trigger()
    assert "error" not in seen, seen.get("error")
    assert seen["canvas"] and seen["palettes"] == (True, True, True) and seen["page"] == "sketch"
    assert seen["locked"] and seen["shortcuts"] and seen["empty"] == "Prázdná skica"
    assert seen["list"] and seen["title"].startswith("Vazby skici · ")
    assert seen["pill"][0][0] == "sketch" and seen["pill"][0][1].startswith("Zbývá určit: ")
    assert seen["pill"][1] == "Modrý obrys jde ještě táhnout myší"
    assert seen["heading"] == ("Bez výběru", "Výběr")
    # po Hotovo: náhled nové skici (P7.5), okno zpátky v 3D
    preview = w.feature_preview
    assert preview is not None and w._sketch_mode is None
    feature = preview.preview.session.feature(preview.preview.feature_id)
    assert feature["type"] == "sketch" and len(feature["elements"][0]["segments"]) == 4
    assert not seen["mode"].canvas.isVisible() and not w.sketch_palette_card.isVisible()
    assert not w.sketch_group.isVisible() and w.view_card.isVisible()
    assert w.status_pill.focus[0] == "preview"
    w.cancel_feature_preview()
    assert {a: a.isEnabled() for a in before} == before  # stav akcí obnoven


def test_cancel_leaves_model_and_history_unchanged(plate):
    w = plate
    document = copy.deepcopy(w.session.document.to_dict())
    history = len(w.session._undo)

    def work(mode, seen):
        draw_rectangle(mode.dialog)
        mode.palette.cancel.click()

    seen = in_mode(w, work)
    w.profile_sketch_action.trigger()
    assert "error" not in seen, seen.get("error")
    assert w.feature_preview is None and w._sketch_mode is None
    assert w.session.document.to_dict() == document and len(w.session._undo) == history
    assert w.palette_card.isVisible() and w.ribbon.page == "model"
    assert w.save_action.isEnabled() and w.status_pill.focus is None


def test_escape_ends_chain_then_clears_selection_and_panel_offers_constraints(plate):
    w = plate

    def work(mode, seen):
        dialog = mode.dialog
        dialog.set_tool("line")
        dialog.click(0, 0)
        dialog.click(30, 0)
        seen["chain"] = dialog.chain_start is not None
        mode.escape_action.trigger()  # 1. Esc: konec řetězu čar
        seen["after1"] = dialog.chain_start is None and dialog.tool == "line"
        dialog.set_tool("circle")
        dialog.click(50, 0)
        dialog.click(55, 0)
        dialog.set_tool("select")
        line = next(n for n, s in dialog.profile["segments"].items() if s["type"] == "line")
        circle = next(n for n, s in dialog.profile["segments"].items()
                      if s["type"] == "circle")
        dialog.select([line, circle])
        seen["title"] = w.workspace.heading("editor")
        seen["kinds"] = applicable(dialog)
        top = [k for k, b in mode.panel.top.items() if not b.isHidden()]
        seen["primary"] = mode.panel.top[top[0]].property("role") if top else None
        seen["top"] = top
        mode.panel.top["tangent"].click()  # skutečné tlačítko vazby
        seen["tangent"] = any(c["type"] == "tangent" for c in dialog.profile["constraints"])
        dialog.select([line])
        mode.escape_action.trigger()  # 2. Esc: zrušit výběr
        seen["cleared"] = dialog.selection == []
        mode.palette.cancel.click()

    seen = in_mode(w, work)
    w.profile_sketch_action.trigger()
    assert "error" not in seen, seen.get("error")
    assert seen["chain"] and seen["after1"]
    assert seen["title"] == "Úsečka a kružnice"
    assert seen["kinds"][0] == "tangent" and seen["top"][0] == "tangent"
    assert seen["primary"] == "primary" and seen["tangent"] and seen["cleared"]


def test_editing_existing_sketch_returns_to_its_preview(plate):
    w = plate
    sketch = w.session.document.features[0]
    w._selected_id = sketch["id"]
    w._reload_all()
    w.start_feature_edit()
    panel = w.feature_preview
    assert panel is not None and not w.ribbon.isEnabled()

    def work(mode, seen):
        seen["stack"] = w.editor_stack.currentWidget() is mode.panel
        mode.palette.done.click()

    seen = in_mode(w, work)
    profile = sketch["elements"][0] if sketch["elements"][0].get("shape") == "profile" else None
    if profile is None:  # obdélník desky – skicář dostane obrys nový
        from skodacad.profile_edit import empty_profile
        profile = empty_profile()
    result = panel.edit_profile(profile)
    assert "error" not in seen, seen.get("error")
    assert seen["stack"] and result is not None
    assert w.feature_preview is panel and w.editor_stack.currentWidget() is panel
    assert not w.ribbon.isEnabled() and w.status_pill.focus[0] == "preview"


def test_closing_the_window_in_sketch_mode_cancels_the_sketch_first(plate):
    w = plate

    def work(mode, seen):
        draw_rectangle(mode.dialog)
        seen["closed"] = w.close()

    seen = in_mode(w, work)
    w.profile_sketch_action.trigger()
    assert "error" not in seen, seen.get("error")
    assert seen["closed"] is False and w._sketch_mode is None and w.feature_preview is None


def test_selection_title_words():
    class Dialog:
        profile = {"points": {"P1": [0, 0], "P2": [1, 0]},
                   "segments": {"s1": {"type": "line"}, "s2": {"type": "line"},
                                "k1": {"type": "circle"}}, "constraints": []}
        selection: list = []

    dialog = Dialog()
    assert selection_title(dialog) == "Bez výběru"
    dialog.selection = ["s1", "s2"]
    assert selection_title(dialog) == "2 úsečky"
    dialog.selection = ["P1", "k1"]
    assert selection_title(dialog) == "Bod a kružnice"
    dialog.selection = ["s1", "P1", "P2"]
    assert selection_title(dialog) == "Úsečka a 2 body"


def test_sketch_view_switcher_fits_and_centers_the_origin(plate):
    """P7.71, rám 2d: vpravo dole „Kolmo na skicu | Celá skica“ místo pohledů 3D."""
    w = plate

    def work(mode, seen):
        dialog, canvas = mode.dialog, mode.dialog.canvas
        views = mode.views
        seen["card"] = (w.sketch_view_card.isVisible(), w.view_card.isHidden())
        seen["texts"] = [b.text() for b in views.buttons.values()]
        seen["active"] = views.active
        draw_rectangle(dialog)
        canvas.scale, canvas.center = 0.5, canvas.center + QPointF(500, 500)
        views.buttons["fit"].click()  # celý obrys do volného místa
        seen["fit"] = canvas.scale > 1
        views.buttons["normal"].click()  # počátek doprostřed volného místa
        left, top, right, bottom = canvas.margins
        free = ((left + canvas.width() - right) / 2, (top + canvas.height() - bottom) / 2)
        origin = canvas.to_screen(0, 0)
        seen["origin"] = (abs(origin.x() - free[0]) < 1, abs(origin.y() - free[1]) < 1)
        seen["inside"] = w.card_layer.cards and all(
            not c.geometry().intersects(w.sketch_view_card.geometry())
            for c in w.card_layer.cards if c.isVisible() and c is not w.sketch_view_card)
        mode.palette.cancel.click()

    seen = in_mode(w, work)
    w.profile_sketch_action.trigger()
    assert "error" not in seen, seen.get("error")
    assert seen["card"] == (True, True)
    assert seen["texts"] == ["Kolmo na skicu", "Celá skica"] and seen["active"] == "normal"
    assert seen["fit"] and seen["origin"] == (True, True) and seen["inside"]
    assert not w.sketch_view_card.isVisible() and w.view_card.isVisible()
