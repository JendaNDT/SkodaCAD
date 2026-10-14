"""Testy okna bez skutečného 3D prohlížeče (ten potřebuje OpenGL a obrazovku)."""

import math
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Signal  # noqa: E402

from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.inspection import number  # noqa: E402


class FakeViewer(QtWidgets.QWidget):
    selection_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.parts = []
        self.views = []

    def show_part(self, part, fit=False):
        self.parts.append((part, fit))

    def fit_all(self):
        self.views.append("fit")

    def set_standard_view(self, name):
        self.views.append(name)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app, examples_dir, tmp_path):
    model = tmp_path / "priruba.json"
    shutil.copy(examples_dir / "priruba.json", model)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(model)
    yield w
    w.session.dirty = False  # ať se při zavírání neptá na uložení
    w.close()


def tree_texts(w):
    return [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]


def edit(w, name, text):
    field = w._param_fields[name]
    field.setText(text)
    field.editingFinished.emit()
    return field


def test_open_shows_parameters_tree_and_properties(window):
    assert list(window._param_fields) == ["D", "d", "t", "k", "n", "dh", "s"]
    assert window._param_fields["D"].text() == "165"
    assert all(text.startswith("✓") for text in tree_texts(window))
    assert "Objem:  311 093 mm³" in window.props_label.text()
    assert window.windowTitle() == "Plochá příruba (priruba.json) – ŠkodaCAD"
    part, fit = window.viewer.parts[-1]
    assert part is not None and fit


def test_parameter_change_rebuilds(window):
    volume_before = window.session.properties.volume_mm3
    edit(window, "n", "8")
    assert window.session.document.parameters["n"] == 8
    assert window.windowTitle().startswith("*")
    expected = volume_before - 4 * math.pi / 4 * 18**2 * 18  # 4 díry Ø18 navíc, tloušťka 18
    assert f"Objem:  {number(expected, 0)} mm³" in window.props_label.text()
    assert window.viewer.parts[-1][1] is False  # po změně parametru se kamera nehýbe


def test_invalid_parameter_is_marked_red(window):
    field = edit(window, "n", "neexistuje + 1")
    assert "c0392b" in field.styleSheet()
    assert "neznámý parametr" in field.toolTip()
    assert window.session.document.parameters["n"] == 4
    edit(window, "n", "6")
    assert field.styleSheet() == ""


def test_failing_feature_shows_error(window):
    edit(window, "s", "50")
    assert window.error_label.isVisibleTo(window)
    assert "Sražení obvodu" in window.error_label.text()
    texts = tree_texts(window)
    assert texts[4].startswith("✕") and texts[5].startswith("·")


def test_save_clears_dirty(window):
    edit(window, "D", "200")
    assert window.save()
    assert not window.session.dirty
    assert not window.windowTitle().startswith("*")


def test_examples_menu_opens_template(window, examples_dir):
    window.session.dirty = False
    assert window.open_model(examples_dir / "krabicka.json", template=True)
    assert window.session.path is None
    assert "Krabička" in window.windowTitle()
    assert list(window._param_fields) == ["L", "W", "H", "r", "stena", "dira"]


def test_selection_shows_in_status_bar(window):
    window.viewer.selection_changed.emit("Plocha – rovinná")
    assert window.statusBar().currentMessage() == "Plocha – rovinná"
    window.viewer.selection_changed.emit("")
    assert "otáčení" in window.statusBar().currentMessage()


# --- tlačítka a položky menu -----------------------------------------------------------
# Každá akce se opravdu „stiskne“. Chyba uvnitř akce by v Qt jen tiše skončila v
# sys.excepthook, proto ji fixture slot_errors zachytí a test pak selže.


@pytest.fixture
def slot_errors(monkeypatch):
    import sys

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: errors.append(value))
    return errors


@pytest.fixture
def no_dialogs(monkeypatch):
    """Dialogy by v testu čekaly na kliknutí – nahradíme je zrušením / zavřením."""
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    shown = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    for name in ("information", "about", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, n=name, **k: shown.append(n))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Discard)
    return shown


