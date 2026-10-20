"""Panel *Předběžný NDT audit* (etapa 14, ``docs/ndt/25-navrh-etapa-14.md``, oddíl 6).

Seznam studií se zaškrtávátky (co se spočítá a jak dlouho, nebo proč ne), u UT studie bez plánu
volba „i návrh poloh“, spuštění na pozadí se zastavením, přehled studií a tabulka problémových
míst. Klik na místo vybere studii v panelu NDT a ukáže její mapu ve 3D s kuličkou ve středu
místa (stávající kresba map a bodů). Export složky: zpráva HTML a PDF, CSV a obrázky map z 3D
okna. Všechno jde přes ``ModelSession``; panel sám nic nepočítá a model nemění.
"""

from __future__ import annotations

import base64
import re
import tempfile
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPageSize,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.ndt import DISCLAIMER
from skodacad.ndt.audit import (
    METHODS,
    NOTE,
    PERCENT_NOTE,
    TITLE,
    AuditEntry,
    AuditError,
    AuditItem,
    Place,
    _dec,
    duration_text,
    estimate_seconds,
)

if TYPE_CHECKING:
    from skodacad.gui.main_window import MainWindow

KIND = Qt.ItemDataRole.UserRole  # druh řádku seznamu: „study“ nebo „access“
STUDY = Qt.ItemDataRole.UserRole + 1  # id studie
MARK = (0.15, 0.35, 1.0)  # kulička ve středu vybraného místa (barvy map ji nepřebijí)
GROUP_COLORS = {"blocked": "#c62828", "uncertain": "#757575", "limited": "#ef6c00"}
HINT = ("Audit spočítá zaškrtnuté studie jejich uloženým nastavením a složí zprávu o "
        "geometrickém posouzení. Model se nemění; výsledek je jen pohled.")
COLUMNS = ("Místo", "Studie", "Stav", "Rozsah", "Podíl", "Důvody")


