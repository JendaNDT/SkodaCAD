"""Nativní výběr projektu musí předcházet čtení složek a lze jej zrušit."""

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
        return answer["folder"]

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[1:]))
    return answer, calls, warnings


def test_project_root_uses_parent_reference_without_listing_directories(chooser, examples_dir,
                                                                      monkeypatch):
    answer, calls, warnings = chooser
    answer["folder"] = str(examples_dir)

    def forbidden(*args):
        raise AssertionError("adresář se nesmí číst před systémovým výběrem")

    monkeypatch.setattr(assembly_access.os, "listdir", forbidden)
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
