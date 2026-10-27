"""Identita a obnova vloženého zdroje STEP."""
import copy
from pathlib import Path

import pytest

from skodacad.step_probe import StepProbeError
from skodacad.step_source import read_source_file, restore_source, source_bytes, source_record

STEP = Path(__file__).parent / "fixtures" / "step" / "01-jedno-teleso.step"


def test_round_trip_and_path_not_preserved():
    raw = read_source_file(STEP)
    record = source_record(raw, r"C:\\private\\part.step")
    assert record["source_name"] == "part.step"
    assert source_bytes(record) == raw


@pytest.mark.parametrize(("field", "value"), [
    ("size_bytes", 1), ("size_bytes", True), ("sha256", "0" * 64),
    ("data", "!"), ("encoding", "hex"),
])
def test_corruption_is_rejected(field, value):
    record = source_record(STEP.read_bytes(), "part.step")
    record[field] = value
    with pytest.raises(StepProbeError):
        source_bytes(record)


def test_restore_requires_identical_data_without_mutating_original():
    raw = STEP.read_bytes()
    record = source_record(raw, "part.step")
    del record["data"]
    before = copy.deepcopy(record)
    with pytest.raises(StepProbeError):
        restore_source(record, raw + b"x")
    assert record == before
    assert source_bytes(restore_source(record, raw)) == raw
    assert record == before
