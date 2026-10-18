"""3D prohlížeč: OpenGL zobrazení z Open CASCADE (V3d/AIS) uvnitř Qt widgetu.

Tohle je jediné místo v GUI, které smí sahat na OCCT – a jen kvůli kreslení.
Modelování jde vždy přes jádro (``ModelSession``).

Ovládání: levé tlačítko táhnout = otáčení, prostřední nebo pravé = posun,
kolečko = zoom ke kurzoru, klik = výběr plochy/hrany (s Ctrl nebo Shift přidat/ubrat),
pravý klik = nabídka akcí s výběrem, dvojklik = celý díl.

Prohlížeč jen hlásí, co je vybrané (tvary OCCT, signál ``selection_changed``);
co s výběrem udělat, řeší okno přes ``ModelSession``.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

from OCP.AIS import (
    AIS_ColoredShape,
    AIS_InteractiveContext,
    AIS_SelectionScheme_Replace,
    AIS_SelectionScheme_XOR,
    AIS_Shaded,
    AIS_Shape,
    AIS_TextLabel,
    AIS_Triangulation,
    AIS_WireFrame,
)
from OCP.Aspect import (
    Aspect_DisplayConnection,
    Aspect_GFM_VER,
    Aspect_TOL_SOLID,
    Aspect_TOM_BALL,
    Aspect_TOM_POINT,
    Aspect_TOTP_LEFT_LOWER,
)
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Font import Font_FA_Bold
from OCP.GeomAbs import GeomAbs_C1
from OCP.gp import gp_Pnt
from OCP.Graphic3d import (
    Graphic3d_DiagnosticInfo_Basic,
    Graphic3d_MaterialAspect,
    Graphic3d_NameOfMaterial_Plastified,
    Graphic3d_TypeOfShadingModel_Unlit,
    Graphic3d_ZLayerId_Topmost,
)
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.Poly import Poly_Triangle, Poly_Triangulation
from OCP.Prs3d import (
    Prs3d_LineAspect,
    Prs3d_PointAspect,
    Prs3d_TypeOfHighlight_LocalDynamic,
    Prs3d_TypeOfHighlight_LocalSelected,
)
from OCP.Quantity import Quantity_Color, Quantity_NOC_BLACK, Quantity_TOC_RGB
from OCP.TCollection import TCollection_ExtendedString
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS_Compound
from OCP.V3d import (
    V3d_Viewer,
    V3d_XnegYposZpos,
    V3d_Xpos,
    V3d_XposYnegZpos,
    V3d_Yneg,
    V3d_Ypos,
    V3d_ZBUFFER,
    V3d_Zneg,
    V3d_Zpos,
)
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from skodacad.ndt.plan import STEP_COLORS, ZONE_COLOR

log = logging.getLogger(__name__)

# Klíče odpovídají viewer_views.VIEW_LABELS (názvy a zkratky pro menu).
STANDARD_VIEWS = {
    "iso": V3d_XposYnegZpos,
    "iso_back": V3d_XnegYposZpos,
    "top": V3d_Zpos,
    "bottom": V3d_Zneg,
    "front": V3d_Yneg,
    "back": V3d_Ypos,
    "right": V3d_Xpos,
}

_DRAG_THRESHOLD = 3  # pixely; menší pohyb myši je pořád „klik“


PROBE_COLORS = {"ok": (0.13, 0.62, 0.30), "tight": (0.93, 0.55, 0.10),
                "lift_off": (0.93, 0.55, 0.10), "overhang": (0.93, 0.55, 0.10),
                "uncertain": (0.93, 0.55, 0.10), "collision": (0.86, 0.15, 0.15)}
# Náhled cílového objemu NDT (svar): modrá – jiná než tři stavy pokrytí i barvy sondy.
TARGET_COLOR = (0.20, 0.45, 0.85)
TARGET_OUTLINE = (0.35, 0.35, 0.40)
PLAN_START_COLOR = STEP_COLORS["scan"]  # začátek dráhy sondy (etapa 10)


def _rgb(r: float, g: float, b: float) -> Quantity_Color:
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


def _faces_of(shape: Any) -> list[Any]:
    """Plochy tvaru OCCT (pro zkoušku kreslení v self-testu)."""
    from OCP.TopAbs import TopAbs_FACE as face_kind
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, face_kind)
    faces = []
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    return faces


def _unlit(shown: Any) -> None:
    """Barvy bez osvětlení a materiálu – přesně jako v legendě (jinak OCCT přimíchá
    výchozí materiál „mosaz“ a modrá vyjde olivově)."""
    drawer = shown.Attributes()
    drawer.SetupOwnShadingAspect()
    drawer.ShadingAspect().Aspect().SetShadingModel(Graphic3d_TypeOfShadingModel_Unlit)


def _as_capsule(handle: int) -> Any:
    """Windows HWND / macOS NSView jako PyCapsule – tak ho OCP předá do C++ jako ukazatel."""
    new_capsule = ctypes.pythonapi.PyCapsule_New
    new_capsule.restype = ctypes.py_object
    new_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    return new_capsule(handle, None, None)


def pixel_ratio(platform: str, occ_width: int, qt_width: int, device_ratio: float) -> float:
    """Kolik pixelů okna OCCT připadá na jeden bod Qt.

    Windows a Linux: ``devicePixelRatioF`` (škálování obrazovky 125–150 %). macOS: poměr
    skutečné šířky okna OCCT k šířce plochy v Qt – Retina má 2 pixely na bod, ale OCCT v cizím
    NSView může počítat v bodech i v pixelech, a tak se to nehádá, ale měří.
    """
    if platform == "darwin" and occ_width > 0 and qt_width > 0:
        return occ_width / qt_width
    return device_ratio


class _NativeSurface(QWidget):
    """Holá nativní plocha, do které kreslí OpenGL z OCCT. Události předává prohlížeči."""

    def __init__(self, owner: OccViewer) -> None:
        super().__init__(owner)
        self._owner = owner
        for attribute in (Qt.WidgetAttribute.WA_NativeWindow, Qt.WidgetAttribute.WA_PaintOnScreen,
                          Qt.WidgetAttribute.WA_NoSystemBackground,
                          Qt.WidgetAttribute.WA_OpaquePaintEvent):
            self.setAttribute(attribute)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEngine(self):  # noqa: N802 – kreslí OpenGL, ne Qt
        return None

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._owner._initialize()

    def paintEvent(self, event) -> None:  # noqa: N802
        self._owner._redraw()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._owner._resized()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._owner._mouse_press(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._owner._mouse_move(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._owner._mouse_release(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._owner.fit_all()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        self._owner._wheel(event)


class OccViewer(QWidget):
    """3D prohlížeč dílu. Když se OpenGL nepodaří spustit, ukáže místo pádu zprávu."""

    selection_changed = Signal(list)  # vybrané plochy a hrany (TopoDS), [] = nic
    context_menu_requested = Signal(QPoint)  # pravý klik bez tažení, globální souřadnice
    probe_dragged = Signal(list, object)  # plocha a bod [x, y, z] při jízdě sondou
    probe_rotated = Signal(int)  # otočení sondy kolečkem (±15°)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.error: str | None = None
        # Kde spuštění selhalo: "display" (není obrazovka), "window" (chyba v našem kódu),
        # "opengl" (grafická karta / ovladač).
        self.failed_stage: str | None = None

        self._surface = _NativeSurface(self)
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setMargin(24)
        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._surface)
        self._stack.addWidget(self._message)

        self._view = None
        self._context = None
        self._window = None
        self._ais: AIS_Shape | None = None
        self._highlight: AIS_Shape | None = None
        self._measure_objects: list[Any] = []  # čáry a popisky měření
        self._map_objects: list[Any] = []  # barevná mapa tloušťky a značka nejtenčího místa
        self._coverage_objects: list[Any] = []
        self._probe_objects: list[Any] = []  # virtuální NDT sonda a směr paprsku
        self._target_objects: list[Any] = []  # náhled cílového objemu NDT (svar)
        self._point_objects: list[Any] = []  # barevné body (mapa kontaktních ploch, etapa 09)
        self._plan_objects: list[Any] = []  # plán dráhy sondy a zakázané zóny (etapa 10)
        self.picked_point: tuple[float, float, float] | None = None  # kam mířil poslední klik
        self.probe_drag_enabled = False  # režim „Jezdit sondou myší“
        self._probe_dragging = False
        self._pending: tuple[Any, bool] | None = None
        self._press: QPoint | None = None
        self._last: QPoint | None = None
        self._dragging = False
        self._known_size: tuple[int, int] | None = None
        self.software = False  # macOS bez grafické karty: OpenGL kreslí procesor
        self._failed: list[Any] = []  # nepovedený pokus o OpenGL – na Macu se neruší dřív než okno

    # --- veřejné API ------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._view is not None

    def show_part(self, part: Any | None, fit: bool = False,
                  accent: list[Any] | None = None) -> None:
        """Zobrazí díl (build123d ``Part``) nebo nic; ``fit`` = přizpůsobit pohled,
        ``accent`` = plochy jinou barvou (plochy řezu)."""
        if not self.ready:
            self._pending = (part, fit, accent)
            return
        context = self._context
        if self._ais is not None:
            context.Remove(self._ais, False)
            self._ais = None
        self._remove_highlight()
        self._remove_measurement()
        self._remove_map()
        self._remove_probe()
        self._remove_target()
        self._remove_coverage()
        self._remove_points()
        self._remove_plan()
        if part is not None:
            ais = AIS_ColoredShape(part.wrapped)  # jako AIS_Shape, navíc barva po plochách
            ais.SetMaterial(Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial_Plastified))
            ais.SetColor(_rgb(0.56, 0.62, 0.70))
            for face in accent or []:
                ais.SetCustomColor(getattr(face, "wrapped", face), _rgb(0.82, 0.38, 0.33))
            drawer = ais.Attributes()  # obrysy ploch až po barvě, jinak je SetColor přebarví
            drawer.SetFaceBoundaryDraw(True)
            drawer.SetFaceBoundaryAspect(
                Prs3d_LineAspect(_rgb(0.10, 0.10, 0.12), Aspect_TOL_SOLID, 1.2)
            )
            # Nekreslit hrany plošek vymodelovaného závitu (označené C2 v threads.py);
            # ostré i tečné hrany (zaoblení, G1/C1) zůstanou vidět.
            drawer.SetFaceBoundaryUpperContinuity(GeomAbs_C1)
            drawer.UIsoAspect().SetNumber(0)  # drátěný režim (pod mapou tloušťky) bez izočar
            drawer.VIsoAspect().SetNumber(0)
            context.Display(ais, False)
            context.Deactivate(ais)  # celé těleso ne, jen plochy a hrany
            context.Activate(ais, AIS_Shape.SelectionMode_s(TopAbs_FACE))
            context.Activate(ais, AIS_Shape.SelectionMode_s(TopAbs_EDGE))
            self._ais = ais
        if fit:
            self._sync_size()
            self._view.FitAll(0.08, False)
        self.picked_point = None
        self.selection_changed.emit([])
        self._view.Redraw()

    def selected_shapes(self) -> list[Any]:
        """Vybrané plochy a hrany jako tvary OCCT."""
        if not self.ready:
            return []
        shapes = []
        context = self._context
        context.InitSelected()
        while context.MoreSelected():
            if context.HasSelectedShape():
                shapes.append(context.SelectedShape())
            context.NextSelected()
        return shapes

    def clear_selection(self) -> None:
        if self.ready:
            self._context.ClearSelected(False)
            self._view.Redraw()
        self.picked_point = None
        self.selection_changed.emit([])

    def highlight(self, shapes: list[Any]) -> None:
        """Zvýrazní tvary (hrany/plochy, které používá vybraný prvek); [] = nic.

        Kreslí se navrch (vidět i skrz díl) a kliknout na ně nejde.
        """
        if not self.ready:
            return
        self._remove_highlight()
        if shapes:
            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            for shape in shapes:
                builder.Add(compound, shape)
            ais = AIS_Shape(compound)
            ais.SetColor(_rgb(0.90, 0.20, 0.55))
            ais.SetWidth(4.0)
            ais.SetTransparency(0.45)
            self._context.Display(ais, False)
            self._context.Deactivate(ais)
            self._context.SetZLayer(ais, Graphic3d_ZLayerId_Topmost)
            self._highlight = ais
        self._view.Redraw()

    def show_measurement(self, lines: list[tuple[Any, Any, str]]) -> None:
        """Čáry měření (od bodu k bodu, s popiskem) navrch dílu; [] = žádné.

        Kreslí se přes díl (vidět i skrz něj) a kliknout na ně nejde.
        """
        if not self.ready:
            return
        self._remove_measurement()
        for start, end, text in lines:
            self._measure_objects += self._marker_objects(start, end, text,
                                                          _rgb(0.0, 0.22, 0.07))
        self._view.Redraw()

    def show_probe(self, body: Any, state: str, start: Any, end: Any, text: str,
                   beam: Any = ()) -> None:
        """Virtuální NDT sonda: průhledné tělo v barvě stavu (zelená přiloženo, oranžová málo
        místa / nedosedá / přesahuje, červená kolize), čára směru paprsku z výstupního bodu
        s popiskem a lomená dráha osy UT paprsku v dílu. Kliknout na ni nejde – plochy dílu
        pod ní jdou dál vybírat."""
        if not self.ready:
            return
        self._remove_probe()
        color = _rgb(*PROBE_COLORS.get(state, PROBE_COLORS["uncertain"]))
        shown = AIS_Shape(getattr(body, "wrapped", body))
        shown.SetColor(color)
        shown.SetTransparency(0.35)
        self._context.Display(shown, False)
        self._context.Deactivate(shown)
        self._probe_objects = [shown, *self._marker_objects(start, end, text, color),
                               *self._beam_objects(beam, color)]
        self._view.Redraw()

    def hide_probe(self) -> None:
        if not self.ready:
            return
        self._remove_probe()
        self._view.Redraw()

    def _remove_probe(self) -> None:
        for shown in self._probe_objects:
            self._context.Remove(shown, False)
        self._probe_objects = []

    def show_target(self, body: Any, outline: Any = None) -> None:
        """Náhled cílového objemu NDT: průhledné modré těleso (účinný objem v materiálu)
        a ``outline`` – šedé hrany zadaného tvaru, když z dílu vyčnívá. Kliknout na ně nejde,
        plochy dílu pod nimi jdou dál vybírat."""
        if not self.ready:
            return
        self._remove_target()
        shown = AIS_Shape(getattr(body, "wrapped", body))
        shown.SetColor(_rgb(*TARGET_COLOR))
        shown.SetTransparency(0.55)
        self._context.Display(shown, False)
        self._context.Deactivate(shown)
        # Navrch (jako zvýraznění): cíl leží uvnitř dílu a jeho stěny splývají se stěnami
        # dílu – jinak by ho neprůhledný díl schoval.
        self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
        self._target_objects = [shown]
        if outline is not None:
            edges = AIS_Shape(getattr(outline, "wrapped", outline))
            edges.SetColor(_rgb(*TARGET_OUTLINE))
            edges.SetWidth(1.5)
            edges.Attributes().UIsoAspect().SetNumber(0)
            edges.Attributes().VIsoAspect().SetNumber(0)
            edges.SetDisplayMode(0)  # jen hrany (okno má výchozí režim 1 = stínovaně)
            self._context.Display(edges, False)
            self._context.Deactivate(edges)
            self._context.SetZLayer(edges, Graphic3d_ZLayerId_Topmost)
            self._target_objects.append(edges)
        self._view.Redraw()

    def hide_target(self) -> None:
        if self.ready:
            self._remove_target()
            self._view.Redraw()

    def show_points(self, points: list, colors: list) -> None:
        """Barevné body (kuličky) navrch dílu – mapa kontaktních ploch návrhu poloh sondy.
        Jedna kresba na barvu; kliknout na ně nejde, plochy dílu jdou dál vybírat."""
        if not self.ready:
            return
        self._remove_points()
        groups: dict[tuple, list] = {}
        for point, color in zip(points, colors, strict=True):
            groups.setdefault(tuple(color), []).append(point)
        for color, group in groups.items():
            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            for point in group:
                builder.Add(compound, BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex())
            shown = AIS_Shape(compound)
            quantity = _rgb(*color)
            shown.SetColor(quantity)
            # Kulička jako u měření: bezpečná i se základním ovladačem Windows (self-test).
            shown.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, quantity, 2.0))
            self._context.Display(shown, False)
            self._context.Deactivate(shown)
            self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
            self._point_objects.append(shown)
        self._view.Redraw()

    def hide_points(self) -> None:
        if self.ready:
            self._remove_points()
            self._view.Redraw()

    def _remove_points(self) -> None:
        for shown in self._point_objects:
            self._context.Remove(shown, False)
        self._point_objects = []

    def show_plan(self, lines: dict, start: Any = None, zones: list[Any] = ()) -> None:
        """Plán dráhy sondy: úsečky po barvách (``lines`` = {barva: [(od, do), …]} – úseky,
        přesuny po povrchu, přestavení obloukem nad dílem), začátek kuličkou a zakázané zóny
        jako průhledné červené kvádry. Kliknout na ně nejde, plochy dílu jdou dál vybírat."""
        if not self.ready:
            return
        self._remove_plan()
        for color, pairs in lines.items():
            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            count = 0
            for a, b in pairs:
                begin, finish = gp_Pnt(*a), gp_Pnt(*b)
                if begin.Distance(finish) > 1e-6:
                    builder.Add(compound, BRepBuilderAPI_MakeEdge(begin, finish).Edge())
                    count += 1
            if not count:
                continue
            shown = AIS_Shape(compound)
            shown.SetColor(_rgb(*color))
            shown.SetWidth(2.5)
            self._context.Display(shown, False)
            self._context.Deactivate(shown)
            self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
            self._plan_objects.append(shown)
        if start is not None:  # kulička jako u měření (bezpečná i s ovladačem bez GPU)
            quantity = _rgb(*PLAN_START_COLOR)
            ball = AIS_Shape(BRepBuilderAPI_MakeVertex(gp_Pnt(*start)).Vertex())
            ball.SetColor(quantity)
            ball.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, quantity, 3.0))
            self._context.Display(ball, False)
            self._context.Deactivate(ball)
            self._context.SetZLayer(ball, Graphic3d_ZLayerId_Topmost)
            self._plan_objects.append(ball)
        for zone in zones:
            box = AIS_Shape(getattr(zone, "wrapped", zone))
            box.SetColor(_rgb(*ZONE_COLOR))
            box.SetTransparency(0.35)
            _unlit(box)  # bez osvětlení – shora by červená ve světle zbělala
            self._context.Display(box, False)
            self._context.Deactivate(box)
            self._plan_objects.append(box)
        self._view.Redraw()

    def hide_plan(self) -> None:
        if self.ready:
            self._remove_plan()
            self._view.Redraw()

    def _remove_plan(self) -> None:
        for shown in self._plan_objects:
            self._context.Remove(shown, False)
        self._plan_objects = []

    def _remove_target(self) -> None:
        for shown in self._target_objects:
            self._context.Remove(shown, False)
        self._target_objects = []

    def scale_info(self) -> str:
        """Velikost okna OCCT proti Qt a poměr pro klik myší (diagnostika Retina, 150 %)."""
        if not self.ready:
            return ""
        self._sync_size()
        width, height = self._known_size or (0, 0)
        ratio = pixel_ratio(sys.platform, width, self._surface.width(),
                            self._surface.devicePixelRatioF())
        return (f"okno OCCT {width}×{height}, Qt {self._surface.width()}×"
                f"{self._surface.height()}, poměr myši {ratio:.2f}")

    def graphics_info(self) -> str:
        """Grafický ovladač OpenGL (výrobce, zařízení, verze) – pro log a self-test."""
        if not self.ready:
            return ""
        try:
            from OCP.OCP.collections import (
                IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString as Info,
            )

            info = Info()
            self._view.DiagnosticInformation(info, Graphic3d_DiagnosticInfo_Basic)
            values = {info.FindKey(i).ToCString(): info.FindFromIndex(i).ToCString()
                      for i in range(1, info.Extent() + 1)}
        except Exception as exc:  # noqa: BLE001 – jen informace
            return f"neznámý ({type(exc).__name__})"
        return " / ".join(values[key] for key in ("GLvendor", "GLdevice", "GLversion")
                          if key in values)

    def probe_drawing(self, variant: str) -> None:
        """Self-test: nakreslí jeden druh značky měření a hned překreslí (při pádu ovladače
        OpenGL je ve zprávě vidět, na kterém druhu to bylo)."""
        color = _rgb(0.0, 0.55, 0.25)
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        if variant == "line":
            builder.Add(compound, BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0),
                                                          gp_Pnt(10, 0, 0)).Edge())
        else:
            builder.Add(compound, BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Vertex())
        shown: Any = AIS_Shape(compound)
        shown.SetColor(color)
        if variant in ("map", "map_top"):  # barevná síť (mapa) a díl jen hranami; „map_top“
            # navrch jako objemová mapa svaru (07C)
            mesh = Poly_Triangulation(3, 1, False)
            for i, point in enumerate(((0, 0, 0), (10, 0, 0), (0, 10, 0)), start=1):
                mesh.SetNode(i, gp_Pnt(*point))
            mesh.SetTriangle(1, Poly_Triangle(1, 2, 3))
            from OCP.OCP.collections import HArray1_int

            packed = HArray1_int(1, 3)
            for i, value in enumerate((0x0000FF, 0x00FF00, 0xFF0000), start=1):
                packed.SetValue(i, value)
            shown = AIS_Triangulation(mesh)
            shown.SetColors(packed)
            shown.SetDisplayMode(0)
            _unlit(shown)
            self._context.Display(shown, False)
            if variant == "map_top":
                self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
            if self._ais is not None:
                self._context.SetDisplayMode(self._ais, AIS_WireFrame, False)
            self._view.Redraw()
            self._context.Remove(shown, False)
            if self._ais is not None:
                self._context.SetDisplayMode(self._ais, AIS_Shaded, False)
            self._view.Redraw()
            return
        if variant == "probe":  # průhledné těleso (virtuální NDT sonda)
            body = AIS_Shape(BRepPrimAPI_MakeBox(10, 10, 10).Shape())
            body.SetColor(_rgb(*PROBE_COLORS["ok"]))
            body.SetTransparency(0.35)
            self._context.Display(body, False)
            self._view.Redraw()
            self._context.Remove(body, False)
            self._view.Redraw()
            return
        if variant == "points":  # mapa kontaktních ploch návrhu poloh (etapa 09)
            self.show_points([(0, 0, 0), (10, 0, 0), (0, 10, 0)],
                             [(0.15, 0.7, 0.25), (0.95, 0.55, 0.1), (0.85, 0.2, 0.15)])
            self.hide_points()
            return
        if variant == "plan":  # plán dráhy sondy: čáry po barvách, kulička, průhledná zóna
            self.show_plan({(0.1, 0.6, 0.2): [((0, 0, 0), (10, 0, 0))],
                            (0.95, 0.55, 0.1): [((10, 0, 0), (10, 0, 5))]}, (0, 0, 0),
                           [BRepPrimAPI_MakeBox(5, 5, 5).Shape()])
            self.hide_plan()
            return
        if variant == "target":  # průhledný cílový objem NDT a drátěný obrys zadaného tvaru
            self.show_target(BRepPrimAPI_MakeBox(10, 10, 10).Shape(),
                             BRepPrimAPI_MakeBox(12, 12, 12).Shape())
            self.hide_target()
            return
        if variant == "accent":  # díl s plochami jiné barvy (plochy řezu)
            colored = AIS_ColoredShape(BRepPrimAPI_MakeBox(10, 10, 10).Shape())
            colored.SetColor(color)
            for face in _faces_of(colored.Shape()):
                colored.SetCustomColor(face, _rgb(0.82, 0.38, 0.33))
                break
            self._context.Display(colored, False)
            self._view.Redraw()
            self._context.Remove(colored, False)
            self._view.Redraw()
            return
        if variant in ("point", "ball"):
            marker = Aspect_TOM_BALL if variant == "ball" else Aspect_TOM_POINT
            shown.Attributes().SetPointAspect(Prs3d_PointAspect(marker, color, 2.0))
        if variant in ("label", "arial"):
            shown = AIS_TextLabel()
            shown.SetText(TCollection_ExtendedString("12.50 mm 45°", True))
            shown.SetPosition(gp_Pnt(0, 0, 0))
            if variant == "arial":
                shown.SetHeight(17)
                shown.SetFont("Arial")
                shown.SetFontAspect(Font_FA_Bold)
        self._context.Display(shown, False)
        self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
        self._view.Redraw()
        self._context.Remove(shown, False)
        self._view.Redraw()

    def show_thickness_map(self, nodes: list, triangles: list, colors: list,
                           marker: tuple[Any, str] | None = None,
                           fill: list[Any] | None = None) -> None:
        """Barevná mapa tloušťky stěny přes díl. Díl se ukáže jen obrysem hran, ale plochy jde
        dál vybírat kliknutím (měření v bodě). ``marker`` = (bod, popisek) nejtenčího místa,
        ``fill`` = plochy vyplněné barvou řezu (díl je pod mapou jen drátěný)."""
        if not self.ready:
            return
        self._remove_map()
        mesh = Poly_Triangulation(len(nodes), len(triangles), False)
        for i, (x, y, z) in enumerate(nodes, start=1):
            mesh.SetNode(i, gp_Pnt(x, y, z))
        for i, (a, b, c) in enumerate(triangles, start=1):
            mesh.SetTriangle(i, Poly_Triangle(a + 1, b + 1, c + 1))
        from OCP.OCP.collections import HArray1_int

        packed = HArray1_int(1, max(1, len(nodes)))
        for i, (r, g, b) in enumerate(colors, start=1):  # barva uzlu: R + G<<8 + B<<16
            packed.SetValue(i, int(r * 255) | int(g * 255) << 8 | int(b * 255) << 16)
        colored = AIS_Triangulation(mesh)
        colored.SetColors(packed)
        colored.SetDisplayMode(0)  # AIS_Triangulation kreslí jen režim 0 (okno má výchozí 1)
        _unlit(colored)
        self._context.Display(colored, False)
        self._context.Deactivate(colored)
        self._map_objects.append(colored)
        if fill:
            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            for face in fill:
                builder.Add(compound, getattr(face, "wrapped", face))
            cut_faces = AIS_Shape(compound)
            cut_faces.SetColor(_rgb(0.82, 0.38, 0.33))
            cut_faces.SetDisplayMode(1)
            self._context.Display(cut_faces, False)
            self._context.Deactivate(cut_faces)
            self._map_objects.append(cut_faces)
        if marker is not None:
            point, text = marker
            self._map_objects += self._marker_objects(point, point, text, _rgb(0.55, 0.0, 0.55))
        if self._ais is not None:
            self._context.SetDisplayMode(self._ais, AIS_WireFrame, False)
        self._highlight_fill(False)  # výběr jen obtáhnout, ať nezakryje barvy mapy
        self._view.Redraw()

    def hide_thickness_map(self) -> None:
        if not self.ready:
            return
        self._remove_map()
        self._view.Redraw()

    def show_coverage_map(self, nodes: list, triangles: list, colors: list,
                          fill: list[Any] | None = None, topmost: bool = False) -> None:
        """Tři diskrétní barvy cílových plošek UT, nezávisle na sondě a měřeních.

        Objemový cíl (07C) leží uvnitř dílu: kreslí se navrch (``topmost``) a ``fill`` jsou
        plochy řezu dílu, vyplněné šedě – barevný průřez svarem je pak vidět v nich."""
        if not self.ready:
            return
        self._remove_coverage()
        if fill:
            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            for face in fill:
                builder.Add(compound, getattr(face, "wrapped", face))
            cut_faces = AIS_Shape(compound)
            cut_faces.SetColor(_rgb(0.55, 0.57, 0.60))  # šedě – červená je „nepokryto“
            cut_faces.SetDisplayMode(1)
            self._context.Display(cut_faces, False)
            self._context.Deactivate(cut_faces)
            self._coverage_objects.append(cut_faces)
        if not triangles:
            self._view.Redraw()
            return
        from OCP.OCP.collections import HArray1_int

        mesh = Poly_Triangulation(len(nodes), len(triangles), False)
        for i, point in enumerate(nodes, start=1):
            mesh.SetNode(i, gp_Pnt(*point))
        for i, (a, b, c) in enumerate(triangles, start=1):
            mesh.SetTriangle(i, Poly_Triangle(a + 1, b + 1, c + 1))
        packed = HArray1_int(1, len(nodes))
        for i, (r, g, b) in enumerate(colors, start=1):
            packed.SetValue(i, int(r * 255) | int(g * 255) << 8 | int(b * 255) << 16)
        shown = AIS_Triangulation(mesh)
        shown.SetColors(packed)
        shown.SetDisplayMode(0)
        _unlit(shown)
        self._context.Display(shown, False)
        self._context.Deactivate(shown)
        if topmost:
            self._context.SetZLayer(shown, Graphic3d_ZLayerId_Topmost)
        self._coverage_objects.append(shown)
        if self._ais is not None:
            self._context.SetDisplayMode(self._ais, AIS_WireFrame, False)
        self._highlight_fill(False)
        self._view.Redraw()

    def hide_coverage_map(self) -> None:
        if self.ready:
            self._remove_coverage()
            self._view.Redraw()

    def _remove_coverage(self) -> None:
        for shown in self._coverage_objects:
            self._context.Remove(shown, False)
        self._coverage_objects = []
        if self._ais is not None and not self._map_objects:
            self._context.SetDisplayMode(self._ais, AIS_Shaded, False)
        self._highlight_fill(bool(not self._map_objects))

    def _remove_map(self) -> None:
        if not self._map_objects:
            return
        for shown in self._map_objects:
            self._context.Remove(shown, False)
        self._map_objects = []
        if self._ais is not None and not self._coverage_objects:
            self._context.SetDisplayMode(self._ais, AIS_Shaded, False)
        self._highlight_fill(not self._coverage_objects)

    def _highlight_fill(self, fill: bool) -> None:
        for kind in (Prs3d_TypeOfHighlight_LocalSelected, Prs3d_TypeOfHighlight_LocalDynamic):
            self._context.HighlightStyle(kind).SetDisplayMode(1 if fill else 0)

    def _marker_objects(self, start: Any, end: Any, text: str, color: Any) -> list[Any]:
        """Čára (nebo jen bod) s kuličkami na koncích a popiskem – navrch dílu."""
        begin, finish = gp_Pnt(*start), gp_Pnt(*end)
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        if begin.Distance(finish) > 1e-6:
            builder.Add(compound, BRepBuilderAPI_MakeEdge(begin, finish).Edge())
        for point in (begin, finish):
            builder.Add(compound, BRepBuilderAPI_MakeVertex(point).Vertex())
        line = AIS_Shape(compound)
        line.SetColor(color)
        line.SetWidth(3.0)
        line.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, color, 2.0))
        label = AIS_TextLabel()
        label.SetText(TCollection_ExtendedString(text, True))
        label.SetPosition(gp_Pnt((begin.X() + finish.X()) / 2, (begin.Y() + finish.Y()) / 2,
                                 (begin.Z() + finish.Z()) / 2))
        label.SetColor(color)
        # Jen prostý text: podklad (Aspect_TODT_SUBTITLE) shodí základní ovladač Windows
        # bez grafické karty (GDI Generic, OpenGL 1.1) – ověřuje to self-test.
        label.SetHeight(17)
        label.SetFont("Arial")  # bezpatkové písmo (bez něj OCCT bere patkové)
        label.SetFontAspect(Font_FA_Bold)  # tučně – čitelné i na šedém dílu
        shown = [line, label]
        for item in shown:
            self._context.Display(item, False)
            self._context.Deactivate(item)
            self._context.SetZLayer(item, Graphic3d_ZLayerId_Topmost)
        return shown

    def _beam_objects(self, points: Any, color: Any) -> list[Any]:
        """Lomená čára osy UT paprsku v dílu s kuličkami v bodech odrazu a dopadu."""
        pts = list(points)
        if len(pts) < 2:
            return []
        pnts = [gp_Pnt(*pt) for pt in pts]
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for a, b in zip(pnts, pnts[1:], strict=False):
            if a.Distance(b) > 1e-6:
                builder.Add(compound, BRepBuilderAPI_MakeEdge(a, b).Edge())
        for pnt in pnts:
            builder.Add(compound, BRepBuilderAPI_MakeVertex(pnt).Vertex())
        line = AIS_Shape(compound)
        line.SetColor(color)
        line.SetWidth(2.5)
        line.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, color, 2.0))
        self._context.Display(line, False)
        self._context.Deactivate(line)
        self._context.SetZLayer(line, Graphic3d_ZLayerId_Topmost)
        return [line]

    def _remove_measurement(self) -> None:
        for shown in self._measure_objects:
            self._context.Remove(shown, False)
        self._measure_objects = []

    def _remove_highlight(self) -> None:
        if self._highlight is not None:
            self._context.Remove(self._highlight, False)
            self._highlight = None

    def fit_all(self) -> None:
        if self.ready:
            self._sync_size()
            self._view.FitAll(0.08, False)
            self._view.Redraw()

    def set_standard_view(self, name: str) -> None:
        if self.ready:
            self._view.SetProj(STANDARD_VIEWS[name])
            self.fit_all()

    def dump(self, path: str) -> bool:
        """Uloží aktuální 3D obraz do souboru (PNG)."""
        return bool(self.ready and self._view.Dump(path))

    # --- inicializace -------------------------------------------------------------

    def _initialize(self) -> None:
        if self.ready or self.error:
            return
        stage = "display"
        try:
            display = Aspect_DisplayConnection()
            stage = "window"
            handle = int(self._surface.winId())
            if sys.platform == "win32":
                from OCP.WNT import WNT_Window

                window = WNT_Window(_as_capsule(handle))
            elif sys.platform == "darwin":  # Qt winId() je na Macu NSView
                from OCP.Cocoa import Cocoa_Window

                window = Cocoa_Window(_as_capsule(handle))
            else:
                from OCP.Xw import Xw_Window

                window = Xw_Window(display, handle)

            stage = "opengl"
            try:
                viewer, view = self._open_view(display, window, software=False)
            except Exception as exc:  # noqa: BLE001
                if sys.platform != "darwin":
                    raise
                # Mac bez grafické karty (virtuál, vzdálená plocha): zkusit softwarové OpenGL.
                log.warning("OpenGL s grafickou kartou nejde (%s) – zkouším softwarové", exc)
                viewer, view = self._open_view(display, window, software=True)
                self.software = True
            if not window.IsMapped():
                window.Map()
            context = AIS_InteractiveContext(viewer)
        except Exception as exc:  # noqa: BLE001 – bez 3D má zbytek aplikace fungovat dál
            self._fail(stage, exc)
            return

        self._window, self._view, self._context = window, view, context
        self._style()
        self._sync_size()
        log.info("3D prohlížeč spuštěn (OpenGL: %s)", self.graphics_info())
        if self._pending is not None:
            part, fit, accent = self._pending
            self._pending = None
            self.show_part(part, fit=fit, accent=accent)

    def _open_view(self, display: Any, window: Any, software: bool) -> tuple[Any, Any]:
        """Grafický ovladač, prohlížeč a pohled OCCT napojený na okno. ``software`` = bez
        hardwarové akcelerace (OpenGL_Caps.contextNoAccel, na Macu softwarový renderer Apple)."""
        driver = OpenGl_GraphicDriver(display, True)
        if software:
            driver.ChangeOptions().contextNoAccel = True
        viewer = V3d_Viewer(driver)
        viewer.SetDefaultLights()
        viewer.SetLightOn()
        view = viewer.CreateView()
        self._failed.append((driver, viewer, view))  # při chybě zůstanou až do zavření okna
        view.SetWindow(window)
        self._failed.pop()
        return viewer, view

    def _style(self) -> None:
        view, context = self._view, self._context
        view.SetBgGradientColors(_rgb(0.95, 0.96, 0.98), _rgb(0.72, 0.77, 0.84),
                                 Aspect_GFM_VER, False)
        view.TriedronDisplay(Aspect_TOTP_LEFT_LOWER, Quantity_Color(Quantity_NOC_BLACK), 0.08,
                             V3d_ZBUFFER)
        params = view.ChangeRenderingParams()
        params.NbMsaaSamples = 4
        params.IsAntialiasingEnabled = True
        context.SetDisplayMode(AIS_Shaded, False)
        for kind, color in ((Prs3d_TypeOfHighlight_LocalSelected, _rgb(1.0, 0.55, 0.0)),
                            (Prs3d_TypeOfHighlight_LocalDynamic, _rgb(0.0, 0.65, 1.0))):
            style = context.HighlightStyle(kind)
            style.SetColor(color)
            style.SetDisplayMode(1)  # vybranou plochu vyplnit barvou, ne jen obtáhnout
        view.SetProj(V3d_XposYnegZpos)

    def _fail(self, stage: str, exc: Exception) -> None:
        self.failed_stage = stage
        self.error = f"{type(exc).__name__}: {exc}"
        log.exception("3D prohlížeč se nepodařilo spustit (fáze %s)", stage)
        self._message.setText(
            "3D zobrazení se nepodařilo spustit.\n\n"
            f"Podrobnosti: {self.error}\n\n"
            "Zbytek aplikace funguje (parametry, uložení, export). "
            "Pošli prosím soubor skodacad.log ze složky SkodaCAD ve svém profilu."
        )
        self._stack.setCurrentWidget(self._message)

    # --- kreslení a myš -----------------------------------------------------------

    def _redraw(self) -> None:
        if self.ready:
            self._sync_size()
            self._view.Redraw()

    def _resized(self) -> None:
        if self.ready:
            self._sync_size()

    def _sync_size(self) -> None:
        """OCCT si velikost okna jinak nepřečte znovu – bez toho by výběr myší mířil vedle.

        Ptáme se přímo okna (ne Qt): nativní okno se může zvětšit o chvilku později.
        """
        size = tuple(self._view.Window().Size())
        if size != self._known_size:
            self._known_size = size
            self._view.MustBeResized()

    def _pixels(self, pos) -> tuple[int, int]:
        """Qt dává souřadnice v logických bodech, OCCT chce pixely svého okna (150 %, Retina)."""
        ratio = pixel_ratio(sys.platform, self._known_size[0] if self._known_size else 0,
                            self._surface.width(), self._surface.devicePixelRatioF())
        return int(pos.x() * ratio), int(pos.y() * ratio)

    def _mouse_press(self, event: QMouseEvent) -> None:
        if not self.ready:
            return
        self._surface.setFocus()
        self._press = self._last = event.position().toPoint()
        self._dragging = False
        if event.button() == Qt.MouseButton.LeftButton:
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            if self.probe_drag_enabled or alt:
                self._probe_dragging = True
                picked = self._pick_face_at(*self._pixels(event.position()))
                if picked is not None:
                    self.probe_dragged.emit([picked[0]], picked[1])
                return
            self._probe_dragging = False
            self._view.StartRotation(*self._pixels(event.position()))

    def _mouse_move(self, event: QMouseEvent) -> None:
        if not self.ready:
            return
        pos = event.position().toPoint()
        buttons = event.buttons()
        x, y = self._pixels(event.position())
        if buttons and self._press is not None:
            if (pos - self._press).manhattanLength() > _DRAG_THRESHOLD:
                self._dragging = True
            if self._probe_dragging and buttons & Qt.MouseButton.LeftButton:
                self._dragging = True
                picked = self._pick_face_at(x, y)
                if picked is not None:
                    self.probe_dragged.emit([picked[0]], picked[1])
            else:
                pan = bool(buttons & (Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton)
                           or event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if self._dragging and pan:  # Shift + levé: posun i na trackpadu (Mac)
                    lx, ly = self._pixels(self._last)
                    self._view.Pan(x - lx, ly - y)
                elif self._dragging and buttons & Qt.MouseButton.LeftButton:
                    self._view.Rotation(x, y)
        else:
            self._context.MoveTo(x, y, self._view, True)  # předvýběr pod kurzorem
        self._last = pos

    def _mouse_release(self, event: QMouseEvent) -> None:
        if not self.ready:
            return
        if self._probe_dragging:
            self._probe_dragging = False
            self._press = None
            self._dragging = False
            return
        if not self._dragging:
            x, y = self._pixels(event.position())
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers = event.modifiers()
                toggle = bool(modifiers & (Qt.KeyboardModifier.ControlModifier
                                           | Qt.KeyboardModifier.ShiftModifier))
                self._select_at(x, y, toggle)
            elif event.button() == Qt.MouseButton.RightButton:
                self._select_for_menu(x, y)
                self.context_menu_requested.emit(event.globalPosition().toPoint())
        self._press = None
        self._dragging = False

    def _pick_face_at(self, x: int, y: int) -> tuple[Any, tuple[float, float, float]] | None:
        """Plocha a bod pod kurzorem [x, y] v pixelech OCCT (pro plynulou jízdu sondou)."""
        context = self._context
        context.MoveTo(x, y, self._view, False)
        if not context.HasDetected() or not context.HasDetectedShape():
            return None
        shape = context.DetectedShape()
        if shape.ShapeType() != TopAbs_FACE:
            return None
        self._remember_point()
        if self.picked_point is None:
            return None
        return shape, self.picked_point

    def _select_at(self, x: int, y: int, toggle: bool = False) -> None:
        """Klik: nahradí výběr tím pod kurzorem; s Ctrl/Shift ho přidá nebo ubere."""
        context = self._context
        context.MoveTo(x, y, self._view, False)
        self._remember_point()
        if toggle:
            if context.HasDetected():
                context.SelectDetected(AIS_SelectionScheme_XOR)
        else:
            context.SelectDetected(AIS_SelectionScheme_Replace)
        context.UpdateCurrentViewer()
        self.selection_changed.emit(self.selected_shapes())

    def _select_for_menu(self, x: int, y: int) -> None:
        """Pravý klik na nevybraný prvek ho vybere (jako běžně v programech), na vybraný
        nechá výběr, jak je – nabídka pak pracuje s ním."""
        context = self._context
        context.MoveTo(x, y, self._view, False)
        if not context.HasDetected() or not context.HasDetectedShape():
            return
        detected = context.DetectedShape()
        if any(detected.IsSame(shape) for shape in self.selected_shapes()):
            self._remember_point()
            return
        self._select_at(x, y)

    def _remember_point(self) -> None:
        selector = self._context.MainSelector()
        if selector.NbPicked() > 0:
            point = selector.PickedPoint(1)
            self.picked_point = (point.X(), point.Y(), point.Z())
        else:
            self.picked_point = None

    def _wheel(self, event: QWheelEvent) -> None:
        if not self.ready:
            return
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if (self.probe_drag_enabled or alt) and self._probe_objects:
            delta = event.angleDelta().y()
            if delta:
                self.probe_rotated.emit(15 if delta > 0 else -15)
                return
        x, y = self._pixels(event.position())
        step = int(event.angleDelta().y() / 8)  # jeden „cvak“ kolečka = 15
        if step:
            self._view.StartZoomAtPoint(x, y)
            self._view.ZoomAtPoint(x, y, x + step, y + step)
