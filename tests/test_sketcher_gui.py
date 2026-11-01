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
    window.add_profile_sketch()
    sketch = window.session.feature("sketch1")
    assert sketch["elements"][0]["shape"] == "profile"
    window.add_feature("extrude")
    assert window.session.properties.volume_mm3 == pytest.approx(30 * 20 * 10)
    window.undo()
    window.undo()
    assert window.session.document.features == []


def test_cancelled_sketcher_changes_nothing(window, monkeypatch):
    monkeypatch.setattr(type(window), "_exec_dialog",
                        lambda self, dialog: QDialog.DialogCode.Rejected)
    window.add_profile_sketch()
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
    window.edit_feature_action.trigger()
    panel = window.feature_preview
    shapes = panel.editor.form.widget("elements")
    button = shapes._form.findChild(QtWidgets.QPushButton, "open_sketcher")
    button.click()
    assert window.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    assert panel.preview.session.properties.volume_mm3 == pytest.approx(60 * 30 * 10)
    panel.accept_button.click()
    assert window.session.properties.volume_mm3 == pytest.approx(60 * 30 * 10)
    window.undo()
    assert window.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    assert math.isclose(len(window.session.document.features), 2)


def test_keyboard_shortcuts_switch_tools(sketcher):
    from PySide6.QtTest import QTest

    sketcher.show()
    sketcher.activateWindow()  # zkratky fungují jen v aktivním okně (ve Windows je)
    QTest.qWaitForWindowActive(sketcher, 2000)
    sketcher.canvas.setFocus()
    for key, tool in ((Qt.Key.Key_S, "select"), (Qt.Key.Key_A, "arc"), (Qt.Key.Key_R, "circle"),
                      (Qt.Key.Key_L, "line")):
        QTest.keyClick(sketcher.canvas, key)
        assert sketcher.tool == tool
    sketcher.hide()


def test_mouse_clicks_draw_and_select(sketcher):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    sketcher.resize(1100, 700)
    sketcher.show()
    canvas = sketcher.canvas

    def at(x, y):
        point = canvas.to_screen(x, y)
        return QPoint(round(point.x()), round(point.y()))

    sketcher.set_tool("line")
    for xy in ((0, 0), (30, 0.3), (15, 20), (0, 0)):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=at(*xy))
    assert len(sketcher.profile["segments"]) == 3 and sketcher.chain_start is None
    sketcher.set_tool("select")
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=at(15, 0.1))
    assert sketcher.selection == ["s1"]
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                     at(7.5, 10))
    assert sketcher.selection == ["s1", "s3"]
    sketcher.hide()


# --- kružnice a vazby mezi tvary --------------------------------------------------------


def dimensioned_rectangle(d, answers, width="40", height="30"):
    draw_rectangle(d)
    answers += [width, height]
    d.set_tool("select")
    d.click(20, 0.2)
    d.add_dimension()
    d.click(float(width), 15)
    d.add_dimension()
    assert d.solution.dof == 0


def test_circle_hole_with_diameter_and_position(sketcher, answers):
    dimensioned_rectangle(sketcher, answers)
    sketcher.set_tool("circle")
    sketcher.click(12, 10)  # střed
    sketcher.click(16, 10)  # bod na obvodu → poloměr 4
    profile = sketcher.result_profile()
    circle = profile["segments"]["k1"]
    assert circle["type"] == "circle" and circle["radius"] == pytest.approx(4)
    sketcher.set_tool("select")
    sketcher.click(12 + 4 / math.sqrt(2), 10 + 4 / math.sqrt(2))  # klik na obvod
    assert sketcher.selection == ["k1"]
    answers.append("10")
    sketcher.add_dimension()  # u kružnice průměr
    assert sketcher.profile["constraints"][-1] == {"type": "diameter", "segment": "k1",
                                                   "value": 10}
    assert sketcher.profile["segments"]["k1"]["radius"] == pytest.approx(5)
    center = sketcher.profile["segments"]["k1"]["center"]
    for line, value in (("s1", "12"), ("s4", "15")):  # vzdálenost středu od hran
        sketcher.select([center, line])
        answers.append(value)
        sketcher.add_dimension()
    assert sketcher.solution.dof == 0
    assert sketcher.profile["points"][center] == pytest.approx([15, 12])
    labels = [sketcher.dimension_label(c)[1] for c in sketcher.profile["constraints"]
              if c["type"] == "diameter"]
    assert labels == ["Ø10"]


