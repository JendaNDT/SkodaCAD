"""Formuláře pro úpravu prvků – stavěné automaticky ze schématu (``skodacad.schema``).

Okno samo nic nemodeluje: formulář jen sestaví nový obsah prvku (slovník
jako v JSON modelu) a pošle ho signálem ``changed``. Okno ho předá
``ModelSession.update_feature`` a jádro díl přepočítá.

Chybně vyplněné pole (prázdná povinná hodnota, nesmyslný výraz …) se
zbarví červeně a prvek se nezmění.
"""

from __future__ import annotations

import ast
import copy
import html
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.gui.cad_icons import icon as cad_icon
from skodacad.gui.guide_drag import DEFAULT_STEP, DIRECTION_CHOICES, MAX_STEP
from skodacad.gui.guide_style import COLORS as GUIDE_COLORS
from skodacad.gui.loft_wall_panel import LoftWallPanel
from skodacad.guided_loft import CORNERS, LABELS, default_guides
from skodacad.schema import (
    FACE_CHOICES,
    FEATURE_SCHEMAS,
    SHAPE_SCHEMAS,
    Field,
    field_shown,
    new_shape,
)
from skodacad.selectors import describe_edges, describe_plane
from skodacad.session import format_parameter_value, parse_parameter_text

MISSING = object()  # pole je prázdné a nepovinné → klíč se z prvku odebere
_PICKED = "__plocha_z_3D__"  # volba „plocha vybraná ve 3D“ v poli Rovina
# Otevře skicář nad obrysem; vrátí upravený obrys, nebo None (Zrušit). Dodává hlavní okno.
ProfileEditor = Callable[[dict[str, Any]], dict[str, Any] | None]
_BAD_STYLE = "border: 2px solid #c0392b; background: #fdecea;"

EDGE_FACE_CHOICES = (("", "všechny plochy"), *FACE_CHOICES)
EDGE_TYPE_CHOICES = (("", "všechny"), ("line", "úsečky"), ("circle", "kružnice a oblouky"))
EDGE_AXIS_CHOICES = (("", "libovolně"), ("X", "s osou X"), ("Y", "s osou Y"), ("Z", "s osou Z"))
_FORM_EDGE_KEYS = {"face", "type", "parallel", "radius"}  # co umí formulář; zbytek = výběr z 3D


class InvalidValue(ValueError):
    """Pole je vyplněné špatně (zpráva je česky)."""


def parse_number(text: str, field: Field) -> Any:
    """Text z políčka → číslo nebo výraz; prázdné nepovinné pole → MISSING."""
    text = text.strip()
    if not text:
        if field.required:
            raise InvalidValue(f"{field.label}: hodnota je povinná.")
        return MISSING
    try:
        value = parse_parameter_text(text)
    except DocumentError as exc:
        raise InvalidValue(str(exc)) from None
    if isinstance(value, str):
        try:
            ast.parse(value, mode="eval")
        except SyntaxError:
            raise InvalidValue(f"{field.label}: výraz „{value}“ má chybný zápis.") from None
    return value


def _number_text(value: Any) -> str:
    return "" if value is None else format_parameter_value(value)


class _PlainTextEdit(QPlainTextEdit):
    """Víceřádkové pole, které ohlásí dokončení úprav při opuštění (jako QLineEdit)."""

    editingFinished = Signal()  # noqa: N815 – stejný název jako u QLineEdit

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.editingFinished.emit()


def _combo(choices, current: Any, optional: bool, empty_label: str = "(automaticky)") -> QComboBox:
    combo = QComboBox()
    # Dlouhé popisky (např. „válcové zahloubení pro imbus …“) nesmí roztáhnout panel –
    # seznam se přizpůsobí šířce panelu, celý text je v rozbalené nabídce a v bublině.
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(12)
    combo.currentTextChanged.connect(combo.setToolTip)
    if optional:
        combo.addItem(empty_label, None)
    for key, label in choices:
        combo.addItem(label, key)
    index = combo.findData(current) if current is not None else 0
    combo.setCurrentIndex(max(index, 0))
    combo.setToolTip(combo.currentText())
    return combo


