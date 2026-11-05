"""Personal command pins and session history shared by the application windows."""

import json

from PySide6.QtCore import QIODevice, QObject, QSaveFile, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from skodacad.gui.command_search import collect_commands, plain_label

MAX_FAVORITES = 6
_MAX_RECENT = 6
_KINDS = ("part", "assembly")
_MAX_BYTES = 16_384


def _clean(items):
    if not isinstance(items, (list, tuple)):
        return ()
    keys = (key for key in items if isinstance(key, str) and key.isascii() and 0 < len(key) <= 120)
    return tuple(dict.fromkeys(keys))[:MAX_FAVORITES]


class FavoriteStore(QObject):
    changed = Signal(str)

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path
        self._items = dict.fromkeys(_KINDS, ())
        self._recent = dict.fromkeys(_KINDS, ())
        if path is None:
            return
        try:
            with path.open("rb") as stream:
                raw = stream.read(_MAX_BYTES + 1)
            if len(raw) <= _MAX_BYTES:
                data = json.loads(raw)
                if (isinstance(data, dict) and type(data.get("version")) is int
                        and data["version"] == 1):
                    self._items = {kind: _clean(data.get(kind)) for kind in _KINDS}
        except (OSError, ValueError, RecursionError):
            pass

    def get(self, kind):
        return self._items[kind]

    def recent(self, kind):
        return self._recent[kind]

    def record_use(self, kind, key):
        previous = self._recent[kind]
        self._recent[kind] = (key, *(item for item in previous if item != key))[:_MAX_RECENT]

    def replace(self, kind, keys):
        if self.get(kind) == (keys := _clean(keys)):
            return
        items = {**self._items, kind: keys}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps({"version": 1, **items}, ensure_ascii=True, indent=2).encode()
            target = QSaveFile(str(self.path))
            if (not target.open(QIODevice.OpenModeFlag.WriteOnly)
                    or target.write(data) != len(data) or not target.commit()):
                raise OSError(target.errorString())
        self._items = items
        self.changed.emit(kind)


def _catalogue(owner, groups, namespaces):
    # These code identifiers survive label, shortcut and menu changes. Anonymous
    # dynamic entries (e.g. example files) deliberately do not get saved IDs.
    keys = {}
    for prefix, source in (("window", owner), *namespaces):
        for name, value in vars(source).items():
            if isinstance(value, QAction):
                keys.setdefault(value, f"{prefix}.{name}")
        for name, value in vars(source).items():
            if isinstance(value, dict):
                for key, action in value.items():
                    if isinstance(key, str) and isinstance(action, QAction):
                        keys.setdefault(action, f"{prefix}.{name}.{key}")
    result = {}
    for command in collect_commands(owner.menuBar(), groups, include_hidden=True,
                                    exclude=(owner.command_search_action,)):
        key = command.action.property("favorite_id") or keys.get(command.action)
        if key:
            result[key] = command
    return result


class _FavoriteButton(QToolButton):
    def __init__(self, command):
        super().__init__()
        self.command = command
        self.setAutoRaise(True)
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setMaximumWidth(124)
        self.clicked.connect(self._run)
        for action in (*command.parents, command.action):
            action.changed.connect(self._sync)
        self._sync()

    @Slot()
    def _sync(self):
        action = self.command.action
        self.setEnabled(self.command.available)
        if not isValid(action):
            return
        label = plain_label(action.text())
        self.setAccessibleName(label)
        self.setIcon(action.icon())
        width = 87 if not action.icon().isNull() else 106
        text = self.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, width)
        self.setText(text.replace("&", "&&"))
        shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        self.setToolTip(label + (f" ({shortcut})" if shortcut else ""))
        self.setCheckable(action.isCheckable())
        self.setChecked(action.isChecked())

    @Slot()
    def _run(self):
        if self.command.available:
            self.command.action.trigger()
        if isValid(self):
            self._sync()


