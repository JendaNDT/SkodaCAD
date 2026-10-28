"""Hodnoty kót a jejich umístění musí odpovídat modelu, měřítku a pohledu."""
import copy

import pytest
from build123d import GeomType

from skodacad.document import Document, DocumentError
from skodacad.drawing_annotations import annotations
from skodacad.drawing_dimensions import new_cylinder, new_distance, new_overall
from skodacad.drawing_sheet import layout
from skodacad.rebuild import rebuild
from skodacad.session import ModelSession


def model():
    return Document(parameters={"W": 100, "D": 20}, features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": "W", "height": 60}]},
        {"id": "body", "type": "extrude", "sketch": "s", "distance": 10},
        {"id": "hole_s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "circle", "diameter": "D", "center": [15, 5]}]},
        {"id": "hole", "type": "extrude", "sketch": "hole_s", "operation": "cut",
         "through_all": True},
    ])


def annotated(document, result, scale=1):
    sheet = layout(document, result, scale=scale)
    return sheet, annotations(document, result, sheet)


def test_overall_dimension_uses_model_values_and_sheet_scale():
    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x")]}
    sheet, dims = annotated(doc, result, 0.5)
    assert not dims.warnings
    dimension = dims.items[0]
    assert dimension.text == "100" and dimension.view == "front"
    a, b = dimension.lines[-1]
    assert abs(b[0] - a[0]) == pytest.approx(50)
    view = next(v for v in sheet.views if v.name == "front")
    assert (min(a[0], b[0]), max(a[0], b[0])) == pytest.approx(
        (view.bounds[0], view.bounds[2]))


def test_cylinder_uses_correct_center_view_and_updates():
    doc = model()
    result = rebuild(doc)
    face = next(f for f in result.part.faces() if f.geom_type == GeomType.CYLINDER)
    doc.drawing = {"dimensions": [new_cylinder(doc, result, "d1", face, "diameter")]}
    sheet, dims = annotated(doc, result)
    assert not dims.warnings and dims.items[0].text == "Ø20"
    top = next(v for v in sheet.views if v.name == "top")
    contact = dims.items[0].lines[0][0]
    center = (15 + top.offset[0], 5 + top.offset[1])
    radius = ((contact[0] - center[0]) ** 2 + (contact[1] - center[1]) ** 2) ** 0.5
    assert radius == pytest.approx(10)
    doc.parameters["D"] = 24
    assert annotated(doc, rebuild(doc))[1].items[0].text == "Ø24"
    doc.features = doc.features[:2]
    bad = annotated(doc, rebuild(doc))[1]
    assert not bad.items and len(bad.warnings) == 1 and "d1" in bad.warnings[0]


def test_distance_uses_selected_planes_and_bad_view_is_visible():
    doc = model()
    result = rebuild(doc)
    faces = [f for f in result.part.faces() if f.geom_type == GeomType.PLANE
             and abs(f.normal_at().Z) > 0.9]
    distance = new_distance(doc, result, "d1", faces)
    doc.drawing = {"dimensions": [distance]}
    _, dims = annotated(doc, result)
    assert not dims.warnings and dims.items[0].text == "10"
    a, b = dims.items[0].lines[-1]
    assert abs(b[1] - a[1]) == pytest.approx(10)
    distance["placement"] = {"view": "top", "side": "low", "offset": 6}
    bad = annotated(doc, result)[1]
    assert not bad.items and "nepromítá" in bad.warnings[0]


def test_position_is_saved_and_undoable_and_invalid_data_rejected():
    session = ModelSession()
    session.new_document()
    session.replace_document(model().to_dict())
    did = session.add_drawing_dimension("overall", axis="x")
    session.set_drawing_dimension_placement(did, "top", "high", 12)
    saved = Document.from_dict(session.document.to_dict())
    assert saved.drawing["dimensions"][0]["placement"]["offset"] == 12
    assert annotated(saved, session.result)[1].items[0].view == "top"
    session.undo()
    assert "placement" not in session.document.drawing["dimensions"][0]
    broken = copy.deepcopy(saved.to_dict())
    broken["drawing"]["dimensions"][0]["placement"]["offset"] = float("nan")
    with pytest.raises(DocumentError, match="Odstup"):
        Document.from_dict(broken)