class GuidesEditor(QGroupBox):
    """Pevné řádky rukojetí; výběr řádku je jen pohled, úprava hodnot jde přes formulář."""

    edited = Signal()
    selected = Signal(int)
    handle_selected = Signal(int)
    step_changed = Signal(float)
    direction_changed = Signal(str)

    def __init__(self, value) -> None:
        super().__init__("Vodítka · posuny rukojetí [mm]")
        layout = QVBoxLayout(self)
        self.corner_picker = QComboBox()
        self.corner_picker.setObjectName("guide_corner")
        self.corner_picker.setAccessibleName("Vodítko")
        self.buttons = QButtonGroup(self)
        self.buttons.setExclusive(True)
        for row, label in enumerate(LABELS):
            color = "#" + "".join(f"{round(value*255):02x}" for value in GUIDE_COLORS[row])
            self.corner_picker.addItem(cad_icon("loft", color), label, row)
            button = QToolButton(self)  # compatible ids for selection and drag/history callbacks
            button.setText(label)
            button.setCheckable(True)
            self.buttons.addButton(button, row)
            button.setChecked(row == 0)
            button.hide()
        layout.addWidget(QLabel("Vodítko"))
        layout.addWidget(self.corner_picker)
        handles = QHBoxLayout()
        self.handle_buttons = QButtonGroup(self)
        self.handle_buttons.setExclusive(True)
        for index in range(2):
            button = QToolButton()
            button.setObjectName(f"guide_handle_{index}")
            button.setText(f"Rukojeť {index+1}")
            button.setCheckable(True)
            self.handle_buttons.addButton(button, index)
            button.setChecked(index == 0)
            handles.addWidget(button)
        layout.addLayout(handles)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        self.edits = {}
        by_corner = {(g["corner"]["x"], g["corner"]["y"]): g for g in value or default_guides()}
        for row, corner in enumerate(CORNERS):
            for handle in range(2):
                page = QWidget()
                form = QFormLayout(page)
                form.setContentsMargins(0, 0, 0, 0)
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                for axis in range(2):
                    edit = QLineEdit(_number_text(by_corner[corner]["controls"][handle][axis]))
                    edit.setMinimumWidth(120)
                    edit.setObjectName(f"guide_{row}_{handle}_{axis}")
                    edit.setToolTip(f"{LABELS[row]} · rukojeť {handle+1} · {'XY'[axis]} [mm]")
                    edit.editingFinished.connect(self.edited)
                    form.addRow(f"{'XY'[axis]} [mm]", edit)
                    self.edits[row, handle, axis] = edit
                self.pages.addWidget(page)
        self.corner_picker.currentIndexChanged.connect(
            lambda row: self.buttons.button(row).setChecked(True))
        self.buttons.idToggled.connect(self._corner_toggled)
        self.handle_buttons.idToggled.connect(self._handle_toggled)
        step_row = QHBoxLayout()
        self.drag_step = QDoubleSpinBox()
        self.drag_step.setObjectName("guide_drag_step")
        self.drag_step.setDecimals(3)
        self.drag_step.setRange(0, MAX_STEP)
        self.drag_step.setSingleStep(.1)
        self.drag_step.setSuffix(" mm")
        self.drag_step.setSpecialValueText("Volně (0)")
        self.drag_step.setKeyboardTracking(False)
        self.drag_step.setValue(DEFAULT_STEP)
        self.drag_step.setToolTip("0 = volně. Krok 0,001 až 1000 mm zaokrouhluje posun "
                                  "od začátku tahu, zvlášť pro X a Y.")
        self.drag_step.valueChanged.connect(self.step_changed)
        step_row.addWidget(QLabel("Krok tažení:"))
        step_row.addWidget(self.drag_step)
        step_row.addStretch(1)
        layout.addLayout(step_row)
        direction_row = QHBoxLayout()
        self.drag_direction = QComboBox()
        self.drag_direction.setObjectName("guide_drag_direction")
        for key, label in DIRECTION_CHOICES:
            self.drag_direction.addItem(label, key)
        self.drag_direction.setToolTip("Osy X/Y patří dílu a nemění se s natočením pohledu. "
                                       "Zvolený směr používá nastavený krok tažení.")
        self.drag_direction.currentIndexChanged.connect(
            lambda index: self.direction_changed.emit(self.drag_direction.itemData(index)))
        direction_row.addWidget(QLabel("Směr tažení:"))
        direction_row.addWidget(self.drag_direction)
        direction_row.addStretch(1)
        layout.addLayout(direction_row)
        note = QLabel("Rukojeť 1 je v H/3, rukojeť 2 ve 2H/3. "
                      "Posun rukojeti není kóta skutečného vyboulení. "
                      "Ve 3D táhni větší bod rukojeti v XY; puštění ověří těleso, Esc zruší. "
                      "Během tahu se mění jen vodítko. Výrazy zachovají vazbu na parametry.")
        note.setWordWrap(True)
        note.setProperty("secondaryText", True)
        layout.addWidget(note)

    def _corner_toggled(self, row, checked):
        if checked:
            blocker = QSignalBlocker(self.corner_picker)
            self.corner_picker.setCurrentIndex(row)
            del blocker
            self.pages.setCurrentIndex(2*row + self.selected_handle)
            self.selected.emit(row)

    def _handle_toggled(self, handle, checked):
        if checked:
            self.pages.setCurrentIndex(2*self.selected_index + handle)
            self.handle_selected.emit(handle)

    def set_selection(self, row, handle):
        blockers = [QSignalBlocker(group) for group in
                    (self.buttons, self.handle_buttons, self.corner_picker)]
        self.buttons.button(row).setChecked(True)
        self.handle_buttons.button(handle).setChecked(True)
        self.corner_picker.setCurrentIndex(row)
        self.pages.setCurrentIndex(2*row + handle)
        del blockers

    @property
    def selected_index(self) -> int:
        return self.buttons.checkedId()

    @property
    def selected_handle(self) -> int:
        return self.handle_buttons.checkedId()

    def value(self) -> list:
        result = default_guides()
        for row in range(4):
            for handle in range(2):
                for axis in range(2):
                    field = Field("guides", f"{LABELS[row]} · rukojeť {handle+1} · {'XY'[axis]}",
                                  "number")
                    result[row]["controls"][handle][axis] = parse_number(
                        self.edits[row, handle, axis].text(), field)
        return result


