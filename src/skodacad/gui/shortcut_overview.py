"""Přehled klávesových zkratek a ovládání myší (P7.45) – jen pohled, nic nespouští.

Zkratky příkazů se čtou přímo z QAction okna (menu a pás karet, stejně jako hledání
příkazů P7.37), takže přehled nikdy nezastará: změněná zkratka se v něm ukáže sama.
Ovládání, které není příkazem (myš ve 3D, klávesy ve filtrech a ve stromu sestavy),
je pevný seznam ověřený proti `viewer.py`, `tree_filter.py` a `assembly_window.py`.
"""

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from skodacad.gui.command_search import collect_commands, plain_label
from skodacad.gui.tree_filter import SEARCH_ROLE, TreeFilter

MOUSE = "Myš ve 3D"
KEYS = "Ve stromu a filtrech"

# Společné ovládání 3D prohlížeče (viewer.py: _mouse_press/_mouse_move/_wheel/dvojklik/Esc).
VIEW_MOUSE = (
    ("Levé tažení", "Otáčení pohledu"),
    ("Prostřední/pravé tažení, Shift+levé", "Posun pohledu (Shift+levé i na trackpadu)"),
    ("Kolečko", "Přiblížení a oddálení k místu kurzoru"),
    ("Dvojklik", "Zobrazit celý model"),
)

PART_MOUSE = (
    ("Klik", "Vybrat plochu nebo hranu"),
    ("Ctrl/⌘+klik nebo Shift+klik", "Přidat nebo ubrat plochu či hranu z výběru"),
    ("Pravý klik", "Nabídka, co udělat s výběrem"),
    *VIEW_MOUSE,
    ("Alt+levé tažení", "Posun přiložené NDT sondy po povrchu"),
    ("Alt+kolečko", "Natočení přiložené NDT sondy o 15°"),
    ("Esc ve 3D", "Zrušit rozpracované tažení rukojeti vodítka"),
)

ASSEMBLY_MOUSE = (
    ("Klik", "Vybrat komponentu (díl) nebo plochu pro vazbu"),
    ("Ctrl/⌘+klik nebo Shift+klik", "Přidat nebo ubrat z výběru"),
    *VIEW_MOUSE,
    ("Esc ve 3D", "Zrušit rozpracované tažení rukojeti nebo výběr středu otáčení"),
)

FILTER_KEYS = (
    ("Enter nebo ↓ ve filtru", "Přejít na první nalezený řádek"),
    ("Esc ve filtru", "Zrušit filtr (zobrazí všechny řádky)"),
)

PART_KEYS = (
    ("Esc v náhledu nového prvku", "Zrušit náhled (model se nezmění)"),
    ("Ctrl/⌘+Enter v panelu AI", "Odeslat dotaz AI asistentovi"),
    *FILTER_KEYS,
)

# Akce se zkratkou mimo nabídky (platí jen v panelu) – jsou výše jako pevné řádky.
LOCAL_ACTIONS = frozenset({"Zrušit náhled prvku", "Odeslat"})

ASSEMBLY_KEYS = (
    ("Ctrl/⌘+A ve stromu", "Vybrat všechny komponenty (s filtrem jen nalezené)"),
    ("Esc ve stromu", "Zrušit výběr komponent"),
    ("Ctrl/⌘+klik, Shift+klik ve stromu", "Přidat do výběru, vybrat rozsah"),
    *FILTER_KEYS,
)


@dataclass(frozen=True)
class Shortcut:
    keys: str      # text zkratky v zápisu systému (na Macu ⌘, ⇧ …)
    command: str   # název příkazu bez „&“ a „…“
    place: str     # skupina: první úroveň nabídky, karta pásu nebo „Myš ve 3D“


def local_keys(text: str, platform: str | None = None) -> str:
    """Pevné řádky píší modifikátory obecně; na Macu ⌘ a ⌥, jinde Ctrl a Alt."""
    mac = (platform or sys.platform) == "darwin"
    return (text.replace("Ctrl/⌘", "⌘" if mac else "Ctrl")
            .replace("Alt+", "⌥+" if mac else "Alt+"))


def key_text(action) -> str:
    sequences = [sequence for sequence in action.shortcuts() if not sequence.isEmpty()]
    return ", ".join(sequence.toString(QKeySequence.SequenceFormat.NativeText)
                     for sequence in sequences)


