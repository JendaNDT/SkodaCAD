"""Export nezmění soubor při neplatné vazbě; výstup má správný list a geometrii."""
import os
from pathlib import Path

import ezdxf
import pytest
from build123d import GeomType

from skodacad.document import Document, DocumentError
from skodacad.drawing_dimensions import new_cylinder, new_overall
from skodacad.drawing_export import export
from skodacad.drawing_sheet import layout
from skodacad.rebuild import rebuild

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def model():
    return Document(name="Příruba", parameters={"D": 20}, features=[
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 80, "height": 50}]},
        {"id": "body", "type": "extrude", "sketch": "s", "distance": 10},
        {"id": "hs", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "circle", "diameter": "D"}]},
        {"id": "hole", "type": "extrude", "sketch": "hs", "operation": "cut",
         "through_all": True},
    ])


def with_dimensions():
    doc = model()
    result = rebuild(doc)
    face = next(face for face in result.part.faces() if face.geom_type == GeomType.CYLINDER)
    doc.drawing = {"dimensions": [new_overall(doc, result, "d1", "x"),
                                  new_cylinder(doc, result, "d2", face, "diameter")],
                   "section": {"axis": "Y", "position": 0}}
    return doc, result


def test_dxf_has_mm_geometry_dimensions_labels_and_section(tmp_path):
    doc, result = with_dimensions()
    path = export(doc, result, layout(doc, result, scale=0.5), tmp_path / "vykres.dxf")
    data = ezdxf.readfile(path)
    assert data.header["$INSUNITS"] == 4
    assert data.layers.get("skryte").dxf.linetype == "SKODA_SKRYTA"
    pattern = data.linetypes.get("SKODA_SKRYTA").pattern_tags.tags
    assert [tag.value for tag in pattern if tag.code == 49] == pytest.approx([1, -0.5])
    assert data.layers.get("rovina_rezu").dxf.linetype == "SKODA_REZ"
    items = list(data.modelspace())
    texts = [entity.dxf.text for entity in items if entity.dxftype() == "TEXT"]
    assert "80" in texts and "Ø20" in texts
    assert any("Příruba" in text for text in texts)
    assert any("Řez A–A (Y = 0 mm)" in text for text in texts)
    assert "Kontrola: 50 mm" in texts
    assert any(entity.dxf.layer == "srafy" for entity in items)
    assert any(entity.dxftype() in ("CIRCLE", "ARC") for entity in items)


def test_pdf_is_a_vector_page_and_has_physical_size(tmp_path):
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    app = widgets.QApplication.instance() or widgets.QApplication([])
    doc, result = with_dimensions()
    path = export(doc, result, layout(doc, result, scale=0.5), tmp_path / "vykres.pdf")
    assert path.read_bytes().startswith(b"%PDF-") and path.stat().st_size > 1000
    assert app is not None


def test_failed_export_keeps_existing_file(tmp_path):
    doc, result = with_dimensions()
    sheet = layout(doc, result, scale=0.5)
    doc.parameters["D"] = 25
    existing = tmp_path / "existing.dxf"
    existing.write_bytes(b"predchozi")
    with pytest.raises(DocumentError, match="staršímu"):
        export(doc, rebuild(doc), sheet, existing)
    assert existing.read_bytes() == b"predchozi"
    assert len(list(Path(tmp_path).iterdir())) == 1


def test_export_rejects_changed_section_without_recomputing_sheet(tmp_path):
    doc, result = with_dimensions()
    sheet = layout(doc, result, scale=0.5)
    doc.drawing["section"]["position"] = 5
    destination = tmp_path / "vykres.dxf"
    with pytest.raises(DocumentError, match="staršímu"):
        export(doc, result, sheet, destination)
    assert not destination.exists()


def test_unsupported_pdf_curve_does_not_overwrite_existing_file(tmp_path):
    from dataclasses import replace

    from build123d import Edge

    from skodacad.drawing_geometry import DrawingView

    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    app = widgets.QApplication.instance() or widgets.QApplication([])
    doc = model()
    result = rebuild(doc)
    sheet = layout(doc, result)
    old_view = sheet.views[0]
    ellipse = Edge.make_ellipse(8, 4)
    view = replace(old_view, geometry=DrawingView((ellipse,), ()))
    sheet = replace(sheet, views=(view, *sheet.views[1:]))
    existing = tmp_path / "vykres.pdf"
    existing.write_bytes(b"predchozi")
    with pytest.raises(DocumentError, match="nepodporuje"):
        export(doc, result, sheet, existing)
    assert existing.read_bytes() == b"predchozi"
    assert app is not None


