"""Náhled vložení i úpravy prvku; návrh patří oddělené ModelSession."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.features import REPEATABLE_FEATURES, describe, short_label
from skodacad.gui.feature_editor import FeatureEditor
from skodacad.gui.floating import ContentScroll
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
        layout.setContentsMargins(4, 0, 4, 0)
        # P7.52: nadpis je v hlavičce karty (malý titulek „… · náhled“, velký název prvku),
        # vysvětlení v bublině tlačítka Potvrdit – karta se vejde bez posouvání.
        self.kind_title = "Úprava prvku · náhled" if preview.editing else "Nový prvek · náhled"
        self.hint_text = ("Uprav hodnoty a prohlédni si celý výsledek. Potvrdit přijme úpravu "
                          "včetně navazujících prvků; Zrušit ponechá původní díl."
                          if preview.editing else
                          "Uprav hodnoty a prohlédni si náhled. Potvrdit přidá prvek do stromu; "
                          "Zrušit ponechá původní díl.")
        self.editor = FeatureEditor(profile_editor=self.edit_profile)
        session = preview.session
        index = session.feature_index(preview.feature_id)
        before = session.document.features[:index]
        self.editor.show_feature(session.feature(preview.feature_id),
                                 [(f["id"], describe(f)) for f in before if f["type"] == "sketch"],
                                 [(f["id"], short_label(f)) for f in before
                                  if f["type"] in REPEATABLE_FEATURES])
        self.editor.wall_panel.hide()
        for hint in self.editor.findChildren(QLabel, "edges_hint"):
            hint.hide()  # během náhledu se ve 3D hrany nevybírají (P7.61)
        if self.editor.help.text():  # popis druhu prvku v bublině nadpisu (místo v kartě)
            self.editor.title.setToolTip(self.editor.help.text())
            self.editor.help.hide()
        if session.feature(preview.feature_id)["type"] == "guided_loft":
            guides = self.editor.form.widget("guides")
            guides.set_selection(window._guide_edit_corner, window._guide_edit_handle)
            guides.drag_step.setValue(window._guide_drag_step)
            guides.drag_direction.setCurrentIndex(
                guides.drag_direction.findData(window._guide_drag_direction))
        self.editor.guide_selected.connect(
            lambda row: setattr(window, "_guide_edit_corner", row))
        self.editor.guide_handle_selected.connect(
            lambda handle: setattr(window, "_guide_edit_handle", handle))
        self.editor.guide_step_changed.connect(window._guide_step_changed)
        self.editor.guide_direction_changed.connect(window._guide_direction_changed)
        self.scroll = scroll = ContentScroll()  # celý formulář; karta naroste (P7.52)
        scroll.setWidget(self.editor)
        layout.addWidget(scroll, 1)
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setMaximumHeight(110)
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.message.setObjectName("preview_message")
        self.message.setProperty("cardInfo", True)  # rámeček --accentbg (návrh 3a)
        layout.addWidget(self.message)
        self.refresh_button = QPushButton("Náhled")  # v patičce, ať karta neposouvá
        self.refresh_button.setObjectName("refresh_feature_preview")
        self.refresh_button.setProperty("role", "secondary")
        self.refresh_button.setToolTip("Zobrazit náhled s aktuálními hodnotami")
        self.refresh_button.setAccessibleName("Zobrazit náhled")
        self.refresh_button.clicked.connect(self.refresh)
        # Náhled se obnovuje sám po každé změně; tlačítko je jen pro nový pokus po chybě
        # (rám 3a má v patičce jen Zrušit a Potvrdit, P7.61).
        self.refresh_button.hide()
        # P7.52: patička jako v návrhu 1a – „Esc zahodí“, Zrušit (vedlejší), Potvrdit.
        buttons = QHBoxLayout()
        self.esc_hint = QLabel("Esc zahodí")
        self.esc_hint.setProperty("cardHint", True)
        self.accept_button = QPushButton("Potvrdit")
        self.accept_button.setObjectName("confirm_feature_preview")
        self.accept_button.setProperty("role", "primary")
        self.accept_button.setToolTip(self.hint_text)
        self.accept_button.setDefault(False)
        self.cancel_button = QPushButton("Zrušit")
        self.cancel_button.setObjectName("cancel_feature_preview")
        self.cancel_button.setProperty("role", "secondary")
        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(lambda: self.finished.emit(False))
        buttons.addWidget(self.esc_hint)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.accept_button)
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
        self.refresh_button.show()
        self._dirty = True
        self.accept_button.setEnabled(False)
        self._message(f"{message}\nZobrazen je původní díl.")
        self._show_original()

    def _show_original(self):
        self._last_result = None
        self.window.viewer.show_part(self.window.session.display_part)
        self.window.viewer.disable_model_selection()
        self.window.viewer.highlight_preview = False  # původní díl: vybraný prvek růžově
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
        failed = not session.computing and (
            bool(session.failure) or (result is not None and not result.ok))
        self.refresh_button.setVisible(failed)
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
            # Rám 3a: co svítí, že se dá otáčet a co počká na Potvrdit; objem zůstává.
            self._message("Náhled je připravený" +
                          (f": objem {number(props.volume_mm3, 3)} mm³, "
                           f"počet těles {props.solids}." if props else ", skica je platná.") +
                          " Hrany prvku svítí ve 3D modře, pohled můžeš dál otáčet. "
                          "Uložení a export počkají na Potvrdit.")
        if ready and result is not self._last_result:
            first = self._last_result is None
            self._last_result = result
            self.window.viewer.show_part(session.display_part,
                                         fit=first and self.window.session.display_part is None)
            self.window.viewer.highlight_preview = True  # hrany náhledu modře (rám 3a)
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
