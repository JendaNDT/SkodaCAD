"""Rozmístění pohledů dodržuje osy, měřítko a dostupné místo na listu."""
import copy

import pytest

from skodacad.document import Document, DocumentError
from skodacad.drawing_sheet import GAP, PAPER, layout
from skodacad.rebuild import rebuild


def box(width=100, height=60, depth=10):
    return Document(parameters={"W": width}, features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": "W", "height": height, "center": [20, 10]}]},
        {"id": "body", "type": "extrude", "sketch": "s", "distance": depth},
    ])


def test_views_are_aligned_in_european_layout_without_changing_scale():
    document = box()
    sheet = layout(document, rebuild(document))
    front, top, right = (next(view for view in sheet.views if view.name == name)
                         for name in ("front", "top", "right"))
    assert (sheet.width, sheet.height) == PAPER["A4"]
    assert front.bounds[0] == pytest.approx(top.bounds[0])
    assert front.bounds[1] == pytest.approx(right.bounds[1])
    assert front.bounds[0] - right.bounds[2] == pytest.approx(GAP)
    assert front.bounds[1] - top.bounds[3] == pytest.approx(GAP)
    assert front.bounds[2] - front.bounds[0] == pytest.approx(100)
    assert top.bounds[3] - top.bounds[1] == pytest.approx(60)


def test_oversized_views_are_rejected_instead_of_auto_scaled():
    document = box(width=300)
    result = rebuild(document)
    with pytest.raises(DocumentError, match="nevejdou"):
        layout(document, result)
    sheet = layout(document, result, scale=0.5)
    front = next(view for view in sheet.views if view.name == "front")
    assert front.bounds[2] - front.bounds[0] == pytest.approx(150)


def test_hidden_views_and_stale_model():
    document = box()
    result = rebuild(document)
    for views in [("front",), ("top",), ("right",), ("top", "right")]:
        assert tuple(v.name for v in layout(document, result, views=views).views) == views
    changed = copy.deepcopy(document)
    changed.parameters["W"] = 120
    with pytest.raises(DocumentError, match="neodpovídá"):
        layout(changed, result)
    with pytest.raises(DocumentError, match="opakování"):
        layout(document, result, views=("front", "front"))


def test_preview_renders_the_sheet_without_exporting():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtGui import QImage

    from skodacad.gui.drawing_preview import SheetPreview

    app = widgets.QApplication.instance() or widgets.QApplication([])
    document = box()
    widget = SheetPreview(layout(document, rebuild(document)))
    widget.resize(600, 450)
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    assert not image.isNull()
    assert image.pixelColor(300, 225).alpha() == 255
    widget.close()
    assert app is not None


def test_section_is_placed_and_hatched_and_cannot_be_silently_dropped():
    document = box(width=40, height=30, depth=20)
    result = rebuild(document)
    document.drawing = {"dimensions": [], "section": {"axis": "Y", "position": 10}}
    sheet = layout(document, result)
    section = next(view for view in sheet.views if view.name == "section")
    assert section.geometry.visible and section.geometry.hatching
    assert section.bounds[0] > next(v for v in sheet.views if v.name == "front").bounds[2]
    document.drawing["section"]["position"] = 1000
    with pytest.raises(ValueError, match="Rovina řezu"):
        layout(document, result)


def test_section_settings_survive_save_and_undo():
    from skodacad.session import ModelSession

    session = ModelSession()
    session.new_document()
    session.replace_document(box().to_dict())
    session.set_drawing_section("X", 20, True)
    saved = Document.from_dict(session.document.to_dict())
    assert saved.drawing["section"] == {"axis": "X", "position": 20, "flipped": True}
    session.undo()
    assert session.document.drawing is None


@pytest.mark.parametrize(("axis", "position", "component", "expected"), [
    ("X", 20, 0, -1), ("Y", 10, 1, 1), ("Z", 10, 1, -1),
])
@pytest.mark.parametrize("flipped", [False, True])
def test_section_arrows_point_toward_retained_material(axis, position, component, expected,
                                                       flipped):
    from skodacad.drawing_section_mark import section_mark

    document = box(width=40, height=30, depth=20)
    result = rebuild(document)
    document.drawing = {"dimensions": [], "section": {"axis": axis, "position": position,
                                                       "flipped": flipped}}
    mark = section_mark(layout(document, result))
    start, end = mark.arrows[0]
    delta = end[component] - start[component]
    assert delta == pytest.approx(4 * expected * (-1 if flipped else 1))
