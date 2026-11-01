"""Náhled přímé úpravy; původní model se změní až po potvrzení."""

import copy

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from skodacad.document import DocumentError
from skodacad.session import format_parameter_value, parse_parameter_text


class DirectEditDialog(QDialog):
    def __init__(self, window, kind, shapes, point, value=None, feature_id=None,
                 edited_feature=None):
        super().__init__(window)
        self.window, self.kind, self.shapes, self.point = window, kind, shapes, point
        self.feature_id = feature_id
        self.edited_feature = copy.deepcopy(edited_feature)
        key = "distance" if kind == "move_face" else "diameter"
        if edited_feature is not None:
            value = edited_feature.get(key, value)
        elif feature_id:
            value = window.session.feature(feature_id).get(key, value)
        self.preview = None
        self.setWindowTitle("Náhled přímé úpravy")
        layout = QVBoxLayout(self)
        self.info = QLabel("Náhled změní jen zobrazení. Model se změní až tlačítkem Potvrdit.")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        if kind == "face_diameter":
            warning = QLabel("U díry z prvku Díra se označení závitu ani tabulková velikost "
                             "touto úpravou nemění. Zkontroluj je v původním prvku.")
            warning.setWordWrap(True)
            layout.addWidget(warning)
        form = QFormLayout()
        self.value = QLineEdit(format_parameter_value(
            value if value is not None else (1 if kind == "move_face" else 10)))
        self.value.setPlaceholderText("Číslo nebo výraz s parametry, v mm")
        form.addRow("Posun [mm] (+ ven, − dovnitř):" if kind == "move_face"
                    else "Nový průměr [mm]:",
                    self.value)
        layout.addLayout(form)
        self.preview_button = QPushButton("Zobrazit náhled")
        self.preview_button.clicked.connect(self.calculate)
        layout.addWidget(self.preview_button)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Potvrdit")
        self.apply_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.value.textChanged.connect(self.invalidate)
        layout.addWidget(self.buttons)

    def showEvent(self, event):  # noqa: N802 – Qt API
        super().showEvent(event)
        self.move(self.window.mapToGlobal(QPoint(12, 90)))

    def invalidate(self):
        self.preview = None
        self.apply_button.setEnabled(False)
        self.message.setText("Hodnota se změnila – zobraz nový náhled.")
        self.window.viewer.show_part(self.window.session.display_part)

    def calculate(self):
        self.invalidate()
        try:
            value = parse_parameter_text(self.value.text())
            if self.edited_feature is not None:
                feature = copy.deepcopy(self.edited_feature)
                key = "distance" if self.kind == "move_face" else "diameter"
                feature[key] = value
                self.preview = self.window.session.preview_direct_feature(feature)
            else:
                self.preview = self.window.session.preview_direct_edit(
                    self.kind, self.shapes, self.point, value, self.feature_id)
        except DocumentError as exc:
            self.message.setText(str(exc))
            return
        self.window.viewer.show_part(self.preview.result.part)
        self.window.viewer.show_design_ghost(self.window.session.display_part)
        self.message.setText("Náhled je platný. Průhledně je zobrazen původní díl.")
        self.apply_button.setEnabled(True)
