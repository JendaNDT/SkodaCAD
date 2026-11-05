"""Search the window's existing commands, preserving their state and callbacks."""

import unicodedata
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QBrush, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)
from shiboken6 import isValid

from skodacad.gui.ui_colors import secondary_color


def plain_label(text):
    return text.split("\t", 1)[0].replace("&&", "\0").replace("&", "").replace("\0", "&")


def searchable(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


@dataclass(frozen=True)
class Command:
    action: QAction
    path: str
    parents: tuple[QAction, ...] = ()

    @property
    def visible(self):
        return all(isValid(action) and action.isVisible()
                   for action in (*self.parents, self.action))

    @property
    def available(self):
        return self.visible and all(action.isEnabled()
                                    for action in (*self.parents, self.action))


def collect_commands(menu_bar, groups=(), exclude=()):
    """Menu leaves first, then ribbon-only commands; reuse each QAction just once."""
    commands = []
    seen = {id(action) for action in exclude}

    def visit(actions, path, parents=()):
        for action in actions:
            if not isValid(action) or action.isSeparator() or not action.isVisible():
                continue
            if menu := action.menu():
                visit(menu.actions(), (*path, plain_label(action.text())), (*parents, action))
            elif id(action) not in seen and plain_label(action.text()).strip():
                seen.add(id(action))
                commands.append(Command(action, " › ".join(path), parents))

    visit(menu_bar.actions(), ())
    for path, actions in groups:
        visit(actions, path)
    return commands


class CommandSearchDialog(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Najít příkaz")
        self.setObjectName("command_search")
        self.resize(680, 460)
        self.commands = commands
        self.selected_command = None
        layout = QVBoxLayout(self)
        label = QLabel("&Hledat podle názvu nebo nabídky:")
        self.query = QLineEdit()
        self.query.setObjectName("command_query")
        self.query.setPlaceholderText("Např. uložit, průhlednost, parametry…")
        self.query.setClearButtonEnabled(True)
        label.setBuddy(self.query)
        layout.addWidget(label)
        layout.addWidget(self.query)
        self.results = QTreeWidget()
        self.results.setObjectName("command_results")
        self.results.setAccessibleName("Nalezené příkazy")
        self.results.setHeaderLabels(["Příkaz", "Nabídka", "Zkratka"])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setColumnWidth(0, 285)
        self.results.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.results)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("Zavřít")
        cancel.setAutoDefault(False)
        self.run_button = buttons.addButton("Spustit", QDialogButtonBox.ButtonRole.AcceptRole)
        self.run_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.query.textChanged.connect(self.refresh)
        self.query.installEventFilter(self)
        self.results.installEventFilter(self)
        self.results.currentItemChanged.connect(self._selection_changed)
        self.results.itemActivated.connect(lambda *_: self.accept())
        self._watched = list({id(action): action for command in commands
                              for action in (*command.parents, command.action)}.values())
        for action in self._watched:
            action.changed.connect(self.refresh)
        self.finished.connect(self._disconnect)
        self.refresh()
        self.query.setFocus()

    def _disconnect(self, *_):
        watched, self._watched = self._watched, []
        for action in watched:
            if isValid(action):
                action.changed.disconnect(self.refresh)

    def refresh(self, *_):
        previous = self.current_command()
        tokens = searchable(self.query.text()).split()
        matches = []
        for command in self.commands:
            if not command.visible:
                continue
            name = searchable(plain_label(command.action.text()))
            haystack = f"{name} {searchable(command.path)}"
            if all(token in haystack for token in tokens):
                matches.append((not all(token in name for token in tokens), command))
        matches.sort(key=lambda item: item[0])  # stable: menu order within each rank
        self.results.blockSignals(True)
        self.results.clear()
        current = None
        for _, command in matches:
            action = command.action
            name = plain_label(action.text())
            if not command.available:
                name += " [nedostupné]"
            item = QTreeWidgetItem([name, command.path,
                                   action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)])
            item.setData(0, Qt.ItemDataRole.UserRole, command)
            if not command.available:
                brush = QBrush(secondary_color(self.palette()))
                for column in range(3):
                    item.setForeground(column, brush)
            details = "Nyní nedostupné. " if not command.available else ""
            item.setToolTip(0, details + plain_label(action.text()))
            item.setToolTip(1, command.path)
            self.results.addTopLevelItem(item)
            if previous is not None and command.action is previous.action:
                current = item
        if current is None and matches:
            current = self.results.topLevelItem(0)
        self.results.setCurrentItem(current)
        self.results.blockSignals(False)
        self._selection_changed()

    def current_command(self):
        item = self.results.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, *_):
        command = self.current_command()
        available = command is not None and command.available
        self.run_button.setEnabled(available)
        if command is None:
            self.note.setText("Žádný příkaz neodpovídá hledání. Zkus kratší název.")
        elif not available:
            self.note.setText("Příkaz nyní není dostupný v aktuálním stavu okna nebo výběru.")
        else:
            hint = "Enter spustí · ↑/↓ vyberou · Esc zavře"
            state = ("Zapnuto. " if command.action.isChecked() else "Vypnuto. ") \
                if command.action.isCheckable() else ""
            self.note.setText(state + hint)

    def eventFilter(self, watched, event):
        if watched in (self.query, self.results) and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept()
                return True
            if watched is self.query and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                count = self.results.topLevelItemCount()
                if count:
                    row = self.results.indexOfTopLevelItem(self.results.currentItem())
                    row = max(0, min(count - 1, row + (1 if key == Qt.Key.Key_Down else -1)))
                    self.results.setCurrentItem(self.results.topLevelItem(row))
                    self.results.scrollToItem(self.results.currentItem())
                return True
        return super().eventFilter(watched, event)

    def accept(self):
        command = self.current_command()
        if command is not None and command.available:
            self.selected_command = command
            super().accept()
        else:
            self.refresh()


def show_command_search(window, groups=()):
    dialog = CommandSearchDialog(collect_commands(window.menuBar(), groups,
                                                 exclude=(window.command_search_action,)), window)
    try:
        execute = getattr(window, "_exec_dialog", lambda d: d.exec())
        accepted = execute(dialog) == QDialog.DialogCode.Accepted
        command = dialog.selected_command
    finally:
        dialog._disconnect()
        dialog.deleteLater()
    # Close the search first: commands may open their own modal dialog or close the owner.
    if accepted and command is not None and command.available:
        command.action.trigger()