def action(window, text):
    from PySide6.QtGui import QAction

    matches = [a for a in window.findChildren(QAction) if a.text() == text]
    assert matches, f"akce „{text}“ v okně není"
    return matches[0]


def test_view_buttons_switch_view(window, slot_errors):
    from skodacad.gui.viewer_views import VIEW_LABELS

    for key, (label, _shortcut) in VIEW_LABELS.items():
        action(window, label).trigger()
        assert window.viewer.views[-1] == key
    action(window, "Celý díl").trigger()
    assert window.viewer.views[-1] == "fit"
    assert slot_errors == []


def test_examples_menu_items_open_examples(window, slot_errors):
    for stem, title in (("krabicka", "Krabička"), ("hridel", "hřídel"), ("priruba", "příruba")):
        window.session.dirty = False
        action(window, stem).trigger()
        assert title in window.windowTitle()
        assert window.session.path is None
    assert slot_errors == []


@pytest.mark.parametrize("fmt", ["step", "stl", "3mf"])
def test_export_menu_writes_file(window, slot_errors, monkeypatch, tmp_path, fmt):
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / f"export.{fmt}"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    label = next(text for f, text in __import__(
        "skodacad.gui.main_window", fromlist=["EXPORT_FORMATS"]).EXPORT_FORMATS if f == fmt)
    action(window, label + "…").trigger()
    assert target.stat().st_size > 0
    assert slot_errors == []


def test_open_and_save_as_buttons(window, slot_errors, monkeypatch, examples_dir, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(examples_dir / "hridel.json"), ""))
    action(window, "Otevřít…").trigger()
    assert "hřídel" in window.windowTitle()

    target = tmp_path / "kopie.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(window, "Uložit jako…").trigger()
    assert target.exists()
    assert window.session.path == target
    assert slot_errors == []


def test_every_action_runs_without_error(window, slot_errors, no_dialogs):
    from PySide6.QtGui import QAction

    actions = [a for a in window.findChildren(QAction) if a.text() and a.text() != "Konec"]
    assert len(actions) >= 15
    for item in actions:
        item.trigger()
    assert slot_errors == []
    assert {"information", "about"} <= set(no_dialogs)  # Ovládání a O aplikaci se ukázaly


# --- tvorba a úpravy dílu v okně ---------------------------------------------------------


@pytest.fixture
def empty_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    action(w, "Nový").trigger()
    yield w
    assert slot_errors == [], slot_errors
    w.session.dirty = False
    w.close()


def selected_text(w):
    item = w.tree.currentItem()
    return item.text(0) if item else None


def form_field(w, key):
    return w.feature_editor.form.widget(key)


def set_text(widget, text):
    widget.setText(text)
    widget.editingFinished.emit()


def build_box(w):
    action(w, "Skica").trigger()
    action(w, "Vysunutí").trigger()


def test_new_part_from_scratch(empty_window):
    w = empty_window
    assert w.tree.topLevelItemCount() == 0
    assert "Vyber prvek" in w.feature_editor.title.text()
    build_box(w)
    assert tree_texts(w) == ["✓  Skica „Skica 1“", "✓  Vysunutí „Vysunutí 1“"]
    assert selected_text(w) == "✓  Vysunutí „Vysunutí 1“"  # nový prvek je hned vybraný
    assert "Vysunutí" in w.feature_editor.title.text()
    assert "Objem:  12 000 mm³" in w.props_label.text()
    assert w.viewer.parts[-1][0] is not None


def test_edit_feature_value_in_form(empty_window):
    w = empty_window
    build_box(w)
    set_text(form_field(w, "distance"), "2 * 12,5".replace(",", "."))
    assert "Rozměry:  40.00 × 30.00 × 25.00 mm" in w.props_label.text()
    set_text(form_field(w, "distance"), "7,5")  # desetinná čárka
    assert "× 7.50 mm" in w.props_label.text()