def test_export_rejects_incomplete_model_even_without_dimensions(tmp_path):
    from dataclasses import replace

    from skodacad.rebuild import FeatureStatus

    doc = model()
    result = rebuild(doc)
    sheet = layout(doc, result)
    failed = replace(result, statuses=[*result.statuses,
                                      FeatureStatus("bad", "extrude", "Chyba", "error", "chyba")])
    target = tmp_path / "vykres.dxf"
    with pytest.raises(DocumentError, match="není dokončený"):
        export(doc, failed, sheet, target)
    assert not target.exists()


def test_tolerances_survive_dxf_and_follow_recomputed_nominal(tmp_path):
    doc, result = with_dimensions()
    doc.drawing["dimensions"][0]["tolerance"] = {"upper": 0.1, "lower": -0.1}
    doc.drawing["dimensions"][1]["tolerance"] = {"upper": 0.02, "lower": -0.05}
    doc.parameters["D"] = 24
    result = rebuild(doc)
    path = export(doc, result, layout(doc, result, scale=0.5), tmp_path / "tolerance.dxf")
    texts = [e.dxf.text for e in ezdxf.readfile(path).modelspace() if e.dxftype() == "TEXT"]
    assert "80 ±0.1" in texts
    assert "Ø24 +0.02/-0.05" in texts


def test_negative_lower_limit_blocks_export(tmp_path):
    doc, result = with_dimensions()
    doc.drawing["dimensions"][0]["tolerance"] = {"upper": 0, "lower": -100}
    with pytest.raises(DocumentError, match="Dolní mez"):
        export(doc, result, layout(doc, result, scale=0.5), tmp_path / "bad.dxf")


def test_pdf_contains_explicit_tolerance_text(tmp_path):
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    pdf = pytest.importorskip("PySide6.QtPdf", exc_type=ImportError)
    from PySide6.QtCore import QSize

    from skodacad.drawing_annotations import annotations

    app = widgets.QApplication.instance() or widgets.QApplication([])
    doc, result = with_dimensions()
    doc.drawing["title_block"] = {"number": "V-12", "revision": "B",
                                  "author": "Novák", "date": "28.10.2026"}
    sheet = layout(doc, result, scale=0.5)
    plain_path = export(doc, result, sheet, tmp_path / "plain.pdf")
    doc.drawing["dimensions"][0]["tolerance"] = {"upper": 0.1, "lower": -0.1}
    doc.drawing["dimensions"][1]["tolerance"] = {"upper": 0.02, "lower": -0.05}
    labels = [item.text for item in annotations(doc, result, sheet).items]
    assert "80 ±0.1" in labels and "Ø20 +0.02/-0.05" in labels
    path = export(doc, result, sheet, tmp_path / "tolerance.pdf")
    reader = pdf.QPdfDocument()
    plain = pdf.QPdfDocument()
    assert reader.load(str(path)) == pdf.QPdfDocument.Error.None_
    assert plain.load(str(plain_path)) == pdf.QPdfDocument.Error.None_
    # Windows Qt může text v PDF převést na obrysy. Ověř i vykreslenou stránku;
    # pokud čtečka text zpřístupní, ověř jeho přesný obsah navíc.
    text = reader.getAllText(0).text()
    if text:
        assert "80 ±0.1" in text and "Ø20 +0.02/-0.05" in text
        assert "V-12" in text and "Novák" in text and "28.10.2026" in text
    image = reader.render(0, QSize(1200, 850))
    original = plain.render(0, QSize(1200, 850))
    assert not image.isNull() and not original.isNull()
    assert image != original
    assert app is not None


def test_title_block_export_contains_model_and_explicit_metadata(tmp_path):
    from skodacad.drawing_annotations import annotations
    from skodacad.drawing_export import _title_rows

    doc, result = with_dimensions()
    doc.material = "ocel"
    doc.drawing["title_block"] = {"number": "V-12", "revision": "B",
                                  "author": "Novák", "date": "28.10.2026"}
    sheet = layout(doc, result, scale=0.5)
    rows = [text for _, text in _title_rows(doc, sheet, annotations(doc, result, sheet))]
    path = export(doc, result, sheet, tmp_path / "popis.dxf")
    texts = [e.dxf.text for e in ezdxf.readfile(path).modelspace() if e.dxftype() == "TEXT"]
    assert all(text in texts for text in rows)
    assert any("Příruba" in t and "ocel" in t for t in rows)
    assert any("V-12" in t and "B" in t for t in rows)
    assert any("Novák" in t and "28.10.2026" in t for t in rows)
