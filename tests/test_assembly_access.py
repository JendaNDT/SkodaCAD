"""Nativní výběr projektu musí předcházet čtení složek a lze jej zrušit."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from skodacad.gui import assembly_access  # noqa: E402


@pytest.fixture
def chooser(monkeypatch):
    monkeypatch.setattr(assembly_access, "IS_MACOS", True)
    monkeypatch.setattr(assembly_access, "_granted_projects", set())
    calls, warnings = [], []
    answer = {"folder": ""}

    def choose(parent, title, start, **kwargs):
        calls.append((title, start, kwargs))
        if "folders" in answer:
            return answer["folders"].pop(0)
        return answer["folder"]

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[1:]))
    return answer, calls, warnings


def test_project_root_uses_parent_reference_without_listing_directories(chooser, examples_dir,
                                                                      monkeypatch):
    answer, calls, warnings = chooser
    answer["folder"] = str(examples_dir)

    real_listdir = assembly_access.os.listdir

    def after_choice(*args):
        assert calls, "adresář se nesmí číst před systémovým výběrem"
        return real_listdir(*args)

    monkeypatch.setattr(assembly_access.os, "listdir", after_choice)
    source = examples_dir / "sestavy" / "krabicka_s_vickem.json"
    assert assembly_access.request_project_access(None, source)
    assert calls[0][1] == str(examples_dir)
    assert calls[0][2]["options"] & QFileDialog.Option.ShowDirsOnly
    assert not calls[0][2]["options"] & QFileDialog.Option.DontUseNativeDialog
    assert not warnings
    # Souhlas platí jen v procesu a pokrývá další sestavy téhož projektu.
    assert assembly_access.request_project_access(None, source)
    assert len(calls) == 1


@pytest.mark.parametrize("choice", ["cancel", "too_narrow", "unrelated"])
def test_cancel_or_wrong_project_does_not_grant_access(chooser, examples_dir, tmp_path, choice):
    answer, calls, warnings = chooser
    answer["folder"] = {"cancel": "", "too_narrow": str(examples_dir / "sestavy"),
                        "unrelated": str(tmp_path)}[choice]
    assert not assembly_access.request_project_access(
        None, examples_dir / "sestavy" / "krabicka_s_vickem.json")
    assert not assembly_access._granted_projects
    assert bool(warnings) == (choice != "cancel")
    assert len(calls) == 1


def test_non_macos_and_invalid_recipe_defer_to_normal_open(chooser, examples_dir, tmp_path,
                                                         monkeypatch):
    _, calls, _ = chooser
    monkeypatch.setattr(assembly_access, "IS_MACOS", False)
    assert assembly_access.request_project_access(
        None, examples_dir / "sestavy/krabicka_s_vickem.json")
    monkeypatch.setattr(assembly_access, "IS_MACOS", True)
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"kind":"assembly"}')
    assert assembly_access.request_project_access(None, invalid)
    assert not calls


def test_cached_project_does_not_cover_another_project(chooser, examples_dir, tmp_path):
    answer, calls, _ = chooser
    answer["folder"] = str(examples_dir)
    source = examples_dir / "sestavy/krabicka_s_vickem.json"
    assert assembly_access.request_project_access(None, source)
    # Přesunutý recept s relativními cestami potřebuje nový systémový výběr.
    other = tmp_path / "other" / "sestavy"
    other.mkdir(parents=True)
    file = other / source.name
    file.write_bytes(source.read_bytes())
    answer["folder"] = ""
    assert not assembly_access.request_project_access(None, file)
    assert len(calls) == 2


def test_subassembly_requires_its_external_part_folder_before_open(chooser, tmp_path):
    from test_assembly import assembly_data, component, part_data, write

    answer, calls, warnings = chooser
    project = tmp_path / "projekt"
    source = write(project / "sestavy/hlavni.json", assembly_data([
        component("pod", "moduly/pod.json")]))
    write(project / "sestavy/moduly/pod.json", assembly_data([
        component("dil", "../../dily/kvadr.json")]))
    write(project / "dily/kvadr.json", part_data())
    # První systémový výběr dovolí sestavy, ale ještě ne jejich vzdálený díl.
    answer["folder"] = str(project / "sestavy")
    assert not assembly_access.request_project_access(None, source)
    assert warnings  # úzká složka nesmí spustit sestavení s neověřeným přístupem


@pytest.fixture
def nested(tmp_path):
    from test_assembly import assembly_data, component, part_data, write

    root = tmp_path / "projekt"
    source = write(root / "sestavy/hlavni.json", assembly_data([
        component("pod", "moduly/pod.json")]))
    sub = write(root / "sestavy/moduly/pod.json", assembly_data([
        component("dil", "../../dily/kvadr.json")]))
    part = write(root / "dily/kvadr.json", part_data())
    return root, source, sub, part


def test_nested_access_expands_before_external_directory_or_recipe_is_read(
        chooser, nested, monkeypatch):
    root, source, sub, part = nested
    answer, calls, warnings = chooser
    answer["folders"] = [str(source.parent), str(root)]
    real_listdir, real_read = assembly_access.os.listdir, Path.read_text

    def listdir(path):
        if Path(path) == part.parent:
            assert len(calls) == 2, "vnější složka se nesmí vypsat před druhým panelem"
        return real_listdir(path)

    def read(path, *args, **kwargs):
        if path == part:
            assert len(calls) == 2, "vnější díl se nesmí číst před druhým panelem"
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(assembly_access.os, "listdir", listdir)
    monkeypatch.setattr(Path, "read_text", read)
    assert assembly_access.request_project_access(None, source)
    assert [c[1] for c in calls] == [str(source.parent), str(root)]
    assert not warnings
    assert assembly_access.request_project_access(None, source)
    assert len(calls) == 2  # širší souhlas lze použít znovu


def test_cancel_expansion_never_reads_external_part_and_retry_is_possible(
        chooser, nested, monkeypatch):
    root, source, sub, part = nested
    answer, calls, warnings = chooser
    answer["folders"] = [str(source.parent), ""]
    real_read = Path.read_text

    def read(path, *args, **kwargs):
        assert path != part, "zrušený panel nesmí otevřít soubor dílu"
        return real_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", read)
        assert not assembly_access.request_project_access(None, source)
    assert not warnings
    answer["folders"] = [str(root)]
    assert assembly_access.request_project_access(None, source)
    assert len(calls) == 3


def test_cached_narrow_project_still_checks_subassembly_sources(chooser, nested):
    root, source, sub, part = nested
    answer, calls, _ = chooser
    assembly_access._granted_projects.add(source.parent)
    answer["folder"] = str(root)
    assert assembly_access.request_project_access(None, source)
    assert len(calls) == 1 and calls[0][1] == str(root)


def test_case_mismatched_subassembly_is_checked_before_external_access(chooser, nested):
    from test_assembly import assembly_data, component, write

    root, source, sub, part = nested
    write(source, assembly_data([component("pod", "MODULY/POD.JSON")]))
    answer, calls, warnings = chooser
    answer["folders"] = [str(source.parent), str(root)]
    assert assembly_access.request_project_access(None, source)
    assert len(calls) == 2 and not warnings


def test_symlink_cannot_lead_to_unselected_directory(chooser, nested, monkeypatch):
    from test_assembly import assembly_data, component, write

    root, source, sub, part = nested
    link = source.parent / "odkaz"
    try:
        link.symlink_to(part.parent, target_is_directory=True)
    except OSError:
        pytest.skip("Systém nedovoluje vytvořit symbolický odkaz bez dalšího oprávnění.")
    write(source, assembly_data([component("dil", "odkaz/kvadr.json")]))
    answer, calls, warnings = chooser
    answer["folders"] = [str(source.parent), ""]
    real_listdir = assembly_access.os.listdir

    def listdir(path):
        assert Path(path) != part.parent, "cíl symlinku potřebuje vlastní souhlas"
        return real_listdir(path)

    monkeypatch.setattr(assembly_access.os, "listdir", listdir)
    assert not assembly_access.request_project_access(None, source)
    assert len(calls) == 2 and not warnings


def test_shared_subassembly_and_cycle_are_visited_once(chooser, nested, monkeypatch):
    from test_assembly import assembly_data, component, write

    root, source, sub, part = nested
    write(source, assembly_data([component("a", "moduly/pod.json"),
                                component("b", "moduly/pod.json")]))
    write(sub, assembly_data([component("zpet", "../hlavni.json")]))
    answer, calls, _ = chooser
    answer["folder"] = str(root)
    read_count = []
    real_read = Path.read_text

    def read(path, *args, **kwargs):
        read_count.append(path)
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    assert assembly_access.request_project_access(None, source)
    assert read_count.count(sub) == 1 and read_count.count(source) == 1
    assert len(calls) == 1  # skutečný cyklus pak ohlásí běžné sestavení


def test_preflight_has_a_component_budget(chooser, nested, monkeypatch):
    root, source, sub, part = nested
    answer, calls, warnings = chooser
    answer["folder"] = str(root)
    monkeypatch.setattr(assembly_access, "MAX_COMPONENTS", 1)
    assert not assembly_access.request_project_access(None, source)
    assert "přesáhla 1" in warnings[0][1]


@pytest.mark.parametrize("state", ["missing", "json", "utf8"])
def test_missing_or_broken_subassembly_is_left_to_normal_diagnostics(chooser, nested, state):
    root, source, sub, part = nested
    if state == "missing":
        sub.unlink()
    else:
        sub.write_bytes(b"{broken" if state == "json" else b"\xff")
    answer, calls, warnings = chooser
    answer["folder"] = str(root)
    assert assembly_access.request_project_access(None, source)
    assert not warnings and len(calls) == 1
