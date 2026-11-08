"""UI preferences are recoverable and never modify the CAD recipe."""
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402

from skodacad.gui.ui_colors import contrast, secondary_color, status_color  # noqa: E402
from skodacad.gui.window_state import (  # noqa: E402
    MAX_BYTES,
    clean_state,
    fit_geometry,
    load_state,
    save_state,
)


@pytest.mark.parametrize('raw', [b'', b'{', b'[]', b'null', b'\xff', b' '*(MAX_BYTES+1),
                                b'{"version":3}', b'{"version":true}', b'['*2000])
def test_bad_preferences_fall_back_without_blocking_open(tmp_path, raw):
    path = tmp_path / 'okno.json'
    path.write_bytes(raw)
    assert load_state(path) == {}


def test_preferences_validate_types_and_ignore_unknown_fields(tmp_path):
    state = clean_state({'version': 2, 'left_visible': 'false', 'panel': 'not-a-panel',
                         'activity': [], 'geometry': [0, 0, True, 600],
                         'left_sections': {'info': False, 'unknown': True},
                         'inspector': {'measure.drawing': True, 'ndt.studies': True,
                                       'ndt.beam': 1},
                         'appearance': 'dark', 'document': {'features': []}})
    assert state == {'left_sections': {'info': False}, 'inspector': {'measure.drawing': True},
                     'appearance': 'dark'}
    path = tmp_path / 'okno.json'
    save_state(path, {'panel': None, 'geometry': [-500, 20, 1200, 720], 'appearance': 'system'})
    assert load_state(path) == {'panel': None, 'geometry': [-500, 20, 1200, 720],
                                'appearance': 'system'}
    assert json.loads(path.read_text())['version'] == 2


def test_version_1_is_converted_and_obsolete_values_are_dropped(tmp_path):
    """P7.58: verze 1 se načte pod jmény verze 2; šířky karet a stránka Soubor zmizí."""
    path = tmp_path / 'okno.json'
    path.write_text(json.dumps({
        'version': 1, 'model_visible': False, 'ribbon_collapsed': True, 'maximized': False,
        'model_width': 320, 'editor_width': 360, 'panel': 'measure', 'page': 'ndt',
        'appearance': 'light', 'sidebar_tab': 'part',
        'sections': {'info': True, 'parameters': False, 'properties': True},
        'geometry': [10, 20, 1280, 800], 'activity': 'view'}))
    assert load_state(path) == {
        'left_visible': False, 'palette_collapsed': True, 'maximized': False,
        'panel': 'measure', 'activity': 'ndt', 'appearance': 'light', 'left_tab': 'part',
        'left_sections': {'info': True, 'parameters': False, 'properties': True},
        'geometry': [10, 20, 1280, 800]}
    assert clean_state({'version': 1, 'page': 'file'}) == {}
    save_state(path, load_state(path))
    written = json.loads(path.read_text())
    assert written['version'] == 2 and 'page' not in written and 'model_width' not in written


def test_failed_atomic_write_keeps_last_preferences(tmp_path, monkeypatch):
    import skodacad.gui.window_state as state

    path = tmp_path / 'okno.json'
    save_state(path, {'panel': 'editor'})
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(state.os, 'replace', fail)
    with pytest.raises(OSError):
        save_state(path, {'panel': 'ndt'})
    assert load_state(path) == {'panel': 'editor'}
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('rect,screens,expected', [
    (QRect(-1200, 50, 1000, 700), [QRect(-1440, 0, 1440, 900), QRect(0, 0, 1470, 866)],
     QRect(-1200, 50, 1000, 700)),
    (QRect(5000, 900, 1800, 1000), [QRect(0, 30, 1470, 836)], QRect(0, 30, 1470, 836)),
    (QRect(1400, 20, 1280, 720), [QRect(0, 30, 1470, 836)], QRect(190, 30, 1280, 720)),
])
def test_removed_monitor_and_negative_screen_origins(rect, screens, expected):
    assert fit_geometry(rect, screens) == expected


@pytest.mark.parametrize('background,foreground', [('#ffffff', '#202020'), ('#323232', '#eeeeee')])
def test_secondary_text_and_status_remain_legible(background, foreground):
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(foreground))
    assert contrast(secondary_color(palette), QColor(background)) >= 4.5
    for status in ('ok', 'error', 'pending', 'skipped'):
        assert contrast(status_color(status, palette), QColor(background)) >= 4.5