def test_invalid_form_value_is_red_and_model_unchanged(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Zaoblení").trigger()
    radius = form_field(w, "radius")
    set_text(radius, "")
    assert "c0392b" in radius.styleSheet()
    assert "povinná" in w.statusBar().currentMessage()
    assert w.session.feature("fillet1")["radius"] == 2
    set_text(radius, "1")
    assert radius.styleSheet() == ""
    assert w.session.feature("fillet1")["radius"] == 1


def test_cut_with_choice_field(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Skica").trigger()  # druhá skica – automaticky na horní ploše
    sketch = w.session.feature("sketch2")
    assert sketch["plane"] == "top"
    action(w, "Vysunutí").trigger()
    operation = form_field(w, "operation")
    operation.setCurrentIndex(operation.findData("cut"))
    assert w.session.feature("extrude2")["operation"] == "cut"
    assert w.session.result.ok
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - math.pi * 25 * 10)


def test_shapes_editor_adds_hole(empty_window):
    w = empty_window
    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))  # vybrat skicu
    shapes = form_field(w, "elements")
    shapes.add_shape("circle")
    assert [e["shape"] for e in w.session.feature("sketch1")["elements"]] == ["rectangle",
                                                                             "circle"]
    mode = shapes._form.widget("mode")
    mode.setCurrentIndex(mode.findData("subtract"))
    assert w.session.feature("sketch1")["elements"][1]["mode"] == "subtract"
    assert w.session.properties.volume_mm3 == pytest.approx(
        (40 * 30 - math.pi * 10**2) * 10, rel=1e-6)
    assert shapes.list.item(1).text() == "Kružnice (odečíst)"


def test_delete_move_and_undo(empty_window, no_dialogs):
    w = empty_window
    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))
    action(w, "Smazat prvek").trigger()  # skicu používá vysunutí → jen varování
    assert "warning" in no_dialogs
    assert w.tree.topLevelItemCount() == 2

    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    action(w, "Posunout nahoru").trigger()
    assert tree_texts(w)[0].startswith("✕  Vysunutí")  # vysunutí před skicou nejde
    assert w.error_label.isVisibleTo(w)

    action(w, "Zpět").trigger()
    assert all(text.startswith("✓") for text in tree_texts(w))
    action(w, "Znovu").trigger()
    assert tree_texts(w)[0].startswith("✕")
    action(w, "Zpět").trigger()

    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    action(w, "Smazat prvek").trigger()
    assert tree_texts(w) == ["✓  Skica „Skica 1“"]
    assert selected_text(w) == "✓  Skica „Skica 1“"


def test_undo_redo_enabled_states(empty_window):
    w = empty_window
    assert not action(w, "Zpět").isEnabled()
    action(w, "Skica").trigger()
    assert action(w, "Zpět").isEnabled() and not action(w, "Znovu").isEnabled()
    action(w, "Zpět").trigger()
    assert w.tree.topLevelItemCount() == 0
    assert action(w, "Znovu").isEnabled()


def test_add_and_delete_parameter(empty_window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = empty_window
    answers = iter([("sirka", True), ("55", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    action(w, "Přidat parametr…").trigger()
    assert w._param_fields["sirka"].text() == "55"

    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))
    shapes = form_field(w, "elements")
    set_text(shapes._form.widget("width"), "sirka")
    assert "Rozměry:  55.00 × 30.00" in w.props_label.text()

    set_text(w._param_fields["sirka"], "60")
    assert "Rozměry:  60.00 × 30.00" in w.props_label.text()

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("sirka", True))
    action(w, "Smazat parametr…").trigger()  # používá ho skica → jen varování
    assert "sirka" in w._param_fields


def test_part_name_and_material(empty_window):
    w = empty_window
    build_box(w)
    set_text(w.name_edit, "Držák senzoru")
    assert w.windowTitle().startswith("*Držák senzoru")
    combo = w.material_combo
    combo.setCurrentIndex(combo.findData("hliník"))
    assert w.session.document.material == "hliník"
    assert "(hliník)" in w.props_label.text()
    action(w, "Zpět").trigger()
    assert w.material_combo.currentData() == "ocel"


def test_example_material_is_shown(window):
    assert window.material_combo.currentData() == "ocel"
    window.session.dirty = False
    action(window, "krabicka").trigger()
    assert window.material_combo.currentData() == "PETG"
