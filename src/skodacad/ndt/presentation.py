"""Úlohy náhledu; pouze pomocný proces. Vstup i výstup jsou přenosná data."""

from __future__ import annotations

from typing import Any


def execute(payload: dict) -> Any:
    from skodacad.document import Document
    from skodacad.ndt.volume_display import cross_section, target_preview
    from skodacad.rebuild import rebuild

    kind = payload["kind"]
    if kind == "slice":
        return cross_section(payload["source"], payload["states"], payload["plane"],
                             payload["step"])
    if kind in ("preview", "outline"):
        result = rebuild(Document.from_dict(payload["document"]))
        saved, mesh, numbers = target_preview(result.part, payload["target"])
        return {"target": saved, "mesh": mesh, "numbers": numbers, "ndt": result.ndt}
    if kind == "convergence":
        from skodacad.ndt.volume_coverage import check_volume_convergence
        from skodacad.session import ModelSession

        session = ModelSession()
        session.document = Document.from_dict(payload["document"])
        session.rebuild()
        session.ndt_placement_request = payload["placement"]
        geo, placed, target, angle = session._coverage_inputs()
        options = payload["options"]
        fine = payload["fine"]
        if fine is None:
            fine = session.compute_ndt_coverage(**options, capture_display=True)
        check_volume_convergence(geo, placed, fine=fine, target=target,
                                 mode=options["mode"], scan_step=options["step_mm"],
                                 target_step=options["target_step_mm"],
                                 tolerance_mm=options["tolerance_mm"], angle_deg=angle,
                                 spread_deg=options["spread_deg"], length_mm=options["length_mm"])
        return {"fine": fine, "source": session._volume_source}
    raise ValueError("Neznámý druh náhledu.")
