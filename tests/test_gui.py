"""Testy okna bez skutečného 3D prohlížeče (ten potřebuje OpenGL a obrazovku)."""

import math
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QPoint, Signal  # noqa: E402

from conftest import edge_at, face_at  # noqa: E402
from skodacad.gui.main_window import HELP_HINT, MainWindow  # noqa: E402
from skodacad.inspection import number  # noqa: E402


class FakeViewer(QtWidgets.QWidget):
    selection_changed = Signal(list)
    context_menu_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self.parts = []
        self.views = []
        self.highlighted = []
        self.measurement = []  # čáry měření (od, do, popisek)
        self.thickness_map = None  # (uzlů, trojúhelníků, barvy, značka) zobrazené mapy
        self.picked_point = None

    def show_part(self, part, fit=False, accent=None):
        self.parts.append((part, fit))
        self.accent = list(accent or [])  # plochy jinou barvou (plochy řezu)
        self.picked_point = None
        self.measurement = []
        self.thickness_map = None
        self.selection_changed.emit([])  # jako skutečný prohlížeč: nový díl = nic vybráno

    def highlight(self, shapes):
        self.highlighted = list(shapes)

    def show_measurement(self, lines):
        self.measurement = list(lines)

    def show_thickness_map(self, nodes, triangles, colors, marker=None, fill=None):
        self.thickness_map = (len(nodes), len(triangles), list(colors), marker)
        self.map_fill = list(fill or [])

    def hide_thickness_map(self):
        self.thickness_map = None

    def clear_selection(self):
        self.picked_point = None
        self.selection_changed.emit([])

    def click(self, shapes, point=None):
        """Jako by uživatel klikl (s Ctrl) na tyto plochy/hrany."""
        self.picked_point = point
        self.selection_changed.emit([shape.wrapped for shape in shapes])

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
    part = window.session.result.part
    window.viewer.click([face_at(part, 60, 0, 18)])
    assert window.statusBar().currentMessage().startswith("Plocha – rovinná")
    assert "skica nebo díra na ploše" in window.statusBar().currentMessage()
    window.viewer.click([edge_at(part, 82.5, 0, 0), edge_at(part, 0, 32, 0)])
    assert window.statusBar().currentMessage().startswith("Vybráno: 2 hrany")
    window.viewer.click([])
    assert window.statusBar().currentMessage() == HELP_HINT


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
    # Skicář (a další vlastní dialogy) jde přes MainWindow._exec_dialog → „Zrušit“.
    monkeypatch.setattr(MainWindow, "_exec_dialog",
                        lambda self, dialog: shown.append(type(dialog).__name__) or 0)
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
    # Zapnutá mapa tloušťky by se počítala znovu s každou další změnou – stisknout až nakonec.
    actions.sort(key=lambda a: a is window.thickness_map_action)
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


# --- výběr ve 3D → prvky ---------------------------------------------------------------


def shown_part(w):
    return w.session.result.part


def test_fillet_from_clicked_edge(empty_window):
    w = empty_window
    build_box(w)
    fillet = action(w, "Zaoblit vybrané hrany")
    assert not fillet.isEnabled()  # nic nevybráno
    w.viewer.click([edge_at(shown_part(w), 20, -15, 5)])
    assert fillet.isEnabled()
    fillet.trigger()
    assert selected_text(w) == "✓  Zaoblení „Zaoblení 1“"
    assert "hrana mezi přední a pravou plochou" in form_field(w, "edges").text()
    loss = (2 ** 2 - math.pi * 2 ** 2 / 4) * 10
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - loss)
    assert len(w.viewer.highlighted) == 1  # zvýrazněná zaoblená hrana
    assert not fillet.isEnabled()  # díl se překreslil, výběr zmizel
    set_text(form_field(w, "radius"), "4")  # poloměr dál jde měnit ve formuláři
    loss = (4 ** 2 - math.pi * 4 ** 2 / 4) * 10
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - loss)


