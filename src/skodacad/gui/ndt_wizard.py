"""NDT průvodce v pravé kartě (P7.55, rámy 2c a 3d návrhu 1a).

Kroky studie (u UT: 1 Kontrolovaná oblast → 2 Sonda → 3 Přiložení sondy → 4 Geometrické
pokrytí) se **odvozují ze stavu studie**, nic se neukládá. Hotový krok je jeden řádek
(zelený kruh s ✓, název, shrnutí, „Změnit“), aktivní krok je vnořená karta s ovládáním,
budoucí krok je poloprůhledný (jen název a co ho odemkne). „Další“ jde jen u splněného
kroku. Ovládání v krocích jsou dosavadní widgety panelu NDT – průvodce je jen přeskupí.

Povinné upozornění metody zůstává v kartě vždy celé (rozhodnutí R7); odkaz
„Celé upozornění“ ukáže závazné vymezení metody z ``docs/ndt`` (přibalené v aplikaci).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui import ui_theme

# Závazná vymezení metod (přibalená v aplikaci do docs/ndt, viz packaging/skodacad.spec).
SCOPE_FILES = {"UT": "04-zavazne-vymezeni-ut.md", "PT": "20-vymezeni-pt.md",
               "MT": "22-vymezeni-mt.md", "RT": "24-vymezeni-rt.md"}
BADGES = {"ok": ("✓ platná", "ok"), "stale": ("⚠ zastaralá", "warn"),
          "incomplete": ("⚠ neúplná", "warn"), "broken": ("✕ neplatná vazba", "err")}
CIRCLE = 20


def scope_path(method: str) -> Path | None:
    """Soubor závazného vymezení metody (vývoj: repozitář, aplikace: přibalená data)."""
    name = SCOPE_FILES.get(method)
    if name is None:
        return None
    roots = [Path(__file__).resolve().parents[3], Path(getattr(sys, "_MEIPASS", "."))]
    for root in roots:
        path = root / "docs" / "ndt" / name
        if path.is_file():
            return path
    return None


def scope_text(method: str) -> str:
    """Celé závazné vymezení metody (Markdown), nebo prázdný text, když soubor chybí."""
    path = scope_path(method)
    try:
        return path.read_text(encoding="utf-8") if path is not None else ""
    except OSError:
        return ""


class ScopeDialog(QDialog):
    """„Celé upozornění“: závazné vymezení metody, jen ke čtení."""

    def __init__(self, method: str, disclaimer: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Závazné vymezení {method}")
        self.resize(640, 560)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setObjectName("ndt_scope_text")
        self.browser.setOpenExternalLinks(False)
        text = scope_text(method)
        if text:
            self.browser.setMarkdown(text)
        else:  # soubor nenalezen – aspoň povinné upozornění doslova
            self.browser.setPlainText(disclaimer)
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


@dataclass(frozen=True)
class StepState:
    """Stav kroku pro průvodce: hotový, dostupný a krátké shrnutí / co ho odemkne."""

    done: bool
    summary: str = ""
    skippable: bool = False  # nesplněný krok neblokuje další (přiložení u návrhu poloh)


def _circle(widget: QLabel, text: str, kind: str) -> None:
    """Kruh 20 px s číslem (aktivní, budoucí) nebo ✓ (hotový)."""
    t = ui_theme.tokens()
    styles = {"done": (t["ok"], "#ffffff", "none"),
              "active": (t["btn"], "#ffffff", "none"),
              "future": ("transparent", t["fg3"], f"1px solid {t['fg3']}")}
    background, color, border = styles[kind]
    widget.setText(text)
    widget.setStyleSheet(f"background: {background}; color: {color}; border: {border};"
                         f" border-radius: {CIRCLE // 2}px; font-size: 11px; font-weight: 700;")


class WizardStep(QFrame):
    """Jeden krok průvodce: hlavička (kruh, název, shrnutí, Změnit) a obsah aktivního kroku."""

    change_requested = Signal()

    def __init__(self, number: int, title: str, body: QWidget, short: str | None = None,
                 parent=None, auto_next: bool = False) -> None:
        super().__init__(parent)
        self.number, self.title = number, title
        self.auto_next = auto_next  # výpočet: po dokončení sám otevře další krok (mapu)
        self.short = short or title[0].lower() + title[1:]  # „Další: pokrytí“
        self.setObjectName("ndt_step")
        self.setProperty("stepState", "future")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.circle = QLabel()
        self.circle.setFixedSize(CIRCLE, CIRCLE)
        self.circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.circle, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("ndt_step_title")
        self.title_label.setWordWrap(True)  # dlouhé doporučené názvy map (MT, RT)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("ndt_step_summary")
        self.summary_label.setProperty("cardHint", True)
        self.summary_label.setWordWrap(True)
        texts.addWidget(self.title_label)
        texts.addWidget(self.summary_label)
        head.addLayout(texts, 1)
        self.change = QPushButton("Změnit")
        self.change.setObjectName("ndt_step_change")
        self.change.setFlat(True)
        self.change.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change.setAccessibleName(f"Změnit krok {number}: {title}")
        self.change.clicked.connect(self.change_requested.emit)
        head.addWidget(self.change, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)
        self.body = body
        if body.layout() is not None:
            body.layout().setContentsMargins(0, 0, 0, 0)  # odsazení dává krok
        body.setContentsMargins(CIRCLE + 10, 0, 0, 0)  # obsah odsazený pod název (návrh 30 px)
        layout.addWidget(body)
        self.kind = ""

    def show_state(self, kind: str, summary: str) -> None:
        """``done`` = řádek s ✓, ``active`` = vnořená karta s obsahem, ``future`` = šedě."""
        self.kind = kind
        _circle(self.circle, "✓" if kind == "done" else str(self.number), kind)
        t = ui_theme.tokens()
        self.title_label.setStyleSheet(
            f"font-weight: 600; color: {t['fg3'] if kind == 'future' else t['fg']};")
        self.summary_label.setText(summary)
        self.summary_label.setVisible(bool(summary) and kind != "active")
        self.change.setVisible(kind == "done")
        self.body.setVisible(kind == "active")
        if self.property("stepState") != kind:
            self.setProperty("stepState", kind)
            self.style().unpolish(self)
            self.style().polish(self)


class Wizard(QWidget):
    """Kroky studie a patička „Krok N ze M · Zpět · Další: … / Hotovo“."""

    def __init__(self, title: str = "", name: str = "ndt_wizard", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._title = title
        self.setAccessibleName(title)
        self.steps: list[WizardStep] = []
        self._states: list[StepState] = []
        self._chosen: int | None = None  # otevřený krok (výběr studie, Změnit, Zpět, Další)
        self._overview = False  # Hotovo: všechny kroky jako řádky
        self._key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.caption = QLabel(title)  # doporučený název metody (závazné vymezení)
        self.caption.setObjectName("ndt_wizard_caption")
        self.caption.setProperty("cardHint", True)
        self.caption.setWordWrap(True)
        self.caption.setVisible(bool(title))
        layout.addWidget(self.caption)
        self._list = QVBoxLayout()
        self._list.setSpacing(2)
        layout.addLayout(self._list)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: palette(mid);")
        layout.addWidget(line)
        footer = QHBoxLayout()
        self.position = QLabel()
        self.position.setObjectName("ndt_wizard_position")
        self.position.setProperty("cardHint", True)
        footer.addWidget(self.position)
        footer.addStretch(1)
        self.back = QPushButton("Zpět")
        self.back.setObjectName("ndt_wizard_back")
        self.back.setProperty("role", "secondary")
        self.back.clicked.connect(self.go_back)
        self.next = QPushButton("Další")
        self.next.setObjectName("ndt_wizard_next")
        self.next.setProperty("role", "primary")
        self.next.clicked.connect(self.go_next)
        footer.addWidget(self.back)
        footer.addWidget(self.next)
        layout.addLayout(footer)

    def title(self) -> str:
        return self._title

    def add_step(self, title: str, body: QWidget, short: str | None = None,
                 auto_next: bool = False) -> WizardStep:
        step = WizardStep(len(self.steps) + 1, title, body, short, self, auto_next)
        index = len(self.steps)
        step.change_requested.connect(lambda i=index: self.open_step(i))
        self.steps.append(step)
        self._list.addWidget(step)
        return step

    @property
    def derived(self) -> int:
        """Krok podle stavu studie: první nesplněný (u hotové studie poslední)."""
        for index, state in enumerate(self._states):
            later = any(s.done for s in self._states[index + 1:])
            if not state.done and not (state.skippable and later):
                return index
        return max(0, len(self._states) - 1)

    @property
    def active(self) -> int | None:
        """Otevřený krok (index od 0); None = přehled po Hotovo.

        Krok se odvodí ze stavu jen při výběru studie; pak zůstává, dokud je dostupný –
        přiložená sonda tedy nepřeskočí sama na pokrytí (rám 2c: „Další: pokrytí“)."""
        if self._overview:
            return None
        if self._chosen is not None and self._reachable(self._chosen):
            return self._chosen
        return self.derived

    def _reachable(self, index: int) -> bool:
        """Krok jde otevřít, když jsou všechny předchozí splněné."""
        return 0 <= index < len(self._states) and all(
            s.done or s.skippable for s in self._states[:index])

    def set_states(self, states: list[StepState], key=None) -> None:
        """Nový stav kroků; jiný ``key`` (jiná studie) vrátí průvodce na odvozený krok."""
        before = self._states
        self._states = list(states)
        chosen = self._chosen
        if (key == self._key and chosen is not None and chosen + 1 < len(self.steps)
                and self.steps[chosen].auto_next and chosen < len(before)
                and not before[chosen].done and self._states[chosen].done):
            self._chosen = chosen + 1  # výpočet doběhl → mapa
        if key != self._key:  # jiná studie: krok podle jejího stavu
            self._key = key
            self._overview = False
            self._chosen = self.derived
        elif self._chosen is not None and not self._reachable(self._chosen):
            self._chosen = self.derived  # krok zmizel (např. smazaná oblast)
        self._render()

    def open_step(self, index: int) -> None:
        if self._reachable(index):
            self._chosen = index
            self._overview = False
            self._render()

    def go_back(self) -> None:
        active = self.active
        if active is None:
            self.open_step(len(self.steps) - 1)
        elif active > 0:
            self.open_step(active - 1)

    def go_next(self) -> None:
        active = self.active
        if active is None or not self.next.isEnabled():
            return
        if active == len(self.steps) - 1:
            self._overview = True  # Hotovo: všechny kroky jako hotové řádky
            self._chosen = None
            self._render()
        else:
            self.open_step(active + 1)

    def _render(self) -> None:
        active = self.active
        for index, (step, state) in enumerate(zip(self.steps, self._states, strict=False)):
            kind = ("active" if index == active else "done" if state.done
                    else "future")
            step.show_state(kind, state.summary)
        count = len(self.steps)
        if active is None:
            self.position.setText("Všechny kroky hotové")
            self.next.setText("Hotovo")
            self.next.setEnabled(False)
            self.back.setEnabled(count > 0)
            return
        self.position.setText(f"Krok {active + 1} ze {count}")
        self.back.setEnabled(active > 0)
        last = active == count - 1
        self.next.setText("Hotovo" if last else f"Další: {self.steps[active + 1].short}")
        state = self._states[active] if active < len(self._states) else None
        self.next.setEnabled(state is not None and (state.done or state.skippable and not last))

    def refresh_style(self) -> None:
        self._render()


class TitledBox(QWidget):
    """Skupina bez rámečku; ``title()`` jako dřívější QGroupBox (název je v sekci nad ní)."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self.setAccessibleName(title)

    def title(self) -> str:
        return self._title


