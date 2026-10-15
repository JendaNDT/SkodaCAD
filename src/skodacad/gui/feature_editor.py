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
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.schema import (
    FACE_CHOICES,
    FEATURE_SCHEMAS,
    SHAPE_SCHEMAS,
    Field,
    new_shape,
)
from skodacad.selectors import describe_edges
from skodacad.session import format_parameter_value, parse_parameter_text

MISSING = object()  # pole je prázdné a nepovinné → klíč se z prvku odebere
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
    if optional:
        combo.addItem(empty_label, None)
    for key, label in choices:
        combo.addItem(label, key)
    index = combo.findData(current) if current is not None else 0
    combo.setCurrentIndex(max(index, 0))
    return combo


class FieldsForm(QWidget):
    """Formulář nad jedním slovníkem (prvek nebo tvar skici) podle seznamu polí.

    Po každé dokončené úpravě přečte všechna pole a vyšle ``edited`` s novým
    slovníkem. Klíče, které schéma nezná, zůstanou zachované.
    """

    edited = Signal(dict)
    invalid = Signal(str)

    def __init__(self, fields: tuple[Field, ...], data: dict[str, Any],
                 sketches: list[tuple[str, str]] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = copy.deepcopy(data)
        self._sketches = sketches or []
        self._rows: list[tuple[Field, QWidget, Callable[[], Any]]] = []
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in fields:
            widget, read = self._build(field, self._data.get(field.key))
            widget.setObjectName(f"field_{field.key}")
            if field.help:
                widget.setToolTip(field.help)
            if field.kind in ("shapes", "bool"):
                layout.addRow(widget)
            else:
                layout.addRow(field.label, widget)
            self._rows.append((field, widget, read))

    @property
    def data(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def widget(self, key: str) -> QWidget:
        return next(widget for field, widget, _ in self._rows if field.key == key)

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
        combo = _combo(field.choices, value if value is not None else field.default,
                       optional=not field.required)
        combo.currentIndexChanged.connect(self._commit)

        def read() -> Any:
            key = combo.currentData()
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
                       "<span style='color:#666'>Další hrany: vyber je ve 3D (Ctrl+klik) → "
                       "pravé tlačítko → Přidat vybrané hrany. Hrany prvku jsou ve 3D "
                       "zvýrazněné růžově.</span>")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        kept = copy.deepcopy(value)
        return label, lambda: copy.deepcopy(kept)

    def _build_point(self, field: Field, value: Any):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        point = value if isinstance(value, list | tuple) and len(value) == 2 else [None, None]
        edits = []
        for axis, coordinate in zip(("x", "y"), point, strict=True):
            edit = QLineEdit(_number_text(coordinate))
            edit.setObjectName(f"point_{axis}")
            edit.setPlaceholderText(f"{axis} = 0")
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

    def _build_points(self, field: Field, value: Any):
        edit = _PlainTextEdit()
        lines = [f"{_number_text(x)}; {_number_text(y)}" for x, y in (value or [])]
        edit.setPlainText("\n".join(lines))
        edit.setToolTip("Jeden bod na řádek ve tvaru  x; y  (např. 10; 0). Stačí 3 body.")
        edit.setFixedHeight(110)
        edit.editingFinished.connect(self._commit)

        def read() -> Any:
            points = []
            coordinate = Field(field.key, "Souřadnice bodu", "number")
            for number_, line in enumerate(edit.toPlainText().splitlines(), start=1):
                if not line.strip():
                    continue
                parts = line.split(";")
                if len(parts) != 2:
                    raise InvalidValue(f"Řádek {number_}: napiš bod jako  x; y")
                points.append([parse_number(part, coordinate) for part in parts])
            if len(points) < 3:
                raise InvalidValue("Mnohoúhelník potřebuje aspoň 3 body.")
            return points

        return edit, read

    def _build_shapes(self, field: Field, value: Any):
        editor = ShapesEditor(value or [])
        editor.edited.connect(self._commit)
        editor.invalid.connect(self.invalid)
        return editor, editor.elements

    # --- přečtení a odeslání ---------------------------------------------------------

    def _commit(self) -> None:
        new = copy.deepcopy(self._data)
        problems = []
        for field, widget, read in self._rows:
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
            self.edited.emit(copy.deepcopy(new))


def shape_label(element: dict[str, Any]) -> str:
    schema = SHAPE_SCHEMAS.get(element.get("shape"))
    label = schema.label if schema else str(element.get("shape"))
    return f"{label} (odečíst)" if element.get("mode") == "subtract" else label


class ShapesEditor(QWidget):
    """Seznam tvarů skici: přidat, smazat, přesunout a upravit vybraný tvar."""

    edited = Signal()
    invalid = Signal(str)

    def __init__(self, elements: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elements = copy.deepcopy(elements)
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
        self._form = FieldsForm(schema.fields, self._elements[row])
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

    changed = Signal(str, dict)  # id prvku, nový obsah prvku
    invalid = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self._layout.addWidget(self.title)
        self._layout.addStretch(1)  # volné místo dole, ne mezi poli formuláře
        self.form: FieldsForm | None = None
        self.feature_id: str | None = None
        self.show_feature(None)

    def show_feature(self, feature: dict[str, Any] | None,
                     sketches: list[tuple[str, str]] | None = None) -> None:
        """Ukáže formulář prvku; ``sketches`` = skici před ním jako (id, popis)."""
        if self.form is not None:
            self._layout.removeWidget(self.form)
            self.form.hide()  # smaže se až později – do té doby nesmí překrývat nový formulář
            self.form.deleteLater()
            self.form = None
        self.feature_id = feature["id"] if feature else None
        if feature is None:
            self.title.setText("Vyber prvek ve stromu prvků – tady se ukážou jeho hodnoty.\n\n"
                               "Nový prvek přidáš tlačítkem „Přidat prvek“ pod stromem.")
            return
        schema = FEATURE_SCHEMAS.get(feature.get("type"))
        if schema is None:
            self.title.setText(f"Prvek typu „{feature.get('type')}“ tady upravit nejde.")
            return
        self.title.setText(f"<b>{schema.label}</b> <span style='color:#777'>({feature['id']})"
                           f"</span><br><span style='color:#555'>{schema.help}</span>")
        self.form = FieldsForm(schema.fields, feature, sketches)
        self.form.setObjectName("feature_form")
        self.form.edited.connect(lambda data: self.changed.emit(self.feature_id, data))
        self.form.invalid.connect(self.invalid)
        self._layout.insertWidget(1, self.form)
