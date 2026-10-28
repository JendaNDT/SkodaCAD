"""Přenositelné bajty STEP, jejich kontrola a obnova; bez změny formátu modelu."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path
from typing import Any

from skodacad.step_probe import MAX_STEP_BYTES, StepProbeError

MAX_ENCODED = 4 * ((MAX_STEP_BYTES + 2) // 3)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def source_record(data: bytes, filename: str) -> dict[str, Any]:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_STEP_BYTES:
        raise StepProbeError("STEP je prázdný nebo větší než povolených 16 MiB.")
    # Název je jen popisek, nikdy cesta pro čtení. Odstranit i cesty z druhého OS.
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not name or any(ord(c) < 32 for c in name):
        raise StepProbeError("Název STEP není platný.")
    return {"source_name": name, "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "encoding": "base64",
            "data": base64.b64encode(data).decode("ascii")}


def read_source_file(path: str | Path) -> bytes:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_STEP_BYTES + 1)
    except OSError as exc:
        raise StepProbeError(f"Soubor STEP nelze přečíst: {exc}.") from exc
    if not data or len(data) > MAX_STEP_BYTES:
        raise StepProbeError("STEP je prázdný nebo větší než povolených 16 MiB.")
    return data


def source_bytes(record: dict[str, Any]) -> bytes:
    if not isinstance(record, dict):
        raise StepProbeError("Údaje zdroje STEP chybí.")
    size = record.get("size_bytes")
    digest = record.get("sha256")
    encoded = record.get("data")
    if (type(size) is not int or not 0 < size <= MAX_STEP_BYTES
            or not isinstance(digest, str) or not HASH_RE.fullmatch(digest)
            or record.get("encoding") != "base64" or not isinstance(encoded, str)
            or len(encoded) > MAX_ENCODED or len(encoded) != 4 * ((size + 2) // 3)):
        raise StepProbeError("Údaje vloženého STEP jsou neúplné nebo neplatné.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise StepProbeError("Vložený STEP není platně zakódovaný.") from exc
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise StepProbeError("Vložený STEP má jinou velikost nebo kontrolní otisk.")
    return data


def restore_source(record: dict[str, Any], data: bytes) -> dict[str, Any]:
    """Vrátí kopii s obnoveným obsahem jen při přesné shodě identity."""
    if (not isinstance(record, dict) or type(record.get("size_bytes")) is not int
            or not isinstance(record.get("sha256"), str)
            or not isinstance(data, bytes) or len(data) != record["size_bytes"]
            or len(data) > MAX_STEP_BYTES or hashlib.sha256(data).hexdigest() != record["sha256"]):
        raise StepProbeError("Vybraný soubor neodpovídá původnímu STEP.")
    restored = dict(record)
    restored.update(encoding="base64", data=base64.b64encode(data).decode("ascii"))
    source_bytes(restored)
    return restored