COVERAGE_NOTE = "Geometrický podíl plochy, ne pravděpodobnost nálezu vady."
AREA_NOTE = "Geometrický podíl kontrolované oblasti, ne pravděpodobnost nálezu vady."


class CoverageBar(QWidget):
    """Pruh 8 px pokryto / nepokryto / nelze vyhodnotit, legenda s procenty (rám 3d)."""

    def __init__(self, parent=None, *, name: str = "ndt_coverage_bar", note: str = COVERAGE_NOTE,
                 decimals: int = 2, comma: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._decimals, self._comma = decimals, comma  # PT/MT/RT píšou „94,9 %“ jako souhrn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.bar = QWidget()
        self.bar.setFixedHeight(8)
        self._bar = QHBoxLayout(self.bar)
        self._bar.setContentsMargins(0, 0, 0, 0)
        self._bar.setSpacing(0)
        self.parts: dict[str, QFrame] = {}
        self.rows: dict[str, QLabel] = {}
        layout.addWidget(self.bar)
        self.legend = QVBoxLayout()
        self.legend.setSpacing(1)
        layout.addLayout(self.legend)
        self.sensitivity = QLabel()
        self.sensitivity.setObjectName("ndt_coverage_sensitivity")
        self.sensitivity.setWordWrap(True)
        self.sensitivity.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.sensitivity)
        self.note = QLabel(note)
        self.note.setObjectName(f"{name}_note")
        self.note.setWordWrap(True)
        self.note.setProperty("cardHint", True)
        layout.addWidget(self.note)
        self.percents: dict[str, float] = {}

    def show_result(self, states: dict, colors: dict, percents: dict | None,
                    sensitivity: str = "") -> None:
        """``percents`` = stav → %, nebo None (zatím nespočítáno – pruh a legenda skryté)."""
        self.percents = dict(percents or {})
        self.bar.setVisible(percents is not None)
        for key, label in states.items():
            if key not in self.parts:
                part = QFrame()
                part.setObjectName(f"ndt_coverage_part_{key}")
                self.parts[key] = part
                self._bar.addWidget(part)
                row = QLabel()
                row.setObjectName(f"ndt_coverage_row_{key}")
                row.setTextFormat(Qt.TextFormat.RichText)
                row.setWordWrap(True)  # dlouhé stavy RT/MT se zalomí, karta je úzká
                self.rows[key] = row
                self.legend.addWidget(row)
            rgb = colors.get(key, (0.5, 0.5, 0.5))
            hex_color = "#" + "".join(f"{round(255 * v):02x}" for v in rgb)
            value = self.percents.get(key, 0.0)
            self.parts[key].setStyleSheet(f"background: {hex_color};")
            self._bar.setStretch(self._bar.indexOf(self.parts[key]), max(0, round(value * 10)))
            self.parts[key].setVisible(percents is not None and value > 0)
            number = f"{value:.{self._decimals}f}"
            if self._comma:
                number = number.replace(".", ",")
            self.rows[key].setText(
                f'<table width="100%"><tr><td><span style="color: {hex_color};">■</span> '
                f"{label}</td><td align=\"right\"><b>{number} %</b></td></tr></table>")
            self.rows[key].setVisible(percents is not None)
        self.sensitivity.setText(sensitivity)
        self.sensitivity.setVisible(bool(sensitivity) and percents is not None)
