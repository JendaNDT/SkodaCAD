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
    AIS_InteractiveContext,
    AIS_SelectionScheme_Replace,
    AIS_SelectionScheme_XOR,
    AIS_Shaded,
    AIS_Shape,
)
from OCP.Aspect import (
    Aspect_DisplayConnection,
    Aspect_GFM_VER,
    Aspect_TOL_SOLID,
    Aspect_TOTP_LEFT_LOWER,
)
from OCP.BRep import BRep_Builder
from OCP.GeomAbs import GeomAbs_C1
from OCP.Graphic3d import (
    Graphic3d_MaterialAspect,
    Graphic3d_NameOfMaterial_Plastified,
    Graphic3d_ZLayerId_Topmost,
)
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.Prs3d import (
    Prs3d_LineAspect,
    Prs3d_TypeOfHighlight_LocalDynamic,
    Prs3d_TypeOfHighlight_LocalSelected,
)
from OCP.Quantity import Quantity_Color, Quantity_NOC_BLACK, Quantity_TOC_RGB
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


def _rgb(r: float, g: float, b: float) -> Quantity_Color:
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


def _as_capsule(handle: int) -> Any:
    """Windows HWND jako PyCapsule – tak ho OCP předá do C++ jako ukazatel."""
    new_capsule = ctypes.pythonapi.PyCapsule_New
    new_capsule.restype = ctypes.py_object
    new_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    return new_capsule(handle, None, None)


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
        self.picked_point: tuple[float, float, float] | None = None  # kam mířil poslední klik
        self._pending: tuple[Any, bool] | None = None
        self._press: QPoint | None = None
        self._last: QPoint | None = None
        self._dragging = False
        self._known_size: tuple[int, int] | None = None

    # --- veřejné API ------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._view is not None

    def show_part(self, part: Any | None, fit: bool = False) -> None:
        """Zobrazí díl (build123d ``Part``) nebo nic; ``fit`` = přizpůsobit pohled."""
        if not self.ready:
            self._pending = (part, fit)
            return
        context = self._context
        if self._ais is not None:
            context.Remove(self._ais, False)
            self._ais = None
        self._remove_highlight()
        if part is not None:
            ais = AIS_Shape(part.wrapped)
            ais.SetMaterial(Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial_Plastified))
            ais.SetColor(_rgb(0.56, 0.62, 0.70))
            drawer = ais.Attributes()  # obrysy ploch až po barvě, jinak je SetColor přebarví
            drawer.SetFaceBoundaryDraw(True)
            drawer.SetFaceBoundaryAspect(
                Prs3d_LineAspect(_rgb(0.10, 0.10, 0.12), Aspect_TOL_SOLID, 1.2)
            )
            # Nekreslit hrany plošek vymodelovaného závitu (označené C2 v threads.py);
            # ostré i tečné hrany (zaoblení, G1/C1) zůstanou vidět.
            drawer.SetFaceBoundaryUpperContinuity(GeomAbs_C1)
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
            else:
                from OCP.Xw import Xw_Window

                window = Xw_Window(display, handle)

            stage = "opengl"
            driver = OpenGl_GraphicDriver(display, True)
            viewer = V3d_Viewer(driver)
            viewer.SetDefaultLights()
            viewer.SetLightOn()
            view = viewer.CreateView()
            view.SetWindow(window)
            if not window.IsMapped():
                window.Map()
            context = AIS_InteractiveContext(viewer)
        except Exception as exc:  # noqa: BLE001 – bez 3D má zbytek aplikace fungovat dál
            self._fail(stage, exc)
            return

        self._window, self._view, self._context = window, view, context
        self._style()
        self._sync_size()
        log.info("3D prohlížeč spuštěn")
        if self._pending is not None:
            part, fit = self._pending
            self._pending = None
            self.show_part(part, fit=fit)

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
        """Qt dává souřadnice v logických bodech, OCCT chce fyzické pixely (škálování 150 %…)."""
        ratio = self._surface.devicePixelRatioF()
        return int(pos.x() * ratio), int(pos.y() * ratio)

    def _mouse_press(self, event: QMouseEvent) -> None:
        if not self.ready:
            return
        self._surface.setFocus()
        self._press = self._last = event.position().toPoint()
        self._dragging = False
        if event.button() == Qt.MouseButton.LeftButton:
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
            if self._dragging and buttons & Qt.MouseButton.LeftButton:
                self._view.Rotation(x, y)
            elif self._dragging and buttons & (Qt.MouseButton.MiddleButton
                                               | Qt.MouseButton.RightButton):
                lx, ly = self._pixels(self._last)
                self._view.Pan(x - lx, ly - y)
        else:
            self._context.MoveTo(x, y, self._view, True)  # předvýběr pod kurzorem
        self._last = pos

    def _mouse_release(self, event: QMouseEvent) -> None:
        if not self.ready:
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
        x, y = self._pixels(event.position())
        step = int(event.angleDelta().y() / 8)  # jeden „cvak“ kolečka = 15
        if step:
            self._view.StartZoomAtPoint(x, y)
            self._view.ZoomAtPoint(x, y, x + step, y + step)
