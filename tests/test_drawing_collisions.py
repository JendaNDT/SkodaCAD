"""Upozornění na možná překrytí a jejich předání do náhledu i exportu."""
import os
from dataclasses import replace

import ezdxf
import pytest
from build123d import Edge

from skodacad.document import Document
from skodacad.drawing_annotations import Annotation, annotations
from skodacad.drawing_collisions import check
from skodacad.drawing_dimensions import new_overall
from skodacad.drawing_export import export
from skodacad.drawing_geometry import DrawingView
from skodacad.drawing_sheet import layout
from skodacad.rebuild import rebuild

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def model():
    return Document(features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 60, "height": 40}]},
        {"id": "body", "type": "extrude", "sketch": "s", "distance": 10},
    ])


def overlapping():
    doc = model()
    result = rebuild(doc)
    first = new_overall(doc, result, "d1", "x")
    second = new_overall(doc, result, "d2", "x")
    first["placement"] = second["placement"] = {"view": "front", "side": "low", "offset": 6}
    doc.drawing = {"dimensions": [first, second]}
    sheet = layout(doc, result)
    return doc, result, sheet, annotations(doc, result, sheet)


def test_same_placement_warns_without_discarding_dimensions():
    _, _, _, result = overlapping()
    assert len(result.items) == 2 and not result.warnings
    assert any("d1" in line and "d2" in line for line in result.collisions)
    assert result.collision_check_complete


def test_separate_dimension_lines_do_not_trigger_overlap():
    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x")]}
    sheet = layout(doc, result)
    values = annotations(doc, result, sheet)
    assert not values.warnings and not values.collisions


def test_label_over_model_geometry_is_reported():
    doc = model()
    result = rebuild(doc)
    sheet = layout(doc, result)
    view = sheet.views[0]
    dx, dy = view.offset
    edge = Edge.make_line((100 - dx, 80 - dy, 0), (120 - dx, 80 - dy, 0))
    view = replace(view, geometry=DrawingView((edge,), ()))
    sheet = replace(sheet, views=(view,))
    item = Annotation("d1", "front", "25", (((130, 100), (150, 100)),), (105, 79))
    report = check(sheet, (item,))
    assert any("d1" in line and "geometrií" in line for line in report.messages)


def test_crossing_dimension_lines_are_reported():
    doc = model()
    sheet = layout(doc, rebuild(doc))
    a = Annotation("a", "front", "10", (((80, 90), (100, 90)),), (75, 100))
    b = Annotation("b", "front", "20", (((90, 80), (90, 100)),), (105, 80))
    report = check(sheet, (a, b))
    assert any("a" in line and "b" in line for line in report.messages)


def test_warning_is_written_to_dxf_without_blocking_export(tmp_path):
    doc, result, sheet, dims = overlapping()
    assert dims.collisions
    path = export(doc, result, sheet, tmp_path / "vykres.dxf")
    text = [entity.dxf.text for entity in ezdxf.readfile(path).modelspace()
            if entity.dxftype() == "TEXT"]
    assert any("Možné překrytí kót" in item for item in text)
    assert "60" in text


def test_preview_shows_collision_details():
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from skodacad.gui.drawing_preview import DrawingPreviewDialog

    app = widgets.QApplication.instance() or widgets.QApplication([])
    _, _, sheet, dims = overlapping()
    dialog = DrawingPreviewDialog(sheet, dims)
    labels = [label.text() for label in dialog.findChildren(widgets.QLabel)]
    assert any("d1" in label and "d2" in label and "překrytí" in label for label in labels)
    dialog.close()
    assert app is not None


def test_many_dimensions_do_not_silently_skip_collision_check():
    doc = model()
    sheet = layout(doc, rebuild(doc))
    item = Annotation("d", "front", "1", (((80, 90), (100, 90)),), (75, 100))
    report = check(sheet, (item,) * 201)
    assert not report.complete
    assert any("Příliš mnoho kót" in message for message in report.messages)


def test_incomplete_check_is_reported_in_export():
    from skodacad.drawing_annotations import AnnotationSet
    from skodacad.drawing_export import collision_notice

    dims = AnnotationSet((), (), ("Kontrolu se nepodařilo dokončit.",), False)
    assert "není úplná" in collision_notice(dims)


def test_failed_collision_check_is_not_silently_treated_as_success(monkeypatch, tmp_path):
    import skodacad.drawing_collisions as collisions

    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x")]}
    sheet = layout(doc, result)

    def failed(*_args):
        raise RuntimeError("chyba geometrického jádra")

    monkeypatch.setattr(collisions, "check", failed)
    dimensions = annotations(doc, result, sheet)
    assert not dimensions.collision_check_complete
    assert any("nepodařilo dokončit" in item for item in dimensions.collisions)
    path = export(doc, result, sheet, tmp_path / "vykres.dxf")
    text = [entity.dxf.text for entity in ezdxf.readfile(path).modelspace()
            if entity.dxftype() == "TEXT"]
    assert any("Kontrola překrytí není úplná" in item for item in text)


def test_dimension_text_crossing_section_marker_warns():
    from skodacad.drawing_section_mark import section_mark

    doc = model()
    result = rebuild(doc)
    doc.drawing = {"dimensions": [], "section": {"axis": "Y", "position": 0}}
    sheet = layout(doc, result)
    mark = section_mark(sheet)
    x = (mark.line[0][0] + mark.line[1][0]) / 2
    y = mark.line[0][1]
    item = Annotation("d1", "top", "25", (((x + 20, y + 20), (x + 25, y + 20)),),
                      (x, y))
    report = check(sheet, (item,))
    assert any("označením řezu" in line for line in report.messages)