class FavoriteEditor(QDialog):
    def __init__(self, bar):
        super().__init__(bar.owner)
        self.setWindowTitle("Upravit oblíbené příkazy")
        self.setObjectName("favorite_editor")
        self.resize(430, 300)
        self.bar = bar
        self.keys = list(bar.keys)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pořadí shora dolů odpovídá tlačítkům zleva doprava."))
        self.items = QListWidget()
        self.items.setAccessibleName("Oblíbené příkazy v pořadí")
        layout.addWidget(self.items)
        controls = QHBoxLayout()
        self.up = QPushButton("Posunout výš")
        self.down = QPushButton("Posunout níž")
        self.remove = QPushButton("Odebrat")
        for button in (self.up, self.down, self.remove):
            button.setAutoDefault(False)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.note = QLabel("Další příkazy přidáš přes Najít příkaz…")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Uložit")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.items.currentRowChanged.connect(self._selection)
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.remove.clicked.connect(self._remove)
        self._fill(0)

    def _fill(self, row):
        self.items.clear()
        for key in self.keys:
            command = self.bar.commands.get(key)
            self.items.addItem(plain_label(command.action.text())
                               if command and isValid(command.action)
                               else "Příkaz již není dostupný")
        self.items.setCurrentRow(min(row, len(self.keys) - 1))
        self._selection(self.items.currentRow())

    def _selection(self, row):
        self.up.setEnabled(row > 0)
        self.down.setEnabled(0 <= row < len(self.keys) - 1)
        self.remove.setEnabled(row >= 0)

    def _move(self, offset):
        row = self.items.currentRow()
        target = row + offset
        if 0 <= row < len(self.keys) and 0 <= target < len(self.keys):
            self.keys[row], self.keys[target] = self.keys[target], self.keys[row]
            self._fill(target)

    def _remove(self):
        row = self.items.currentRow()
        if row >= 0:
            del self.keys[row]
            self._fill(row)

    def accept(self):
        try:
            self.bar.store.replace(self.bar.kind, self.keys)
        except OSError:
            self.note.setText("Oblíbené příkazy se nepodařilo uložit. Zkus to znovu.")
        else:
            super().accept()


class FavoriteBar(QToolBar):
    def __init__(self, owner, store, kind, groups=(), namespaces=()):
        super().__init__("Oblíbené příkazy", owner)
        self.setObjectName("favorite_commands")
        self.setMovable(False)
        self.setFloatable(False)
        self.toggleViewAction().setVisible(False)
        self.owner, self.store, self.kind = owner, store, kind
        self.commands = _catalogue(owner, groups, namespaces)
        self.command_keys = {command.action: key for key, command in self.commands.items()}
        for action in self.command_keys:
            action.triggered.connect(self._record_use)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(3, 0, 3, 0)
        layout.setSpacing(3)
        layout.addWidget(QLabel("Oblíbené:"))
        self._pins = QHBoxLayout()
        self._pins.setSpacing(3)
        layout.addLayout(self._pins)
        layout.addStretch(1)
        self.manage_action = QAction("Upravit oblíbené příkazy…", self)
        self.manage_action.triggered.connect(self.edit)
        edit = QToolButton()
        edit.setDefaultAction(self.manage_action)
        edit.setText("Upravit…")
        edit.setAccessibleName(self.manage_action.text())
        layout.addWidget(edit)
        self.addWidget(row)
        owner.addToolBarBreak()
        owner.addToolBar(self)
        store.changed.connect(self._refresh)
        self._refresh(kind)

    @property
    def keys(self):
        return self.store.get(self.kind)

    @Slot()
    def _record_use(self):
        key = self.command_keys.get(self.sender())
        if key is not None:
            self.store.record_use(self.kind, key)

    def pinned_buttons(self):
        return [self._pins.itemAt(i).widget() for i in range(self._pins.count())]

    @property
    def can_add(self):
        return len(self.keys) < MAX_FAVORITES

    def toggle(self, key):
        keys = list(self.keys)
        if key in keys:
            keys.remove(key)
        elif key in self.commands and len(keys) < MAX_FAVORITES:
            keys.append(key)
        else:
            return
        self.store.replace(self.kind, keys)

    @Slot(str)
    def _refresh(self, kind):
        if kind != self.kind:
            return
        while self._pins.count():
            widget = self._pins.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        for key in self.keys:
            if command := self.commands.get(key):
                if isValid(command.action):
                    self._pins.addWidget(_FavoriteButton(command))
        self.setVisible(bool(self.keys))

    @Slot()
    def edit(self):
        dialog = FavoriteEditor(self)
        try:
            self.owner._exec_dialog(dialog)
        finally:
            dialog.deleteLater()
