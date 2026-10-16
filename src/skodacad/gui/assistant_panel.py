"""Panel „AI asistent“: rozhovor s Claudem, který upravuje otevřený model.

Rozhovor (síť) běží v pomocném vlákně, aby okno nestálo. Každý krok s modelem ale provádí
hlavní vlákno (``_MainThread.call``) přes ``ModelSession`` – stejně jako formulář, se Zpět
a kontrolou. Po změně vlákno počká, až okno převezme přepočet (i z pomocného procesu), a
Claudovi pošle jeho souhrn. Celá odpověď je jeden krok Zpět.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.assistant import (
    EFFORTS,
    KEY_URL,
    MODELS,
    Assistant,
    AssistantError,
    AssistantSettings,
    ModelTools,
    ToolOutput,
    make_client,
    new_assistant,
    settings_path,
)

log = logging.getLogger(__name__)

WAIT_LIMIT = 600.0  # s – nejdéle čekání na přepočet jednoho kroku


class _Job:
    def __init__(self, fn: Any) -> None:
        self.fn = fn
        self.result: Any = None
        self.error: BaseException | None = None


class _MainThread(QObject):
    """Zavolá funkci v hlavním vlákně a počká na výsledek (volá se z pomocného vlákna)."""

    request = Signal(object)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.request.connect(self._run, Qt.ConnectionType.BlockingQueuedConnection)

    def _run(self, job: _Job) -> None:
        try:
            job.result = job.fn()
        except BaseException as exc:  # noqa: BLE001 – chyba se předá zpět do vlákna
            job.error = exc

    def call(self, fn: Any) -> Any:
        job = _Job(fn)
        if QThread.currentThread() is self.thread():
            self._run(job)
        else:
            self.request.emit(job)
        if job.error is not None:
            raise job.error
        return job.result


class _Worker(QThread):
    """Jeden dotaz na asistenta (síť) v pomocném vlákně."""

    event = Signal(str, str)
    done = Signal(str, str)  # (odpověď, chyba)

    def __init__(self, panel: AssistantPanel, text: str, document: dict, report: str):
        super().__init__(panel)
        self.panel, self.text, self.document, self.report = panel, text, document, report

    def run(self) -> None:
        panel = self.panel
        try:
            answer = panel.assistant.ask(
                self.text, self.document, self.report, panel.run_tool,
                lambda kind, value: self.event.emit(kind, value),
                lambda: panel.main.call(lambda: panel.window.session.document.to_dict()))
        except AssistantError as exc:
            self.done.emit("", str(exc))
        except Exception as exc:  # noqa: BLE001 – neočekávaná chyba nesmí shodit okno
            log.exception("Chyba AI asistenta")
            self.done.emit("", f"Neočekávaná chyba asistenta ({type(exc).__name__}: {exc}). "
                               "Podrobnosti jsou v souboru skodacad.log.")
        else:
            self.done.emit(answer, "")


class AssistantPanel(QWidget):
    """Rozhovor s AI asistentem nad modelem okna ``window`` (``MainWindow``)."""

    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        self.main = _MainThread(self)
        self.settings = AssistantSettings.load(settings_path(window.user_dir))
        self.client_factory = make_client  # testy podstrčí odpovědi bez sítě
        self.assistant: Assistant | None = None
        self.tools = ModelTools(window.session, self._look)
        self._worker: _Worker | None = None
        self._entries: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        self.history = QTextBrowser()
        self.history.setOpenExternalLinks(True)
        self.history.setMinimumHeight(160)
        self.history.setPlaceholderText(
            "Napiš dole česky, co s modelem udělat – třeba „zvětši přírubu na D 200“, "
            "„přidej 4 díry M5 do rohů“ nebo „udělej krabičku 100 × 60 × 40, stěna 2 mm“. "
            "AI model upraví, sama si výsledek zkontroluje a celou úpravu vrátíš jedním Zpět "
            "(Ctrl+Z). Poprvé zadej API klíč v Nastavení AI.")
        layout.addWidget(self.history, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Co upravit? (Ctrl+Enter odešle)")
        self.prompt.setFixedHeight(80)
        layout.addWidget(self.prompt)

        self.send_action = self._action("Odeslat", self.send, "Ctrl+Return")
        self.stop_action = self._action("Zastavit AI", self.stop)
        self.reset_action = self._action("Nová konverzace", self.new_conversation)
        self.settings_action = self._action("Nastavení AI…", self.edit_settings)
        buttons = QHBoxLayout()
        for item in (self.send_action, self.stop_action, self.reset_action,
                     self.settings_action):
            button = QToolButton()
            button.setDefaultAction(item)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._refresh()

    def _action(self, text: str, slot: Any, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda _checked=False: slot())
        self.addAction(action)
        return action

    # --- stav ----------------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._worker is not None

    def _refresh(self) -> None:
        busy = self.busy
        self.send_action.setEnabled(not busy)
        self.stop_action.setEnabled(busy)
        self.reset_action.setEnabled(not busy)
        self.settings_action.setEnabled(not busy)
        self.prompt.setReadOnly(busy)
        usage = (self.assistant.usage.describe(self.settings.model) if self.assistant
                 else "zatím nic")
        key = "" if self.settings.key() else " · chybí API klíč (Nastavení AI…)"
        state = "⏳ Pracuji… " if busy else ""
        self.status.setText(f"{state}{MODELS[self.settings.model]}, "
                            f"{EFFORTS[self.settings.effort]} · spotřeba: {usage}{key}")

    def _add(self, kind: str, text: str) -> None:
        if kind == "text" and self._entries and self._entries[-1][0] == "ai":
            self._entries[-1] = ("ai", self._entries[-1][1] + text)
        else:
            self._entries.append(("ai" if kind == "text" else kind, text))
        parts = []
        for entry_kind, value in self._entries:
            if entry_kind == "user":
                parts.append(f"**Ty:** {value}")
            elif entry_kind == "ai":
                parts.append(value)
            elif entry_kind == "tool":
                parts.append(f"*→ {value}*")
            elif entry_kind == "result":
                parts.append(f"  *{value}*")
            elif entry_kind == "error":
                parts.append(f"**⚠ {value}**")
            else:
                parts.append(f"*{value}*")
        self.history.setMarkdown("\n\n".join(parts))
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def history_text(self) -> str:
        return self.history.toPlainText()

    # --- akce -----------------------------------------------------------------------------

    def send(self) -> None:
        text = self.prompt.toPlainText().strip()
        session = self.window.session
        if self.busy:
            return
        if not text:
            self.window.statusBar().showMessage("Napiš nejdřív, co s modelem udělat.", 6000)
            return
        if session.document is None:
            session.new_document()
            self.window.after_assistant_change()
        try:
            if self.assistant is None:
                self.assistant = new_assistant(self.settings, self.tools,
                                               self.window.examples_dir,
                                               client=self.client_factory(self.settings))
        except AssistantError as exc:
            self._add("user", text)
            self._add("error", str(exc))
            return
        self.prompt.clear()
        self._add("user", text)
        session.begin_group()
        self.window.set_assistant_busy(True)
        self._worker = _Worker(self, text, session.document.to_dict(), self.tools.report())
        self._worker.event.connect(self._add)
        self._worker.done.connect(self._finished)
        self._worker.start()
        self._refresh()

    def _finished(self, answer: str, error: str) -> None:
        if self._worker is not None:
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        self.window.session.end_group()
        if error:
            self._add("error", error)
        elif not answer:
            self._add("info", "Hotovo.")
        self.window.set_assistant_busy(False)
        self.window.after_assistant_change()
        self._refresh()

    def stop(self) -> None:
        if self.assistant is not None and self.busy:
            self.assistant.cancel()
            self._add("info", "Zastavuji…")

    def new_conversation(self) -> None:
        if self.busy:
            return
        if self.assistant is not None:
            self.assistant.reset()
        self._entries.clear()
        self.history.clear()
        self._refresh()

    def model_replaced(self) -> None:
        """Otevřený jiný model: Claude začne novou konverzaci."""
        if self.assistant is not None and self.assistant.messages:
            self.assistant.reset()
            self._add("info", "— Otevřen jiný model, nová konverzace —")

    def edit_settings(self) -> None:
        dialog = AssistantSettingsDialog(self.settings, self)
        try:
            if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
                return
            self.apply_settings(dialog.values())
        finally:
            dialog.deleteLater()

    def apply_settings(self, settings: AssistantSettings) -> None:
        """Uloží nastavení do profilu; další dotaz už jde s novým klíčem a modelem."""
        settings.save(settings_path(self.window.user_dir))
        self.settings = settings
        if self.assistant is not None:
            self.assistant.settings = settings
            try:
                self.assistant.client = self.client_factory(settings)
            except AssistantError as exc:
                self._add("error", str(exc))
        self._refresh()

    def shutdown(self) -> None:
        """Před zavřením okna: zastavit rozhovor a počkat na vlákno."""
        if self._worker is None:
            return
        if self.assistant is not None:
            self.assistant.cancel()
        end = time.monotonic() + 10
        while self._worker is not None and self._worker.isRunning() \
                and time.monotonic() < end:
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()
            self._worker.wait(50)

    # --- kroky s modelem (volá pomocné vlákno) -------------------------------------------

    def run_tool(self, name: str, data: Any) -> ToolOutput:
        """Provede nástroj v hlavním vlákně a počká na přepočet (okno ho mezitím ukáže)."""
        self._wait_computed()
        output = self.main.call(lambda: self._apply(name, data))
        if output.changed:
            self._wait_computed()
            report = self.main.call(self.tools.report)
            output.content = f"{output.content}\n\n{report}"
        return output

    def _apply(self, name: str, data: Any) -> ToolOutput:
        output = self.tools.apply(name, data)
        if output.changed:
            self.window.after_assistant_change()
        return output

    def _wait_computed(self) -> None:
        end = time.monotonic() + WAIT_LIMIT
        while self.main.call(lambda: self.window.session.computing) \
                and time.monotonic() < end:
            time.sleep(0.05)

    def _look(self, view: str) -> bytes | None:
        """PNG dílu z 3D prohlížeče (hlavní vlákno)."""
        viewer = self.window.viewer
        if self.window.session.result is None or self.window.session.result.part is None:
            return None
        if view != "current" and hasattr(viewer, "set_standard_view"):
            viewer.set_standard_view(view)
        dump = getattr(viewer, "dump", None)
        if dump is None:
            return None
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dil.png"
            if not dump(str(path)) or not path.exists():
                return None
            return path.read_bytes()


class AssistantSettingsDialog(QDialog):
    """API klíč, model Claude a důkladnost."""

    def __init__(self, settings: AssistantSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Nastavení AI asistenta")
        layout = QVBoxLayout(self)
        info = QLabel(
            f"Asistent používá Claude API (Anthropic). Potřebuješ vlastní API klíč – vytvoříš "
            f"ho na <a href=\"{KEY_URL}\">console.anthropic.com</a> (účet s kreditem; "
            "předplatné Claude.ai API nezahrnuje). Úprava stojí orientačně 2–7 Kč u Opus, "
            "u Sonnet zhruba polovinu. Model (JSON) se posílá ke zpracování společnosti "
            "Anthropic. Klíč se uloží jen do tvého profilu "
            f"({Path('SkodaCAD', 'nastaveni.json')}); funguje i proměnná ANTHROPIC_API_KEY.")
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)
        form = QFormLayout()
        self.key_edit = QLineEdit(settings.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-ant-…")
        form.addRow("API klíč", self.key_edit)
        self.model_combo = QComboBox()
        for key, label in MODELS.items():
            self.model_combo.addItem(label, key)
        self.model_combo.setCurrentIndex(self.model_combo.findData(settings.model))
        form.addRow("Model", self.model_combo)
        self.effort_combo = QComboBox()
        for key, label in EFFORTS.items():
            self.effort_combo.addItem(label, key)
        self.effort_combo.setCurrentIndex(self.effort_combo.findData(settings.effort))
        form.addRow("Důkladnost", self.effort_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, 300)

    def values(self) -> AssistantSettings:
        return AssistantSettings(api_key=self.key_edit.text().strip(),
                                 model=self.model_combo.currentData(),
                                 effort=self.effort_combo.currentData())
