"""Worker diagnostics preserve messages and expose incomplete termination tails."""
import json

import pytest

from diagnose_p85 import Trace, TracedConnection, read_worker_trace


def test_trace_forwards_the_same_objects_and_records_job_identity(tmp_path):
    request = ("rebuild", 7, {"features": [{"id": "s"}]}, False)
    reply = ("result", 7, {"part": None})

    class Connection:
        sent = None

        def recv(self):
            return request

        def send(self, message):
            self.sent = message

    original = Connection()
    trace = Trace(tmp_path, started=1.)
    summary = tmp_path / "summary.json"
    connection = TracedConnection(original, trace, summary)
    try:
        assert connection.recv() is request
        connection.send(reply)
        assert original.sent is reply
        saved = json.loads(summary.read_text())
        assert saved["epoch_perf_s"] == 1.
        assert saved["last_job_context"] == {"kind": "rebuild", "job": 7, "features": 1}
        assert saved["errors"] == [] and not saved["loop_finished"]
        records, partial = read_worker_trace(tmp_path / "timing.jsonl")
        assert [r["type"] for r in records] == ["identity", "request", "reply"]
        assert records[-1]["job"] == 7 and partial == 0
        assert len({r["pid"] for r in records}) == 1
    finally:
        trace.stream.close()


def test_only_an_unfinished_last_worker_record_is_tolerated(tmp_path):
    path = tmp_path / "timing.jsonl"
    path.write_bytes(b'{"type":"identity"}\n{"type":')
    records, partial = read_worker_trace(path)
    assert records == [{"type": "identity"}] and partial == 8
    path.write_bytes(b'{"type":"identity"}\n{"type":\n')
    with pytest.raises(ValueError):
        read_worker_trace(path)
    path.write_bytes(b'{bad}\n{"type":"reply"}')
    with pytest.raises(ValueError):
        read_worker_trace(path)
