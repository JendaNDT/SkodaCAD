# Závazný požadavek: podpora macOS (Apple Silicon)

**Rozhodnutí autora: 16. 10. 2026.** ŠkodaCAD má být nativní aplikace nejen pro Windows, ale také pro macOS. Cílové zařízení pro osobní zkoušení a prezentaci: **MacBook Air s čipem Apple M4 a 16 GB RAM**, tedy Apple Silicon (arm64). Dokument je zadáním pro Claude Code, **nikoli potvrzením, že macOS build už funguje**.

## Pořadí prací

1. **Dokončit právě rozpracovanou, ucelenou etapu NDT a stabilizovat ji** (testy, commit); nepřerušovat souběžnou práci bez domluvy.
2. **Hned poté provést audit kompatibility a vytvořit první spustitelnou macOS verzi**, nečekat na dokončení všech UT/PT/MT/RT modulů.
3. Po dosažení stabilního macOS sestavení průběžně testovat nové funkce na **Windows i macOS**; systémově specifické změny oddělit.
4. Dokud nejsou macOS závislosti, 3D prohlížeč, pozadí procesů a balíček vyzkoušené přímo na Apple Silicon, netvrdit, že je kompatibilita zajištěna.

## Technické požadavky

- Zachovat společné **Python/build123d/Open CASCADE výpočetní jádro**, JSON formát souborů a stejnou funkčnost NDT. Nepsat druhý samostatný CAD.
- Prověřit skutečnou dostupnost a funkčnost přesně požadovaných verzí knihoven **build123d / OCP, PySide6, slvs, PyInstaller** na macOS arm64 a kompatibilitu jejich binárních závislostí. Pokud je nutná změna verze, nejdříve předložit důvody a dopady ke schválení.
- Otestovat nativní **3D prohlížeč Open CASCADE** na macOS (vytvoření okna, OpenGL/kreslení, přepočty, výběr myší, Retina škálování, řez, barevná mapa). Windows-specifické zacházení s HWND není přenositelné a je nutné vytvořit odpovídající macOS větev.
- Prověřit cestu uživatelských dat/logů a nastavení API klíče pro macOS; neodvozovat ji z Windows adresářů.
- Ověřit **multiprocessing se spawn** a přenos geometrií mezi procesy jak při běhu ze zdrojů, tak v zabalené aplikaci, včetně zastavení dlouhého přepočtu.
- Připravit běžně spustitelnou **.app** aplikaci a vhodný distribuční archiv (např. ZIP nebo DMG); přidat **samostatnou GitHub Actions úlohu na macOS arm64**, bez rozbití stávajícího Windows workflow. Ověřit možnosti runneru a případná omezení buildů.
- Popsat omezení nepodepsané aplikace a Gatekeeperu; **notarizace/podepisování až při rozhodnutí o distribuci**. Neslibovat, že nepodepsaná .app bude bez varování fungovat na každém Macu.
- Žádné automatické zasílání firemních modelů ani NDT podkladů do externích služeb; funkce používající AI API musí být jasně označené a volitelné, obzvlášť pro pracovní prezentace.

## Podmínky dokončení první etapy macOS

- Uživatel stáhne balíček z GitHub Releases, na svém MacBooku Air M4 jej otevře a spustí **bez instalace Pythonu či vývojářských nástrojů** (s dokumentovaným postupem pro bezpečnostní upozornění).
- Na obou platformách lze otevřít stejný model, otočit jej ve 3D, vybrat plochu, upravit parametr, provést přepočet, měření a export.
- Funguje mapa tloušťky, řez a alespoň ukázka aktuálně hotové NDT funkce.
- Úspěšné automatické testy a explicitní ruční test na skutečném **Apple Silicon Macu**; výsledky a známá omezení zaznamenat.
- Žádná regrese Windows sestavení.

## Určení priorit

Pro prezentaci ve Škoda JS je cílem umožnit bezpečné předvedení fiktivního modelu na vlastním MacBooku bez instalace programu na firemní PC. Přinesení soukromého notebooku na pracoviště a jeho případné připojení k firemní infrastruktuře vždy podléhá interním pravidlům a svolení.

**Tento požadavek doplňuje plán v `03-implementacni-plan.md`; neoslabuje bezpečnostní a metodická omezení UT v `04-zavazne-vymezeni-ut.md`.**
