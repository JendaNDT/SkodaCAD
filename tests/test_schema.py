"""Schéma prvků musí odpovídat tomu, co jádro opravdu umí postavit."""

import math
import re

import pytest

from conftest import make_doc
from skodacad import rebuild
from skodacad.features import FEATURE_TYPES
from skodacad.schema import FEATURE_SCHEMAS, SHAPE_DEFAULTS, SHAPE_SCHEMAS, new_feature


def test_every_feature_type_has_schema():
    assert set(FEATURE_SCHEMAS) == set(FEATURE_TYPES)
    for key, schema in FEATURE_SCHEMAS.items():
        assert schema.label == FEATURE_TYPES[key].label_cz


def test_shape_schemas_match_core_shapes():
    result = rebuild(make_doc([{"id": "s", "type": "sketch", "elements": [{"shape": "x"}]}]))
    listed = re.search(r"povolené: (.*)\.", result.first_error.message).group(1)
    assert set(listed.split(", ")) == set(SHAPE_SCHEMAS) == set(SHAPE_DEFAULTS)


@pytest.mark.parametrize("shape", sorted(SHAPE_DEFAULTS))
def test_default_shapes_build(shape):
    result = rebuild(make_doc([
        {"id": "s", "type": "sketch", "elements": [SHAPE_DEFAULTS[shape]]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 5},
    ]))
    assert result.ok, result.first_error
    assert result.part.volume > 0


def test_choices_are_accepted_by_core():
    """Každá nabízená volba ve formuláři musí jádro znát (žádná neznámá hodnota)."""
    base = [{"id": "s", "type": "sketch", "elements": [{"shape": "rectangle", "width": 40,
                                                        "height": 30}]}]
    for key, label in FEATURE_SCHEMAS["sketch"].fields[1].choices:
        features = base + [{"id": "e", "type": "extrude", "sketch": "s", "distance": 10},
                           {"id": "s2", "type": "sketch", "plane": key,
                            "elements": [{"shape": "circle", "diameter": 4}]}]
        result = rebuild(make_doc(features))
        assert result.ok, (key, label, result.first_error)


def build(features):
    result = rebuild(make_doc(features))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    return result


def add(features, feature_type, **changes):
    feature = new_feature(feature_type, features)
    feature.update(changes)
    features.append(feature)
    return feature


def test_new_features_build_a_part_step_by_step():
    features = []
    sketch = add(features, "sketch")
    assert sketch["plane"] == "XY" and sketch["id"] == "sketch1"
    extrude = add(features, "extrude")
    assert extrude["sketch"] == "sketch1"
    assert build(features).part.volume == pytest.approx(40 * 30 * 10)

    hole = add(features, "sketch", elements=[{"shape": "circle", "diameter": 10}])
    assert hole["plane"] == "top" and hole["id"] == "sketch2"  # po tělese kreslí nahoru
    cut = add(features, "extrude", operation="cut", through_all=True)
    assert cut["sketch"] == "sketch2" and cut["id"] == "extrude2"
    assert build(features).part.volume == pytest.approx(40 * 30 * 10 - math.pi * 25 * 10)

    add(features, "fillet", edges={"parallel": "Z", "type": "line"})
    assert build(features).part.is_valid


@pytest.mark.parametrize("feature_type", ["fillet", "chamfer", "shell"])
def test_default_finishing_features_build(feature_type):
    features = []
    add(features, "sketch")
    add(features, "extrude")
    add(features, feature_type)
    result = build(features)
    assert result.part.volume < 40 * 30 * 10


def test_revolve_default_axis():
    features = []
    add(features, "sketch", plane="XZ",
        elements=[{"shape": "rectangle", "width": 10, "height": 20, "center": [15, 10]}])
    add(features, "revolve")
    assert build(features).part.volume == pytest.approx(math.pi * (20**2 - 10**2) * 20)


def test_new_feature_ids_are_unique_and_index_aware():
    features = [{"id": "sketch1", "type": "sketch"}, {"id": "sketch2", "type": "sketch"},
                {"id": "extrude1", "type": "extrude"}]
    assert new_feature("sketch", features)["id"] == "sketch3"
    inserted = new_feature("extrude", features, index=1)  # vložení hned za první skicu
    assert inserted["sketch"] == "sketch1"
    assert inserted["id"] == "extrude2"
