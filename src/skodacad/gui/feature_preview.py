"""Pravý panel nového prvku; rozepsaný návrh patří oddělené ModelSession."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.features import REPEATABLE_FEATURES, describe, short_label
from skodacad.gui.feature_editor import FeatureEditor
from skodacad.gui.sketcher import SketcherDialog
from skodacad.inspection import number


class FeaturePreviewPanel(QWidget):
    finished = Signal(bool)

    def __init__(self, window, preview):
        super().__init__()
        self.setObjectName("feature_preview")
        self.window, self.preview = window, preview
        self._collecting = False
        self._dirty = False
        self._closed = False
        self._last_result = None
        self._listened = set()
        layout = QVBoxLayout(self)
        heading = QLabel("<b>Nový prvek · náhled</b>")
        layout.addWidget(heading)
        hint = QLabel("Uprav hodnoty a prohlédni si náhled. Potvrdit přidá prvek do stromu; "
                      "Zrušit ponechá původní díl.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.editor = FeatureEditor(profile_editor=self.edit_profile)
        session = preview.session
        index = session.feature_index(preview.feature_id)
        before = session.document.features[:index]
        self.editor.show_feature(session.feature(preview.feature_id),
                                 [(f["id"], describe(f)) for f in before if f["type"] == "sketch"],
                                 [(f["id"], short_label(f)) for f in before
                                  if f["type"] in REPEATABLE_FEATURES])
        self.editor.wall_panel.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        layout.addWidget(scroll, 1)
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setMaximumHeight(110)
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.message.setObjectName("preview_message")
        layout.addWidget(self.message)
        self.refresh_button = QPushButton("Zobrazit náhled")
        self.refresh_button.setObjectName("refresh_feature_preview")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        buttons = QHBoxLayout()
        self.accept_button = QPushButton("Potvrdit")
        self.accept_button.setObjectName("confirm_feature_preview")
        self.accept_button.setDefault(False)
        self.cancel_button = QPushButton("Zrušit")
        self.cancel_button.setObjectName("cancel_feature_preview")
        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(lambda: self.finished.emit(False))
        buttons.addWidget(self.accept_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        self.editor.changed.connect(lambda *_: self.refresh())
        self.editor.invalid.connect(self.invalid)
        self._listen()

    def _message(self, text):
        self.message.setText(text)
        self.message.setToolTip(text)

    def _listen(self):
        for cls in (QLineEdit, QPlainTextEdit):
            for edit in self.editor.findChildren(cls):
                if edit not in self._listened:
                    edit.textChanged.connect(self.inputs_changed)
                    self._listened.add(edit)

    def inputs_changed(self):
        if self._closed or self._collecting:
            return
        self._dirty = True
        self.accept_button.setEnabled(False)
        self._message("Hodnoty se změnily – připravuji nový náhled…")
        self.timer.start()

    def invalid(self, message):
        self._dirty = True
        self.accept_button.setEnabled(False)
        self._message(f"{message}\nZobrazen je původní díl.")
        self._show_original()

    def _show_original(self):
        self._last_result = None
        self.window.viewer.show_part(self.window.session.display_part)
        self.window.viewer.disable_model_selection()
        self.window.viewer.highlight(self.window.session.feature_highlight(self.window._selected_id)
                                     if self.window._selected_id else [])

    def refresh(self):
        if self._closed or self._collecting:
            return
        self.timer.stop()
        self._collecting = True
        try:
            if not self.editor.form.commit_pending():
                return
            self.preview.session.update_feature(self.preview.feature_id, self.editor.form.data)
            if self.preview.session.failure:
                self.preview.session.rebuild()  # retry a crashed worker with unchanged inputs
            self._dirty = False
        except DocumentError as exc:
            self.invalid(str(exc))
            return
        finally:
            self._collecting = False
            self._listen()
        self.show_result()

    def poll(self):
        if self._closed:
            return
        if self.preview.session.poll():
            self.show_result()

    def show_result(self):
        session = self.preview.session
        result = session.result
        ready = not self._dirty and self.preview.ready
        self.accept_button.setEnabled(ready)
        if self._dirty:
            return
        if session.computing:
            self._message("Počítám náhled… Zrušit je dostupné i během výpočtu.")
        elif session.failure:
            self._message(f"{session.failure}\nZobrazen je původní díl.")
            self._show_original()
        elif result is not None and not result.ok:
            self._message(f"{result.first_error.message}\nZobrazen je původní díl.")
            self._show_original()
        elif ready:
            props = session.properties
            self._message("Náhled je připravený. " +
                                 (f"Objem {number(props.volume_mm3, 3)} mm³, "
                                  f"počet těles {props.solids}." if props else "Skica je platná."))
        if ready and result is not self._last_result:
            first = self._last_result is None
            self._last_result = result
            self.window.viewer.show_part(session.display_part,
                                         fit=first and self.window.session.display_part is None)
            self.window.viewer.highlight(session.feature_highlight(self.preview.feature_id))
            self.window.viewer.disable_model_selection()
            if first and self.window.session.display_part is None:
                self.window.viewer.fit_all()

    def accept(self):
        if self._closed:
            return
        self.refresh()  # also protects against a click before a pending text timer fires
        if not self.accept_button.isEnabled():
            return
        try:
            self.window.session.apply_feature_preview(self.preview)
        except DocumentError as exc:
            self.invalid(str(exc))
            return
        self.finished.emit(True)

    def shutdown(self):
        self._closed = True
        self.timer.stop()
        self.preview.cancel()

    def edit_profile(self, profile):
        session = self.preview.session
        projection = session.sketch_projection(profile, feature_id=self.preview.feature_id)
        dialog = SketcherDialog(profile, session.solve_profile, self.window, projection)
        try:
            if self.window._exec_dialog(dialog) == QDialog.DialogCode.Accepted:
                return dialog.result_profile()
            return None
        finally:
            dialog.deleteLater()
