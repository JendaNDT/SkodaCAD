"""Odolnost proti „topological naming problem“.

Po změně parametrů jádro přečísluje plochy a hrany. Prvky se ale odkazují
významem („horní plocha“, „kružnice o poloměru D/2“), takže musí dál zasahovat
správnou geometrii. Ověřujeme to přesným porovnáním objemu se vzorcem.
"""

import math

import pytest

from skodacad import Document, rebuild


def flange_volume_without_chamfers(p):
    return math.pi / 4 * (p["D"] ** 2 - p["d"] ** 2 - p["n"] * p["dh"] ** 2) * p["t"]


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"n": 8},
        {"D": 220, "k": 180, "t": 30},
        {"n": 6, "dh": 14, "d": 40},
    ],
)
def test_flange_follows_parameter_changes(examples_dir, overrides):
    document = Document.load(examples_dir / "priruba.json")
    without_chamfers = Document.from_dict({
        **document.to_dict(),
        "features": [f for f in document.features if f["type"] != "chamfer"],
    })

    plain = rebuild(without_chamfers, overrides)
    full = rebuild(document, overrides)
    assert plain.ok and full.ok

    params = plain.parameters
    assert plain.part.volume == pytest.approx(flange_volume_without_chamfers(params))
    # Sražení obvodu i otvoru se po změně parametrů stále najde (jinak by rebuild selhal)
    # a odebere jen malé množství materiálu, ne celé plochy.
    removed = plain.part.volume - full.part.volume
    assert 0 < removed < 0.02 * plain.part.volume
    # Díry jsou pořád skrz celou tloušťku – horní plocha se po změně t posunula s dílem.
    assert full.part.bounding_box().size.Z == pytest.approx(params["t"])


def test_box_cable_hole_stays_in_front_wall(examples_dir):
    document = Document.load(examples_dir / "krabicka.json")
    for overrides in ({}, {"L": 120, "W": 70, "H": 45}):
        result = rebuild(document, overrides)
        assert result.ok
        p = result.parameters
        # Válcová plocha otvoru je krátká ve směru Y (tloušťka stěny); vnitřní rohy krabičky
        # mají shodou okolností stejný poloměr, ale jsou vysoké ve směru Z.
        hole = [f for f in result.part.faces()
                if f.geom_type.name == "CYLINDER" and f.radius == pytest.approx(p["dira"] / 2)
                and f.bounding_box().size.Y <= p["stena"] + 1e-6]
        assert hole, "otvor na kabel chybí"
        for face in hole:
            assert face.center().Y == pytest.approx(-p["W"] / 2 + p["stena"] / 2, abs=1e-3)
            assert face.center().Z == pytest.approx(p["H"] / 2, abs=1e-3)
