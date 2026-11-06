"""P7.48 – zkouška: dají se položit plovoucí karty nad nativní 3D pohled OCCT?

Spuštění z kořene repozitáře (Linux, cloud):
    xvfb-run -a -s "-screen 0 1440x900x24" .venv/bin/python \
        docs/p7-48-zkouska-karet-nad-3d.py out/zkouska-karet.png

Do dnešního hlavního okna s ukázkou deska.json položí nad 3D tři karty se zaoblenými
rohy (maska): A obyčejná neprůhledná, B nativní neprůhledná, C obyčejná s průhledností
60 %. Výsledek 6. 11. 2026 (Linux/Xvfb): A i B se kreslí nad dílem, C místo dílu
ukáže šedou plochu – nativní plocha OCCT se s poloprůhlednými widgety neskládá.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout

from skodacad.gui.main_window import MainWindow

WIDTH, HEIGHT, RADIUS = 230, 140, 12


def card(window, native, alpha, x, text):
    frame = QFrame(window.viewer)
    if native:
        frame.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
    frame.setStyleSheet(f"QFrame {{ background: rgba(247, 247, 249, {alpha});"
                        f" border-radius: {RADIUS}px; border: 1px solid rgba(0, 0, 0, .17) }}")
    QVBoxLayout(frame).addWidget(QLabel(text))
    frame.setGeometry(x, 14, WIDTH, HEIGHT)
    path = QPainterPath()
    path.addRoundedRect(0, 0, WIDTH, HEIGHT, RADIUS, RADIUS)
    frame.setMask(QRegion(path.toFillPolygon().toPolygon()))
    frame.show()
    frame.raise_()
    return frame


def main(out: Path) -> None:
    app = QApplication([])
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    window.open_model(Path("examples/deska.json"))
    cards = []

    def place():
        cards.append(card(window, False, 1.0, 14, "A: obyčejná\nneprůhledná"))
        cards.append(card(window, True, 1.0, 260, "B: nativní\nneprůhledná"))
        cards.append(card(window, False, 0.6, 506, "C: obyčejná\nprůhledná 60 %"))
        QTimer.singleShot(2500, shot)

    def shot():
        window.viewer.fit_all()
        app.processEvents()
        g = window.frameGeometry()
        window.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(str(out))
        app.quit()

    QTimer.singleShot(2500, place)
    app.exec()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
