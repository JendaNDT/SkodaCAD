"""Skicář v okně (offscreen): kreslení klikáním, vazby, kóty, oblouk, mazání, Zpět."""

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QDialog, QInputDialog  # noqa: E402

from skodacad.gui.sketcher import SketcherDialog  # noqa: E402
from skodacad.profile_edit import empty_profile  # noqa: E402
from skodacad.session import ModelSession  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session():
    s = ModelSession()
    s.new_document()
    s.add_parameter("sirka", "50")
    return s


@pytest.fixture
def sketcher(app, session):
    dialog = SketcherDialog(empty_profile(), session.solve_profile)
    yield dialog
    dialog.deleteLater()


@pytest.fixture
def answers(monkeypatch):
    """Odpovědi do okénka „Kóta“ (jinak by test čekal na uživatele)."""
    queue = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (queue.pop(0), True))
    return queue


def draw_rectangle(d):
    """Obdélník klikáním: začátek v počátku, body schválně nepřesně."""
    d.set_tool("line")
    for x, y in ((0, 0), (40, 0.4), (40.3, 30), (0.2, 30.2)):
        d.click(x, y)
    d.click(0, 0)  # zpět na první bod = uzavřeno


def test_drawing_rectangle_adds_automatic_constraints(sketcher):
    draw_rectangle(sketcher)
    profile = sketcher.result_profile()
    assert len(profile["segments"]) == 4 and len(profile["points"]) == 4
    kinds = sorted(c["type"] for c in profile["constraints"])
    assert kinds == ["coincident", "horizontal", "horizontal", "vertical", "vertical"]
    assert sketcher.chain_start is None  # uzavřením kreslení skončilo
    assert sketcher.solution.ok and sketcher.solution.dof == 2  # chybí šířka a výška
    assert "Zbývá určit 2 rozměry" in sketcher.status.text()


def test_dimensions_with_parameter_make_it_fully_defined(sketcher, answers):
    draw_rectangle(sketcher)
    answers += ["sirka", "25,5"]
    sketcher.set_tool("select")
    sketcher.click(20, 0.2)  # spodní úsečka
    assert sketcher.selection == ["s1"]
    sketcher.add_dimension()
    sketcher.click(50, 15)  # pravá úsečka – po kótě sirka = 50 je už na x = 50
    assert sketcher.selection == ["s2"]
    sketcher.add_dimension()
    assert sketcher.solution.dof == 0
    assert "plně určený" in sketcher.status.text()
    points = sketcher.result_profile()["points"]
    assert points["P2"] == pytest.approx([50, 0])  # sirka = 50
    assert points["P3"] == pytest.approx([50, 25.5])
    texts = [sketcher.constraint_list.item(i).text()
             for i in range(sketcher.constraint_list.count())]
    assert "vazba 6 (délka s1 = sirka)" in texts and "vazba 7 (délka s2 = 25.5)" in texts


def test_arc_by_three_clicks(sketcher):
    sketcher.set_tool("arc")
    for xy in ((10, 0), (-10, 0), (0, 10)):
        sketcher.click(*xy)
    profile = sketcher.result_profile()
    [arc] = profile["segments"].values()
    assert arc["type"] == "arc"
    center = profile["points"][arc["center"]]
    assert center == pytest.approx([0, 0], abs=1e-6)
    # Horní půlkruh zprava doleva = proti směru hodin, začátek vpravo.
    assert profile["points"][arc["start"]] == pytest.approx([10, 0])


