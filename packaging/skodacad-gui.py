"""Vstupní bod sestavené aplikace (PyInstaller).

Když aplikace spadne už při startu (např. chybí knihovna v balíčku), zapíše
chybu do ~/SkodaCAD/skodacad.log. Při --self-test skončí s chybovým kódem
místo dialogu, který by na sestavovacím počítači čekal na kliknutí.
"""

import multiprocessing
import sys
import traceback
from pathlib import Path


def run() -> int:
    try:
        from skodacad.gui.app import main
    except Exception:
        report = "Chyba při startu ŠkodaCAD:\n" + traceback.format_exc()
        try:
            log = Path.home() / "SkodaCAD" / "skodacad.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(report)
        except OSError:
            pass
        if "--self-test" in sys.argv:
            position = sys.argv.index("--self-test") + 1
            if position < len(sys.argv):
                Path(sys.argv[position]).write_text(report + "VÝSLEDEK: CHYBA\n",
                                                    encoding="utf-8")
            raise SystemExit(1) from None
        raise
    return main()


if __name__ == "__main__":
    # Přepočet na pozadí spouští pomocný proces = znovu tento SkodaCAD.exe. freeze_support()
    # ho pozná a místo okna spustí jen výpočet – musí být úplně první, ještě před okny.
    multiprocessing.freeze_support()
    raise SystemExit(run())
