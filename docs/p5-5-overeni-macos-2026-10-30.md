# P5.5 — místní technické ověření sestav na Macu

Datum: **30. 10. 2026**. Výchozí `main`: `5a57f79` (sloučené PR #68).
Ověření provedl agent na autorově MacBooku, nikoli autor jako konečné přijetí P5.
Windows ručně ani odborná validace NDT nebyly součástí tohoto průchodu.

## Prostředí a způsob zkoušky

- Apple M4, arm64, macOS 27.2 (26B123), Retina.
- Python 3.12.14, build123d 0.13.0, OCP 8.0.1.1.
  Výchozí PySide6/Qt 6.11.2; konečné ověření s **6.11.3**.
- Místně sestavený balíček PyInstallerem 6.22.3; skutečný OpenGL prohlížeč
  `Apple / Apple M4 / 2.1 Metal - 91.7`.
- Pro ovládání samostatná kopie balíčku s identifikátorem
  `io.github.jendandt.skodacad.p55qa` / `io.github.jendandt.skodacad.p55qt613`,
  testovací kopie dílů a samostatný profil.
  Změna identifikátoru slouží jen k rozlišení zkušebního procesu.
- FreeCAD **1.1.4**, vlastní OCCT **7.8.1**, stažený z oficiálního
  [vydání](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4).
  SHA-256 DMG: `071343b4abb70492b75c973f41eaf1d2528f9b9c7ea018d22a4f46ae14d27ac0`.
  Použit jen jako samostatný ověřovací nástroj, není závislostí ŠkodaCADu.

## Nalezené chyby a opravy

### Obnova stromu a přístupnost macOS

Před opravou opakovaně spadl místní `.app` po změně vzdálenosti víčka
a následném čtení přístupného obsahu okna. Hlášení macOS uvádějí `SIGSEGV`,
`EXC_BAD_ACCESS`, vrchol zásobníku v `libqcocoa.dylib`, následovaný
`NSAccessibilityAttributeAccessorInfo` a čtením hierarchie AX.
Čistě offscreen testy tento problém neodhalily.

Strom se nyní aktualizuje podle identit komponent a vazeb. Existující řádky,
výběr a rozbalení se zachovají; nové položky se přidají a zaniklé odeberou jednotlivě.
Obnova už nevolá `expandAll` na existujícím stromu. Buňky kusovníku a nálezů
se také aktualizují na místě. Nová regrese drží trvalý index vybrané vazby,
ověřuje změnu polohy, Zpět, odstranění jiné vazby a zachování sbalené skupiny.

Po opravě ve skutečném okně prošly opakované změny mezery na 15 a 20 mm,
výběr víčka, Zpět/Znovu a návrat do výchozí polohy bez pádu.

Zamčená verze PySide6 se zároveň zvyšuje na **6.11.3** (včetně odpovídajícího
Shibokenu). Ve zkušebním balíčku s 6.11.2 padalo i zadání názvu v dialogu Qt;
tentýž vstup s 6.11.3 prošel. Aktualizace Qt a zachování položek při obnově byly
ověřovány odděleně i společně. Formát modelu ani geometrické algoritmy se nemění.

### Výběr souborů v okně sestavy

Při místním ovládání přes přístupnost ponechávaly nativní panely pro samostatné
filtry JSON/CSV potvrzení zakázané i pro platné soubory a názvy. Běžný ruční
průchod bez přístupnostního klienta tímto nebyl nezávisle potvrzen.
Okno sestavy na macOS používá dialogy Qt se stejnými filtry pro otevření,
uložení, vložení/přesměrování komponenty, kusovník a STEP. Na Windows zůstává
výchozí systémový dialog. Nezavádí se další knihovna; mění se opravná verze PySide6.

## Skutečně provedené zkoušky

| Zkouška | Výsledek |
|---|---|
| Otevření krabičky s víčkem v samostatném skutečném okně | 6 komponent, 7 splněných vazeb, víčko plně určené |
| Mezery 15 / 20 mm zadané ve formuláři vazby | poloha Z víčka 47 / 52 mm |
| Tlačítka Zpět / Znovu | Z 52 → 47 → 52; následně návrat na 32 mm |
| Uložení pracovní kopie | zmizel příznak neuložené změny |
| Kolize krabičky s víčkem z okna na pozadí | 15 dvojic, 5 dotyků, žádná kolize ani nejistý nález |
| Kusovník v okně | 3 řádky, 6 kusů, 39,76 g; nožička 4× |
| CSV z dialogu okna | soubor vznikl, stavový řádek potvrdil uložení |
| Otevření JSON zadáním názvu v dialogu Qt 6.11.3 | deska se šroubem otevřena, 2 splněné vazby |
| Přijatá kolize šroubu z okna | 12,959 mm³; zrušení přijetí zobrazí kolizi, Zpět vrátí přijetí |
| Export STEP z nabídky Soubor | vznikl `deska_se_sroubem.step`, stavový řádek potvrdil export |
| Uložení a otevření z kopie složky jinde na disku | úplná sestava, Z víčka 47 mm, stejný objem |
| Zdrojové díly po změnách sestavy | bajt po bajtu beze změny |
| Chybějící nožička | neúplná sestava, STEP i CSV odmítnuty; po vrácení souboru úplná |
| Cílené testy sestav a dokumentu s konečnou opravou / Qt 6.11.3 | **147 prošlo**, 16,36 s |
| Self-test konečného místního `.app` s Qt 6.11.3 | **VÝSLEDEK: OK**, kód 0; 3D, NDT, vazby, kusovník, STEP i pomocný proces |
| Ověření podpisu místně sestaveného balíčku | `codesign --verify --deep` prošlo |
| Ruff a kontrola diffu | bez chyb |

Změny poloh a přenos složky byly navíc ověřeny přes `AssemblySession` s kontrolou
čísel a původních bajtů dílů. Nenahrazují zkoušku jednotlivých nativních dialogů.

## Nezávislý přenos STEP přes FreeCAD

Přenos běžel přes skutečný FreeCAD v konzolovém režimu, nikoli přes čtečku ŠkodaCADu.
Pro každou sestavu se zkontrolovala validita, počet solidů, součet objemů,
přesná obálka a poloha i objem každé jednotlivé kopie. Tolerance:
objem relativně `1e-6` (absolutní minimum `1e-5 mm³`), souřadnice `1e-4 mm`.

| Sestava | Solidů | Objem FreeCAD [mm³] | Přesná obálka [mm] |
|---|---:|---:|---|
| Krabička s víčkem a vazbami | 6 | 31 309,287393459 | (−40, −25, −3) až (40, 25, 32) |
| Deska se šroubem M3 | 2 | 7 305,471830501 | (−20, −15, −4) až (20, 15, 9) |

Obě sestavy FreeCAD znovu vyexportoval do STEP. Následná kontrola přes build123d/OCP
8.0.1.1 potvrdila stejný počet solidů, platnost a objemy. Importní funkce ŠkodaCADu
pro jeden díl nadále správně odmítá sestavu; nepřidává se tím podpora importu sestav.

FreeCAD zachoval skupinu sestavy a všechny geometrické kopie, ale ve výchozím
importu používá vlastní popisky výrobků/kopií (`nozicka`, `nozicka001` …);
u šroubu byl popisek generátoru OCCT. Shodu názvů komponent mezi CADy proto tento
protokol neprohlašuje. Geometrické polohy a jednotky souhlasí.

## Evidence a zbývající přejímka

Místní evidence je v ignorované složce `out/p5-5-macos-2026-10-30/`:
`pytest-p55.xml`, protokoly sestavení, `session-transfer-result.json`,
`exports/expected.json`, `exports/freecad-result.json`, `exports/freecad-roundtrip.json`,
`pytest-final.xml`, `self-test-final.txt`, STEP, CSV a dokumenty FreeCADu.
Zkušební data nejsou uživatelské modely.

Tento průchod **není přijetím celé P5 autorem**. Zbývá ruční průchod Windows,
ověření CSV v Excelu, přijetí autorem a sledování známých omezení P5.4
(místní vůle u dotýkajících se dvojic, výkon velkých sestav, NDT mezi díly).
Úplné testy a kontrolu balíčků obou systémů zajišťují workflow navazujícího PR.