def test_constraint_buttons_need_right_selection(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    sketcher.click(20, 0.2)
    sketcher.constraint_actions["perpendicular"].trigger()  # jen jedna úsečka
    assert "dvě úsečky" in sketcher.status.text()
    sketcher.click(40.1, 15, ctrl=True)
    assert sketcher.selection == ["s1", "s2"]
    sketcher.constraint_actions["perpendicular"].trigger()
    assert sketcher.result_profile()["constraints"][-1] == {
        "type": "perpendicular", "segments": ["s1", "s2"]}


def test_conflict_is_red_and_undo_fixes_it(sketcher, answers):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    answers += ["40", "55"]  # protější strany obdélníku nemůžou mít různou délku
    sketcher.click(20, 0.2)
    sketcher.add_dimension()
    sketcher.click(20, 30)
    sketcher.add_dimension()
    assert not sketcher.solution.ok
    assert "odporují" in sketcher.status.text()
    failed = [i for i in range(sketcher.constraint_list.count())
              if sketcher.constraint_list.item(i).foreground().color().name() == "#c0392b"]
    assert failed
    sketcher.undo_action.trigger()
    assert sketcher.solution.ok


def test_collapsed_line_is_reported(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    sketcher.click(20, 0.2)
    sketcher.constraint_actions["vertical"].trigger()  # vodorovná i svislá = bod
    assert "nulovou délku" in sketcher.status.text()


def test_delete_point_and_undo(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    sketcher.click(40, 30)  # pravý horní roh
    assert sketcher.selection == ["P3"]
    sketcher.delete_action.trigger()
    assert set(sketcher.profile["segments"]) == {"s1", "s4"}
    assert "není uzavřený" in sketcher.status.text()
    sketcher.undo()
    assert len(sketcher.profile["segments"]) == 4


def test_drag_point_moves_free_geometry(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    sketcher.press(40, 30)
    sketcher.move(60, 45)
    sketcher.release(60, 45)
    points = sketcher.profile["points"]
    assert points["P3"] == pytest.approx([60, 45])
    assert points["P2"] == pytest.approx([60, 0])  # svislá pravá strana jde s ním
    assert sketcher.solution.ok


def test_construction_line_and_escape_does_not_close(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("line")
    sketcher.click(0, 0)
    sketcher.click(40, 30)  # úhlopříčka z rohu do rohu
    sketcher.set_tool("select")
    sketcher.click(20, 15)
    sketcher.construction_action.trigger()
    assert sketcher.profile["segments"]["s5"]["construction"] is True
    assert "není uzavřený" not in sketcher.status.text()
    sketcher.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                     Qt.KeyboardModifier.NoModifier))
    assert sketcher.result() == 0 and sketcher.selection == []


# --- napojení na hlavní okno -----------------------------------------------------------


@pytest.fixture
def window(app, examples_dir, tmp_path, monkeypatch):
    from skodacad.gui.main_window import MainWindow
    from test_gui import FakeViewer

    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    w.new_model()
    yield w
    w.session.dirty = False
    w.close()


def test_new_sketch_from_sketcher_then_extrude(window, monkeypatch, answers):
    def draw(self, dialog):
        draw_rectangle(dialog)
        answers.extend(["30", "20"])
        dialog.set_tool("select")
        dialog.click(20, 0.2)
        dialog.add_dimension()
        dialog.click(30, 15)  # pravá strana je po kótě 30 na x = 30
        dialog.add_dimension()
        assert dialog.solution.dof == 0
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", draw)
    window.profile_sketch_action.trigger()
    sketch = window.session.feature("sketch1")
    assert sketch["elements"][0]["shape"] == "profile"
    window.add_feature_actions["extrude"].trigger()
    assert window.session.properties.volume_mm3 == pytest.approx(30 * 20 * 10)
    window.undo()
    window.undo()
    assert window.session.document.features == []


def test_cancelled_sketcher_changes_nothing(window, monkeypatch):
    monkeypatch.setattr(type(window), "_exec_dialog",
                        lambda self, dialog: QDialog.DialogCode.Rejected)
    window.profile_sketch_action.trigger()
    assert window.session.document.features == []


def test_edit_profile_from_shape_form(window, monkeypatch, answers):
    from skodacad.schema import new_shape

    sketch = window.session.add_feature("sketch", values={"elements": [new_shape("profile")]})
    window.session.add_feature("extrude")
    window._selected_id = sketch
    window._reload_all()

    def widen(self, dialog):
        index = next(i for i, c in enumerate(dialog.profile["constraints"])
                     if c.get("segment") == "s1" and c["type"] == "length")
        answers.append("sirka2")
        dialog.edit_constraint_value(index)  # neznámý parametr → chyba v kótě
        assert "neznámý parametr" in dialog.status.text()
        answers.append("60")
        dialog.edit_constraint_value(index)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", widen)
    shapes = window.feature_editor.form.widget("elements")
    button = shapes._form.findChild(QtWidgets.QPushButton, "open_sketcher")
    button.click()
    assert window.session.properties.volume_mm3 == pytest.approx(60 * 30 * 10)
    window.undo()
    assert window.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    assert math.isclose(len(window.session.document.features), 2)