class FieldsForm(QWidget):
    """Formulář nad jedním slovníkem (prvek nebo tvar skici) podle seznamu polí.

    Po každé dokončené úpravě přečte všechna pole a vyšle ``edited`` s novým
    slovníkem. Klíče, které schéma nezná, zůstanou zachované.
    """

    edited = Signal(dict)
    guide_selected = Signal(int)
    guide_handle_selected = Signal(int)
    guide_step_changed = Signal(float)
    guide_direction_changed = Signal(str)
    invalid = Signal(str)

    def __init__(self, fields: tuple[Field, ...], data: dict[str, Any],
                 sketches: list[tuple[str, str]] | None = None,
                 parent: QWidget | None = None,
                 profile_editor: ProfileEditor | None = None,
                 features: list[tuple[str, str]] | None = None) -> None:
        super().__init__(parent)
        self._data = copy.deepcopy(data)
        self._sketches = sketches or []
        self._features = features or []  # dřívější prvky, které jde opakovat (id, popis)
        self._profile_editor = profile_editor
        self._rows: list[tuple[Field, QWidget, Callable[[], Any]]] = []
        self._layout = layout = QFormLayout(self)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in fields:
            widget, read = self._build(field, self._data.get(field.key))
            widget.setObjectName(f"field_{field.key}")
            if field.help:
                widget.setToolTip(field.help)
            if field.kind in ("shapes", "bool", "guides"):
                layout.addRow(widget)
            else:
                layout.addRow(field.label, widget)
            self._rows.append((field, widget, read))
        self._update_visibility()

    @property
    def data(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def widget(self, key: str) -> QWidget:
        """Pole formuláře; když je pod jedním klíčem víc polí (velikost podle druhu dílu),
        to, které je právě vidět."""
        widgets = [widget for field, widget, _ in self._rows if field.key == key]
        return next((w for w in widgets if self._layout.isRowVisible(w)), widgets[0])

    def is_shown(self, key: str) -> bool:
        """Je pole vidět? (Některá pole patří jen k jedné volbě, např. k druhu pole.)"""
        return self._layout.isRowVisible(self.widget(key))

    def _update_visibility(self) -> None:
        defaults = {field.key: field.default for field, _, _ in self._rows}
        for field, widget, _ in self._rows:
            if field.when:
                self._layout.setRowVisible(widget, field_shown(field, self._data, defaults))

    # --- stavba polí -----------------------------------------------------------------

    def _build(self, field: Field, value: Any) -> tuple[QWidget, Callable[[], Any]]:
        builder = getattr(self, f"_build_{field.kind}")
        return builder(field, value)

    def _build_text(self, field: Field, value: Any):
        edit = QLineEdit("" if value is None else str(value))
        edit.editingFinished.connect(self._commit)

        def read() -> Any:
            text = edit.text().strip()
            if not text:
                if field.required:
                    raise InvalidValue(f"{field.label}: hodnota je povinná.")
                return MISSING
            return text

        return edit, read

    def _build_number(self, field: Field, value: Any):
        edit = QLineEdit(_number_text(value))
        if not field.required:
            edit.setPlaceholderText("(nevyplněno)")
        edit.editingFinished.connect(self._commit)
        return edit, lambda: parse_number(edit.text(), field)

    def _build_choice(self, field: Field, value: Any):
        choices, current = field.choices, value if value is not None else field.default
        picked = copy.deepcopy(value) if isinstance(value, dict) else None
        if picked is not None:  # plocha vybraná ve 3D (šikmá, zakřivená) – nabídne se navíc
            choices, current = (*choices, (_PICKED, describe_plane(picked))), _PICKED
        optional = not field.required and (field.missing_label is None or value is None)
        combo = _combo(choices, current, optional=optional,
                       empty_label=field.missing_label or "(automaticky)")
        combo.currentIndexChanged.connect(self._commit)

        def read() -> Any:
            key = combo.currentData()
            if key == _PICKED:
                return copy.deepcopy(picked)
            return MISSING if key is None else key

        return combo, read

    def _build_sketch(self, field: Field, value: Any):
        choices = list(self._sketches)
        if value is not None and value not in {key for key, _ in choices}:
            choices.append((value, f"{value} (není před tímto prvkem)"))
        combo = _combo(choices, value, optional=False)
        combo.currentIndexChanged.connect(self._commit)

        def read() -> Any:
            if combo.count() == 0:
                raise InvalidValue("Před tímto prvkem není žádná skica – nejdřív ji přidej.")
            return combo.currentData()

        return combo, read

    def _build_sketches(self, field: Field, value: Any):
        """Zaškrtávací seznam dřívějších skic – pořadí je pořadí ve stromu (přechod)."""
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        selected = [v for v in value if isinstance(v, str)] if isinstance(value, list) else []
        choices = list(self._sketches)
        known = {key for key, _ in choices}
        choices += [(key, f"{key} (není před tímto prvkem)") for key in selected
                    if key not in known]
        boxes: dict[str, QCheckBox] = {}
        for key, label in choices:
            box = QCheckBox(label)
            box.setObjectName(f"sketch_{key}")
            box.setChecked(key in selected)
            box.toggled.connect(self._commit)
            column.addWidget(box)
            boxes[key] = box
        if len(choices) < field.min_count:
            note = QLabel(f"Přechod potřebuje aspoň {field.min_count} skici před sebou – "
                          "přidej je (třeba dole a o kus výš s posunem roviny).")
            note.setWordWrap(True)
            column.addWidget(note)

        def read() -> Any:
            checked = [key for key, box in boxes.items() if box.isChecked()]
            if len(checked) < field.min_count:
                raise InvalidValue(f"{field.label}: zaškrtni aspoň {field.min_count} skici.")
            return checked

        return holder, read

    def _build_bool(self, field: Field, value: Any):
        box = QCheckBox(field.label)
        box.setChecked(bool(value))
        box.toggled.connect(self._commit)
        return box, lambda: True if box.isChecked() else MISSING

    def _build_faces(self, field: Field, value: Any):
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        boxes: dict[str, QCheckBox] = {}
        selected = set(value or [])
        for index, (key, label) in enumerate(FACE_CHOICES):
            box = QCheckBox(label.replace(" plocha", ""))
            box.setObjectName(f"face_{key}")
            box.setChecked(key in selected)
            box.toggled.connect(self._commit)
            grid.addWidget(box, index // 2, index % 2)
            boxes[key] = box

        def read() -> Any:
            checked = [key for key, box in boxes.items() if box.isChecked()]
            return checked if checked or field.required else MISSING

        return holder, read

    def _build_face(self, field: Field, value: Any):
        """Plocha přímé úpravy – jen popis; mění se výběrem ve 3D (P2.4), ne textem."""
        text = (describe_plane(value) if isinstance(value, dict) and "at" in value
                else "(vyber plochu ve 3D)")
        label = QLabel(text)
        label.setWordWrap(True)
        kept = copy.deepcopy(value)
        return label, lambda: MISSING if kept is None else copy.deepcopy(kept)

    def _build_origin(self, field: Field, value: Any):
        """Původ plochy (id prvku) – jen ke čtení, doplní ho výběr plochy."""
        label = QLabel(str(value) if value else "(chybí – vyber plochu znovu)")
        return label, lambda: MISSING if value is None else value

    def _build_edges(self, field: Field, value: Any):
        if isinstance(value, list) or (isinstance(value, dict) and set(value) - _FORM_EDGE_KEYS):
            return self._build_picked_edges(value)
        spec = value if isinstance(value, dict) else {}
        holder = QWidget()
        form = QFormLayout(holder)
        form.setContentsMargins(0, 0, 0, 0)
        face = _combo(EDGE_FACE_CHOICES, spec.get("face", ""), optional=False)
        kind = _combo(EDGE_TYPE_CHOICES, spec.get("type", ""), optional=False)
        axis = _combo(EDGE_AXIS_CHOICES, spec.get("parallel", ""), optional=False)
        radius = QLineEdit(_number_text(spec.get("radius")))
        radius.setPlaceholderText("libovolný")
        for name, widget in (("edge_face", face), ("edge_type", kind),
                             ("edge_parallel", axis), ("edge_radius", radius)):
            widget.setObjectName(name)
        form.addRow("Na ploše", face)
        form.addRow("Druh", kind)
        form.addRow("Rovnoběžné", axis)
        form.addRow("Poloměr [mm]", radius)
        for combo in (face, kind, axis):
            combo.currentIndexChanged.connect(self._commit)
        radius.editingFinished.connect(self._commit)
        radius_field = Field("radius", "Poloměr hran", "number", required=False)

        def read() -> Any:
            result: dict[str, Any] = {}
            for key, combo in (("face", face), ("type", kind), ("parallel", axis)):
                if combo.currentData():
                    result[key] = combo.currentData()
            radius_value = parse_number(radius.text(), radius_field)
            if radius_value is not MISSING:
                result["radius"] = radius_value
            return result or "all"

        return holder, read

    def _build_picked_edges(self, value: Any):
        """Výběr kliknutím ve 3D (hrana mezi plochami, nejbližší k bodu …) – jen ukázat."""
        label = QLabel(f"<b>Vybráno ve 3D:</b> {describe_edges(value)}<br>"
                       "<span>Další hrany: vyber je ve 3D (Ctrl+klik) → "
                       "pravé tlačítko → Přidat vybrané hrany. Hrany prvku jsou ve 3D "
                       "zvýrazněné růžově.</span>")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        kept = copy.deepcopy(value)
        return label, lambda: copy.deepcopy(kept)

    def _build_profile(self, field: Field, value: Any):
        """Obrys z čar: souhrn (body, čáry, vazby) a tlačítko do skicáře."""
        holder = QWidget()
        row = QVBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(_profile_summary(self._data))
        label.setWordWrap(True)
        row.addWidget(label)
        button = QPushButton("Upravit ve skicáři…")
        button.setObjectName("open_sketcher")
        button.setEnabled(self._profile_editor is not None)
        row.addWidget(button)
        kept = [copy.deepcopy(value)]

        def open_sketcher() -> None:
            result = self._profile_editor(copy.deepcopy(self._data))
            if result is None:
                return
            new = copy.deepcopy(self._data)
            new.update({key: copy.deepcopy(result[key])
                        for key in ("points", "segments", "constraints")})
            if "references" in result:
                new["references"] = copy.deepcopy(result["references"])
            else:
                new.pop("references", None)
            kept[0] = copy.deepcopy(result["segments"])
            label.setText(_profile_summary(new))
            if new != self._data:
                self._data = new
                self.edited.emit(copy.deepcopy(new))

        button.clicked.connect(lambda _checked=False: open_sketcher())
        return holder, lambda: copy.deepcopy(kept[0])

    def _build_point3(self, field: Field, value: Any):
        return self._build_point(field, value, ("x", "y", "z"))

    def _build_point(self, field: Field, value: Any, axes: tuple[str, ...] = ("x", "y")):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        valid = isinstance(value, list | tuple) and len(value) == len(axes)
        point = value if valid else [None] * len(axes)
        edits = []
        for axis, coordinate in zip(axes, point, strict=True):
            edit = QLineEdit(_number_text(coordinate))
            edit.setObjectName(f"point_{axis}")
            edit.setPlaceholderText("0")
            edit.editingFinished.connect(self._commit)
            row.addWidget(QLabel(axis))
            row.addWidget(edit)
            edits.append(edit)

        def read() -> Any:
            texts = [edit.text().strip() for edit in edits]
            if not any(texts) and not field.required:
                return MISSING
            coordinate = Field(field.key, field.label, "number")
            return [parse_number(text or "0", coordinate) for text in texts]

        return holder, read

    def _build_points3(self, field: Field, value: Any):
        return self._build_points(field, value, ("x", "y", "z"))

    def _build_points(self, field: Field, value: Any, axes: tuple[str, ...] = ("x", "y")):
        edit = _PlainTextEdit()
        valid = [p for p in (value or []) if isinstance(p, list | tuple) and len(p) == len(axes)]
        lines = ["; ".join(_number_text(v) for v in point) for point in valid]
        edit.setPlainText("\n".join(lines))
        pattern = "; ".join(axes)
        edit.setToolTip(field.help or f"Jeden bod na řádek ve tvaru  {pattern}.")
        edit.setFixedHeight(110)
        edit.editingFinished.connect(self._commit)

        def read() -> Any:
            points = []
            coordinate = Field(field.key, "Souřadnice bodu", "number")
            for number_, line in enumerate(edit.toPlainText().splitlines(), start=1):
                if not line.strip():
                    continue
                parts = line.split(";")
                if len(parts) != len(axes):
                    raise InvalidValue(f"Řádek {number_}: napiš bod jako  {pattern}")
                points.append([parse_number(part, coordinate) for part in parts])
            if len(points) < field.min_count:
                raise InvalidValue(f"{field.label}: potřeba aspoň {field.min_count} "
                                   f"{'bod' if field.min_count == 1 else 'body'}.")
            return points

        return edit, read

    def _build_features(self, field: Field, value: Any):
        """Zaškrtávací seznam dřívějších prvků, které přidávají či ubírají materiál."""
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        selected = [v for v in value if isinstance(v, str)] if isinstance(value, list) else []
        choices = list(self._features)
        known = {key for key, _ in choices}
        choices += [(key, f"{key} (není před tímto prvkem)") for key in selected
                    if key not in known]
        boxes: dict[str, QCheckBox] = {}
        for key, label in choices:
            box = QCheckBox(label)
            box.setObjectName(f"feature_{key}")
            box.setChecked(key in selected)
            box.toggled.connect(self._commit)
            column.addWidget(box)
            boxes[key] = box
        if not choices:
            note = QLabel("Před tímto prvkem není nic k opakování – přidej nejdřív díru, "
                          "výřez nebo výstupek.")
            note.setWordWrap(True)
            column.addWidget(note)

        def read() -> Any:
            checked = [key for key, box in boxes.items() if box.isChecked()]
            if checked:
                return checked
            if field.required:
                raise InvalidValue(f"{field.label}: zaškrtni aspoň jeden prvek.")
            return MISSING

        return holder, read

    def _build_guides(self, field: Field, value: Any):
        editor = GuidesEditor(value)
        editor.edited.connect(self._commit)
        editor.selected.connect(self.guide_selected)
        editor.handle_selected.connect(self.guide_handle_selected)
        editor.step_changed.connect(self.guide_step_changed)
        editor.direction_changed.connect(self.guide_direction_changed)
        return editor, editor.value

    def _build_shapes(self, field: Field, value: Any):
        editor = ShapesEditor(value or [], profile_editor=self._profile_editor)
        editor.edited.connect(self._commit)
        editor.invalid.connect(self.invalid)
        return editor, editor.elements

    # --- přečtení a odeslání ---------------------------------------------------------

    def _commit(self) -> None:
        new = copy.deepcopy(self._data)
        problems = []
        defaults = {field.key: field.default for field, _, _ in self._rows}
        # Nejdřív pole bez podmínky (třeba druh profilu), pak ta, která se podle nich ukazují –
        # skrytá pole (patří k jiné volbě) se nečtou, zůstanou, jak byla.
        ordered = sorted(self._rows, key=lambda row: bool(row[0].when))
        for field, widget, read in ordered:
            if not field_shown(field, new, defaults):
                continue
            try:
                value = read()
            except InvalidValue as exc:
                widget.setStyleSheet(_BAD_STYLE)
                widget.setToolTip(str(exc))
                problems.append(str(exc))
                continue
            if widget.styleSheet():
                widget.setStyleSheet("")
                widget.setToolTip(field.help)
            if value is MISSING:
                new.pop(field.key, None)
            else:
                new[field.key] = value
        if problems:
            self.invalid.emit(problems[0])
            return
        if new != self._data:
            self._data = new
            self._update_visibility()
            self.edited.emit(copy.deepcopy(new))


def _profile_summary(data: dict[str, Any]) -> str:
    counts = (len(data.get("points") or {}), len(data.get("segments") or {}),
              len(data.get("constraints") or []))
    return f"{counts[0]} bodů, {counts[1]} čar, {counts[2]} vazeb a kót"


def shape_label(element: dict[str, Any]) -> str:
    schema = SHAPE_SCHEMAS.get(element.get("shape"))
    label = schema.label if schema else str(element.get("shape"))
    return f"{label} (odečíst)" if element.get("mode") == "subtract" else label


class ShapesEditor(QWidget):
    """Seznam tvarů skici: přidat, smazat, přesunout a upravit vybraný tvar."""

    edited = Signal()
    invalid = Signal(str)

    def __init__(self, elements: list[dict[str, Any]], parent: QWidget | None = None,
                 profile_editor: ProfileEditor | None = None) -> None:
        super().__init__(parent)
        self._elements = copy.deepcopy(elements)
        self._profile_editor = profile_editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Tvary ve skice (otvor = tvar s režimem „odečíst“):"))

        self.list = QListWidget()
        self.list.setObjectName("shapes_list")
        self.list.setMaximumHeight(110)
        self.list.currentRowChanged.connect(self._show_selected)
        layout.addWidget(self.list)

        buttons = QHBoxLayout()
        self.add_button = QToolButton()
        self.add_button.setText("Přidat tvar")
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.add_button)
        for key, schema in SHAPE_SCHEMAS.items():
            action = menu.addAction(schema.label)
            action.setObjectName(f"add_shape_{key}")
            action.triggered.connect(lambda _checked=False, k=key: self.add_shape(k))
        self.add_button.setMenu(menu)
        buttons.addWidget(self.add_button)
        for text, slot in (("Smazat tvar", self.remove_selected), ("▲", lambda: self.move(-1)),
                           ("▼", lambda: self.move(+1))):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, s=slot: s())
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self._detail = QVBoxLayout()
        layout.addLayout(self._detail)
        self._form: FieldsForm | None = None
        self._refresh_list(0 if self._elements else -1)

    def elements(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._elements)

    def add_shape(self, shape_type: str) -> None:
        self._elements.append(new_shape(shape_type))
        self._refresh_list(len(self._elements) - 1)
        self.edited.emit()

    def remove_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        del self._elements[row]
        self._refresh_list(min(row, len(self._elements) - 1))
        self.edited.emit()

    def move(self, offset: int) -> None:
        row = self.list.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < len(self._elements):
            return
        self._elements.insert(target, self._elements.pop(row))
        self._refresh_list(target)
        self.edited.emit()

    def _refresh_list(self, select: int) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for element in self._elements:
            self.list.addItem(shape_label(element))
        self.list.blockSignals(False)
        self.list.setCurrentRow(select)
        self._show_selected(select)

    def _show_selected(self, row: int) -> None:
        if self._form is not None:
            self._detail.removeWidget(self._form)
            self._form.hide()  # smaže se až později – do té doby nesmí překrývat nový formulář
            self._form.deleteLater()
            self._form = None
        if not 0 <= row < len(self._elements):
            return
        schema = SHAPE_SCHEMAS.get(self._elements[row].get("shape"))
        if schema is None:
            return
        self._form = FieldsForm(schema.fields, self._elements[row],
                                profile_editor=self._profile_editor)
        self._form.setObjectName("shape_form")
        self._form.edited.connect(lambda data, r=row: self._shape_edited(r, data))
        self._form.invalid.connect(self.invalid)
        self._detail.addWidget(self._form)

    def _shape_edited(self, row: int, data: dict[str, Any]) -> None:
        self._elements[row] = data
        item = self.list.item(row)
        if item is not None:
            item.setText(shape_label(data))
        self.edited.emit()


