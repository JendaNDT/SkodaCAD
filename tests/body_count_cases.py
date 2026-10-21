"""Analytická zadání pro stejné počty těles napříč rozhraními (bez Qt a AI sítě)."""

import math

from conftest import box_features, make_doc

COUNT_CASE_NAMES = ("single", "two_regions", "changes", "three_pipes")


def body_count_case(name):
    if name == "single":
        return make_doc(box_features()), 24000, 1, {"e": (0, 1)}
    if name == "two_regions":
        return make_doc([
            {"id": "s", "type": "sketch", "elements": [
                {"shape": "circle", "diameter": 10, "center": [-15, 0]},
                {"shape": "circle", "diameter": 10, "center": [15, 0]},
            ]},
            {"id": "e", "type": "extrude", "sketch": "s", "distance": 10, "operation": "new"},
        ]), 500 * math.pi, 2, {"e": (0, 2)}
    if name == "changes":
        return make_doc(box_features() + [
            {"id": "ss", "type": "sketch", "elements": [
                {"shape": "rectangle", "width": 5, "height": 5, "center": [100, 0]},
            ]},
            {"id": "add", "type": "extrude", "sketch": "ss", "distance": 10, "operation": "add"},
            {"id": "remove", "type": "extrude", "sketch": "ss", "distance": 10,
             "operation": "cut", "direction": "normal"},
            {"id": "edit", "type": "chamfer", "edges": {"parallel": "Z"}, "distance": 2},
        ]), 23680, 1, {"e": (0, 1), "add": (1, 2), "remove": (2, 1), "edit": (1, 1)}
    if name == "three_pipes":
        length = 2 * (100 - 40) + math.pi / 2 * 40
        volume = 3 * math.pi * (15**2 - 13**2) * length
        return make_doc([
            {"id": "pipe", "type": "sweep", "path": [[0, 0, 0], [0, 0, 100], [100, 0, 100]],
             "bend_radius": 40, "profile": "circle", "diameter": 30, "wall": 2},
            {"id": "pattern", "type": "pattern", "features": ["pipe"], "kind": "linear",
             "direction": "Y", "count": 3, "spacing": 50},
        ]), volume, 3, {"pipe": (0, 1), "pattern": (1, 3)}
    raise AssertionError(name)
