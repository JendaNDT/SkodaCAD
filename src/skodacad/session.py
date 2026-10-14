"""Otevřený model v aplikaci: dokument, poslední přepočet, neuložené změny.

Tahle vrstva je mezi grafickým rozhraním a jádrem. Okno nikdy nemodeluje
samo – jen volá metody ``ModelSession`` (otevři, změň parametr, ulož,
exportuj) a zobrazuje výsledek. Díky tomu jde celá logika aplikace
testovat bez okna.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from skodacad.document import Document, DocumentError
from skodacad.export import export
from skodacad.expressions import ExpressionError, resolve_parameters
from skodacad.properties import PartProperties, compute
from skodacad.rebuild import BuildResult, rebuild

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


def parse_parameter_text(text: str) -> int | float | str:
    """Text z políčka parametru → číslo (i s desetinnou čárkou), jinak výraz."""
    text = text.strip()
    if not text:
        raise DocumentError("Hodnota parametru nesmí být prázdná.")
    if _NUMBER.fullmatch(text):
        value = float(text.replace(",", "."))
        return int(value) if value.is_integer() and "," not in text and "." not in text else value
    return text


def format_parameter_value(value: Any) -> str:
    """Hodnota parametru pro zobrazení v políčku."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class ModelSession:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.document: Document | None = None
        self.result: BuildResult | None = None
        self.dirty = False

    # --- otevření a přepočet ---------------------------------------------------

    def open(self, path: str | Path) -> BuildResult:
        document = Document.load(path)
        self.path = Path(path)
        self.document = document
        self.dirty = False
        return self.rebuild()

    def open_template(self, path: str | Path) -> BuildResult:
        """Otevře model jako předlohu (ukázku): „Uložit“ se zeptá na nový soubor."""
        result = self.open(path)
        self.path = None
        return result

    def rebuild(self) -> BuildResult:
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        self.result = rebuild(self.document)
        return self.result

    # --- úpravy ------------------------------------------------------------------

    def set_parameter(self, name: str, text: str) -> BuildResult:
        """Změní parametr a přepočítá model.

        Neplatná hodnota (neznámý parametr ve výrazu, kruhový odkaz …) vyvolá
        ``DocumentError`` a model zůstane beze změny.
        """
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        if name not in self.document.parameters:
            raise DocumentError(f"Model nemá parametr „{name}“.")
        value = parse_parameter_text(text)
        candidate = copy.deepcopy(self.document.parameters)
        candidate[name] = value
        try:
            resolve_parameters(candidate)
        except ExpressionError as exc:
            raise DocumentError(str(exc)) from None
        if candidate[name] != self.document.parameters[name]:
            self.document.parameters[name] = value
            self.dirty = True
        return self.rebuild()

    # --- ukládání a export ---------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        target = Path(path) if path is not None else self.path
        if target is None:
            raise DocumentError("Model zatím nemá soubor, zvol „Uložit jako“.")
        self.document.save(target)
        self.path = target
        self.dirty = False
        return target

    def export(self, path: str | Path) -> Path:
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá žádné těleso, není co exportovat.")
        return export(self.result.part, path)

    # --- informace pro zobrazení -------------------------------------------------

    @property
    def properties(self) -> PartProperties | None:
        if self.result is None or self.result.part is None or self.document is None:
            return None
        return compute(self.result.part, self.document.material)

    @property
    def title(self) -> str:
        if self.document is None:
            return "ŠkodaCAD"
        star = "*" if self.dirty else ""
        filename = self.path.name if self.path else "nový model"
        return f"{star}{self.document.name} ({filename}) – ŠkodaCAD"
