from build123d import Box, Cylinder, GeomType

from skodacad.inspection import describe_shape, number


def test_number_format():
    assert number(1234.5) == "1 234.50"
    assert number(9, 0) == "9"
    assert number(-0.001) == "0.00"


def test_describe_faces_edges_vertices():
    box = Box(10, 20, 30)
    top = box.faces().sort_by()[-1]
    assert describe_shape(top.wrapped) == (
        "Plocha – rovinná, obsah 200.00 mm², normála (0.00, 0.00, 1.00)"
    )
    edge = box.edges().filter_by(GeomType.LINE).sort_by(lambda e: e.length)[-1]
    assert describe_shape(edge.wrapped) == "Hrana – úsečka, délka 30.00 mm"
    vertex = box.vertices().sort_by()[-1]
    assert describe_shape(vertex.wrapped).startswith("Bod – X ")


def test_describe_cylinder():
    cyl = Cylinder(9, 20)
    side = next(f for f in cyl.faces() if f.geom_type == GeomType.CYLINDER)
    assert "válcová" in describe_shape(side.wrapped)
    assert "R 9.00 (Ø 18.00)" in describe_shape(side.wrapped)
    circle = cyl.edges().filter_by(GeomType.CIRCLE)[0]
    assert describe_shape(circle.wrapped).startswith("Hrana – kružnice R 9.00 (Ø 18.00) mm")
