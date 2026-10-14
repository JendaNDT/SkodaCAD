from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skodacad import Document

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def make_doc(features: list[dict[str, Any]], parameters: dict[str, Any] | None = None,
             material: str = "ocel") -> Document:
    return Document.from_dict({
        "format": "skodacad",
        "version": 1,
        "name": "test",
        "material": material,
        "parameters": parameters or {},
        "features": features,
    })


def box_features(width: Any = 20, depth: Any = 30, height: Any = 40) -> list[dict[str, Any]]:
    """Kvádr width × depth × height stojící na rovině XY, vystředěný v X a Y."""
    return [
        {"id": "s", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": width, "height": depth}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": height},
    ]


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES
