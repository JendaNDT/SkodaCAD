"""Analytické případy pozdní chyby pole a zrcadlení P1.2B."""

from conftest import box_features, make_doc


def late_failure_document(kind, repaired=False):
    features = box_features(100, 80, 10)
    order = [-20, 45] if kind == "pattern" else [45, -20]
    for index, x in enumerate(order):
        features.extend([
            {"id": f"s{index}", "type": "sketch", "plane": "top", "elements": [
                {"shape": "circle", "diameter": 4, "center": [x, 0]}]},
            {"id": f"h{index}", "type": "extrude", "sketch": f"s{index}",
             "operation": "cut", "distance": 5},
        ])
    feature = {"id": "bad", "type": kind, "features": ["h0", "h1"]}
    if kind == "pattern":
        feature.update(name="Pole dvou otvorů", kind="linear", direction="X", count=2,
                       spacing=-20 if repaired else 20)
    elif kind == "mirror":
        feature.update(name="Zrcadlení dvou otvorů", plane="YZ", offset=0 if repaired else 20)
    else:
        raise ValueError(kind)
    features.extend([feature, {"id": "tail", "name": "Kontrola po chybě", "type": "sketch",
                              "plane": "XY", "elements": [
                                  {"shape": "rectangle", "width": 1, "height": 1}]}])
    return make_doc(features)
