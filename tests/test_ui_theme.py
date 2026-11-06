"""P7.48: barvy, písmo a ikony Duo podle návrhu hlavního okna 1a."""

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtGui import QColor, QPalette  # noqa: E402

from skodacad.gui import ui_theme  # noqa: E402
from skodacad.gui.cad_icons import duo_svg, icon  # noqa: E402
from skodacad.gui.duo_icons import DUO  # noqa: E402
from skodacad.gui.ui_colors import contrast  # noqa: E402

DESIGN = Path(__file__).parents[1] / "docs" / "p7-48-navrh-okna"
SKETCH = ("skbg", "skgrid", "skfree", "sktext")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def appearance(app):
    """Vzhled zvolený v testu; po testu se vrátí původní volba i paleta."""
    before = app.property("skodacadAppearance")

    def choose(key):
        app.setProperty("skodacadAppearance", key)
        return ui_theme.apply(app)

    yield choose
    app.setProperty("skodacadAppearance", before)
    ui_theme.apply(app)


def _parse(value):
    value = re.sub(r"\(=.*?\)", "", value).strip()
    rgba = re.fullmatch(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", value)
    if rgba:
        r, g, b, a = rgba.groups()
        return int(r), int(g), int(b), float(a)
    return value


def _design_tokens():
    """Tabulka Design Tokens z README návrhu → {token: (světlý, tmavý)}."""
    text = (DESIGN / "README.md").read_text("utf-8")
    table = text.split("## Design Tokens", 1)[1].strip().split("\n\n", 1)[0]
    result = {}
    for row in table.splitlines()[2:]:
        name, light, dark = (cell.strip() for cell in row.strip("|").split("|"))
        if name.startswith("skicář"):
            names = SKETCH
        else:
            names = [n.strip().lstrip("-").split(" ")[0]
                     for n in re.split(r"\s*(?:/|→)\s*", re.sub(r"\(.*?\)", "", name))]
        lights = re.split(r"\s+(?:/|→)\s+", light)
        darks = re.split(r"\s+(?:/|→)\s+", dark)
        assert len(names) == len(lights) == len(darks), row
        for n, a, b in zip(names, lights, darks, strict=True):
            result[n] = (_parse(a), _parse(b))
    return result


def test_tokens_match_design_table():
    design = _design_tokens()
    assert len(design) == len(ui_theme.LIGHT) == len(ui_theme.DARK) == 23
    for name, (light, dark) in design.items():
        assert ui_theme.LIGHT[name] == light, name
        assert ui_theme.DARK[name] == dark, name


@pytest.mark.parametrize("dark", [False, True])
def test_text_on_cards_and_fields_is_readable(dark):
    t = ui_theme.tokens(dark)
    card, field = ui_theme.card_color(dark), QColor(t["ctl"])
    for key in ("fg", "fg2", "ok", "warn", "err"):
        for background in (card, field):
            assert contrast(QColor(t[key]), background) >= 4.5, (key, dark)
    # Metadata (11 px, --fg3) mají v návrhu nižší kontrast; aspoň 3 : 1.
    assert contrast(QColor(t["fg3"]), card) >= 3
    assert contrast(QColor("#ffffff"), QColor(t["btn"])) >= 4.5


def test_opaque_card_mixes_float_over_viewport():
    assert ui_theme.card_color(False).name() == "#f6f7f9"
    assert ui_theme.card_color(True).name() == "#2c2d31"
    assert ui_theme.opaque(ui_theme.LIGHT["accentbg"], "#ffffff").name() == "#dfebfa"


@pytest.mark.parametrize("dark", [False, True])
def test_palette_uses_design_colors(app, dark):
    t = ui_theme.tokens(dark)
    palette = ui_theme.palette(dark)
    role = QPalette.ColorRole
    assert palette.color(role.Window) == ui_theme.card_color(dark)
    assert palette.color(role.WindowText).name() == t["fg"]
    assert palette.color(role.Base).name() == t["ctl"]
    assert palette.color(role.Link).name() == t["accent"]
    assert palette.color(role.Highlight).name() == t["btn"]
    assert palette.color(role.PlaceholderText).name() == t["fg3"]
    assert palette.color(QPalette.ColorGroup.Disabled, role.Text).name() == t["fg3"]


def test_apply_follows_chosen_appearance(app, appearance):
    assert appearance("dark") is True
    assert app.palette().color(QPalette.ColorRole.Window) == ui_theme.card_color(True)
    assert appearance("light") is False
    assert app.palette().color(QPalette.ColorRole.Link).name() == "#0a64d8"


def test_duo_set_is_complete_and_equal_to_design_files():
    files = sorted(p.stem for p in (DESIGN / "ikony-duo").glob("*.svg"))
    assert sorted(DUO) == files and len(files) == 41
    for name in files:
        source = (DESIGN / "ikony-duo" / f"{name}.svg").read_text("utf-8").strip()
        assert duo_svg(name, "#0a64d8") == source, name


def test_duo_dark_variant_only_changes_color_and_fill_opacity():
    light, dark = duo_svg("hole", "#0a64d8"), duo_svg("hole", "#4a9eff")
    assert 'fill-opacity="0.24"' in light and 'fill-opacity="0.30"' in dark
    assert dark == light.replace("#0a64d8", "#4a9eff").replace('"0.24"', '"0.30"')
    assert duo_svg("ndt", "#0a64d8") == duo_svg("study", "#0a64d8")  # dřívější klíč
    assert duo_svg("document", "#0a64d8") is None  # bez Duo zůstane původní glyf


def _painted(qicon, size=24):
    image = qicon.pixmap(size, size).toImage()
    pixels = [image.pixelColor(x, y) for x in range(image.width())
              for y in range(image.height())]
    return [c for c in pixels if c.alpha() > 200]


@pytest.mark.parametrize("color", ["#0a64d8", "#4a9eff"])
def test_every_duo_icon_renders_in_palette_color(app, color):
    target = QColor(color)
    for name in DUO:
        painted = _painted(icon(name, color))
        assert len(painted) >= 12, name
        # Obrys má barvu odkazu palety (vyhlazené okraje se mohou o kousek lišit).
        assert any(abs(c.red() - target.red()) + abs(c.green() - target.green())
                   + abs(c.blue() - target.blue()) < 30 for c in painted), name


def test_icons_without_duo_still_draw_original_glyph(app):
    assert len(_painted(icon("document", "#0a64d8"))) >= 12
    assert len(_painted(icon("box", "#4a9eff"))) >= 12


def test_flat_3d_background_is_the_middle_of_the_design_gradient():
    """Bez přechodu (GDI Generic, OpenGL 1.1) zůstane pod ním střední barva, ne černá."""
    from skodacad.gui.viewer import BACKGROUNDS, _middle

    assert _middle(*BACKGROUNDS[False]) == "#d5dde8"
    assert _middle(*BACKGROUNDS[True]) == "#292c33"
    assert QColor(_middle(*BACKGROUNDS[False])).lightness() > 110
    assert QColor(_middle(*BACKGROUNDS[True])).lightness() < 110