def test_unknown_or_off_page_placement_is_a_warning():
    doc = model()
    result = rebuild(doc)
    dimension = new_overall(doc, result, "d1", "x")
    doc.drawing = {"dimensions": [dimension]}
    dimension["placement"] = {"view": "right", "side": "low", "offset": 6}
    assert "nepromítá" in annotated(doc, result)[1].warnings[0]
    dimension["placement"] = {"view": "front", "side": "high", "offset": 60}
    assert "nevejde" in annotated(doc, result)[1].warnings[0]


def test_preview_displays_invalid_dimension_warning():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from skodacad.gui.drawing_preview import DrawingPreviewDialog

    app = widgets.QApplication.instance() or widgets.QApplication([])
    doc = model()
    result = rebuild(doc)
    record = new_overall(doc, result, "d1", "x")
    record["placement"] = {"view": "right", "side": "low", "offset": 6}
    doc.drawing = {"dimensions": [record]}
    sheet, dims = annotated(doc, result)
    dialog = DrawingPreviewDialog(sheet, dims)
    labels = [label.text() for label in dialog.findChildren(widgets.QLabel)]
    assert any("d1" in label and "nepromítá" in label for label in labels)
    dialog.close()
    assert app is not None


def test_changed_model_never_places_new_values_on_old_geometry():
    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x")]}
    stale_sheet = layout(doc, result)
    doc.parameters["W"] = 120
    updated = rebuild(doc)
    shown = annotations(doc, updated, stale_sheet)
    assert not shown.items and "staršímu" in shown.warnings[0]
    current = annotations(doc, updated, layout(doc, updated))
    assert current.items[0].text == "120"


def test_overall_circle_extension_lines_start_on_real_circle():
    doc = Document(features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "circle", "diameter": 40}]},
        {"id": "disc", "type": "extrude", "sketch": "s", "distance": 10},
    ])
    result = rebuild(doc)
    dimension = new_overall(doc, result, "d1", "x")
    dimension["placement"] = {"view": "top", "side": "high", "offset": 6}
    doc.drawing = {"dimensions": [dimension]}
    sheet, dims = annotated(doc, result)
    assert not dims.warnings
    top = next(v for v in sheet.views if v.name == "top")
    for source, _ in dims.items[0].lines[:2]:
        x, y = source[0] - top.offset[0], source[1] - top.offset[1]
        assert (x * x + y * y) ** 0.5 == pytest.approx(20, abs=1e-5)


@pytest.mark.parametrize(("plane", "view"), [("XY", "top"), ("XZ", "front"), ("YZ", "right")])
def test_hole_dimension_uses_view_along_its_axis(plane, view):
    doc = Document(features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 40, "height": 30}]},
        {"id": "body", "type": "extrude", "sketch": "s", "distance": 20},
        {"id": "hs", "type": "sketch", "plane": plane, "elements": [
            {"shape": "circle", "diameter": 8,
             "center": [0, 0] if plane == "XY" else [0, 10]}]},
        {"id": "hole", "type": "extrude", "sketch": "hs", "operation": "cut",
         "through_all": True},
    ])
    result = rebuild(doc)
    face = next(f for f in result.part.faces() if f.geom_type == GeomType.CYLINDER)
    doc.drawing = {"dimensions": [new_cylinder(doc, result, "d1", face, "diameter")]}
    _, dims = annotated(doc, result)
    assert not dims.warnings
    assert dims.items[0].view == view and dims.items[0].text == "Ø8"


def test_preview_draws_a_visible_dimension():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtGui import QImage

    from skodacad.gui.drawing_preview import SheetPreview

    app = widgets.QApplication.instance() or widgets.QApplication([])
    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x")]}
    sheet, dims = annotated(doc, result)
    widget = SheetPreview(sheet, dims)
    widget.resize(600, 450)
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    colored = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.blue() > color.red() + 25 and color.blue() > color.green() + 10:
                colored += 1
    assert colored > 10
    widget.close()
    assert app is not None