def write_pdf(html: str, path: str | Path) -> Path:
    """Zpráva HTML → PDF (A4) přes Qt. Obrázky ``data:`` se předají jako zdroje dokumentu."""
    path = Path(path)
    document = QTextDocument()
    images: list[QImage] = []

    def resource(match: re.Match) -> str:
        image = QImage.fromData(base64.b64decode(match.group(1)))
        name = f"obrazek-{len(images)}.png"
        images.append(image)
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        return f'src="{name}"'

    html = re.sub(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', resource, html)
    document.setHtml(html)
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setTitle(TITLE)
    document.print_(writer)  # Qt stránkuje sám (okraj 2 cm) a písmo škáluje na papír
    return path


class AuditPanel(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window = window
        action = window._action
        self.refresh_action = action("Obnovit seznam", self.refresh_items)
        self.refresh_action.setToolTip("Znovu zjistí, co se u které studie spočítá (po změně "
                                       "studií, plánu nebo po výpočtu v panelu NDT)")
        self.run_action = action("Spustit audit", self.start)
        self.run_action.setToolTip("Spočítá zaškrtnuté studie na pozadí (jde zastavit; hotové "
                                   "studie zůstanou)")
        self.stop_action = action("Zastavit", self.stop)
        self.export_action = action("Exportovat zprávu…", self.export)
        self.export_action.setToolTip("Složka se zprávou HTML a PDF, CSV míst a CSV studií; "
                                      "obrázky map se pořídí z 3D okna")
        self.hide_action = action("Skrýt místo ve 3D", self.hide_place)
        self._items: list[AuditItem] = []
        self._items_key: Any = None
        self._problem = ""  # proč seznam nejde sestavit
        self._unchecked: set[str] = set()  # studie, které uživatel vypnul
        self._access: set[str] = set()  # UT studie s návrhem poloh
        self._shown: Any = None  # audit v tabulce
        self._capture: AuditEntry | None = None  # studie, jejíž mapu export právě fotí

        layout = QVBoxLayout(self)
        self.warning = QLabel(DISCLAIMER)  # po auditu upozornění všech metod ve zprávě
        self.warning.setObjectName("audit_warning")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #8a4b00; font-size: 8pt;")  # dlouhé, ale doslova
        self.warning.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.warning)
        hint = QLabel(HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Studie (zaškrtnuté se spočítají):"))
        self.studies = QListWidget()
        self.studies.setObjectName("audit_studies")
        self.studies.setWordWrap(True)
        self.studies.setMinimumHeight(90)
        self.studies.setMaximumHeight(160)
        self.studies.itemChanged.connect(self._item_changed)
        layout.addWidget(self.studies)
        row = QHBoxLayout()
        row.addWidget(QLabel("Zpracoval(a):"))
        self.operator = QLineEdit()
        self.operator.setObjectName("audit_operator")
        self.operator.setPlaceholderText("jméno do zprávy (nepovinné)")
        row.addWidget(self.operator)
        layout.addLayout(row)
        self.estimate = QLabel()
        self.estimate.setObjectName("audit_estimate")
        self.estimate.setWordWrap(True)
        layout.addWidget(self.estimate)
        self._row(layout, (self.run_action, self.stop_action, self.refresh_action))
        self.progress = QLabel()
        self.progress.setObjectName("audit_progress")
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        self.overview = QLabel()
        self.overview.setObjectName("audit_overview")
        self.overview.setWordWrap(True)
        self.overview.setTextFormat(Qt.TextFormat.RichText)
        self.overview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.overview)
        self.places = QTableWidget(0, len(COLUMNS))
        self.places.setObjectName("audit_places")
        self.places.setHorizontalHeaderLabels(COLUMNS)
        self.places.verticalHeader().setVisible(False)
        self.places.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.places.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.places.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.places.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.places.setMinimumHeight(140)
        self.places.itemSelectionChanged.connect(self._place_changed)
        layout.addWidget(self.places)
        self.place_info = QLabel()
        self.place_info.setObjectName("audit_place")
        self.place_info.setWordWrap(True)
        self.place_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.place_info)
        self._row(layout, (self.export_action, self.hide_action))
        layout.addStretch(1)

    def _row(self, layout: QVBoxLayout, actions: tuple) -> None:
        row = QHBoxLayout()
        for item in actions:
            row.addWidget(self.window._tool_button(item))
        row.addStretch()
        layout.addLayout(row)

    def actions(self) -> tuple:
        return (self.refresh_action, self.run_action, self.stop_action, self.export_action,
                self.hide_action)

    # --- seznam studií -------------------------------------------------------------------

    def _key(self) -> Any:
        session = self.window.session
        document = session.document
        if document is None or session.computing:
            return None
        return (session.result, repr(document.ndt), repr(document.thickness_map),
                document.material, id(session.ndt_coverage), id(session.ndt_plan_result),
                id(session.ndt_access), tuple(sorted(self._access)))

    def refresh_items(self) -> None:
        """Znovu zjistí, co audit u které studie spočítá (odhad, důvod proč ne)."""
        key = self._key()
        session = self.window.session
        self._problem = ""
        try:
            items = session.ndt_audit_items(None, sorted(self._access)) if key else []
        except DocumentError as exc:
            items, self._problem = [], str(exc)
        self._items, self._items_key = items, key
        self._fill_items()

    def _fill_items(self) -> None:
        self.studies.blockSignals(True)
        self.studies.clear()
        session = self.window.session
        for item in self._items:
            row = QListWidgetItem(item.text())
            row.setData(KIND, "study")
            row.setData(STUDY, item.study_id)
            row.setToolTip(item.text())
            runs = item.status == "ready"
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if not runs:
                row.setForeground(Qt.GlobalColor.darkGray)
            row.setCheckState(Qt.CheckState.Unchecked if item.study_id in self._unchecked
                              or not runs else Qt.CheckState.Checked)
            self.studies.addItem(row)
            if item.method == "UT" and (item.action == "access" or (
                    item.status == "skipped" and "návrh poloh" in item.reason)):
                try:
                    estimate = session.ndt_access_estimate(item.study_id)
                    when = duration_text(estimate.seconds[1])
                except DocumentError:
                    when = "nejde odhadnout"
                extra = QListWidgetItem(f"    ↳ {item.study_id}: i návrh poloh sondy (pomalé, "
                                        f"{when})")
                extra.setData(KIND, "access")
                extra.setData(STUDY, item.study_id)
                extra.setFlags(extra.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                extra.setCheckState(Qt.CheckState.Checked if item.study_id in self._access
                                    else Qt.CheckState.Unchecked)
                self.studies.addItem(extra)
        self.studies.blockSignals(False)
        self._show_estimate()

    def _item_changed(self, row: QListWidgetItem) -> None:
        sid, checked = row.data(STUDY), row.checkState() == Qt.CheckState.Checked
        if row.data(KIND) == "access":
            (self._access.add if checked else self._access.discard)(sid)
            self.refresh_items()  # UT studie teď počítá návrh poloh (nebo zase ne)
            return
        (self._unchecked.discard if checked else self._unchecked.add)(sid)
        self._show_estimate()

    def included(self) -> list[str]:
        return [item.study_id for item in self._items if item.study_id not in self._unchecked]

    def _show_estimate(self) -> None:
        chosen = [item for item in self._items if item.study_id not in self._unchecked]
        ready = [item for item in chosen if item.status == "ready"]
        if self._problem or not self._items:
            text = self._problem or ("Model nemá NDT studii ani mapu tloušťky stěny."
                                     if self._items_key is not None else "")
        else:
            text = (f"Spočítá se {len(ready)} z {len(self._items)}; odhad celkem "
                    f"{duration_text(estimate_seconds(chosen))}.")
        self.estimate.setText(text)

    # --- běh -------------------------------------------------------------------------------

    def start(self) -> None:
        session = self.window.session
        include = self.included()
        access = sorted(sid for sid in self._access if sid in include)
        operator = self.operator.text()
        try:
            self.window._busy(lambda: session.start_ndt_audit(include, access, operator))
        except DocumentError as exc:
            self.window._error("Audit nejde spustit", str(exc))
            return
        self.window._refresh_all()

    def stop(self) -> None:
        self.window.stop_rebuild()

    def show_progress(self) -> None:
        session = self.window.session
        if session.audit_pending:
            text = session.ndt_audit_progress or "Audit začíná…"
            self.progress.setText(f"⏳ {text} – {session.computing_seconds:.0f} s")
        else:
            self.progress.setText("")
        self.refresh_actions()

    # --- přehled a místa -----------------------------------------------------------------

    def audit(self):
        return self.window.session.ndt_audit

    def refresh(self) -> None:
        """Po přepočtu či změně: seznam studií (jen když je co nového a panel je vidět – odhady
        stojí čas; během výpočtu zůstane), přehled a místa."""
        key = self._key()
        if key is not None and key != self._items_key and self.window.audit_dock.isVisibleTo(
                self.window):
            self.refresh_items()
        self.show_progress()
        audit = self.audit()
        if audit is self._shown:
            return
        self._shown = audit
        self.warning.setText("\n\n".join(audit.disclaimers()) if audit is not None
                             else DISCLAIMER)
        self._fill_overview(audit)
        self._fill_places(audit)

    def _fill_overview(self, audit) -> None:
        if audit is None:
            self.overview.setText("")
            return
        lines = [f"<b>{escape(TITLE)}</b>", *(escape(line) for line in audit.header())]
        for entry in audit.entries:
            color = {"done": "#1b5e20", "skipped": "#555", "unavailable": "#b71c1c"}[entry.status]
            lines.append(f'<span style="color: {color};">■</span> '
                         + escape(audit.overview(entry)))
        lines += [f"<i>{escape(NOTE)}</i>", f"<i>{escape(PERCENT_NOTE)}</i>"]
        self.overview.setText("<br>".join(lines))

    def _fill_places(self, audit) -> None:
        self.places.blockSignals(True)
        self.places.clearSelection()
        places = audit.places() if audit is not None else []
        self.places.setRowCount(len(places))
        for row, place in enumerate(places):
            values = (place.id, f"{place.study_id} {METHODS.get(place.method, place.method)}",
                      place.label, f"{_dec(place.amount)} {place.unit}",
                      f"{_dec(place.share)} %", place.reason_text())
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(place.reason_text())
                if column == 2:
                    cell.setForeground(Qt.GlobalColor.white)
                    cell.setBackground(QBrush(QColor(GROUP_COLORS.get(place.group, "#555"))))
                self.places.setItem(row, column, cell)
            self.places.item(row, 0).setData(Qt.ItemDataRole.UserRole, place.id)
        self.places.resizeColumnsToContents()
        self.places.blockSignals(False)
        self.place_info.setText("Klikni na místo – ukáže se mapa studie ve 3D a modrá kulička "
                                "ve středu místa." if places else "")
        self.window._refresh_probe()

    def place(self) -> Place | None:
        audit = self.audit()
        rows = self.places.selectionModel().selectedRows() if audit is not None else []
        if not rows:
            return None
        place_id = self.places.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((p for p in audit.places() if p.id == place_id), None)

    def select_place(self, place_id: str) -> None:
        for row in range(self.places.rowCount()):
            if self.places.item(row, 0).data(Qt.ItemDataRole.UserRole) == place_id:
                self.places.selectRow(row)
                return

    def _place_changed(self) -> None:
        place = self.place()
        if place is None:
            self.place_info.setText("")
            self.window._refresh_probe()
            self.refresh_actions()
            return
        where = ("poloha neurčena" if place.center is None
                 else "střed " + "; ".join(_dec(v) for v in place.center) + " mm")
        span = ("" if place.low is None else " (od " + "; ".join(_dec(v) for v in place.low)
                + " do " + "; ".join(_dec(v) for v in place.high) + " mm)")
        lines = [f"{place.id} – {place.label}, {place.study_name} "
                 f"({METHODS.get(place.method, place.method)})",
                 f"{_dec(place.amount)} {place.unit} = {_dec(place.share)} % studie, "
                 f"{place.count} bodů sítě; {where}{span}.",
                 f"Důvody: {place.reason_text()}"]
        if place.example:
            lines.append(f"Například: {place.example}")
        self.place_info.setText("\n".join(lines))
        if place.study_id != "tl":
            self.window.ndt_panel.select(place.study_id)  # skupina studie v panelu NDT
            self.window.session.adopt_ndt_audit_map(place.study_id)
        self.window._refresh_probe()
        self.refresh_actions()

    def hide_place(self) -> None:
        self.places.clearSelection()

    def focus(self) -> tuple[AuditEntry, Place | None] | None:
        """Co ukázat ve 3D: mapa studie vybraného místa (nebo studie, kterou fotí export).
        Okno ji kreslí přednostně a kresbu projekce RT přitom skryje (deska by mapu zakryla) –
        proto se po změně volá ``_refresh_probe``, ne jen ``_refresh_coverage``."""
        audit = self.audit()
        if audit is None:
            return None
        if self._capture is not None:
            return self._capture, None
        place = self.place()
        if place is None:
            return None
        try:
            return audit.entry(place.study_id), place
        except AuditError:  # audit se mezitím změnil
            return None

    # --- export ----------------------------------------------------------------------------

    def export(self) -> None:
        audit = self.audit()
        if audit is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Složka pro zprávu auditu")
        if not folder:
            return
        try:
            paths = self.window._busy(lambda: self._export(folder))
        except (DocumentError, OSError) as exc:
            self.window._error("Zprávu nejde uložit", str(exc))
            return
        self.window.statusBar().showMessage(
            f"Zpráva auditu uložena: {Path(folder)} ({len(paths)} souborů)", 10000)

    def _export(self, folder: str) -> list[Path]:
        audit = self.audit()
        images = self.capture_images()
        paths = self.window.session.export_ndt_audit(folder, images)
        paths.append(write_pdf(audit.html(images), Path(folder) / "zprava.pdf"))
        return paths

    def capture_images(self) -> dict[str, list[tuple[str, bytes]]]:
        """Obrázek mapy každé spočítané studie z 3D okna (celý díl v pohledu)."""
        audit = self.audit()
        images: dict[str, list[tuple[str, bytes]]] = {}
        viewer = self.window.viewer
        try:
            with tempfile.TemporaryDirectory() as folder:
                for entry in audit.entries:
                    if entry.status != "done" or entry.layer is None:
                        continue
                    self._capture = entry
                    self.window._refresh_probe()
                    viewer.fit_all()
                    path = Path(folder) / f"{entry.study_id}.png"
                    if viewer.dump(str(path)) and path.exists():
                        images[entry.study_id] = [(f"Mapa ve 3D – {entry.name}",
                                                   path.read_bytes())]
        finally:
            self._capture = None
            self.window._refresh_probe()
        return images

    # --- tlačítka ----------------------------------------------------------------------------

    def refresh_actions(self) -> None:
        session = self.window.session
        ready = session.document is not None and not session.computing \
            and not self.window.ai_busy
        audit = self.audit()
        self.refresh_action.setEnabled(ready)
        self.run_action.setEnabled(ready and any(
            item.status == "ready" and item.study_id not in self._unchecked
            for item in self._items))
        self.stop_action.setEnabled(session.audit_pending)
        self.export_action.setEnabled(ready and audit is not None)
        self.hide_action.setEnabled(audit is not None and self.place() is not None)

