"""Native layout study; no production changes or saved user models.

The proposal manipulates the existing widgets in a disposable test window.
It is a layout experiment, not an implementation of panel persistence.
"""

from __future__ import annotations

import copy
import json
import platform
import subprocess
import traceback
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QTimer, qVersion
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui.app import _screenshot
from skodacad.gui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out/p7-layout-study"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "profile").mkdir(exist_ok=True)


def contrast(foreground, background):
    def luminance(color):
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                  for v in (color.redF(), color.greenF(), color.blueF())]
        return sum(a * b for a, b in zip(values, (.2126, .7152, .0722), strict=True))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def metrics(window, variant, requested):
    form = window.feature_editor.form
    guides = form.widget("guides")
    field = guides.edits[0, 0, 0]
    scroll = window.editor_dock.widget()
    viewport = scroll.viewport() if isinstance(scroll, QScrollArea) else scroll
    background = window.palette().color(QPalette.ColorRole.Window)
    text = field.text()
    return {
        "variant": variant, "requested_window": requested,
        "actual_window": [window.width(), window.height()],
        "viewer": [window.viewer.width(), window.viewer.height()],
        "viewer_width_fraction": window.viewer.width() / window.width(),
        "model_dock_width": window.model_dock.width(),
        "editor_viewport": [viewport.width(), viewport.height()],
        "guide_x1_field_width": field.contentsRect().width(),
        "guide_x1_text": text,
        "guide_x1_estimated_text_width": field.fontMetrics().horizontalAdvance(text),
        "feature_name_field_width": form.widget("name").contentsRect().width(),
        "part_name_field_width": window.name_edit.contentsRect().width(),
        "tree_visible_height": window.tree.height(),
        "background": background.name(),
        "legacy_help_contrast": contrast(QColor("#555555"), background),
        "proposed_help_color": (window._study_help.name()
                                if hasattr(window, "_study_help") else None),
        "proposed_help_contrast": contrast(window._study_help, background)
        if hasattr(window, "_study_help") else None,
        "document_volume_mm3": window.session.result.part.volume,
    }


def readable_help(window):
    background = window.palette().color(QPalette.ColorRole.Window)
    foreground = window.palette().color(QPalette.ColorRole.WindowText)
    result = QColor.fromRgbF(*[
        .8 * a + .2 * b for a, b in zip(
            (foreground.redF(), foreground.greenF(), foreground.blueF()),
            (background.redF(), background.greenF(), background.blueF()), strict=True)
    ])
    # Preserve native palette if a dimmed foreground would fail the design target.
    return result if contrast(result, background) >= 4.5 else foreground


def reflow_guides(editor):
    step, direction, edits = editor.drag_step, editor.drag_direction, editor.edits
    for child in editor.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        child.hide()
    shiboken6.delete(editor.layout())
    layout = QVBoxLayout(editor)
    for title, control in (("Krok tažení [mm]", step), ("Směr tažení", direction)):
        layout.addWidget(QLabel(title))
        layout.addWidget(control)
        control.show()
    layout.addWidget(QLabel("Vodítko"))
    picker = QComboBox()
    picker.addItems(["A · X+ Y+", "B · X− Y+", "C · X− Y−", "D · X+ Y−"])
    layout.addWidget(picker)
    pages = []
    for row in range(4):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        for handle in range(2):
            grid.addWidget(QLabel(f"Rukojeť {handle + 1}"), 3 * handle, 0, 1, 2)
            for axis, label in enumerate(("X [mm]", "Y [mm]")):
                grid.addWidget(QLabel(label), 3 * handle + 1, axis)
                edit = edits[row, handle, axis]
                edit.setMinimumWidth(110)
                grid.addWidget(edit, 3 * handle + 2, axis)
                edit.show()
        layout.addWidget(page)
        page.setVisible(row == 0)
        pages.append(page)
    def selected(row):
        for index, page in enumerate(pages):
            page.setVisible(index == row)
        editor.buttons.button(row).click()
    picker.currentIndexChanged.connect(selected)
    note = QLabel("Výška rukojetí je pevná. Puštění myši ověří změnu, Esc náhled zruší.")
    note.setWordWrap(True)
    layout.addWidget(note)
    editor._study_picker, editor._study_pages = picker, pages


