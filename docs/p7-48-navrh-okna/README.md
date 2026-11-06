# Handoff: ŠkodaCAD – nové hlavní okno (směr 1a „Plovoucí panely“)

## Overview
Redesign hlavního okna dílu v ŠkodaCAD (PySide6 / Qt, OCCT viewer). Cíle: víc místa pro 3D, pravý panel bez dlouhého scrollování a srozumitelný postup NDT studie. 3D pohled zabírá celé okno pod lištou, ovládání leží v plovoucích kartách nad ním. Platí pro macOS i Windows a pro světlý i tmavý režim.

## About the Design Files
Soubory v této složce jsou **návrhové reference v HTML**. Ukazují zamýšlený vzhled a chování, nejsou to produkční kód. Úkolem je **znovu vytvořit tyto návrhy v existující aplikaci** (`src/skodacad/gui/`, PySide6) jejími postupy: QMainWindow, QDockWidget/overlay widgety, QAction, `cad_icons.icon()`, `ui_colors`, `workspace.Workspace`. HTML se do aplikace nepřenáší.

`Hlavni-okno-1a-v2.dc.html` otevři v prohlížeči (vedle musí být `support.js` a SVG). Je to plátno s rámy 1440×900. Ovládání Tweaks (Platforma: macOS/Windows, Vzhled: Světlý/Tmavý) funguje jen v návrhovém nástroji. V prohlížeči se zobrazí výchozí stav: macOS, světlý.

## Fidelity
**High-fidelity** co do rozložení, rozměrů, barev, typografie a textů. Výjimky:
- 3D díl je schematický SVG náčrt. Ve skutečnosti ho kreslí OCCT viewer (`viewer.py`) se stávajícími barvami.
- Ikony: nová sada **Duo** (viz Assets), použitá ve všech rámech.
- Číselné výsledky v NDT (β 45°, pokrytí 81/15/4 %) a v řezu (≈ 1 500 mm²) jsou ilustrační. Rozteč 40,00 mm a nejkratší vzdálenost 33,20 mm odpovídají `examples/deska.json`.

## Screens / Views
Všechny rámy mají stejnou kostru:

