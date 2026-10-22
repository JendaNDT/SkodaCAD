"""Fixed P1.3 recipes shared by interface tests and the manual handoff."""

import datetime

from skodacad import Document
from skodacad.ndt.study import new_study, part_fingerprint
from skodacad.profile_edit import add_circle, add_point, add_reference, empty_profile


def document(name, features, parameters=None):
    return Document.from_dict({"format": "skodacad", "version": 22, "units": "mm",
                               "name": name, "material": "ocel", "parameters": parameters or {},
                               "features": features})


def box_features(width=20, depth=30, height=40):
    return [
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "rectangle", "width": width, "height": depth}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": height},
    ]


def edge_document(repaired=False):
    edges = {"between": ["front", "right"]} if repaired else {
        "parallel": "Z", "near": [0, -15, 20]}
    return document("P1.3 – nejednoznačné hrany", box_features() + [
        {"id": "bad", "type": "fillet", "radius": 3, "edges": edges},
        {"id": "tail", "type": "sketch", "elements": [{"shape": "circle", "diameter": 2}]},
    ])


def add_metadata(doc, spec, kind):
    doc.measurements = [{"id": "m1", "name": "Kontrolní měření", "kind": kind,
                         "a": {"face": spec}}]
    doc.ndt = {"studies": [new_study(
        "PT", [], part_fingerprint(doc), {"kind": "faces", "faces": [{"face": spec}]},
        name="Kontrolní oblast PT", today=datetime.date(2026, 10, 22))]}


def face_document(repaired=False):
    features = []
    for n in (1, 2):
        features.extend([
            {"id": f"s{n}", "type": "sketch", "elements": [
                {"shape": "rectangle", "width": 20, "height": 20, "center": [f"x{n}", 0]}]},
            {"id": f"e{n}", "type": "extrude", "sketch": f"s{n}", "distance": 10},
        ])
    doc = document("P1.3 – nejednoznačné plochy", features, {"x1": -20, "x2": 20})
    spec = {"at": [-20, 0, 10], "normal": [0, 0, 1], "type": "plane"}
    add_metadata(doc, spec, "area")
    doc.parameters["x1"] = -60  # původní odkaz je teď stejně daleko od obou horních ploch
    if repaired:
        doc.measurements[0]["a"]["face"]["at"] = [-60, 0, 10]
        doc.ndt["studies"][0]["target"]["faces"][0]["face"]["at"] = [-60, 0, 10]
        doc.ndt["studies"][0]["part"] = part_fingerprint(doc)
    return doc


def radius_document(repaired=False):
    doc = document("P1.3 – pevný poloměr", [
        {"id": "s", "type": "sketch", "elements": [{"shape": "circle", "diameter": "D"}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10},
    ], {"D": 10})
    spec = {"at": [5, 0, 5], "normal": [1, 0, 0], "type": "cylinder", "radius": 5}
    add_metadata(doc, spec, "diameter")
    doc.parameters["D"] = 12
    if repaired:
        fresh = {"at": [6, 0, 5], "normal": [1, 0, 0], "type": "cylinder", "radius": 6}
        doc.measurements[0]["a"]["face"] = fresh
        doc.ndt["studies"][0]["target"]["faces"][0]["face"] = fresh.copy()
        doc.ndt["studies"][0]["part"] = part_fingerprint(doc)
    return doc


def projection_document(repaired=False):
    profile = empty_profile()
    edge = {"between": ["top", "front"]} if repaired else {
        "parallel": "Z", "near": [0, -15, 20]}
    add_reference(profile, {"edge": edge, "kind": "line", "points": [[-10, -15], [10, -15]]})
    add_circle(profile, add_point(profile, 0, 0), 1)
    return document("P1.3 – promítnutá hrana", box_features() + [
        {"id": "bad", "type": "sketch", "plane": "top", "elements": [profile]},
        {"id": "tail", "type": "extrude", "sketch": "bad", "distance": 2},
    ])


def section_document():
    return document("P1.3 – výběr v řezu", box_features(40, 30, 10) + [
        {"id": "hole_s", "type": "sketch", "plane": "top", "elements": [
            {"shape": "circle", "diameter": 8}]},
        {"id": "hole", "type": "extrude", "sketch": "hole_s", "operation": "cut",
         "through_all": True},
    ])
