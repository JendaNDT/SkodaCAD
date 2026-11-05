"""Text filters above a QTreeWidget or a QFormLayout; they never change the model.

Rows are only hidden (``setHidden`` / ``setRowVisible``), never removed: Cocoa
accessibility keeps references to tree cells, so the filter must not rebuild the
tree. The current row and every selected row always stay visible, so nothing
selected is ever hidden (a hidden selected row could be changed by a later command
without being seen). Hiding a row only shortens the list; it never hides geometry
in the 3D view. A parameter row being edited or holding an error stays visible too.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui.command_search import searchable

SEARCH_ROLE = Qt.ItemDataRole.UserRole + 40


class FilterBox(QWidget):
    """Shared filter field and result note (Enter/↓ jump to the first match, Esc clears)."""

    applied = Signal()

    def __init__(self, *, placeholder: str, nouns: tuple[str, str, str], name: str,
                 tooltip: str, parent=None):
        super().__init__(parent)
        self.nouns = nouns  # genitiv po „z“: 1, 2–4, 5+ (prvku, prvků, prvků)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.field = QLineEdit()
        self.field.setObjectName(name)
        self.field.setPlaceholderText(placeholder)
        self.field.setAccessibleName(placeholder.split(" (")[0].rstrip("…"))
        self.field.setClearButtonEnabled(True)
        self.field.setToolTip(tooltip)
        layout.addWidget(self.field)
        self.note = QLabel()
        self.note.setObjectName(f"{name}_note")
        self.note.setWordWrap(True)
        self.note.setProperty("secondaryText", True)
        self.note.hide()
        layout.addWidget(self.note)
        self.field.textChanged.connect(self.apply)
        self.field.installEventFilter(self)

    @property
    def active(self) -> bool:
        return bool(self.tokens())

    def tokens(self) -> list[str]:
        return searchable(self.field.text()).split()

    def hits(self, text: str) -> bool:
        haystack = searchable(text)
        return all(token in haystack for token in self.tokens())

    def clear(self) -> None:
        self.field.clear()  # textChanged → apply

    def focus(self) -> None:
        self.field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.field.selectAll()

    def apply(self, *_) -> None:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def _jump(self, key) -> None:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def _report(self, shown: int, total: int) -> None:
        if not self.active:
            self.note.hide()
        else:
            if shown:
                self.note.setText(f"Filtr: {shown} z {total} {self._noun(total)}. "
                                  "Esc filtr zruší.")
            else:
                self.note.setText("Žádný řádek neodpovídá filtru. Zkus kratší text, "
                                  "Esc filtr zruší.")
            self.note.show()
        self.applied.emit()

    def _noun(self, count: int) -> str:
        one, few, many = self.nouns
        return one if count == 1 else few if 2 <= count <= 4 else many

    def eventFilter(self, watched, event):
        if watched is self.field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape and self.field.text():
                self.clear()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down):
                self._jump(key)
                return True
        return super().eventFilter(watched, event)


class TreeFilter(FilterBox):
    """Filter above a tree; the tree keeps its own selection and order."""

    def __init__(self, tree: QTreeWidget, *, placeholder: str, nouns: tuple[str, str, str],
                 parent=None):
        super().__init__(
            placeholder=placeholder, nouns=nouns, name="tree_filter", parent=parent,
            tooltip="Zobrazí jen řádky, které obsahují zadaný text. "
                    "Velikost písmen ani diakritika nerozhoduje. "
                    "Enter vybere první nalezený, Esc filtr zruší. Vybrané řádky "
                    "zůstávají vidět. Mění jen strom – model ani 3D se nemění.")
        self.field.setAccessibleName("Filtr stromu")
        self.tree = tree
        tree.currentItemChanged.connect(self.apply)
        tree.itemSelectionChanged.connect(self.apply)

    def _items(self, parent: QTreeWidgetItem | None = None):
        count = parent.childCount() if parent else self.tree.topLevelItemCount()
        for index in range(count):
            yield parent.child(index) if parent else self.tree.topLevelItem(index)

    def matches(self, item: QTreeWidgetItem) -> bool:
        text = item.data(0, SEARCH_ROLE)
        return self.hits(text if isinstance(text, str) else item.text(0))

    def visible_matches(self) -> list[QTreeWidgetItem]:
        """Matching rows in tree order (the kept current row is not a match)."""
        found = []

        def visit(parent):
            for item in self._items(parent):
                if not item.isHidden() and self.matches(item):
                    found.append(item)
                visit(item)

        visit(None)
        return found

    def apply(self, *_):
        tokens = self.tokens()
        current = self.tree.currentItem()
        shown = total = 0

        def visit(parent) -> bool:
            nonlocal shown, total
            any_visible = False
            for item in self._items(parent):
                total += 1
                hit = not tokens or self.matches(item)
                child_visible = visit(item)
                visible = hit or child_visible or item is current or item.isSelected()
                shown += hit
                if item.isHidden() == visible:  # change only what differs (AX friendly)
                    item.setHidden(not visible)
                any_visible = any_visible or visible
            return any_visible

        visit(None)
        self._report(shown, total)

    def _jump(self, key) -> None:
        found = self.visible_matches() if self.active else []
        if found:
            self.tree.setCurrentItem(found[0])
            self.tree.scrollToItem(found[0])
            self.tree.setFocus(Qt.FocusReason.OtherFocusReason)
        elif key == Qt.Key.Key_Down and not self.active:
            self.tree.setFocus(Qt.FocusReason.OtherFocusReason)


class FormFilter(FilterBox):
    """Filter above a QFormLayout of named fields (P7.42: parameters of the part).

    A row matches by its label (name) or the field text (value or expression).
    The row being edited and a row marked invalid stay visible."""

    def __init__(self, form: QFormLayout, *, placeholder: str, nouns: tuple[str, str, str],
                 parent=None):
        super().__init__(
            placeholder=placeholder, nouns=nouns, name="form_filter", parent=parent,
            tooltip="Zobrazí jen parametry, jejichž název nebo hodnota obsahuje zadaný "
                    "text. Velikost písmen ani diakritika nerozhoduje. Enter skočí do "
                    "prvního nalezeného pole, Esc filtr zruší. Upravované pole a pole "
                    "s chybou zůstávají vidět. Model se filtrem nemění.")
        self.form = form

    def rows(self) -> list[tuple[int, QLabel | None, QWidget]]:
        found = []
        for row in range(self.form.rowCount()):
            label = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = self.form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if field is not None and field.widget() is not None:
                found.append((row, label.widget() if label else None, field.widget()))
        return found

    def matches(self, label: QLabel | None, field: QWidget) -> bool:
        text = field.text() if isinstance(field, QLineEdit) else ""
        return self.hits(f"{label.text() if label else ''} {text}")

    def visible_matches(self) -> list[QWidget]:
        return [field for row, label, field in self.rows()
                if self.form.isRowVisible(row) and self.matches(label, field)]

    def apply(self, *_) -> None:
        focused = QApplication.focusWidget()
        shown = total = 0
        for row, label, field in self.rows():
            total += 1
            hit = not self.active or self.matches(label, field)
            shown += hit
            visible = hit or field is focused or bool(field.styleSheet())
            if self.form.isRowVisible(row) != visible:
                self.form.setRowVisible(row, visible)
        self._report(shown, total)

    def _jump(self, key) -> None:
        found = self.visible_matches() if self.active else [
            field for row, _, field in self.rows() if self.form.isRowVisible(row)]
        if found:
            found[0].setFocus(Qt.FocusReason.OtherFocusReason)
            if isinstance(found[0], QLineEdit):
                found[0].selectAll()
