import pytest

from profile_p8 import Recorder


def test_nested_wall_intervals_partition_root_without_double_counting():
    values = iter([0., 1., 2., 5., 7., 9.])
    r = Recorder(clock=lambda: next(values))
    with r.span("root"), r.span("a"), r.span("b"):
        pass
    assert r.rows["root"]["inclusive_s"] == 9
    assert r.rows["a"]["inclusive_s"] == 6
    assert [r.rows[n]["self_s"] for n in ("root", "a", "b")] == [3, 3, 3]
    assert sum(row["self_s"] for row in r.rows.values()) == 9
    assert not r.stack


def test_recursive_label_accumulates_self_without_adding_inclusive_twice():
    values = iter([0., 1., 2., 4.])
    r = Recorder(clock=lambda: next(values))
    with r.span("recursive"), r.span("recursive"):
        pass
    assert r.rows["recursive"] == {"calls": 2, "inclusive_s": 5., "self_s": 4.}


def test_other_thread_does_not_enter_main_thread_intervals():
    import threading

    class Target:
        @classmethod
        def identity(cls):
            return cls

    original = Target.__dict__["identity"]
    returned = []
    r = Recorder()
    with r.patch([(Target, "identity", "identity")]), r.span("root"):
        worker = threading.Thread(target=lambda: returned.append(Target.identity()))
        worker.start()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert Target.identity() is Target
    assert returned == [Target]
    assert r.rows["identity"]["calls"] == 1
    assert Target.__dict__["identity"] is original


def test_wrapped_static_and_bound_methods_keep_semantics_and_restore_after_error():
    class Target:
        @staticmethod
        def add(a, b):
            return a+b

        def fail(self):
            raise ValueError("původní chyba")

    original_add = Target.__dict__["add"]
    original_fail = Target.fail
    r = Recorder()
    with pytest.raises(ValueError, match="původní chyba"):
        with r.patch([(Target, "add", "add"), (Target, "fail", "fail")]), r.span("root"):
            assert Target().add(2, 3) == 5
            Target().fail()
    assert Target.__dict__["add"] is original_add and Target.fail is original_fail
    assert r.rows["add"]["calls"] == r.rows["fail"]["calls"] == 1
    assert not r.stack
