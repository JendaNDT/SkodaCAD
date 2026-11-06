# P7.48–P7.58 – plán přestavby hlavního okna podle návrhu „1a Plovoucí panely“

*Stav: autor 6. 11. 2026 schválil rozhodnutí R1–R7 slovy „schvaluji R1–R7“.
P7.48 ([evidence](p7-48-vzhled-a-ikony.md)), P7.49 ([evidence](p7-49-plovouci-karty.md))
a P7.50 ([evidence](p7-50-hlavni-lista-a-paleta.md)) jsou implementované (vydání A),
další kroky čekají.*

## Zadání autora

Autor 6. 11. 2026 dodal návrhový balíček *ŠkodaCAD – nové hlavní okno (směr 1a
„Plovoucí panely“)* a napsal: „Potřebuji, aby ten náš ŠkodaCAD vypadal přesně takto.
Půjde tomu přizpůsobit ovládání a vzhled?“ Na otázku navázal pokynem „vytvoř si plán
implementace“.

Referenční podklady jsou uložené v [`p7-48-navrh-okna/`](p7-48-navrh-okna/):

- [`README.md`](p7-48-navrh-okna/README.md) – původní popis návrhu: rozměry, barvy,
  chování a design tokeny. Je závazný pro rozměry a barvy.
- [`obrazovky/`](p7-48-navrh-okna/obrazovky/) – osm referenčních rámů 1440 × 900 px:
  2a/2b model (světlý/tmavý), 2c NDT průvodce, 2d skicář, 3a náhled prvku,
  3b měření, 3c řez a 3d NDT pokrytí.
