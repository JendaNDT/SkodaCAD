import pytest

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.cli import main
from skodacad.export import FORMATS, export

# všechny ukázky i referenční díly NDT („ndt/deska“)
EXAMPLE_NAMES = sorted(path.relative_to(EXAMPLES).with_suffix("").as_posix()
                       for path in [*EXAMPLES.glob("*.json"), *EXAMPLES.glob("ndt/*.json")])


def test_examples_are_found():
    assert {"priruba", "krabicka", "hridel", "paka", "deska", "kryt"} <= set(EXAMPLE_NAMES)
    assert "ndt/zebro" in EXAMPLE_NAMES


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_build_and_export_everything(examples_dir, tmp_path, name):
    result = rebuild(Document.load(examples_dir / f"{name}.json"))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    assert len(result.part.solids()) == 1
    for fmt in FORMATS:
        path = export(result.part, tmp_path / f"{name.replace('/', '_')}.{fmt}")
        assert path.stat().st_size > 0


def test_cli_build_prints_tree_and_writes_files(examples_dir, tmp_path, capsys):
    code = main(["build", str(examples_dir / "priruba.json"), "-o", str(tmp_path),
                 "--set", "n=6", "--format", "step,svg"])
    out = capsys.readouterr().out
    assert code == 0
    assert "✓ Vysunutí „Vrtání děr“" in out
    assert "n=6" in out
    assert "Hmotnost:" in out
    assert (tmp_path / "priruba.step").exists() and (tmp_path / "priruba.svg").exists()


def test_cli_reports_failed_feature(tmp_path, capsys):
    model = tmp_path / "chyba.json"
    model.write_text(
        '{"format": "skodacad", "version": 1, "features": ['
        '{"id": "s", "type": "sketch", "elements": [{"shape": "circle", "diameter": 10}]},'
        '{"id": "e", "type": "extrude", "sketch": "s", "distance": 5},'
        '{"id": "f", "type": "fillet", "edges": "all", "radius": 20}]}',
        encoding="utf-8",
    )
    code = main(["build", str(model), "-o", str(tmp_path), "--format", "step"])
    out = capsys.readouterr().out
    assert code == 1
    assert "✕ Zaoblení f – Zaoblení R20 se nepodařilo" in out


def test_cli_bad_override(examples_dir, capsys):
    code = main(["build", str(examples_dir / "priruba.json"), "--set", "neexistuje=1"])
    assert code == 2
    assert "nemá parametr" in capsys.readouterr().err


def test_cli_prints_saved_measurements(examples_dir, tmp_path, capsys):
    code = main(["build", str(examples_dir / "trubka.json"), "-o", str(tmp_path),
                 "--set", "h=4", "--format", "step"])
    out = capsys.readouterr().out
    assert code == 0
    assert ("Měření:\n  Jmenovitá tloušťka stěny: 6.00 mm\n"
            "  Zbytková tloušťka pod jamkou: 2.00 mm\n  Vnější průměr: 114.30 mm") in out