def test_add_clicked_edges_to_selected_fillet(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([edge_at(shown_part(w), 20, -15, 5)])
    action(w, "Srazit vybrané hrany").trigger()
    w.viewer.click([edge_at(shown_part(w), -20, 15, 5), edge_at(shown_part(w), -20, -15, 5)])
    add = action(w, "Přidat vybrané hrany do: Sražení „Sražení 1“")
    assert add.isEnabled()
    add.trigger()
    edges = w.session.feature("chamfer1")["edges"]
    assert edges == [{"between": ["front", "right"]}, {"face": "left", "parallel": "Z"}]
    assert "hrany na levé ploše, rovnoběžné s osou Z" in form_field(w, "edges").text()
    assert len(w.viewer.highlighted) == 3
    w.viewer.click([edge_at(shown_part(w), 0, 15, 0)])
    action(w, "Nahradit hrany vybraného prvku výběrem").trigger()
    assert w.session.feature("chamfer1")["edges"] == {"between": ["bottom", "back"]}


def test_sketch_on_clicked_face(empty_window):
    w = empty_window
    build_box(w)
    sketch = action(w, "Skica na vybrané ploše")
    w.viewer.click([face_at(shown_part(w), 0, -15, 5)], point=(8, -15, 4))
    sketch.trigger()
    feature = w.session.feature("sketch2")
    assert feature["plane"] == "front"
    assert feature["elements"][0]["center"] == [8, 4]  # na přední ploše: x a výška z
    assert form_field(w, "plane").currentData() == "front"


def test_curved_face_offers_sketch_but_not_shell(window, no_dialogs, slot_errors):
    part = shown_part(window)
    bore = next(face for face in part.faces() if face.geom_type.name == "CYLINDER")
    window.viewer.click([bore])
    assert action(window, "Skica na vybrané ploše").isEnabled()  # na tečné rovině
    assert action(window, "Díra na vybrané ploše").isEnabled()
    assert not action(window, "Skořepina – otevřít vybrané plochy").isEnabled()
    assert "díra na ploše" in window.statusBar().currentMessage()
    # Skořepina zakřivenou plochu otevřít neumí: česká hláška, model beze změny.
    before = len(window.session.document.features)
    window.add_from_selection("shell")
    assert no_dialogs == ["warning"]
    assert len(window.session.document.features) == before
    assert slot_errors == []


def test_selecting_feature_in_tree_highlights_its_edges(window):
    chamfer = next(i for i in range(window.tree.topLevelItemCount())
                   if "Sražení" in window.tree.topLevelItem(i).text(0))
    window.tree.setCurrentItem(window.tree.topLevelItem(chamfer))
    assert window.viewer.highlighted
    window.tree.setCurrentItem(None)
    assert window.viewer.highlighted == []


def test_context_menu_offers_selection_actions(window, monkeypatch):
    shown = []  # nabídka by v testu čekala na kliknutí – jen si zapamatujeme její položky
    monkeypatch.setattr(window, "_exec_menu", lambda menu, position: shown.append(
        [(item.text(), item.isEnabled()) for item in menu.actions() if item.text()]))
    window.viewer.context_menu_requested.emit(QPoint(10, 10))
    assert shown[-1][0] == ("Nic není vybrané – klikni na hranu nebo plochu", False)
    window.viewer.click([edge_at(shown_part(window), 82.5, 0, 0)])
    window.viewer.context_menu_requested.emit(QPoint(10, 10))
    items = dict(shown[-1])
    assert items["Zaoblit vybrané hrany"] and items["Srazit vybrané hrany"]
    assert not items["Skica na vybrané ploše"]
    action(window, "Zrušit výběr ve 3D").trigger()
    assert not action(window, "Zaoblit vybrané hrany").isEnabled()


def test_hole_from_clicked_face_and_size_change(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([face_at(shown_part(w), 5, 5, 10)], point=(5, 5, 10))
    action(w, "Díra na vybrané ploše").trigger()
    assert selected_text(w) == "✓  Díra „Díra 1“ – M6 závit"
    size = form_field(w, "size")
    assert size.currentData() == "M6"
    size.setCurrentIndex(size.findData("M3"))  # menší závit → menší vrták Ø2,5
    hole = w.session.feature("hole1")
    assert hole["size"] == "M3" and hole["positions"] == [[5, 5]]
    drill = math.pi * 1.25 ** 2 * 6 + math.pi * 1.25 ** 2 * (1.25 / math.tan(math.radians(59))) / 3
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - drill)
    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("countersink"))  # M3 zápustná, skrz? hloubka 6
    assert "zápustné" in selected_text(w)