- [`ikony-duo/`](p7-48-navrh-okna/ikony-duo/) – 41 ikon Duo (světlá varianta) bez
  vložených metadat. Tmavá varianta se liší jen barvou (#4a9eff) a průhledností
  výplně (0,30), proto se barví za běhu podle `QPalette.Link`.
- Rozsáhlé HTML plátno (`Hlavni-okno-1a-v2.dc.html`, 1,3 MB) a náčrty `deska*.svg` se
  do repozitáře neukládají. Obsah HTML odpovídá referenčním obrazovkám.

Jde jen o okno: **geometrie, výpočty, NDT ani formát souborů se nemění.**

## Shrnutí pro autora

- Ovládání půjde přizpůsobit celé. Vzhled půjde přizpůsobit celý **kromě průsvitnosti
  plovoucích karet** (rozmazaný 3D díl pod kartou, měkký stín). Viz zkoušku níže.
- Práce je rozdělená do **11 kroků (P7.48–P7.58)** a **4 vydání (A–D)**. Po každém
  vydání bude okno použitelné a ověřené na Windows i Macu. Nic se nerozbije napůl.
- Každý krok se porovná snímkem s referenční obrazovkou ve stejné velikosti
  1440 × 900 px.
- Rozhodnutí R1–R7 autor 6. 11. 2026 schválil; platí doporučení z tabulky.

## Zkouška: karty nad 3D pohledem (6. 11. 2026)

Zkouška ověřila, jak se karty chovají nad 3D pohledem
([skript](p7-48-zkouska-karet-nad-3d.py), [snímek](p7-48-navrh-okna/zkouska-karet-nad-3d.png)).
Do dnešního okna s `examples/deska.json` byly nad 3D pohled položeny tři karty:
obyčejná neprůhledná, nativní neprůhledná a obyčejná se 60% průhledností. Rohy byly
zaoblené maskou. Okno běželo v Linuxu (Xvfb, 1440 × 900).

| Zkouška | Výsledek |
|---|---|
| neprůhledná karta nad 3D | ✅ kreslí se nad dílem, 3D kolem ní se dál vykresluje |
| zaoblené rohy maskou (`setMask`) | ✅ fungují, okraj je trochu zubatý (bez vyhlazení) |
| průhledná karta | ❌ místo dílu je pod kartou šedá plocha |

**Příčina:** OCCT kreslí do samostatné nativní plochy (`_NativeSurface`,
`WA_NativeWindow` + `WA_PaintOnScreen`). Qt ji nemůže skládat s poloprůhlednými
widgety. Na Windows a macOS se čeká stejné chování (nativní HWND / NSView). Ověří to
až první krok na GitHubu, tvrzení zatím není doložené.

## Rozhodnutí k potvrzení (R1–R7)

| # | Otázka | Doporučení (výchozí) | Proč |
|---|---|---|---|
| R1 | Průsvitnost karet | **Neprůhledné karty** v barvě `--float` bez průhlednosti, zaoblené maskou, místo stínu linka `--sep2`. Průsvitnost až jako volitelný krok P7.58 | Přestavba vykreslování 3D (QOpenGLWidget) zasahuje do oprav P7.2/P7.10 pro Mac. Karty jsou v obou variantách tytéž, nic se nezahodí |
| R2 | Windows: řádek titulku 32 px s nabídkami a vlastními tlačítky okna | Nejdřív **systémový titulek** a nabídky v hlavní liště. Vlastní titulek bez rámu jako samostatný krok P7.57 se zkouškou přichycení oken (Snap), dvojkliku a více monitorů | Vlastní titulek ve Windows ruší přichycení oken, pokud se nedopíše nativní obsluha. Je to riziko, ale ne podmínka ostatních kroků |
| R3 | macOS: semafor v hlavní liště | `Qt.WindowType.NoTitleBarBackgroundHint`, případně `setUnifiedTitleAndToolBarOnMac`. Ověří se v P7.50 | PySide6 6.11.3 obě volby nabízí, chování na Macu ověří self-test na GitHubu a M4 |
| R4 | Oblíbené příkazy (P7.38) a rychlá lišta (Nový/Otevřít/Uložit) | Připnuté příkazy na **konec plovoucí palety** za oddělovač. Nový/Otevřít/Uložit jen v nabídce Soubor a zkratkách (jako v návrhu). Zpět/Znovu v liště | Návrh oblíbené nezobrazuje, ale funkci si autor sám vyžádal. Nesmí zmizet |
| R5 | Stavový řádek s nápovědou k myši | Zprávy (`statusBar().showMessage`) jdou do **stavové pilulky**. Nápověda k myši je v F1 / *Ovládání myší* (P7.46) a v bublině 3D pohledu | Návrh stavový řádek nemá. Nápověda už má svoje místo |
| R6 | Okno sestavy | V tomto plánu jen **společné barvy, písmo a ikony**. Rozložení sestavy podle stejného vzoru až samostatně (P7.59+) | Návrh pokrývá jen hlavní okno dílu. Sestava má vlastní ověřené chování P7.11–P7.36 |
| R7 | Zkrácené upozornění UT v průvodci (rám 2c) | **Plné znění `ndt.UT_DISCLAIMER` zůstane v kartě vždy viditelné** (12 px, `--fg2`). Odkaz „Celé upozornění“ otevře celé vymezení. Totéž platí pro PT/MT/RT | Závazné vymezení UT (16. 10. 2026) vyžaduje upozornění **doslovně v okně**. Zkrácení by porušilo pravidlo autora a `tests/test_ndt_scope.py` |

## Kroky a vydání

Každý krok má cílené testy, `ruff check src tests`, snímek pod Xvfb proti referenční
obrazovce a nový nebo upravený nativní self-test. Kroky jednoho vydání se sbírají
v jednom draftu PR. Úplná sada běží na GitHubu u hotové dávky (pravidlo 6).

### Vydání A – vzhled, kostra a lišta

**P7.48 – vzhled a ikony Duo**
- Nový `gui/ui_theme.py`: tokeny z README návrhu (světlý/tmavý), písmo
  (SF Pro Text / Segoe UI Variable Text, 13 px základ), jeden styl (QSS) pro karty,
  pole 22 px, tlačítka 24 px (primární `--btn`), segmentové přepínače a štítky stavu.
  `ui_colors.status_color` zůstane a doplní se o `warn`.
- Ikony Duo jako balíková data `gui/icons/duo/*.svg`, načtení přes `QSvgRenderer`
  s barvou `QPalette.Link` a průhledností výplně 0,24/0,30. `cad_icons.icon()` dostane
  stejné klíče a chybějící ikona spadne na dnešní kresbu. `skodacad.spec` ikony přibalí.
- Tmavý přechod 3D pozadí `#3b4049 → #16181c` (světlý zůstává podle `viewer.py`).
  Mění se jen barva pozadí, výběr a kreslení OCCT ne.
- Ověření: test kontrastu tokenů (≥ 4,5 : 1 pro text), test načtení všech 41 ikon
  v obou režimech, self-test „Vzhled a ikony“ v balíčku.

**P7.49 – plovoucí karty nad 3D (kostra)**
- `gui/floating.py`: `FloatingCard` (maska se zaoblením 12 px, odstup 14 px,
  ukotvení vlevo, vpravo, nahoře uprostřed, dole uprostřed a vpravo dole; přepočet při
  změně velikosti pohledu a DPR). Karty jsou sourozenci `_NativeSurface` uvnitř
  `OccViewer` a drží se nahoře (`raise_`).
- Dnešní `QDockWidget` nahradí karty. **Rozhraní `Workspace` se zachová:**
  `show_panel`, `close_panel`, `active`, `docks`, `actions`, F4, F9 a `panels_menu`.
  Desítky testů a self-test na něm stojí.
- Kliky a kolečko vedle karty musí jít do 3D, kliky na kartu ne. Výběr myší počítá
  s Retinou (`_mouse_ratio`).
- Ověření: nativní self-test „Karty nad 3D“ – skutečný klik na plochu vedle karty
  vybere plochu, klik na kartu nic nevybere, po změně velikosti okna (1440/1024/960)
  se karty nepřekrývají a 3D má nejméně 40 % šířky. Snímek na Windows a Macu.
  **Tady se potvrdí nebo vyvrátí neprůhlednost na obou systémech.**

**P7.50 – hlavní lišta a plovoucí paleta**
- Lišta 52 px: název dílu 13/700 a podtitulek („deska.json · ocel · upraveno“),
  segment činností 3D model | Skica | Výkres | Sestava | NDT | Zobrazení, Zpět/Znovu
  a pole „Najít příkaz…“ 220 × 26 (Ctrl+Shift+P / ⌘⇧P).
- Plovoucí paleta: stránky `Ribbon.add_page` bez popisků skupin, tlačítka 56 px
  (ikona 24 nad popiskem 11 px), oddělovače skupin. Dvojklik na segment a Ctrl/⌘+F1
  paletu sbalí. Stránka *Soubor* zmizí a její příkazy zůstanou v nabídce Soubor.
  `ribbon.command_groups` dál krmí hledání (P7.37) a přehled zkratek (P7.45).
- Oblíbené podle R4 a semafor na Macu podle R3.
- Ověření: self-test zkratek a konfliktů, test „každá akce palety jde stisknout“,
  snímek proti 2a/2b.

### Vydání B – karty dílu

**P7.51 – levá karta Prvky | Parametry | Díl**
- Segmentový přepínač nahradí sekce „Díl a materiál“, „Parametry dílu“, „Strom prvků“
  a „Vlastnosti dílu“. Filtr 24 px (Ctrl/⌘+F, P7.40) a filtr parametrů (P7.42).
- Řádky 26 px s ikonou 16 px. Vpravo ✓ nebo souhrn („M6 ×4“), vybraný řádek
  `--accentbg` a tučně. Patička + − ↑ ↓ a počet prvků. Sloupec *Tělesa* se přesune
  do bubliny a karty *Díl*.
- V činnosti NDT je pod prvky skupina „NDT studie“ se stavem (⚠ neúplná, ✓ platná).
- Pravidla Cocoa AX platí dál: řádky se znovu používají podle id, nikdy
  `tree.clear()`. Skrývání jde jen přes `setHidden`.

**P7.52 – pravá karta (inspektor) bez posouvání**
- Hlavička: malý titulek s ▾ (menu panelů), velký titulek 15/700, ×. Formulář jako
  mřížka (popisek vpravo), sbalitelné sekce s počtem, patička „Esc zahodí“,
  Zrušit/Potvrdit.
- Výška karty se řídí obsahem. Pravidlo „nikdy neposouvat“ zajistí automatické
  sbalení sekcí. Posuv je jen nouzová pojistka u velmi malého okna a self-test ji
  hlásí jako upozornění.
- Úprava prvku zachová tok P7.6: pracovní kopie, potvrzení jedním krokem Zpět, Esc.

**P7.53 – stavová pilulka a přepínač pohledů**
- Pilulka dole uprostřed (stav přepočtu ✓ Spočítáno, Přepočítávám…, chyba + kontext
  výběru). Přepínač Izo | Zepředu | Shora | Celý díl sdílí `view_actions` a zkratky.
- Zprávy stavového řádku přesměrovat podle R5. Stavový řádek Qt se skryje.

### Vydání C – nástroje a NDT

**P7.54 – karty Měření, Řez, Mapa tloušťky a náhled prvku**
- Rámy 3a (náhled: paleta neaktivní s průhledností 0,4, řádek „· náhled“ ve stromu
  s rámečkem #4782d1, pilulka „● Náhled“), 3b (měření: výsledky řádky, hlavní hodnota
  zvýrazněná, uložená měření jako sekce) a 3c (řez: rovina, poloha posuvník + mm,
  otočit, export, vzorek barvy plochy řezu).

**P7.55 – NDT průvodce (UT)**
- Rámy 2c a 3d: hlavička se štítkem stavu studie, upozornění podle R7 a kroky
  1 Kontrolovaná oblast → 2 Sonda → 3 Přiložení → 4 Geometrické pokrytí. Hotový krok
  se zobrazí jako jeden řádek s „Změnit“, aktivní krok jako vnořená karta, budoucí
  krok poloprůhledně. „Další“ je aktivní jen u splněného kroku.
- Krok se **odvozuje ze stavu studie**, neukládá se. Ovládání se jen přeskupí ze
  stávajícího `ndt_panel.py` a výpočty ani `ModelSession` se nemění. Návrh poloh
  a plán dráhy jsou v kroku 4 jako sbalené sekce.
- Pruh pokrytí (pokryto / nepokryto / nelze vyhodnotit) a věta „Geometrický podíl
  plochy, ne pravděpodobnost nálezu vady“.

**P7.56 – průvodce PT, MT, RT, audit a návrh úpravy**
- Stejný vzor kroků pro ostatní metody (oblast → nastavení → výpočet → mapa).
  Povinná upozornění zůstávají doslovně.

### Vydání D – skicář a dokončení

**P7.57 – skicář jako režim hlavního okna (rám 2d)**
- Obsah `SketcherDialog` se přesune do režimu okna: plátno místo 3D, paleta Skica
  (Výběr S, Úsečka L, Oblouk A, Kružnice R, Pomocná G | Kóta D, Promítnout U,
  Převzít W | Zrušit, Hotovo), levá karta s vazbami a pravá karta „Výběr“
  s doporučenou vazbou a pilulka „Zbývá určit: N rozměrů“.
- Hotovo = jeden krok Zpět (jako dnes), Esc ukončí řetěz a druhé Esc zruší výběr.
  Řešič `slvs` a `profile_edit.py` se nemění. Testy skicáře přejdou z dialogu na režim
  (`_exec_dialog` odpadne).
- Volitelně podle R2 vlastní titulek pro Windows.

**P7.58 – uložení stavu, srovnání a volitelná průsvitnost**
- `okno.json` verze 2: činnost, záložka levé karty, pravý panel nebo None, sbalení
  palety, sekce inspektoru a vzhled. Verze 1 se načte a převede, neznámé hodnoty se
  zahodí (jako dnes `clean_state`).
- Srovnávací snímky všech osmi rámů na deska.json vedle referencí, protokol
  `docs/p7-58-…`.
- **Jen po rozhodnutí R1 = „ano, zkusit“:** samostatná zkouška vykreslování OCCT
  do `QOpenGLWidget` (průsvitnost a stín karet) na Linuxu, Windows a M4. Po dobu
  zkoušky zůstává zachovaná dnešní nativní plocha jako výchozí.

## Co se nezmění

- Jádro, `ModelSession`, přepočet na pozadí, NDT výpočty a formát souborů (34).
- Pravidla okna: úpravy jen přes `ModelSession`, akce přes `MainWindow._action`,
  dialogy v testech nahrazené (`no_dialogs`), testy okna s `timeout`.
- Zkratky. Nové zkratky musí projít kontrolou konfliktů (P7.45) a v přehledu F1 budou
  aktuální.

## Rizika

| Riziko | Opatření |
|---|---|
| Karty nad nativním 3D se na Macu chovají jinak než v Linuxu | P7.49 má nativní self-test na obou systémech dřív, než se staví další karty |
| Pády Cocoa přístupnosti u nových widgetů | znovupoužívání řádků, žádné plošné mazání, self-test „Přístupnost macOS“ |
| Windows `offscreen` má jiné šířky písma (P7.12) | rozměry hlídá nativní self-test, ne offscreen testy |
| Desítky testů okna stojí na `ribbon`, `workspace`, `sidebar_sections` | zachovat rozhraní a měnit vnitřek, testy upravovat po krocích |
| `ndt_panel.py` (2 479 řádků) | průvodce jen přeskupuje stávající skupiny, výpočty se nemění |
| Délka testů na Windows (limit 35 min) | nové testy krátké, sdílené fixtures |

## Stav ověření

- [x] Zkouška karet nad 3D v Linuxu (Xvfb), viz výše.
- [x] Rozhodnutí R1–R7 schválena autorem 6. 11. 2026 („schvaluji R1–R7“), platí doporučení.
- [x] P7.48 vzhled a ikony Duo ([evidence](p7-48-vzhled-a-ikony.md)).
- [x] P7.49 plovoucí karty nad 3D ([evidence](p7-49-plovouci-karty.md)).
- [x] P7.50 hlavní lišta a plovoucí paleta ([evidence](p7-50-hlavni-lista-a-paleta.md)).
- [x] P7.51 levá karta Prvky | Parametry | Díl ([evidence](p7-51-leva-karta.md)).
- [x] P7.52 pravá karta bez posouvání ([evidence](p7-52-prava-karta.md)).
- [x] P7.53 stavová pilulka a přepínač pohledů ([evidence](p7-53-pilulka-a-pohledy.md)).
- [ ] P7.54–P7.58 dle kroků výše.
