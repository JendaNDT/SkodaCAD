"""Hodnotová kontrola sdílených nativních vstupů při skutečném přepočtu."""

import pytest


def shape_metrics(shape):
    box = shape.bounding_box(optimal=False)
    return (shape.volume, shape.area, *box.min, *box.max,
            *shape.location.position, *shape.location.orientation)


def check_accepted_inputs(run_feature, ctx, feature):
    shapes = [ctx.part]
    planes = []
    for plane, sketch in ctx.sketches.values():
        planes.append(plane)
        shapes.append(sketch)
    for operations in ctx.operations.values():
        shapes.extend(tool for tool, _mode in operations)
    if ctx.recording:
        shapes.extend(tool for tool, _mode in ctx.recording)
    unique = {id(shape): shape for shape in shapes if shape is not None}
    before = [(shape, shape_metrics(shape)) for shape in unique.values()]
    plane_before = [(plane, (*plane.origin, *plane.x_dir, *plane.z_dir)) for plane in planes]
    message = run_feature(ctx, feature)
    for shape, metrics in before:
        assert shape.is_valid, (feature["id"], "změna platnosti původního tvaru")
        assert shape_metrics(shape) == pytest.approx(metrics, abs=1e-6, rel=1e-10), feature["id"]
    for plane, metrics in plane_before:
        assert (*plane.origin, *plane.x_dir, *plane.z_dir) == pytest.approx(metrics, abs=1e-9)
    return message
