# P7.10 – ostrý 3D náhled na Macu

Datum: **1. 11. 2026**. Navazuje na zkoušku podsestav v P7.9.

## Příčina a oprava

Na autorově MacBooku M4 byl text Qt ostrý, ale geometrie i osový kříž se
zvětšovaly z velmi malého obrazu. Autor potvrdil, že problém vidí i přímo
na displeji. Zvětšení okna původní aplikace přes zelené tlačítko obraz ihned
zaostřilo. Model i počet komponent byly správné.

`Aspect_NeutralWindow` uchovává rozměry předané aplikací, zde logické body Qt.
Při show/resize může mít NSView ještě původní maličké bounds. Dosavadní
`_sync_size` si zapamatovalo finální Qt rozměr a při následujícím paintu už
`MustBeResized` nevolalo. OpenGL tak nedostalo příležitost zjistit, že se
mezitím ustálilo nativní okno.

Na macOS nyní synchronizace vždy zavolá `MustBeResized`, včetně stejného Qt
rozměru. Vlastní [OCCT OpenGl_Window::Resize](https://github.com/Open-Cascade-SAS/OCCT/blob/V8_0_0/src/Visualization/TKOpenGl/OpenGl/OpenGl_Window_1.mm)
ověří bounds a `convertSizeToBacking`, při změně aktualizuje NSOpenGLContext
a viewport, jinak skončí bez této práce. Dočasné vypnutí immediate update
zabrání dalšímu automatickému snímku uvnitř `MustBeResized`; původní příznak
se vrátí i při výjimce. Událost Qt `DevicePixelRatioChange` požádá o nový paint.

Nevlastnící předání NSView z P7.2 zůstává zachované. NeutralWindow nadále
uvádí logické rozměry pro projekci a výběr; souřadnice se slepě nenásobí
dvěma. Windows a Linux dál kontrolují změnu nativních rozměrů a používají
svůj DPR pro myš. Geometrie, formát dokumentů a přístup ke složkám se nemění.

## Regrese a skutečné vykreslování

`tests/test_viewer_surface.py` simuluje opožděné ustálení NSView při stejném
Qt rozměru. Na původním `_sync_size` z `main` test selhal: zůstal buffer
100 × 30 místo 1280 × 960. Další kontroly pokrývají Windows/Linux a změnu DPR.

Self-test hlavního okna, sestavy a životnosti nativních ploch nově čte skutečné
rozměry `OpenGl_Window.Width/Height` po otevření i změně velikosti. Očekává rozměry
plochy Qt krát DPR, s tolerancí jednoho pixelu. Kontrola probíhá před
`fit_all` nebo exportem obrazu, které by chybnou inicializaci mohly opravit
a zakrýt. Diagnostika `scale_info` vypisuje i toto fyzické rozlišení.
Dosavadní self-test modelování a rukojetí ověřuje skutečné Qt události
myši přes projekci OCCT, včetně výběru ploch a hran.

Na skutečné zabalené aplikaci se opakuje otevření `podsestavy-kopie.json`
z P7.9 přes systémový panel: 6 komponent, 4 díly, 13570,80 mm³, 106,53 g.
Porovnávají se nezměněné rozměry běžného okna a poté zvětšené/zmenšené
okno. Snímky jsou přímo z nativního okna, bez `viewer.dump` před pozorováním.
Místní artefakty jsou v `out/p7-retina-render/`; výsledky obou úplných
systémových sad a stažených balíčků jsou v implementačním PR.

Místní prostředí: Apple M4, macOS 27.2, Retina DPR 2, Qt 6.11.3,
OCCT 8.0.1, OpenGL Apple M4 / 2.1 Metal. Přesun mezi dvěma fyzickými
monitory s různým DPR zde není ručně ověřen; automaticky se ověřuje
obsluha události změny DPR. Nejde o dokončení autorské přejímky P7.4.