def test_modeled_thread_checkbox(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([face_at(shown_part(w), 5, 5, 10)], point=(5, 5, 10))
    action(w, "Díra na vybrané ploše").trigger()
    size = form_field(w, "size")
    size.setCurrentIndex(size.findData("M12"))  # velké stoupání = málo závitů = rychlý test
    before = w.session.properties.volume_mm3
    form_field(w, "modeled_thread").setChecked(True)
    hole = w.session.feature("hole1")
    assert hole["modeled_thread"] is True
    assert selected_text(w).endswith("M12 závit (vymodelovaný)")
    assert w.session.result.ok
    assert w.session.properties.volume_mm3 < before  # drážka závitu ubrala materiál


def test_pattern_and_mirror_from_tree(empty_window):
    w = empty_window
    build_box(w)  # kvádr 40 × 30 × 10
    action(w, "Díra").trigger()
    positions = form_field(w, "positions")
    positions.setPlainText("-10; 5")
    positions.editingFinished.emit()
    one = 40 * 30 * 10 - w.session.properties.volume_mm3
    action(w, "Pole").trigger()  # vybraná je díra → pole ji rovnou opakuje
    assert selected_text(w) == "✓  Pole „Pole 1“ – v řadě, 3 ks"
    form = w.feature_editor.form
    assert form.widget("features").findChild(QtWidgets.QCheckBox, "feature_hole1").isChecked()
    assert form.is_shown("spacing") and not form.is_shown("axis")
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - 3 * one)

    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("circular"))  # 3× dokola kolem osy Z
    assert form.is_shown("axis") and form.is_shown("center") and not form.is_shown("spacing")
    assert w.session.feature("pattern1")["kind"] == "circular"
    assert selected_text(w) == "✓  Pole „Pole 1“ – dokola, 3 ks"
    set_text(form_field(w, "center").findChild(QtWidgets.QLineEdit, "point_z"), "4")
    assert w.session.feature("pattern1")["center"] == [0, 0, 4]
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - 3 * one)

    action(w, "Zrcadlení").trigger()  # zrcadlí pole podle YZ
    assert w.session.feature("mirror1")["features"] == ["pattern1"]
    box = form_field(w, "features").findChild(QtWidgets.QCheckBox, "feature_pattern1")
    box.setChecked(False)  # nic nezaškrtnuto → zrcadlí se celý díl
    assert "features" not in w.session.feature("mirror1")
    plane = form_field(w, "plane")
    plane.setCurrentIndex(plane.findData("right"))
    assert selected_text(w) == "✓  Zrcadlení „Zrcadlení 1“ – celý díl"
    assert w.session.properties.volume_mm3 == pytest.approx(2 * (40 * 30 * 10 - 3 * one))