def collect_shortcuts(menu_bar, groups=(), extra=()) -> list[Shortcut]:
    """Příkazy se zkratkou v pořadí nabídek, pak pevné řádky `extra` (skupina, řádky)."""
    rows = []
    for command in collect_commands(menu_bar, groups):
        keys = key_text(command.action)
        if keys:
            place = command.path.split(" › ")[0] if command.path else "Další příkazy"
            rows.append(Shortcut(keys, plain_label(command.action.text()).rstrip("…").strip(),
                                 place))
    for place, items in extra:
        rows.extend(Shortcut(local_keys(keys), text, place) for keys, text in items)
    return rows


def conflicts(menu_bar, groups=()) -> dict[str, list[str]]:
    """Zkratky, které má víc příkazů jednoho okna (Qt pak nespustí žádný)."""
    owners: dict[str, list[str]] = {}
    for command in collect_commands(menu_bar, groups, include_hidden=True):
        for sequence in command.action.shortcuts():
            if not sequence.isEmpty():
                owners.setdefault(sequence.toString(), []).append(
                    plain_label(command.action.text()))
    return {keys: names for keys, names in owners.items() if len(names) > 1}


class _GroupedFilter(TreeFilter):
    """Nadpisy skupin se nehledají a nepočítají – „Filtr: N z M zkratek“ jen řádky."""

    def _report(self, shown: int, total: int) -> None:
        super()._report(shown, total - self.tree.topLevelItemCount())


class ShortcutDialog(QDialog):
    def __init__(self, rows: list[Shortcut], parent=None, *, title: str = "Klávesové zkratky",
                 start: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("shortcut_overview")
        self.resize(720, 600)
        layout = QVBoxLayout(self)
        search = QKeySequence("Ctrl+Shift+P").toString(QKeySequence.SequenceFormat.NativeText)
        intro = QLabel("Zkratky příkazů se čtou přímo z nabídek, proto vždy odpovídají "
                       f"této verzi. Příkaz spustíš přes Najít příkaz ({search}).")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setObjectName("shortcut_tree")
        self.tree.setAccessibleName("Klávesové zkratky")
        self.tree.setHeaderLabels(["Zkratka", "Příkaz"])
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.filter = _GroupedFilter(self.tree, placeholder="Filtr zkratek…",
                                     nouns=("zkratky", "zkratek", "zkratek"))
        layout.addWidget(self.filter)
        layout.addWidget(self.tree)
        groups: dict[str, QTreeWidgetItem] = {}
        for row in rows:
            group = groups.get(row.place)
            if group is None:
                group = groups[row.place] = QTreeWidgetItem(self.tree, [row.place])
                group.setFirstColumnSpanned(True)
                font = group.font(0)
                font.setBold(True)
                group.setFont(0, font)
                group.setData(0, SEARCH_ROLE, "")  # nadpis sám nic nenajde
                group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item = QTreeWidgetItem(group, [row.keys, row.command])
            item.setData(0, SEARCH_ROLE, f"{row.keys} {row.command} {row.place}")
            item.setToolTip(1, row.command)
        self.tree.expandAll()
        self.rows = rows
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Zavřít")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.filter.focus()
        if start in groups and groups[start].childCount():
            # Ovládání myší: přehled otevřený rovnou na skupině (řádky ostatních zůstávají).
            self.tree.setCurrentItem(groups[start].child(0))
            self.tree.scrollToItem(groups[start], QAbstractItemView.ScrollHint.PositionAtTop)

    def current_place(self) -> str | None:
        item = self.tree.currentItem()
        return item.parent().text(0) if item is not None and item.parent() else None

    def shown_rows(self) -> list[tuple[str, str]]:
        return [(item.text(0), item.text(1)) for item in self.filter.visible_matches()
                if item.parent() is not None]


def show_shortcuts(window, groups=(), extra=(), *, title: str = "Klávesové zkratky",
                   start: str | None = None) -> None:
    dialog = ShortcutDialog(collect_shortcuts(window.menuBar(), groups, extra), window,
                            title=title, start=start)
    try:
        getattr(window, "_exec_dialog", lambda d: d.exec())(dialog)
    finally:
        dialog.deleteLater()
