# P7.2 – nativní prototyp hlavního okna

Datum: **31. 10. 2026**. Navazuje na [audit P7.1](p7-1-audit-a-navrh-prostredi.md)
a autorův pokyn „ok, udělej to“ k variantě **Strom a pravý editor**. Směr vzhledu:
strojní CAD ve stylu Solid Edge / Inventor. Jde o funkční Qt/OCCT aplikaci;
autorská přejímka ergonomie P7.4 zůstává otevřená.

## Chování

- Pás činností **Soubor, 3D model, Skica, Výkres, Sestava, NDT, Zobrazení**.
  Tlačítka používají stejné `QAction` jako nabídky a klávesové zkratky, včetně
  zakázání a zaškrtnutí. Úplná nabídka prvků zůstává pod *Další prvky*.
  Ikony jsou vlastní kresby Qt, ve více velikostech a hustotách pixelů.
- Vlevo strom s odděleným sloupcem **Tělesa** (např. `1 → 2`). Úplný popis
  operace a hlášení jsou v bublině; dlouhý název počet těles neodsunuje.
  Řádky se stále obnovují podle id, bez resetování modelu Qt (ochrana Cocoa AX).
  Díl/materiál, parametry a vlastnosti mají rozbalovací skupiny.
- Vpravo je jeden panel po celé dostupné výšce. Výběr v jeho hlavičce a
  **Zobrazení → Panely** zpřístupňuje editor, měření, mapu tloušťky, řez, NDT,
  audit, konstrukční návrhy a asistenta. Zavření panel nesmaže ani nevytvoří znovu.
- **F4** zavře/obnoví editor, **F9** strom. **Ctrl+F1** (na Macu Cmd+F1)
  sbalí pás; kliknutí na jeho záložku jej rozbalí. Na některých klávesnicích
  se pro funkční klávesy používá i Fn.
- **Zobrazení → Obnovit rozložení** vrátí editor, šířky 250/350 bodů,
  záložku 3D model a rozbalené parametry. Při šířce pod 1180 bodů skryje strom;
  lze jej znovu otevřít F9. Okno má minimum 960 × 600 bodů.
- Vodítka: volba A–D a rukojeti 1/2, pod nimi plná pole X a Y. Všech 16
  hodnot existuje současně; přepnutí hodnoty nepřepisuje. Volba přežije Zpět,
  Znovu a přijaté tažení. Krok a směr tažení se chovají stejně jako v P6.
- Platné pole se potvrzuje Enterem nebo ztrátou fokusu jako dosud. Přepnutí
  panelu tedy může potvrdit rozepsanou platnou hodnotu. Neplatný výraz zůstane
  ve formuláři a nemění recept. Zavření panelu není zrušení změny modelu.
- **Zobrazení → Vzhled**: systém, světlý, tmavý. Pomocné texty editoru a stavy
  stromu reagují na paletu; původní `#555` v pomocných textech NDT nahrazuje
  barva palety. Nejde o kompletní přepracování všech barevných legend NDT.

Skicář i sestava nadále otevírají vlastní skutečná okna. Výkres používá dosavadní
měření/kóty, náhled listu a export; NDT nepřidává nové výpočty. Panely jsou v této
verzi na pevných stranách, lze je zavřít a měnit jejich šířku, nelze je odtrhnout.

## Nastavení a bezpečnost modelu

`~/SkodaCAD/okno.json` (nebo pod `SKODACAD_HOME`) ukládá polohu a rozměry,
maximalizaci, viditelnost stromu, poslední panel, šířky, záložku pásu, jeho sbalení,
vzhled a skupiny vlevo. Uložení při skutečně přijatém zavření je atomické.
Zrušené zavření soubor nepřepíše. Čtení je omezené na 16 KiB, neznámá verze,
poškozený JSON a chybné typy bezpečně přejdou na výchozí/platné hodnoty.
Poloha se omezí na aktuálně připojené obrazovky včetně záporných souřadnic.

Soubor neobsahuje model ani historii. Nezměněné formuláře, přepínání panelů,
pásu a obnova rozložení nesmí změnit dokument, historii ani natočení pohledu.
Geometrické úpravy dál procházejí přes `ModelSession`. Formát dílu zůstává **34**;
žádná nová závislost.

## Místní důkazy

Skutečné Qt/Cocoa + OCCT, MacBook M4; rozměry **klientské oblasti v logických
bodech** (odlišná konvence od historické tabulky rámů v P7.1):

| Okno | 3D plocha | Pravý editor | Pole X/Y | Strom |
|---|---|---|---|---|
| 1400 × 800 | 798 × 649 | 350 × 649 | 255 / 255 | viditelný |
| 1280 × 760 | 678 × 609 | 350 × 609 | 255 / 255 | viditelný |
| 1024 × 720 | 673 × 569 | 350 × 569 | 255 / 255 | skrytý, F9 |

Místní měření a celé snímky: `out/p7-native-workspace/native-metrics.json`,
`native-1400.png`, `native-1280.png`, `native-1024.png`. Obrazovka má Retina 2×.
Zápis výrazem `4*Bx/3+1` do X první rukojeti A dává **78009 mm³**, Zpět
**77760 mm³**, Znovu **78009 mm³**. Test neporovnává jen text formuláře.

`tests/test_gui.py` ověřuje sdílené příkazy, změny geometrie a historii,
viditelnost právě jednoho panelu, kompaktní reset bez změny modelu/kamery,
zachování neplatného vstupu, potvrzení při ztrátě fokusu, volbu vodítka/rukojeti,
obnovu profilu, zrušené zavření a vodorovné přetečení pásu.
`tests/test_window_state.py` ověřuje poškozený/velký profil, typy, atomické selhání,
odpojený monitor, záporné souřadnice a kontrast textů světlé/tmavé palety.
Dosavadní fyzikální případy počtu těles mají navíc kontrolu odděleného sloupce.

Self-test aplikace byl rozšířen o **„✓ Prostředí CAD“**: skutečné widgety všech
osmi rukojetí, osm panelů, Enter, objemy a historii, kompaktní okno, obnovení
panelu a zápis profilu. Zachovává i dosavadní tažení přes Qt události a OCCT
projekci. Místní zdrojový self-test skončil `VÝSLEDEK: OK`. Cílená sada GUI, schémat,
vodítek, sestav, výkresu, STEP a NDT editorů: **290 testů prošlo**; samostatná
kontrola potvrzení při ztrátě fokusu, profilu a přetečení: **3 testy prošly**.
`ruff check src tests` a `git diff --check` prošly.

Úplná sada musí před sloučením projít na Windows i macOS, včetně self-testů
obou stažených balíčků a STEP přenosu. Konkrétní výsledky a odkazy obsahuje
implementační PR. P7.4 (práce autora na vlastním dílu, pocit z hustoty a ovládání),
širší matice trackpadu/Retiny a odborná validace NDT se tím neprohlašují za hotové.