def test_pattern_needs_a_checked_feature(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Pole").trigger()  # před ním je jen základní těleso → nic zaškrtnuté
    assert w.session.result.first_error.id == "pattern1"
    assert "vyber prvky" in w.session.result.first_error.message
    form = form_field(w, "features")
    form.findChild(QtWidgets.QCheckBox, "feature_extrude1").setChecked(True)
    form.findChild(QtWidgets.QCheckBox, "feature_extrude1").setChecked(False)
    assert "zaškrtni aspoň jeden prvek" in w.statusBar().currentMessage()


def test_sketch_on_inclined_face_from_click(empty_window):
    w = empty_window
    build_box(w)  # kvádr 40 × 30 × 10
    w.session.add_feature("chamfer", values={"edges": {"between": ["top", "front"]},
                                             "distance": 5})
    w._reload_all()
    slope = face_at(shown_part(w), 0, -12.5, 7.5)  # šikmá plocha sražení
    w.viewer.click([slope], point=(4, -12.5, 7.5))
    assert action(w, "Skica na vybrané ploše").isEnabled()
    action(w, "Skica na vybrané ploše").trigger()
    sketch = w.session.feature("sketch2")
    assert sketch["plane"]["at"] == pytest.approx([4, -12.5, 7.5])
    assert sketch["elements"][0]["center"] == [0.0, 0.0]  # počátek skici = místo kliknutí
    plane = form_field(w, "plane")
    assert plane.currentText() == "plocha vybraná ve 3D (u bodu 4; -12.5; 7.5)"
    shapes = form_field(w, "elements")
    set_text(shapes._form.widget("diameter"), "4")  # jiné pole – rovina musí zůstat
    assert w.session.feature("sketch2")["plane"]["at"] == pytest.approx([4, -12.5, 7.5])
    w.session.add_feature("extrude", values={"operation": "cut", "distance": 2})
    chamfered = 40 * 30 * 10 - 0.5 * 5 * 5 * 40
    assert w.session.properties.volume_mm3 == pytest.approx(chamfered - math.pi * 4 * 2)


def test_hole_on_shaft_surface_from_click(empty_window):
    w = empty_window
    session = w.session
    session.add_feature("sketch", values={"plane": "YZ", "elements": [
        {"shape": "circle", "diameter": 20}]})
    session.add_feature("extrude", values={"distance": 80, "direction": "both"})
    w._reload_all()
    shaft = face_at(shown_part(w), 5, 0, 10)
    assert shaft.geom_type.name == "CYLINDER"
    w.viewer.click([shaft], point=(5, 0, 10))
    action(w, "Díra na vybrané ploše").trigger()
    hole = session.feature("hole1")
    assert hole["plane"] == {"at": [5.0, 0.0, 10.0], "normal": [0.0, 0.0, 1.0]}
    assert hole["positions"] == [[0.0, 0.0]] and session.result.ok
    assert session.properties.volume_mm3 < math.pi * 100 * 80  # díra do hřídele z boku
    w.viewer.click([face_at(shown_part(w), -20, 0, 10)], point=(-20, 0, 10))
    assert w.add_to_feature_action.text().startswith("Přidat díru v místě kliknutí do:")
    w.add_to_feature_action.trigger()  # na horní přímce hřídele = stejná tečná rovina → další díra
    assert session.feature("hole1")["positions"] == [[0.0, 0.0], [-25.0, 0.0]]
    w.viewer.click([face_at(shown_part(w), 0, -10, 0)], point=(0, -10, 0))
    w.add_to_feature_action.trigger()  # na boku hřídele je jiná tečná rovina → jen hláška
    assert len(session.feature("hole1")["positions"]) == 2


# --- měření -----------------------------------------------------------------------------


def measure_rows(w):
    return [w.measure_list.item(i).text() for i in range(w.measure_list.count())]


def saved_rows(w):
    return [w.saved_list.item(i).text() for i in range(w.saved_list.count())]


def test_measuring_on_click_and_saving_into_the_model(window, no_dialogs, slot_errors,
                                                      monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = window
    assert measure_rows(w) == [] and "Klikni ve 3D" in w.measure_hint.text()
    assert not w.save_measurement_action.isEnabled()
    top = face_at(shown_part(w), 60, 0, 18)
    w.viewer.click([top], point=(60, 0, 18))
    assert measure_rows(w)[0] == "Tloušťka stěny: 18.00 mm"  # deska příruby t = 18
    [(start, end, label)] = w.viewer.measurement  # čára od kliknutí skrz desku
    assert start == pytest.approx((60, 0, 18)) and end == pytest.approx((60, 0, 0))
    assert label == "18.00 mm"
    assert w.save_measurement_action.text() == \
        "Uložit měření do modelu: Tloušťka stěny: 18.00 mm"
    w.save_measurement_action.trigger()
    assert saved_rows(w) == ["Tloušťka stěny: 18.00 mm"]
    assert w.session.document.measurements[0]["kind"] == "thickness"
    assert w.viewer.measurement  # uložené měření je vybrané a jeho čára vidět
    edit(w, "t", "20")
    assert saved_rows(w) == ["Tloušťka stěny: 20.00 mm"]  # přepočítalo se s dílem

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Stěna příruby", True))
    w.saved_list.setCurrentRow(0)
    action(w, "Přejmenovat měření…").trigger()
    assert saved_rows(w) == ["Stěna příruby: 20.00 mm"]
    w.saved_list.setCurrentRow(0)
    action(w, "Smazat měření").trigger()
    assert saved_rows(w) == [] and w.viewer.measurement == []
    action(w, "Zpět").trigger()
    assert saved_rows(w) == ["Stěna příruby: 20.00 mm"]
    assert slot_errors == []


def test_two_holes_show_pitch_in_panel_and_status_bar(window, monkeypatch):
    w = window
    part = shown_part(w)
    pitch = 125 / 2 * math.sqrt(2)  # sousední díry na roztečné kružnici k = 125, n = 4
    corner = 125 / 2 / math.sqrt(2)  # díry jsou pootočené o 45°
    holes = [face_at(part, sx * corner + sx * 9, corner, 9) for sx in (1, -1)]
    assert all(h.geom_type.name == "CYLINDER" for h in holes)
    w.viewer.click(holes)
    assert measure_rows(w)[0] == f"Rozteč os: {number(pitch)} mm"
    assert f"Rozteč os: {number(pitch)} mm" in w.statusBar().currentMessage()
    shown = []
    monkeypatch.setattr(w, "_exec_menu", lambda menu, position: shown.append(
        [item.text() for item in menu.actions() if item.isEnabled()]))
    w.viewer.context_menu_requested.emit(QPoint(10, 10))
    assert f"Uložit měření do modelu: Rozteč os: {number(pitch)} mm" in shown[-1]
    w.measure_list.setCurrentRow(len(measure_rows(w)) - 1)  # nejkratší vzdálenost
    assert w.viewer.measurement[0][2] == f"{number(pitch - 18)} mm"  # mezi stěnami děr Ø18
    w.viewer.click(list(part.faces())[:3])
    assert measure_rows(w) == [] and "jednu nebo dvě" in w.measure_hint.text()


# --- mapa tloušťky stěny ------------------------------------------------------------------


def test_thickness_map_in_window(window, no_dialogs, slot_errors, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w = window  # příruba: deska 18 mm s dírami
    assert w.viewer.thickness_map is None and not w.export_map_action.isEnabled()
    assert "Zapni mapu" in w.map_summary.text()
    action(w, "Mapa tloušťky stěny").trigger()
    nodes, triangles, colors, (point, label) = w.viewer.thickness_map
    assert nodes > 1000 and triangles > 1000 and len(colors) == nodes
    found = w.session.thickness_map
    assert label == f"min {number(found.minimum)} mm"
    assert "Nejčastější tloušťka: 18.00 mm" in w.map_summary.text()
    assert w.map_scale_label.text().endswith("18.00 mm a víc")
    # klik na mapu = přesná tloušťka v bodě i ve stavovém řádku
    w.viewer.click([face_at(shown_part(w), 60, 0, 18)], point=(60, 0, 18))
    assert "Tloušťka stěny: 18.00 mm" in w.statusBar().currentMessage()

    set_text(w.map_fields["limit"], "20")  # minimum nad tloušťkou desky → skoro vše pod ním
    assert w.session.document.thickness_map == {"limit": 20}
    assert "Pod minimem 20.00 mm" in w.map_summary.text()
    set_text(w.map_fields["step"], "nic")
    assert "c0392b" in w.map_fields["step"].styleSheet()  # neplatné číslo → červeně
    assert w.session.document.thickness_map == {"limit": 20}
    set_text(w.map_fields["step"], "8")
    assert w.session.thickness_map.step == 8 and w.map_fields["step"].styleSheet() == ""
    action(w, "Zpět").trigger()
    assert w.map_fields["step"].text() == "" and w.session.thickness_map.step != 8

    target = tmp_path / "mapa.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(w, "Export bodů mapy do CSV…").trigger()
    assert target.read_text(encoding="utf-8-sig").startswith("x [mm];y [mm];z [mm]")

    action(w, "Mapa tloušťky stěny").trigger()  # vypnout
    assert w.viewer.thickness_map is None and not w.session.map_visible
    edit(w, "t", "20")
    assert w.session.thickness_map is None  # vypnutá mapa se nepočítá
    assert slot_errors == []


# --- řez modelem ---------------------------------------------------------------------------


def test_section_in_window(window, no_dialogs, slot_errors, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w = window  # příruba Ø165 × 18 s otvorem Ø62 a čtyřmi děrami Ø18
    full = w.session.result.part
    assert not w.flip_section_action.isEnabled() and "Zapni řez" in w.section_info.text()
    action(w, "Řez modelem").trigger()  # výchozí kolmo na Y uprostřed (středem otvoru)
    shown, _fit = w.viewer.parts[-1]
    assert shown is w.session.section.part and shown.volume == pytest.approx(full.volume / 2)
    assert len(w.viewer.accent) == 2  # dvě plochy řezu vedle otvoru
    area = 2 * (165 - 62) / 2 * 18 - 4 * 2  # bez sražení obvodu 2 a otvoru 1 mm (2 × 2 rohy)
    assert w.session.section.area == pytest.approx(area, rel=0.02)
    assert "Plocha řezu" in w.section_info.text()
    assert w.session.document.to_dict() == w.session.document.to_dict() and not \
        w.session.dirty  # řez model nemění

    set_text(w.section_field, "40")  # poloha číslem
    assert w.session.section_settings.position == 40
    w.section_slider.setValue(1000)  # posuvník na konec dílu → řez díl míjí
    assert w.session.section is None and "✕" in w.section_info.text()
    w.section_slider.setValue(500)
    assert w.session.section is not None
    action(w, "Otočit stranu řezu").trigger()
    assert w.session.section_settings.flipped
    w.section_combo.setCurrentIndex(w.section_combo.findData("Z"))
    w.section_combo.activated.emit(w.section_combo.currentIndex())
    assert w.session.section_settings.axis == "Z"
    assert w.session.section.area == pytest.approx(math.pi * (82.5**2 - 31**2)
                                                   - 4 * math.pi * 81, rel=1e-3)

    # řez rovnoběžně s plochou kliknutím (horní plocha → do hloubky)
    top = face_at(shown_part(w), 60, 0, 18)
    w.viewer.click([top], point=(60, 0, 18))
    action(w, "Řez rovnoběžně s vybranou plochou").trigger()
    assert w.session.section_settings.axis is None
    assert w.section_combo.currentData() == "face"

    target = tmp_path / "rez.dxf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(w, "Export řezu do DXF/SVG…").trigger()
    assert target.exists() and target.stat().st_size > 0

    # mapa tloušťky v řezu: kreslí se jen trojúhelníky zbylé poloviny
    action(w, "Mapa tloušťky stěny").trigger()
    nodes, triangles, colors, marker = w.viewer.thickness_map
    assert 0 < triangles < len(w.session.thickness_map.triangles)
    assert len(colors) == nodes > len(w.session.thickness_map.nodes)  # uzly na řezu navíc
    assert w.viewer.map_fill == w.session.section.faces  # plochy řezu vyplněné
    action(w, "Mapa tloušťky stěny").trigger()

    action(w, "Řez modelem").trigger()  # vypnout → zase celý díl
    assert w.viewer.parts[-1][0] is w.session.result.part and w.session.section is None
    assert slot_errors == []