class FeatureEditor(QWidget):
    """Panel „Úprava prvku“: formulář vybraného prvku ze stromu."""

    guide_selected = Signal(int)
    guide_handle_selected = Signal(int)
    guide_step_changed = Signal(float)
    guide_direction_changed = Signal(str)
    changed = Signal(str, dict)  # id prvku, nový obsah prvku
    invalid = Signal(str)

    def __init__(self, parent: QWidget | None = None,
                 profile_editor: ProfileEditor | None = None) -> None:
        super().__init__(parent)
        self._profile_editor = profile_editor
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self._layout.addWidget(self.title)
        self.help = QLabel()
        self.help.setTextFormat(Qt.TextFormat.PlainText)
        self.help.setWordWrap(True)
        self.help.setProperty("secondaryText", True)
        self._layout.addWidget(self.help)
        self.wall_panel = LoftWallPanel()
        self._layout.addWidget(self.wall_panel)
        self._layout.addStretch(1)  # volné místo dole, ne mezi poli formuláře
        self.form: FieldsForm | None = None
        self.feature_id: str | None = None
        self.show_feature(None)

    def show_feature(self, feature: dict[str, Any] | None,
                     sketches: list[tuple[str, str]] | None = None,
                     features: list[tuple[str, str]] | None = None) -> None:
        """Ukáže formulář prvku; ``sketches`` = skici před ním jako (id, popis),
        ``features`` = prvky před ním, které jde opakovat v poli a zrcadlit."""
        if self.form is not None:
            self._layout.removeWidget(self.form)
            self.form.hide()  # smaže se až později – do té doby nesmí překrývat nový formulář
            self.form.deleteLater()
            self.form = None
        self.feature_id = feature["id"] if feature else None
        self.wall_panel.setVisible(feature is not None and feature.get("type") == "loft")
        if feature is None:
            self.help.hide()
            self.title.setText("Vyber prvek ve stromu prvků – tady se ukážou jeho hodnoty.\n\n"
                               "Nový prvek přidáš tlačítkem „Přidat prvek“ pod stromem.")
            return
        schema = FEATURE_SCHEMAS.get(feature.get("type"))
        if schema is None:
            self.help.hide()
            self.title.setText(f"Prvek typu „{feature.get('type')}“ tady upravit nejde.")
            return
        self.title.setText(f"<b>{html.escape(schema.label)}</b> ({html.escape(feature['id'])})")
        self.help.setText(schema.help)
        self.help.setVisible(bool(schema.help))
        self.form = FieldsForm(schema.fields, feature, sketches,
                               profile_editor=self._profile_editor, features=features)
        self.form.setObjectName("feature_form")
        self.form.edited.connect(lambda data: self.changed.emit(self.feature_id, data))
        self.form.invalid.connect(self.invalid)
        self.form.guide_selected.connect(self.guide_selected)
        self.form.guide_handle_selected.connect(self.guide_handle_selected)
        self.form.guide_step_changed.connect(self.guide_step_changed)
        self.form.guide_direction_changed.connect(self.guide_direction_changed)
        self._layout.insertWidget(2, self.form)
