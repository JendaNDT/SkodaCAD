"""Závazné vymezení UT (``docs/ndt/04-zavazne-vymezeni-ut.md``): povinné upozornění v přesném
znění v okně i ve výstupech a žádné označení, které by slibovalo prozvučitelnost nebo detekci."""

from pathlib import Path

import pytest

from conftest import EXAMPLES
from skodacad.cli import main
from skodacad.ndt import UT_ACCESS, UT_COVERAGE, UT_DISCLAIMER

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "docs" / "ndt" / "04-zavazne-vymezeni-ut.md"
NDT = EXAMPLES / "ndt"


def test_ut_disclaimer_is_word_for_word_from_binding_document():
    text = SCOPE.read_text(encoding="utf-8")
    section = text.split("## Povinné upozornění", 1)[1]
    quote = next(line[2:].strip() for line in section.splitlines() if line.startswith("> "))
    assert UT_DISCLAIMER == quote


def test_recommended_names_from_binding_document():
    text = SCOPE.read_text(encoding="utf-8")
    assert f"„{UT_ACCESS}“" in text and f"„{UT_COVERAGE}“" in text


@pytest.mark.parametrize("phrase", ["mapa prozvučitelnosti", "pravděpodobnost detekce",
                                    "a-scan", "b-scan"])
def test_no_misleading_ut_wording_in_program(phrase):
    """Program nesmí výsledek vydávat za prozvučitelnost ani detekci (texty okna, CLI, AI)."""
    sources = [*sorted((ROOT / "src").rglob("*.py")), ROOT / "README.md"]
    found = [path.relative_to(ROOT).as_posix() for path in sources
             if phrase in path.read_text(encoding="utf-8").lower()]
    assert found == []


def test_cli_prints_ut_disclaimer(capsys, tmp_path):
    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "22,0,20", "--smer", "-1,0,0"]) == 0
    assert f"({UT_DISCLAIMER})" in capsys.readouterr().out
    assert main(["build", str(NDT / "deska.json"), "-o", str(tmp_path),
                 "--format", "step"]) == 0
    assert f"({UT_DISCLAIMER})" in capsys.readouterr().out  # deska má UT studii