def test_tangent_line_and_circle_from_buttons(sketcher, answers):
    dimensioned_rectangle(sketcher, answers)
    sketcher.set_tool("circle")
    sketcher.click(20, 8)
    sketcher.click(25, 8)
    sketcher.set_tool("select")
    sketcher.select(["s1", "k1"])
    sketcher.constraint_actions["tangent"].trigger()  # kružnice se dotkne spodní hrany
    center = sketcher.profile["segments"]["k1"]["center"]
    radius = sketcher.profile["segments"]["k1"]["radius"]
    assert sketcher.profile["points"][center][1] == pytest.approx(radius)
    sketcher.set_tool("circle")
    sketcher.click(30, 20)
    sketcher.click(32, 20)
    sketcher.set_tool("select")
    sketcher.select(["k1", "k2"])
    sketcher.constraint_actions["equal"].trigger()
    assert sketcher.profile["segments"]["k2"]["radius"] == pytest.approx(
        sketcher.profile["segments"]["k1"]["radius"])
    sketcher.select(["k1", "k2"])
    sketcher.constraint_actions["concentric"].trigger()
    assert "už mají společný střed" not in sketcher.status.text()
    assert sketcher.solution.ok


def test_symmetric_and_concentric_buttons_need_right_selection(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("select")
    sketcher.select(["s1"])
    sketcher.constraint_actions["concentric"].trigger()
    assert "dva oblouky nebo kružnice" in sketcher.status.text()
    sketcher.select(["P1", "P3", "s1"])
    sketcher.constraint_actions["symmetric"].trigger()
    assert sketcher.profile["constraints"][-1] == {"type": "symmetric",
                                                   "points": ["P1", "P3"], "segment": "s1"}


def test_drag_circle_changes_radius(sketcher):
    sketcher.set_tool("circle")
    sketcher.click(0, 0)  # střed v počátku
    sketcher.click(5, 0)
    sketcher.set_tool("select")
    sketcher.press(0, 5)  # obvod nahoře
    sketcher.move(0, 9)
    sketcher.release(0, 9)
    assert sketcher.profile["segments"]["k1"]["radius"] == pytest.approx(9)
    sketcher.undo()
    assert sketcher.profile["segments"]["k1"]["radius"] == pytest.approx(5)


def test_circle_center_on_point_and_rim_on_point(sketcher):
    draw_rectangle(sketcher)
    sketcher.set_tool("circle")
    sketcher.click(0, 0)  # střed na rohu P1
    sketcher.click(40, 0)  # obvod na rohu P2 → bod na kružnici
    circle = sketcher.profile["segments"]["k1"]
    assert circle["center"] == "P1"
    assert {"type": "coincident", "point": "P2", "on": "k1"} in sketcher.profile["constraints"]
    assert "se navzájem kříží" in sketcher.status.text()  # kružnice přetíná obdélník
    sketcher.undo()
    assert "kříží" not in sketcher.status.text()


def test_hole_from_sketcher_is_cut_in_the_part(window, monkeypatch, answers):
    def draw(self, dialog):
        dimensioned_rectangle(dialog, answers, "40", "30")
        dialog.set_tool("circle")
        dialog.click(20, 15)
        dialog.click(24, 15)
        dialog.set_tool("select")
        dialog.select(["k1"])
        answers.append("10")
        dialog.add_dimension()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", draw)
    window.add_profile_sketch()
    window.add_feature("extrude")
    assert window.session.properties.volume_mm3 == pytest.approx((40 * 30 - math.pi * 25) * 10)


# --- promítnutí hran dílu ---------------------------------------------------------------


def part_with_hole(window):
    """Kvádr 40 × 30 × 10 (střed v počátku) s dírou Ø6 skrz v [hx, 3]."""
    session = window.session
    session.add_parameter("hx", "5")
    session.add_feature("sketch")
    session.add_feature("extrude")
    session.add_feature("sketch", values={"elements": [
        {"shape": "circle", "diameter": 6, "center": ["hx", 3]}]})
    session.add_feature("extrude", values={"operation": "cut", "through_all": True})
    window._selected_id = "extrude2"
    window._reload_all()
    assert session.result.ok


def test_boss_around_projected_hole_follows_hole(window, monkeypatch, answers):
    part_with_hole(window)

    def draw(self, dialog):
        assert dialog.tool_actions["project"].isEnabled()
        assert len(dialog.candidate_polylines()) == 5  # 4 hrany horní plochy a díra
        dialog.set_tool("project")
        dialog.click(5 + 3, 3)  # na obvod díry
        assert dialog.selection == ["r1"] and dialog.profile["references"]["r1"]["kind"] == \
            "circle"
        dialog.set_tool("circle")
        dialog.click(5, 3)  # střed na středu promítnuté díry → nový bod „na bodě“ r1.center
        dialog.click(11, 3)
        assert {"type": "coincident", "point": "P1", "on": "r1.center"} in \
            dialog.profile["constraints"]
        dialog.set_tool("select")
        dialog.select(["k1"])
        answers.append("12")
        dialog.add_dimension()
        assert dialog.solution.dof == 0
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", draw)
    window.add_profile_sketch()
    window.add_feature("extrude")
    session = window.session
    assert session.result.ok
    expected = 40 * 30 * 10 - math.pi * 9 * 10 + math.pi * 36 * 10
    assert session.properties.volume_mm3 == pytest.approx(expected)
    session.set_parameter("hx", "-8")  # díra se posune – výstupek jde s ní
    assert session.properties.volume_mm3 == pytest.approx(expected)
    from build123d import Axis

    top = session.result.part.faces().sort_by(Axis.Z)[-1]
    assert (top.center().X, top.center().Y) == pytest.approx((-8, 3))


def test_convert_projected_outline_into_profile(window, monkeypatch):
    part_with_hole(window)

    def draw(self, dialog):
        dialog.set_tool("project")
        for x, y in ((0, -15), (20, 0), (0, 15), (-20, 0)):  # čtyři hrany horní plochy
            dialog.click(x, y)
        assert sorted(dialog.profile["references"]) == ["r1", "r2", "r3", "r4"]
        dialog.set_tool("select")
        dialog.select(["r1", "r2", "r3", "r4"])
        dialog.convert_action.trigger()
        assert len(dialog.profile["segments"]) == 4 and dialog.solution.dof == 0
        assert "plně určený" in dialog.status.text()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", draw)
    window.add_profile_sketch()
    window.add_feature("extrude")
    assert window.session.properties.volume_mm3 == pytest.approx(
        40 * 30 * 10 - math.pi * 9 * 10 + 40 * 30 * 10)


def test_projection_tool_is_off_without_part(window, monkeypatch):
    seen = {}

    def draw(self, dialog):
        seen["enabled"] = dialog.tool_actions["project"].isEnabled()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(type(window), "_exec_dialog", draw)
    window.add_profile_sketch()
    assert seen == {"enabled": False}


def test_reference_points_snap_and_cannot_be_dragged(sketcher):
    from skodacad.profile_edit import add_reference

    add_reference(sketcher.profile, {"edge": {"face": "top"}, "kind": "line",
                                     "points": [[0, 0], [30, 0]]})
    sketcher.set_tool("select")
    sketcher.click(30, 0)
    assert sketcher.selection == ["r1.end"]
    sketcher.press(30, 0)
    sketcher.move(35, 5)
    sketcher.release(35, 5)
    assert sketcher.profile["references"]["r1"]["points"][1] == [30, 0]  # pevný bod
    sketcher.delete_action.trigger()  # smazání bodu smaže celou promítnutou hranu
    assert not sketcher.profile["references"]