**Kostra okna (1440×900)**
- *Windows:* řádek titulku 32 px (`--tb`) s ikonou aplikace 16×16 (r 4, `--btn`, bílé „Š“). Následují nabídky **Soubor, Úpravy, Model, NDT, Zobrazení, Nápověda** (12 px, padding 4×9, r 4) a vpravo ovládání okna, 3× 46×32 px.
- *macOS:* nabídky jsou v systémové liště a semafor (12 px kruhy, mezera 8 px, #ff5f57 / #febc2e / #28c840) je v hlavní liště.
- **Hlavní lišta, 52 px**, `--tb`, spodní linka 0.5 px `--sep2`, padding 0 16 0 20, mezera 18:
  1. Název dílu 13/700 + podtitulek 11 px `--fg3` („deska.json · ocel · upraveno“).
  2. Uprostřed segmentový přepínač činností: 3D model | Skica | Výkres | Sestava | NDT | Zobrazení. Podklad `--sep`, r 7, padding 2. Položka padding 3×12. Aktivní položka: `--ctl`, r 5, stín 0 1 2 rgba(0,0,0,.15), weight 500. Nahrazuje záložky `Ribbon.tabs`. Soubor je v nabídce.
  3. Vpravo Zpět ↶ a Znovu ↷ (17 px) a pole „Najít příkaz…“ (220×26, r 7, `--sep`, zkratka 11 px: ⌘⇧P / Ctrl+Shift+P).
- **3D pohled** vyplní zbytek. Pozadí: lineární gradient shora dolů `--vp1` → `--vp2`.
- **Plovoucí karty** mají společný styl: `--float`, backdrop blur 24 px + saturate 1.6, r 12, stín 0 0 0 .5px `--sep2` a 0 8 28 rgba(0,0,0,.16). Odstup od okrajů pohledu je 14 px.

**Plovoucí paleta příkazů** (nahoře, vodorovně uprostřed)
- Padding 6×8, položky 56 px široké, ikona 24 px nad popiskem 11 px, oddělovač skupin 0.5 px `--sep2` s odsazením 6 px.
- 3D model: Skica, Vysunout, Rotovat, Tažení, Přechod ▾ | Díra, Zaoblit, Srazit, Skořepina | Pole, Zrcadlit (skupiny podle `main_window.py` `ribbon.add_page("model"…)`).
- NDT: UT (aktivní: `--accentbg`, r 8), PT, MT, RT | Nová studie, NDT audit, Návrh úpravy.
- Skica: Výběr S, Úsečka L, Oblouk A, Kružnice R, Pomocná G | Kóta D, Promítnout U, Převzít W (fialově #8e44ad) | Zrušit, Hotovo (primární). Pod popiskem je klávesa 10 px `--fg3`.

**Levá karta** (top 14, left 14, bottom 60, šířka 268)
- Segment Prvky | Parametry | Díl (sloučí dnešní Section „Díl a materiál“, „Parametry dílu“, „Strom prvků“ a „Vlastnosti dílu“).
- Pod ním filtr 24 px, r 6, `--sep`, „Filtr prvků“ + ⌘F / Ctrl+F.
- Řádky stromu 26 px, padding 0 8, r 6, ikona 16 px (`cad_icons`, stroke 1.8). Vpravo stav ✓ (`--ok`) nebo souhrn 11 px `--fg3` („M6 ×4“). Vybraný řádek má podklad `--accentbg` a weight 600.
- Patička s linkou nahoře: + − ↑ ↓ a vpravo „6 prvků“.
- V NDT je pod prvky skupina „NDT studie“ (nadpis 11/600 `--fg3`, +). Stav studie je vpravo: ⚠ neúplná `--warn`, ✓ platná `--ok`.

**Pravá karta – inspektor** (top 14, right 14, šířka 304, NDT 320, výška podle obsahu)
- Hlavička: malý titulek 11 px `--fg3` s ▾ (menu panelů = `workspace.panels_menu`), velký titulek 15/700, vpravo × (zavřít panel).
- Formulář: mřížka popisek (vpravo zarovnaný, `--fg2`) / pole. Mezery 8×10, padding 4 14 12.
- Pole: 22 px, r 5, `--ctl`, stín 0 0 0 .5px `--sep2`. Fokus: 0 0 0 3px `--accentbg` + 0 0 0 .5px `--accent`.
- Sbalitelné sekce: řádek s ▶/▼ (10 px), titulkem 600 a počtem vpravo, oddělené linkou 0.5 px `--sep`.
- Patička: „Esc zahodí“ 12 px `--fg3`, Zrušit (sekundární), Potvrdit (primární). Tlačítka 24 px, r 6, padding 0 12–14. Primární: `--btn`, bílý text, 500.
- **Pravidlo:** karta nikdy nescrolluje. Delší obsah se sbalí do sekcí, víc kroků do průvodce.

**Stavová pilulka** (dole uprostřed, 32 px, r 16, 12 px): stav (✓ Spočítáno `--ok` 600) | oddělovač | kontext výběru `--fg2`.
**Přepínač pohledů** (dole vpravo, r 9, padding 3): Izo (aktivní `--accentbg` + `--accent` 600), Zepředu, Shora, Celý díl.

### 2a / 2b – Model (světlý / tmavý)
Inspektor „Úprava prvku · Upínání“: Druh (Válcové zahloubení), Velikost (M6), Na ploše (Horní plocha), ☑ Řez skrz celý díl. Sekce „Polohy děr · 4“ (výrazy v ui-monospace 12 px) a „Vlastní průměr“ (sbalená). Patička Zrušit / Potvrdit.

### 2c – NDT průvodce
Hlavička „NDT studie ▾ / UT horní plocha“ a štítek stavu (⚠ neúplná: `--warnbg`/`--warn`, 11/600, r 5). Pod ní zkrácené upozornění (12 px) s odkazem „Celé upozornění“, který otevře úplný povinný text z `docs/ndt/04-zavazne-vymezeni-ut.md`.

Kroky:
1. Kontrolovaná oblast
2. Sonda
3. Přiložení sondy
4. Geometrické pokrytí

Hotový krok je řádek: zelený kruh 20 px s ✓, titulek 600, shrnutí 12 px a odkaz „Změnit“. Aktivní krok je vnořená karta (`--ctl`, r 10) s číslem v kruhu `--btn` a obsahem odsazeným o 30 px: návod, Směr paprsku [°] s ◀ ▶, Krok [mm], Délka čáry [mm], stav přiložení (box `--okbg`/`--ok`), Projet čáru, Odebrat sondu. Budoucí krok má opacity .55. Patička: „Krok 3 ze 4“, Zpět, „Další: pokrytí“.

### 2d – Skicář
Režim hlavního okna místo samostatného dialogu (`sketcher.py`).
- Plátno: `--skbg` s mřížkou 40 px (`--skgrid`).
- Barvy podle `sketcher.py`: obrys neurčený #1f5fbf (tmavý režim #6aa5ff), výběr #ff8c00 (3 px), pomocná čára #8a8a8a čerchovaně, kóty a text #666, počátek #2e7d32, promítnutá hrana #8e44ad.
- Ikony vazeb jsou malé štítky 20×16 u prvků.
- Levá karta: strom (upravovaná skica zvýrazněná, ostatní opacity .5) a seznam „Vazby skici“.
- Pravá karta „Výběr“: mřížka 2×N tlačítek vazeb, které pro výběr dávají smysl. Doporučená vazba je primární, ostatní jsou ve sbalené sekci. Dole je „Kóta… D“.
- Pilulka: „Zbývá určit: N rozměrů“ (barva `--skfree`), nebo „✓ plně určeno“.

### 3a – Náhled nového prvku
Odpovídá `feature_preview.py`.
- Hlavička karty „Nový prvek · náhled / Sražení“, Vzdálenost [mm] (fokus), Hrany + „Změnit výběrem ve 3D“, informační box `--accentbg`.
- Ve stromu je navíc řádek s rámečkem 1 px #4782d1 a kurzívou „Sražení · náhled“.
- Paleta má opacity .4 a je neaktivní. Hrany náhledu svítí ve 3D #4782d1, což je ghost (0.28, 0.51, 0.82) z `viewer.py`.
- Pilulka „● Náhled · Sražení | Potvrzení přidá jeden krok Zpět“.

### 3b – Měření
- Karta „Měření“: „Vybráno: 2 díry · Závity M8“.
- Výsledky jsou řádky (padding 6×10, r 6). Hlavní hodnota je zvýrazněná `--okbg` a `--ok` 700: Rozteč os 40,00 mm, Nejkratší vzdálenost 33,20 mm, Osy rovnoběžné.
- Tlačítka Uložit do modelu (primární), Přejmenovat…, Smazat (neaktivní, opacity .45).
- Sbalitelné sekce „Uložená měření“ (⌘⇧M / Ctrl+Shift+M) a „Příprava kót výkresu“.
- Ve 3D je zelená čára #1b7f3b se štítkem hodnoty.

### 3c – Řez
- Karta „Řez“: Rovina (Kolmo na Y), Poloha (posuvník + pole mm, rozsah −40 až 40 mm), Otočit stranu, Export DXF/SVG….
- Řádek „Plocha řezu“ se vzorkem barvy #d16154, což je (0.82, 0.38, 0.33) z `viewer.py`. Pod ním poznámka, že řez je jen pohled.

### 3d – NDT krok 4
- Kroky 1–3 sbalené, krok 4 rozbalený: Zdroj poloh (Po ploše přiložení), Krok [mm], ☑ Ověřit citlivost na krok.
- Výsledek: pruh 8 px (pokryto #4caf6e, nepokryto #d9534f, nelze vyhodnotit #e6c229), legenda a stav citlivosti. Pod tím poznámka „Geometrický podíl plochy, ne pravděpodobnost nálezu vady.“
- Tlačítka Export CSV…, Skrýt mapu. Patička „Krok 4 ze 4“, Zpět, Hotovo.

## Interactions & Behavior
- Činnosti (segment) přepínají obsah plovoucí palety, tedy dnešní `Ribbon.add_page`. Dvojklik na segment paletu sbalí (Ctrl/⌘+F1, jako dnes).
- Pravou kartu volíš z menu v jejím titulku (▾) nebo přes Zobrazení → Panely. Klávesy zůstávají: F4 editor, F9 levá karta. Zavření × je stejné jako `Workspace.close_panel()`.
- Náhled prvku: během náhledu je paleta neaktivní, pohled zůstává ovladatelný. Esc = Zrušit. Potvrdit je jeden krok Zpět. Uložení a export čekají.
- NDT průvodce: „Další“ je aktivní jen při splněném kroku. Kliknutí na „Změnit“ rozbalí hotový krok a sbalí aktuální. Stav studie (platná, zastaralá, neúplná, neplatná vazba) se zobrazuje ve štítku hlavičky i ve stromu.
- Skicář: Hotovo uloží obrys jako jeden krok Zpět a vrátí paletu modelu. Esc ukončí řetěz čar, druhé Esc zruší výběr.
- Barvy stavů používej přes `ui_colors.status_color()` (světlé a tmavé hodnoty jsou níže).

## State Management
Do `~/SkodaCAD/okno.json` (`window_state.py`) uložit:
- aktivní činnost
- aktivní záložku levé karty (Prvky / Parametry / Díl)
- pravý panel (nebo None)
- sbalení palety
- stav rozbalení sekcí v inspektoru
- vzhled

Krok NDT průvodce se odvozuje ze stavu studie, neukládá se.

## Design Tokens
| Token | Světlý | Tmavý |
|---|---|---|
| --win (okno) | #ececec | #1f1f21 |
| --tb (lišta) | #f6f6f6 | #2a2a2c |
| --float (karty) | rgba(247,247,249,.88) | rgba(42,42,45,.86) |
| --fg | #1d1d1f | #f2f2f4 |
| --fg2 | #56565b | #b4b4ba |
| --fg3 | #86868b | #8c8c92 |
| --sep | rgba(0,0,0,.09) | rgba(255,255,255,.08) |
| --sep2 | rgba(0,0,0,.17) | rgba(255,255,255,.17) |
| --ctl (pole) | #ffffff | #3a3a3d |
| --accent (ikony, odkazy) | #0a64d8 | #4a9eff |
| --accentbg | rgba(10,100,216,.13) | rgba(74,158,255,.2) |
| --btn (primární tlačítko) | #0a64d8 | #0a6ad8 |
| --vp1 → --vp2 (3D gradient) | #f2f5fa → #b8c4d6 (= viewer.py) | #3b4049 → #16181c |
| --ok / --okbg | #166534 / rgba(22,101,52,.1) | #9bdab5 / rgba(155,218,181,.14) |
| --warn / --warnbg | #8a5a0b / rgba(185,119,14,.13) | #e8b45c / rgba(232,180,92,.16) |
| --err | #b42318 | #ffb0a6 |
| skicář bg / mřížka / neurčeno / text | #fbfbfb / #ececec / #1f5fbf / #666666 | #1c1d20 / rgba(255,255,255,.05) / #6aa5ff / #a8a8ae |

- **Písmo:** macOS -apple-system / SF Pro Text; Windows Segoe UI Variable Text / Segoe UI. Velikosti: 11 (popisky, metadata), 12 (sekundární), 13 (základ), 15/700 (titulek karty), 17 (ikony ↶ ↷).
- **Radiusy:** 4–5 (pole, štítky), 6 (tlačítka, řádky), 7 (segment, hledání), 9–10 (přepínač pohledů, vnořené karty), 12 (plovoucí karty a okno na macOS; na Windows okno 8), 16 (pilulka).
- **Mezery:** 2, 4, 6, 8, 10, 12, 14, 18 px. Odstup karet od okraje 14 px.

## Assets
- **Ikony Duo** (`icons/duo/*.svg` pro světlý, `icons/duo-tmavy/*.svg` pro tmavý režim; přehled v `Ikony.dc.html`, varianta 4b). 41 ikon, mřížka 24×24, živá plocha 2–22, čára 1.5 px, round cap/join. Obrys v barvě `QPalette.Link` (#0a64d8 / #4a9eff); vybrané plochy mají výplň stejnou barvou s průhledností 0.24 (světlý) / 0.30 (tmavý). Plné body (kapky spreje, střed znaku radiace) mají plnou výplň.
- Implementace v Qt: buď načítat SVG přes `QSvgRenderer` a před načtením nahradit hex barvu aktuální `QPalette.Link`, nebo kresbu přepsat do `cad_icons._draw()` (QPainterPath + `QBrush` s alfou pro výplň). Klíče souborů odpovídají příkazům: sketch, extrude, revolve, sweep, loft, hole, fillet, chamfer, shell, pattern, mirror, edit, params, measure, section, thickness, ut, pt, mt, rt, study, audit, design, select, line, arc, circle, construction, dimension, project, convert, iso, front, top, fit, new, open, save, undo, redo, search.
- Promítnout a Převzít ve skicáři kreslit fialově #8e44ad (barva promítnuté hrany ze `sketcher.py`), Pomocnou čáru `--fg3`.
- `deska*.svg`: schematické náčrty dílu z `examples/deska.json`, jen pro návrh.

## Files
- `Ikony.dc.html`: přehled ikon (4a Linka, 4b Duo – zvolena 4b), srovnání s dnešní sadou.
- `Hlavni-okno-1a-v2.dc.html`: všechny rámy (3a–3d nahoře, 2a–2d pod nimi). Vyžaduje `support.js`.
- `screenshots/`: PNG 1440×900 všech osmi rámů, macOS, světlý režim (2b tmavý), s ikonami Duo.
- `deska.svg`, `deska-sonda.svg`, `deska-nahled.svg`, `deska-mereni.svg`, `deska-rez.svg`, `deska-pokryti.svg`.
