"""Text filter above a QTreeWidget: hides non-matching rows, never changes the model.

Rows are only hidden (``setHidden``), never removed: Cocoa accessibility keeps
references to tree cells, so the filter must not rebuild the tree. The current row
and every selected row always stay visible, so nothing selected is ever hidden
(a hidden selected row could be changed by a later command without being seen).
Hiding a row only shortens the tree; it never hides geometry in the 3D view.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from skodacad.gui.command_search import searchable

SEARCH_ROLE = Qt.ItemDataRole.UserRole + 40


class TreeFilter(QWidget):
    """Filter field and result note; the tree keeps its own selection and order."""

    applied = Signal()

    def __init__(self, tree: QTreeWidget, *, placeholder: str, nouns: tuple[str, str, str],
                 parent=None):
        super().__init__(parent)
        self.tree = tree
        self.nouns = nouns  # genitiv po „z“: 1, 2–4, 5+ (prvku, prvků, prvků)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.field = QLineEdit()
        self.field.setObjectName("tree_filter")
        self.field.setPlaceholderText(placeholder)
        self.field.setAccessibleName("Filtr stromu")
        self.field.setClearButtonEnabled(True)
        self.field.setToolTip("Zobrazí jen řádky, které obsahují zadaný text. "
                              "Velikost písmen ani diakritika nerozhoduje. "
                              "Enter vybere první nalezený, Esc filtr zruší. Vybrané řádky "
                              "zůstávají vidět. Mění jen strom – model ani 3D se nemění.")
        layout.addWidget(self.field)
        self.note = QLabel()
        self.note.setObjectName("tree_filter_note")
        self.note.setWordWrap(True)
        self.note.setProperty("secondaryText", True)
        self.note.hide()
        layout.addWidget(self.note)
        self.field.textChanged.connect(self.apply)
        self.field.installEventFilter(self)
        tree.currentItemChanged.connect(self.apply)
        tree.itemSelectionChanged.connect(self.apply)

    @property
    def active(self) -> bool:
        return bool(self.tokens())

    def tokens(self) -> list[str]:
        return searchable(self.field.text()).split()

    def clear(self) -> None:
        self.field.clear()  # textChanged → apply

    def focus(self) -> None:
        self.field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.field.selectAll()

    def _items(self, parent: QTreeWidgetItem | None = None):
        count = parent.childCount() if parent else self.tree.topLevelItemCount()
        for index in range(count):
            yield parent.child(index) if parent else self.tree.topLevelItem(index)

    def matches(self, item: QTreeWidgetItem) -> bool:
        text = item.data(0, SEARCH_ROLE)
        haystack = searchable(text if isinstance(text, str) else item.text(0))
        return all(token in haystack for token in self.tokens())

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
        if not tokens:
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
                found = self.visible_matches() if self.active else []
                if found:
                    self.tree.setCurrentItem(found[0])
                    self.tree.scrollToItem(found[0])
                    self.tree.setFocus(Qt.FocusReason.OtherFocusReason)
                elif key == Qt.Key.Key_Down and not self.active:
                    self.tree.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        return super().eventFilter(watched, event)
