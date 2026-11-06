"""Ikony Duo (P7.48): kresba 24 × 24 z návrhu hlavního okna 1a.

Zdroj: ``docs/p7-48-navrh-okna/ikony-duo/*.svg`` (vnitřek SVG bez kořenového prvku).
Barvu obrysu a průhlednost výplně doplní ``cad_icons`` podle palety; ``{c}`` = barva,
``{a}`` = průhlednost vybraných ploch. Generováno skriptem v plánu P7.48."""

DUO = {
    "arc": (
        '<path d="M4.5 18 A7.5 7.5 0 0 1 19.5 18"></path><rect x="2.75" y="16.25" width="3.5"'
        ' height="3.5" rx="0.6" fill="{c}" fill-opacity="{a}"></rect><rect x="17.75" '
        'y="16.25" width="3.5" height="3.5" rx="0.6" fill="{c}" '
        'fill-opacity="{a}"></rect><circle cx="12" cy="10.5" r="1.6" fill="{c}" '
        'fill-opacity="{a}"></circle>'
    ),
    "audit": (
        '<rect x="5" y="4" width="14" height="17" rx="2"></rect><rect x="9" y="2.5" width="6"'
        ' height="3" rx="1" fill="{c}" fill-opacity="{a}"></rect><polyline points="8.5,13.5 '
        '11,16 15.5,10.5"></polyline>'
    ),
    "chamfer": (
        '<path d="M4 20 V11 L11 4 H20 V20 Z" fill="{c}" fill-opacity="{a}"></path><path d="M4'
        ' 11 V4 H11" stroke-dasharray="2 2.2"></path>'
    ),
    "circle": (
        '<circle cx="12" cy="12" r="8"></circle><path d="M12 10.3 V13.7 M10.3 12 '
        'H13.7"></path><rect x="16" y="4.6" width="3.5" height="3.5" rx="0.6" fill="{c}" '
        'fill-opacity="{a}"></rect>'
    ),
    "construction": (
        '<line x1="4" y1="20" x2="20" y2="4" stroke-dasharray="3 2.6"></line><circle cx="4" '
        'cy="20" r="1.6" fill="{c}" fill-opacity="{a}"></circle><circle cx="20" cy="4" '
        'r="1.6" fill="{c}" fill-opacity="{a}"></circle>'
    ),
    "convert": (
        '<rect x="3" y="3" width="8" height="8" rx="1.2" stroke-dasharray="2 '
        '2.2"></rect><path d="M11.5 11.5 L14.5 14.5"></path><polyline points="11.8,14.5 '
        '14.5,14.5 14.5,11.8"></polyline><rect x="13" y="13" width="8" height="8" rx="1.2" '
        'fill="{c}" fill-opacity="{a}"></rect>'
    ),
    "design": (
        '<polygon points="8,10 14,13.25 8,16.5 2,13.25" fill="{c}" '
        'fill-opacity="{a}"></polygon><polyline points="2,13.25 2,18.25 8,21.5 14,18.25 '
        '14,13.25"></polyline><line x1="8" y1="16.5" x2="8" y2="21.5"></line><polygon '
        'points="18,2 19,5 22,6 19,7 18,10 17,7 14,6 17,5" fill="{c}" '
        'fill-opacity="{a}"></polygon>'
    ),
    "dimension": (
        '<rect x="4" y="14" width="16" height="6" rx="1" fill="{c}" '
        'fill-opacity="{a}"></rect><line x1="4" y1="4.5" x2="4" y2="11.5"></line><line '
        'x1="20" y1="4.5" x2="20" y2="11.5"></line><line x1="4.5" y1="8" x2="19.5" '
        'y2="8"></line><polyline points="7,6 4.5,8 7,10"></polyline><polyline points="17,6 '
        '19.5,8 17,10"></polyline>'
    ),
    "edit": (
        '<polygon points="4,20 5,15.5 15.5,5 19,8.5 8.5,19" fill="{c}" '
        'fill-opacity="{a}"></polygon><line x1="13.5" y1="7" x2="17" y2="10.5"></line><line '
        'x1="13" y1="20" x2="20" y2="20"></line>'
    ),
    "extrude": (
        '<polygon points="12,9 20,13.5 12,18 4,13.5" fill="{c}" '
        'fill-opacity="{a}"></polygon><polyline points="4,13.5 4,17.5 12,22 20,17.5 '
        '20,13.5"></polyline><line x1="12" y1="18" x2="12" y2="22"></line><line x1="12" '
        'y1="13.5" x2="12" y2="2.5"></line><polyline points="9,5.5 12,2.5 15,5.5"></polyline>'
    ),
    "fillet": (
        '<path d="M4 20 V11 A7 7 0 0 1 11 4 H20 V20 Z" fill="{c}" '
        'fill-opacity="{a}"></path><path d="M4 11 V4 H11" stroke-dasharray="2 2.2"></path>'
    ),
    "fit": (
        '<path d="M3 8 V3 H8 M16 3 H21 V8 M21 16 V21 H16 M8 21 H3 V16"></path><polygon '
        'points="12,7 16.5,9.5 12,12 7.5,9.5" fill="{c}" '
        'fill-opacity="{a}"></polygon><polyline points="7.5,9.5 7.5,14.5 12,17 16.5,14.5 '
        '16.5,9.5"></polyline><line x1="12" y1="12" x2="12" y2="17"></line>'
    ),
    "front": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5"></polygon><polygon points="20,7.5 12,12 '
        '12,20.5 20,16"></polygon><polygon points="4,7.5 12,12 12,20.5 4,16" fill="{c}" '
        'fill-opacity="{a}"></polygon>'
    ),
    "hole": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5"></polygon><polyline points="4,7.5 4,16 '
        '12,20.5 20,16 20,7.5"></polyline><line x1="12" y1="12" x2="12" '
        'y2="20.5"></line><ellipse cx="12" cy="7.5" rx="3.6" ry="2" fill="{c}" '
        'fill-opacity="{a}"></ellipse><path d="M8.4 7.5 V10.5 A3.6 2 0 0 0 15.6 10.5 '
        'V7.5"></path>'
    ),
    "iso": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5" fill="{c}" '
        'fill-opacity="{a}"></polygon><polygon points="4,7.5 12,12 12,20.5 4,16" fill="{c}" '
        'fill-opacity="{a}"></polygon><polygon points="20,7.5 12,12 12,20.5 20,16" fill="{c}"'
        ' fill-opacity="{a}"></polygon>'
    ),
    "line": (
        '<line x1="5.5" y1="18.5" x2="18.5" y2="5.5"></line><rect x="3.5" y="17" width="3.5" '
        'height="3.5" rx="0.6" fill="{c}" fill-opacity="{a}"></rect><rect x="17" y="3.5" '
        'width="3.5" height="3.5" rx="0.6" fill="{c}" fill-opacity="{a}"></rect>'
    ),
    "loft": (
        '<polygon points="3,17 12,13 21,17 12,21" fill="{c}" '
        'fill-opacity="{a}"></polygon><ellipse cx="12" cy="5" rx="4" ry="2"></ellipse><line '
        'x1="3" y1="17" x2="8" y2="5"></line><line x1="21" y1="17" x2="16" y2="5"></line>'
    ),
    "measure": (
        '<rect x="2" y="8" width="20" height="8" rx="1.5" fill="{c}" '
        'fill-opacity="{a}"></rect><path d="M6 8 V11 M10 8 V12.5 M14 8 V11 M18 8 '
        'V12.5"></path>'
    ),
    "mirror": (
        '<line x1="12" y1="2" x2="12" y2="22" stroke-dasharray="2 2.2"></line><polygon '
        'points="9,5 3,19 9,19" fill="{c}" fill-opacity="{a}"></polygon><polygon points="15,5'
        ' 21,19 15,19"></polygon>'
    ),
    "mt": (
        '<path d="M4 20.5 V10.5 A8 8 0 0 1 20 10.5 V20.5 H15.5 V10.5 A3.5 3.5 0 0 0 8.5 10.5 '
        'V20.5 Z"></path><rect x="4" y="16.5" width="4.5" height="4" fill="{c}" '
        'fill-opacity="{a}"></rect><rect x="15.5" y="16.5" width="4.5" height="4" fill="{c}" '
        'fill-opacity="{a}"></rect>'
    ),
    "new": (
        '<path d="M6 3 H14 L18 7 V21 H6 Z" fill="{c}" fill-opacity="{a}"></path><polyline '
        'points="14,3 14,7 18,7"></polyline><line x1="12" y1="11" x2="12" '
        'y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line>'
    ),
    "open": (
        '<path d="M3 6.5 H9.5 L11.5 8.5 H19 V11"></path><path d="M3 6.5 V19 L6 11 H22 L19 19 '
        'H3" fill="{c}" fill-opacity="{a}"></path>'
    ),
    "params": (
        '<line x1="3" y1="8" x2="21" y2="8"></line><circle cx="9" cy="8" r="2.6" fill="{c}" '
        'fill-opacity="{a}"></circle><line x1="3" y1="16" x2="21" y2="16"></line><circle '
        'cx="15" cy="16" r="2.6" fill="{c}" fill-opacity="{a}"></circle>'
    ),
    "pattern": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5" fill="{c}" '
        'fill-opacity="{a}"></rect><rect x="14" y="3" width="7" height="7" '
        'rx="1.5"></rect><rect x="3" y="14" width="7" height="7" rx="1.5"></rect><rect x="14"'
        ' y="14" width="7" height="7" rx="1.5"></rect>'
    ),
    "project": (
        '<polygon points="2,16 12,11 22,16 12,21"></polygon><line x1="7" y1="5" x2="17" '
        'y2="5"></line><path d="M7 6.5 V14 M17 6.5 V14" stroke-dasharray="2 2.2"></path><line'
        ' x1="7" y1="16" x2="17" y2="16" stroke-width="2.4"></line>'
    ),
    "pt": (
        '<rect x="4.5" y="10" width="8" height="11.5" rx="1.8" fill="{c}" '
        'fill-opacity="{a}"></rect><path d="M6.5 10 V8 H10.5 V10"></path><rect x="7.5" '
        'y="4.5" width="3.5" height="3.5" rx="0.6"></rect><line x1="7.2" y1="14" x2="9.8" '
        'y2="14"></line><circle cx="15" cy="6.2" r="0.9" fill="{c}" '
        'stroke="none"></circle><circle cx="18" cy="4.2" r="0.9" fill="{c}" '
        'stroke="none"></circle><circle cx="18.6" cy="7.8" r="0.9" fill="{c}" '
        'stroke="none"></circle><circle cx="21.2" cy="5.8" r="0.9" fill="{c}" '
        'stroke="none"></circle><circle cx="21" cy="9.8" r="0.9" fill="{c}" '
        'stroke="none"></circle><circle cx="16.2" cy="10" r="0.9" fill="{c}" '
        'stroke="none"></circle>'
    ),
    "redo": (
        '<path d="M19.5 10 H9.5 A5 5 0 0 0 9.5 20 H15"></path><polyline points="15.5,5.5 '
        '20,10 15.5,14.5"></polyline>'
    ),
    "revolve": (
        '<line x1="12" y1="2" x2="12" y2="22" stroke-dasharray="2 2.2"></line><rect x="14.5" '
        'y="4.5" width="5" height="10" rx="0.5" fill="{c}" fill-opacity="{a}"></rect><path '
        'd="M5 16.5 A7 3 0 0 0 19 16.5"></path><polyline points="16.8,15.6 19,16.5 '
        '18.6,18.8"></polyline>'
    ),
    "rt": (
        '<circle cx="12" cy="12" r="1.7" fill="{c}" stroke="none"></circle><path d="M13.70 '
        '14.94 L16.80 20.31 A9.6 9.6 0 0 1 7.20 20.31 L10.30 14.94 A3.4 3.4 0 0 0 13.70 14.94'
        ' Z" fill="{c}" fill-opacity="{a}"></path><path d="M8.60 12.00 L2.40 12.00 A9.6 9.6 0'
        ' 0 1 7.20 3.69 L10.30 9.06 A3.4 3.4 0 0 0 8.60 12.00 Z" fill="{c}" '
        'fill-opacity="{a}"></path><path d="M13.70 9.06 L16.80 3.69 A9.6 9.6 0 0 1 21.60 '
        '12.00 L15.40 12.00 A3.4 3.4 0 0 0 13.70 9.06 Z" fill="{c}" '
        'fill-opacity="{a}"></path>'
    ),
    "save": (
        '<rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="8" y="4" width="7" '
        'height="5" rx="0.5"></rect><rect x="7" y="13" width="10" height="7" rx="0.8" '
        'fill="{c}" fill-opacity="{a}"></rect>'
    ),
    "search": (
        '<circle cx="10.5" cy="10.5" r="6.5" fill="{c}" fill-opacity="{a}"></circle><line '
        'x1="15.5" y1="15.5" x2="20.5" y2="20.5" stroke-width="2"></line>'
    ),
    "section": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5"></polygon><polyline points="4,7.5 4,16 '
        '12,20.5 20,16 20,7.5"></polyline><line x1="12" y1="12" x2="12" '
        'y2="20.5"></line><polygon points="4,7.5 12,12 12,20.5 4,16" fill="{c}" '
        'fill-opacity="{a}"></polygon><path d="M5.5 11 L10.5 13.8 M5.5 14.3 L10.5 '
        '17.1"></path>'
    ),
    "select": (
        '<polygon points="5,3 5,19 9.4,15.2 12.4,21.5 15,20.3 12.1,14.2 17.8,14" fill="{c}" '
        'fill-opacity="{a}"></polygon>'
    ),
    "shell": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5"></polygon><polyline points="4,7.5 4,16 '
        '12,20.5 20,16 20,7.5"></polyline><line x1="12" y1="12" x2="12" '
        'y2="20.5"></line><polygon points="12,5.3 16.2,7.5 12,9.7 7.8,7.5" fill="{c}" '
        'fill-opacity="{a}"></polygon><polyline points="7.8,7.5 7.8,10.5 12,12.7"></polyline>'
    ),
    "sketch": (
        '<polygon points="2,15 12,9.5 22,15 12,20.5"></polygon><polygon points="7,15 12,12.25'
        ' 17,15 12,17.75" fill="{c}" fill-opacity="{a}"></polygon><polygon points="12.6,11.6 '
        '13.3,9 19,3.3 21,5.3 15.3,11" fill="{c}" fill-opacity="{a}"></polygon>'
    ),
    "study": (
        '<rect x="5" y="4" width="14" height="17" rx="2"></rect><rect x="9" y="2.5" width="6"'
        ' height="3" rx="1" fill="{c}" fill-opacity="{a}"></rect><line x1="12" y1="10" '
        'x2="12" y2="17"></line><line x1="8.5" y1="13.5" x2="15.5" y2="13.5"></line>'
    ),
    "sweep": (
        '<path d="M4 19 C9 19 9 6 20 5"></path><ellipse cx="4" cy="19" rx="2" ry="3" '
        'fill="{c}" fill-opacity="{a}"></ellipse><ellipse cx="20" cy="5" rx="1.4" '
        'ry="2.1"></ellipse>'
    ),
    "thickness": (
        '<polygon points="12,6 22,11.5 12,17 2,11.5"></polygon><polygon points="2,11.5 7,8.75'
        ' 12,11.5 7,14.25" fill="{c}" fill-opacity="{a}"></polygon><line x1="7" y1="14.25" '
        'x2="17" y2="8.75"></line><polyline points="2,11.5 2,14 12,19.5 22,14 '
        '22,11.5"></polyline><line x1="12" y1="17" x2="12" y2="19.5"></line>'
    ),
    "top": (
        '<polygon points="12,3 20,7.5 12,12 4,7.5" fill="{c}" '
        'fill-opacity="{a}"></polygon><polyline points="4,7.5 4,16 12,20.5 20,16 '
        '20,7.5"></polyline><line x1="12" y1="12" x2="12" y2="20.5"></line>'
    ),
    "undo": (
        '<path d="M4.5 10 H14.5 A5 5 0 0 1 14.5 20 H9"></path><polyline points="8.5,5.5 4,10 '
        '8.5,14.5"></polyline>'
    ),
    "ut": (
        '<path d="M3 4 V20 H21"></path><rect x="11.5" y="8.5" width="5" height="11.5" '
        'stroke="none" fill="{c}" fill-opacity="{a}"></rect><polyline points="3,19 4.6,19 '
        '5.6,5.5 6.6,19 12.6,19 14,10 15.4,19 21,19"></polyline><line x1="11.5" y1="14" '
        'x2="16.5" y2="14" stroke-dasharray="1.6 1.6"></line>'
    ),
}