def prototype(window):
    before = copy.deepcopy(window.session.document)
    undo = len(window.session._undo)
    docks = [window.editor_dock, window.measure_dock, window.map_dock,
             window.section_dock, window.ndt_dock, window.audit_dock,
             window.design_dock, window.assistant_dock]
    titles = [dock.windowTitle() for dock in docks]
    for dock in docks[1:]:
        window.tabifyDockWidget(docks[0], dock)
    for dock in docks:
        dock.setMinimumWidth(350)
        title = QWidget()
        row = QHBoxLayout(title)
        row.setContentsMargins(8, 5, 8, 5)
        picker = QComboBox()
        picker.addItems(titles)
        picker.setCurrentIndex(docks.index(dock))
        picker.setAccessibleName("Zobrazený pravý panel")
        picker.currentIndexChanged.connect(lambda index: docks[index].raise_())
        row.addWidget(picker)
        dock.setTitleBarWidget(title)
        dock._study_picker = picker
    for tab in window.findChildren(QTabBar):
        tab.hide()
    window.editor_dock.raise_()
    window.model_dock.setMinimumWidth(250)
    window.description_label.hide()
    info_layout = window.name_edit.parentWidget().layout()
    info_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    info_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    # In the proposal the compact actions keep their full accessible names/tooltips.
    for button, text in ((window.add_feature_button, "+ Přidat"),):
        button.setText(text)
    for button in window.model_dock.findChildren(QToolButton):
        action = button.defaultAction()
        if action is not None:
            if action is window.add_parameter_action:
                button.setText("+")
            elif action in (window.delete_parameter_action, window.delete_feature_action):
                button.setText("−")
            elif action is window.move_up_action:
                button.setText("↑")
            elif action is window.move_down_action:
                button.setText("↓")
            button.setAccessibleName(action.text())
            button.setToolTip(action.text())
    for index in range(window.tree.topLevelItemCount()):
        item = window.tree.topLevelItem(index)
        feature = window.session.feature(item.data(0, Qt.ItemDataRole.UserRole))
        full = item.text(0)
        item.setText(0, "✓ " + feature.get("name", feature["id"]))
        item.setToolTip(0, full)
    window.feature_editor.form._layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    reflow_guides(window.feature_editor.form.widget("guides"))
    window._study_help = readable_help(window)
    color = window._study_help.name()
    for label in window.findChildren(QLabel):
        if "#555" in label.styleSheet() or "#666" in label.styleSheet():
            label.setStyleSheet(f"color: {color};")
    label = window.feature_editor.title
    label.setText(label.text().replace("#555", color).replace("#777", color))
    QApplication.processEvents()
    assert window.session.document == before and len(window.session._undo) == undo


app = QApplication([])
app.setApplicationName("ŠkodaCAD – studie rozložení")
window = MainWindow(examples_dir=ROOT / "examples", user_dir=OUT / "profile")
window.show()


def run():
    exit_code = 0
    try:
        assert window.open_model(ROOT / "examples/rizeny_prechod.json", template=True)
        window._selected_id = "rizeny"
        window._reload_all()
        before = copy.deepcopy(window.session.document)
        records = []
        for variant in ("baseline", "proposal"):
            if variant == "proposal":
                prototype(window)
            for width, height in ((1470, 866), (1280, 800), (1024, 720)):
                window.move(0, 33)
                frame_extra = window.frameGeometry().height() - window.height()
                window.resize(width, height - frame_extra)
                window.resizeDocks([window.model_dock, window.editor_dock],
                                   [380, 360] if variant == "baseline" else [260, 370],
                                   Qt.Orientation.Horizontal)
                QApplication.processEvents()
                window.viewer.fit_all()
                QApplication.processEvents()
                records.append(metrics(window, variant, [width, height]))
                _screenshot(window, OUT / f"{variant}-{width}.png")
                if variant == "baseline" and width == 1470:
                    window.viewer.dump(str(OUT / "part-baseline.png"))
                    guides = window.feature_editor.form.widget("guides")
                    for row, corner in enumerate("ABCD"):
                        guides.buttons.button(row).click()
                        for view in ("iso", "front", "top"):
                            window.viewer.set_standard_view(view)
                            QApplication.processEvents()
                            window.viewer.dump(str(OUT / f"part-{corner}-{view}.png"))
                    guides.buttons.button(0).click()
                    window.viewer.set_standard_view("iso")
                assert window.session.document == before
            if variant == "proposal":
                guides = window.feature_editor.form.widget("guides")
                for row in range(4):
                    guides._study_picker.setCurrentIndex(row)
                    QApplication.processEvents()
                    assert guides.selected_index == row
                    assert guides.edits[row, 0, 0].isVisible()
                    assert window.session.document == before
                guides._study_picker.setCurrentIndex(0)
                current = window.editor_dock
                for dock in (window.measure_dock, window.ndt_dock, window.editor_dock):
                    current._study_picker.setCurrentIndex(docks_index(window, dock))
                    QApplication.processEvents()
                    assert not dock.visibleRegion().isEmpty()
                    assert window.session.document == before
                    current = dock
        data = {
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "platform": platform.platform(), "qt": qVersion(),
            "available_screen": [window.screen().availableGeometry().width(),
                                 window.screen().availableGeometry().height()],
            "records": records, "document_unchanged": True,
            "scope": "Automatic native layout experiment, not production or author acceptance",
        }
        (OUT / "native-study.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
    except Exception:
        exit_code = 1
        traceback.print_exc()
    finally:
        window.session.dirty = False
        window.close()
        app.exit(exit_code)


def docks_index(window, dock):
    return [window.editor_dock, window.measure_dock, window.map_dock, window.section_dock,
            window.ndt_dock, window.audit_dock, window.design_dock,
            window.assistant_dock].index(dock)


QTimer.singleShot(0, run)
raise SystemExit(app.exec())
