# ŠkodaCAD – pravidla projektu pro AI

## Uživatel a účel

- Osobní parametrický 3D CAD **jen pro autora**, nebude se distribuovat. Licence knihoven proto
  nejsou omezením (GPL knihovny jako řešič SolveSpace jsou v pořádku).
- Autor **neprogramuje**, projekt vzniká vibecodingem. Komunikuj česky, jednoduše a bez žargonu:
  co se změnilo, proč, a jak si to může ověřit (náhled, čísla, testy). Zásadní rozhodnutí
  (architektura, nové závislosti, změna formátu) nejdřív navrhni a nech schválit.
- **Každou odpověď zakonči jasně označeným nejvhodnějším dalším krokem** v tomto tvaru:
  `➡️ **Nejvhodnější další krok:** <jeden konkrétní krok> – <proč právě tento>`.
  Případné alternativy uveď až za ním, krátce.
- Použití: strojní díly, NDT, 3D tisk, krabičky na elektroniku – všechno.
- Vývoj probíhá v **Claude Code v cloudu (Linux)**. Cílová aplikace bude pro Windows, proto
  vše musí jít sestavit a otestovat i na Linuxu.

## Rozhodnutí (14. 10. 2026)

- **Python 3.11+ a build123d 0.13.0** nad Open CASCADE 8.0.1 (balík cadquery-ocp). Verze je
  zamčená v `pyproject.toml`. Používej API build123d 0.13 a každé volání ověř spuštěním –
  nevymýšlej třídy ani parametry (OCCT 7.x a 8.x se liší).
- **Model je čitelný JSON „recept“** (parametry + seznam prvků), ne Python skript (bezpečnost,
  editace z GUI i AI) a ne binární formát. Popis formátu je v README.md.
- **Okno: PySide6 6.11.2 + 3D prohlížeč Open CASCADE (V3d/AIS)**. Windows `.exe` staví
  PyInstaller v GitHub Actions (`.github/workflows/windows.yml`); z větve `main` se zveřejní
  jako vydání „nejnovejsi“ (odkaz ke stažení je v README). Repozitář je veřejný.
- Podklady jsou v `docs/` (tři výzkumy; `VYZKUM_3D_CAD.md` a `zprava-hluboky-vyzkum.md` jsou
  stejný text).
- (15. 10. 2026, schváleno) **Řešič vazeb skici: `slvs==3.2`** – oficiální řešič SolveSpace
  (GPL, kola pro Windows i Linux, Python 3.11–3.13). Formát modelu verze 3 přidal tvar
  skici `profile`.
- (15. 10. 2026, schváleno) **Díry podle tabulek** – prvek `hole`, formát verze 4. Závit je
  jen vyznačený (díra = vrták pod závit). Tabulky v `holes.py` jsou ověřené z více zdrojů
  (normy jsou placené) – u každé změny tabulky uveď zdroj v docstringu.
- (15. 10. 2026, schváleno) **Pole a zrcadlení** – prvky `pattern` (kruhové, lineární,
  mřížka) a `mirror` (vybrané prvky nebo celý díl), formát verze 5. Opakují vybrané prvky,
  ne celé těleso; zrcadlení bez vybraných prvků zrcadlí celý díl.
- (15. 10. 2026, schváleno) **Kružnice a vazby mezi tvary ve skicáři** – čára `circle`, víc
  smyček v jednom obrysu (vnořená = díra), vazby `concentric`, `symmetric`, kóta `diameter`,
  tečnost ke kružnici přes skrytý bod dotyku. Formát verze 6.
- (15. 10. 2026, schváleno) **Přepočet na pozadí v pomocném procesu** (`worker.py`), ne ve
  vlákně – OCCT drží zámek Pythonu (GIL) a okno by stálo. Nová změna rozpočítaný přepočet
  hned zruší (záložní proces je připravený), *Zastavit* vrátí poslední spočítaný stav.
- (15. 10. 2026, schváleno) **Promítnutí hran dílu do skici** – `projection.py`, obrys má
  `references` (hrana popsaná významem + poslední promítnutý tvar), ve skicáři šedé hrany
  dílu, nástroj Promítnout a Převzít do obrysu. Formát verze 7.
- (15. 10. 2026, schváleno) **Skica na šikmé a zakřivené ploše** – `plane` může být
  `{"at", "normal"}` (`selectors.face_plane_at`): šikmá plocha nese skicu přímo, zakřivená
  tečnou rovinou v místě kliknutí. Obtočení skici kolem válce zatím ne. Formát verze 8.
- (15. 10. 2026, schváleno) **Měření ve 3D** – `measure.py`: měří se samo při výběru (panel
  *Měření*, čára s hodnotou ve 3D), tloušťka stěny v bodě paprskem kolmo do materiálu (jako UT
  tloušťkoměr). Měření jde uložit do modelu (`measurements`, plochy a hrany významem) a
  přepočítá se s každou změnou. Formát verze 9.

## Architektura (`src/skodacad/`)

| Soubor | Úloha |
|---|---|
| `document.py` | načtení/uložení JSON, kontrola struktury, `DocumentError` |
| `expressions.py` | bezpečné výrazy s parametry (vlastní AST, žádné `eval`) |
| `selectors.py` | sémantický výběr ploch a hran (ochrana proti topological naming problem) |
| `picking.py` | kliknutí ve 3D → popis významem (`between`, `near` …), plocha → rovina skici |
| `solver.py` | obal řešiče vazeb slvs: kontrola obrysu a vazeb, řešení, uzavřené smyčky (i kružnice) |
| `profile_edit.py` | úpravy obrysu pro skicář bez okna (kreslení, mazání, vazby z výběru, kóty, promítnuté hrany, převzetí do obrysu) |
| `projection.py` | promítnutí hran dílu do roviny skici, kandidáti pro skicář, obnova odkazů z dílu |
| `holes.py` | strojnické tabulky děr (ISO 2306, 273, DIN 974-1, DIN 74, 3D tisk) a tvar díry |
| `threads.py` | vymodelovaný vnitřní závit (ISO 68-1) jako drážka z rovinných plošek |
| `features.py` | prvky modelu; registrace dekorátorem `@feature("typ", "Český název")`; pole a zrcadlení |
| `rebuild.py` | přepočet seznamu prvků, stavy `ok` / `error` / `skipped`, záznam operací prvků |
| `properties.py`, `materials.py` | objem, povrch, hmotnost, těžiště |
| `export.py` | STEP, STL, 3MF, GLB, SVG náhled |
| `cli.py` | příkazová řádka `skodacad build` |
| `session.py` | `ModelSession` – otevřený model: úpravy prvků a parametrů, Zpět/Znovu, uložení, export (bez Qt); s `runner` přepočet na pozadí (`poll`, `wait`, `cancel`) |
| `worker.py` | přepočet v pomocném procesu (`BackgroundRebuilder`), přenos výsledku přes BinTools |
| `schema.py` | popis polí každého prvku a tvaru skici (česky) + výchozí hodnoty nových prvků |
| `inspection.py` | český popis vybrané plochy/hrany |
| `measure.py` | měření: rozměry, vzdálenost, rozteč, úhel, tloušťka stěny; uložená měření (odkazy významem, `evaluate`) |
| `gui/app.py` | spuštění okna, log `~/SkodaCAD/skodacad.log`, `--self-test`, `--screenshot` |
| `gui/main_window.py` | hlavní okno: díl, parametry, strom prvků, vlastnosti, menu, panel Měření |
| `gui/feature_editor.py` | panel „Úprava prvku“ – formuláře sestavené ze `schema.py` |
| `gui/sketcher.py` | skicář – 2D editor obrysu (kreslení, vazby, kóty, stav určenosti) |
| `gui/viewer.py` | 3D prohlížeč OCCT (jediné místo GUI, které sahá na OCCT – jen kvůli kreslení a výběru); hlásí vybrané tvary, Ctrl+klik, pravý klik, zvýraznění |
| `packaging/` | PyInstaller (`skodacad.spec`) pro sestavení `SkodaCAD.exe` |

## Pravidla

1. Plochy a hrany se **nikdy nevybírají indexem**, jen významem (`selectors.py`).
2. Každý nový prvek či změna geometrie má **test, který ověřuje fyziku**: objem podle vzorce,
   rozměry, `is_valid`. Nestačí „nespadlo to“.
3. Chyby pro uživatele jsou **česky a lidsky**: co se stalo a co zkusit. Výjimky jádra převádět
   na `FeatureError`; neočekávaná chyba nesmí shodit program.
4. Jednotky vždy **mm**, úhly ve **stupních**.
5. Změna formátu JSON = zvýšit `VERSION` v `document.py` a umět načíst staré soubory.
   Modely v `examples/` musí jít vždy postavit (hlídá to test).
6. Pracuj po **malých krocích**; po každém musí projít `ruff check src tests` a `pytest -q`,
   teprve pak commit.
7. Nové závislosti jen se zdůvodněním a se zamčenou verzí.
8. GUI nesmí modelovat přes build123d/OCCT – jen přes `ModelSession`. Výjimkou je
   `gui/viewer.py`, který OCCT používá jen ke kreslení a výběru.
9. Okno se testuje dvakrát: `tests/test_gui.py` (offscreen, náhradní prohlížeč) a skutečně
   pod Xvfb snímkem okna. Změnu vzhledu ukaž uživateli snímkem.
10. Každá úprava modelu z okna jde přes metodu `ModelSession` (→ `_change`), aby fungovalo
    Zpět/Znovu a neplatná úprava model nepoškodila.
11. Testy okna s dialogem (`QInputDialog`, `QMessageBox`, `QFileDialog`) musí dialog nahradit
    (fixture `no_dialogs`), jinak test čeká navždy. Totéž místní nabídka: `QMenu.exec` jde
    přes `MainWindow._exec_menu` a vlastní dialogy (skicář) přes `MainWindow._exec_dialog`,
    test je nahradí. Testy okna pouštěj s `timeout`.

## Příkazy

- Prostředí se v cloudové session připraví samo (`.claude/hooks/session-start.sh`).
  Ručně: `uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"`
- Testy: `pytest -q`  ·  Kontrola kódu: `ruff check src tests`
- Postavit model: `skodacad build examples/priruba.json --set D=200` → soubory v `out/`
- Výsledek ukaž uživateli jako náhled `out/<model>.svg` spolu s objemem a hmotností.
- Snímek okna v cloudu:
  `xvfb-run -a -s "-screen 0 1280x800x24" skodacad-gui --screenshot out/okno.png`
- Kontrola okna i 3D: `xvfb-run -a skodacad-gui --self-test out/self-test.txt`
- Sestavení aplikace lokálně: `uv pip install -e ".[build]"` a
  `pyinstaller packaging/skodacad.spec --noconfirm`; pak self-test `dist/SkodaCAD/SkodaCAD`.
- Stav sestavení pro Windows sleduj v GitHub Actions (workflow „Windows aplikace“).

## Známé pasti (OCCT prohlížeč)

- Po změně velikosti nativního okna se musí volat `V3d_View.MustBeResized()`, jinak výběr
  myší míří vedle (`OccViewer._sync_size` porovnává skutečnou velikost okna).
- Obrysy ploch (`SetFaceBoundaryAspect`) nastavovat až po `SetColor`, jinak je přebarví.
- Ve Windows se HWND předává OCCT jako PyCapsule (`viewer._as_capsule`).
- Souřadnice myši z Qt násobit `devicePixelRatioF()` (škálování obrazovky 125–150 %).
- build123d importuje IPython – v PyInstalleru ho nevynechávat.
- `QAction.triggered` posílá navíc `checked` (False) – do `lambda k=key: …` by se dostalo
  místo `k`. Akce zakládej jen přes `MainWindow._action` (volá slot bez argumentů) a každou
  novou akci pokryj testem, který ji opravdu stiskne (`tests/test_gui.py`).

## Známé pasti (výběr kliknutím)

- Kliká se na **hotový** díl, ale prvek uprostřed stromu vybírá na dílu **před sebou**
  (`BuildResult.parts_before`). Hrany se proto do něj přenášejí geometricky (`map_edges`),
  ne totožností. Nový prvek z výběru jde vždy na konec stromu.
- Popis z kliknutí se vždy ověří `select_edges` – musí vybrat přesně kliknuté hrany.
- Po každém překreslení dílu je starý výběr neplatný (okno ho maže v `_refresh_all`).

## Známé pasti (pole a zrcadlení)

- Pole/zrcadlení neopakuje celé těleso, ale **záznam operací** prvku: každé `ctx.apply`
  uloží (těleso, přidat/ubrat) do `ctx.operations[id]` a pole totéž zopakuje posunuté.
  Nový prvek, který přidává či ubírá materiál, proto musí jít přes `ctx.apply` a jeho typ
  patří do `REPEATABLE_FEATURES`. Zaoblení/sražení/skořepina mění díl jinak – opakovat nejdou.
- Rovina `XZ` má v build123d normálu **−Y**: posun roviny (`offset`) jde do záporného Y
  (u skic i u zrcadlení stejně).
- Kopie, které padnou na stejné místo (díra ve středu otáčení, souměrný prvek), nic
  neodeberou → chyba „leží mimo díl nebo na stejném místě“ – je to správně.

## Známé pasti (řešič vazeb slvs)

- Při nesmyslném volání (špatný druh nebo pořadí argumentů) slvs **shodí celý proces**
  (`FatalError` → abort), nevyhodí výjimku. Do slvs se proto smí jen přes `solver.py`, který
  vše nejdřív zkontroluje. Test `test_every_constraint_kind_in_both_orders_does_not_crash`
  zkouší každou vazbu v obou pořadích v samostatném procesu – novou vazbu do něj přidej.
- `slvs.tangent` chce **oblouk jako první** (úsečka napřed = pád). Obal pořadí otáčí.
- Kružnice/oblouk potřebují 3D normálu (`add_normal_3d`), ne `add_normal_2d`.
- Vodorovně + svisle na jedné čáře není „spor“ – řešič ji smrskne do bodu. Skicář to hlásí.
- Řešič je globální stav (`clear_sketch`) – volat jen z jednoho vlákna.
- Kružnice se dotknout neumí (`tangent` s kružnicí = pád) – tečnost bez společného bodu
  dělá `solver._touch` skrytým bodem dotyku (na obou křivkách + kolmo / na spojnici středů).
- Vzdálenost bodu od čáry má v slvs **znaménko** (kladná = vpravo od směru čáry). Obal
  znaménko bere z polohy bodu, jinak bod přeskočí na druhou stranu.
- Nové kružnicové vazby: `distance` ani `midpoint` s kružnicí slvs neumí (pád) – kontrola
  v `_check_constraint` je nepustí.

## Známé pasti (šikmé a zakřivené plochy)

- Plocha pro skicu se pamatuje **bodem a směrem** (`at`, `normal`), ne číslem: najde se
  plocha nejbližší bodu, na hraně rozhodne směr. Normála, která se od uložené liší o víc
  než 60°, znamená, že plocha zmizela → česká chyba.
- Počátek skici na šikmé ploše = bod `at` promítnutý do roviny plochy (ne střed plochy);
  u zakřivené = nejbližší bod plochy (tečná rovina sleduje změnu průměru).
- Osa X skici: podél osy válce/kužele (OCCT `Cylinder().Axis()`), jinak `Z × normála`;
  směr se vždy otočí ke kladným souřadnicím, aby nezávisel na orientaci osy v OCCT.
- Další díra kliknutím jde jen do stejné roviny – na válci tedy jen podél té přímky, kde
  se tečná rovina válce dotýká.

## Známé pasti (promítnutí hran)

- Promítnutá hrana je v řešiči **pevná** (skupina 1 jako počátek). Vazba jen mezi pevnými
  prvky (počátek, promítnuté hrany, jejich body) by nic neurčila → `solver` ji odmítne.
- Odkaz drží hranu **významem** (`picking.edge_selector`, často `near`), nikdy indexem.
  Tvar a souřadnice v JSON jsou jen poslední stav – `projection.refresh` je při každém
  přepočtu spočítá znovu z dílu **před skicou** (`ctx.part`, v okně `parts_before`).
- Skicu kreslí skicář v souřadnicích obrysu – promítnutí počítá s rovinou skici i s
  posunem/natočením obrysu (`center`, `angle`).
- Oblouk po promítnutí vede vždy proti směru hodin (jako v řešiči) – `project_edge` podle
  bodu uprostřed hrany případně prohodí konce.
- Body promítnutých hran se jmenují `r1.start` … – tečka je proto ve jménech bodů obrysu
  zakázaná.

## Známé pasti (vymodelovaný závit)

- Tažení profilu po šroubovici (`sweep` + `Helix`) i plochy napnuté mezi šroubovicemi dávají
  platná tělesa, ale **booleovské operace s nimi jsou v OCCT 8 nespolehlivé** (řez se tiše
  neprovede nebo vrátí nesmysl, různě podle velikosti). Proto `threads.py` skládá drážku
  z rovinných plošek se sdílenými hranami a řeže ji až po vyvrtání jádra.
- Hrany plošek jsou označené C2 (`_mark_facet_edges`) a prohlížeč kreslí jen hrany do C1
  (`SetFaceBoundaryUpperContinuity`) – jinak by byl závit posetý čarami trojúhelníků.
- Objem drážky z plošek se od přesné šroubovice liší řádově o desetiny procenta; testy
  ho porovnávají s Pappovou větou s tolerancí, ne přesně.

## Známé pasti (měření)

- Tloušťka stěny = paprsek (`IntCurvesFace_ShapeIntersector`) z bodu proti normále plochy;
  první průsečík dál než 1e-4 je protější stěna. `Face.normal_at` už počítá s orientací
  plochy (u díry míří do díry, ven z materiálu) – neotáčet.
- Uložená plocha se hledá `selectors.find_face` s `type`/`radius`: rovina přednostně mezi
  plochami se **stejnou normálou** (posunutá plocha po změně tloušťky je daleko od `at`),
  válec mezi stejným poloměrem (posunutá díra). Bez `type` (rovina skici v8) jako dřív:
  nejbližší plocha + kontrola směru 60°.
- Bod `at`, který po změně parametru už na ploše neleží (posunutá jamka), nahradí
  `measure.inner_point` – bod uvnitř plochy co nejdál od hran (střed plochy může být v díře).
- Hodnota uloženého měření se do JSON neukládá. `BuildResult.measurements` (`SavedResult`,
  jen čísla a texty) se počítá na konci `rebuild` – tedy i v pomocném procesu – a přenáší se
  obyčejně (pickle).
- Popisek ve 3D (`AIS_TextLabel`) chce `TCollection_ExtendedString(text, True)` (UTF-8 –
  jinak se rozbije „°“) a `SetFont("Arial")`, jinak OCCT kreslí patkovým písmem.
- **Žádný podklad pod popiskem** (`Aspect_TODT_SUBTITLE`): základní ovladač Windows bez
  grafické karty (GDI Generic, OpenGL 1.1 – sestavovací počítač GitHubu, vzdálená plocha,
  virtuál) při překreslení spadne (access violation, celý program). Čára, kuličky
  (`Aspect_TOM_BALL`) a prostý text fungují. Self-test (`_self_test_drawing`) kreslí každý
  použitý druh značky zvlášť a do zprávy píše ovladač OpenGL – nový druh kreslení přidej i tam.
- Zpráva self-testu se zapisuje průběžně a `faulthandler` k ní při pádu připíše zásobník
  Pythonu – v logu GitHubu je pak vidět řádek, kde proces spadl.
- Self-test okna musí otevřít ukázku přes `MainWindow.open_model` (ne jen `show_part`) –
  měření i výběr jdou přes `ModelSession`, bez výsledku přepočtu se nic nezměří.

## Známé pasti (přepočet na pozadí)

- Vlákno nepomůže: OCCT během výpočtu drží GIL (změřeno – okno stálo až 2 s). Proto proces
  (`multiprocessing`, vždy kontext **spawn** – jako ve Windows).
- Tvary build123d nejdou přes `pickle` (drží `BRepTools_History`, `gp_Pln`) – výsledek se
  přenáší přes `worker.encode_result` / `decode_result` (BinTools, řádově ms).
- Spawn spouští pomocný proces znovu z hlavního skriptu: každý spouštěcí skript musí mít
  `if __name__ == "__main__":`, jinak pomocný proces otevře další okno a vše se zasekne.
  V sestaveném exe je navíc nutné `multiprocessing.freeze_support()` jako první příkaz
  (`packaging/skodacad-gui.py`). Self-test to ve Windows ověřuje na staženém balíčku.
- `ModelSession` bez `runner` počítá synchronně (testy, CLI) – testy okna s pomocným
  procesem jsou v `tests/test_background.py` (čekají přes `QTest.qWait`).
- Během přepočtu je `session.result` ten **předchozí**: strom se skládá z `document`,
  výběr z 3D a export hlásí „ještě se přepočítává“.
- Řešič slvs ve skicáři běží v okně, přepočet v pomocném procesu – každý má svůj globální
  stav, nekříží se.

## Známé pasti (sestavení pro Windows)

- `actions/upload-artifact` bez `include-hidden-files: true` vynechá složky s tečkou
  (`sklearn/.libs` s `vcomp140.dll`) → aplikace u uživatele spadla při startu. Proto úloha
  `kontrola-stazeni` testuje přesně stažený balíček, ne složku na sestavovacím počítači.
- Sestavovací počítač GitHubu má Visual C++ Redistributable, uživatel ne. Hlídá to
  `packaging/check_dlls.py` (v balíčku nesmí chybět msvcp140/vcruntime140/vcomp140…).
- Windows konzole na GitHubu není UTF-8 → `PYTHONUTF8=1` v workflow.
- Než pošleš uživateli odkaz ke stažení, musí projít obě úlohy workflow.

## Jak přidat nový prvek

1. Funkce v `features.py` s dekorátorem `@feature("typ", "Český název")`.
2. Číselné hodnoty čti přes `ctx.num` / `ctx.positive` (umí výrazy), chyby hlas `FeatureError`.
3. Pole prvku popiš v `schema.py` (`FEATURE_SCHEMAS`) a doplň výchozí hodnoty v `new_feature`
   – podle toho okno postaví formulář (test `test_schema.py` hlídá shodu s jádrem).
4. Test v `tests/test_features.py` s očekávaným objemem podle vzorce.
5. Doplň tabulku prvků v README.md.

## Plán

- [x] **Fáze 0** – jádro bez GUI: JSON model, parametry a výrazy, skica, vysunutí, rotace,
  zaoblení, sražení, skořepina, exporty, testy.
- [x] **Fáze 1** – [x] skicář s vazbami (úsečky, oblouky, kóty; řešič `slvs`),
  [x] kružnice a vazby mezi obrysem a dalšími tvary, [x] díry se závity podle strojnických
  tabulek (vyznačený závit; [x] vymodelovaný závit pro 3D tisk), [x] pole a zrcadlení.
- [x] **Fáze 2a** – okno (PySide6 + OCCT prohlížeč): parametry s přepočtem, strom prvků,
  vlastnosti, výběr ploch/hran, export; Windows `.exe` přes GitHub Actions.
- [x] **Fáze 2b** – nový díl od nuly v okně: přidání, úprava (formulář), smazání a přesun
  prvků, parametry, název a materiál, Zpět/Znovu.
- [x] **Fáze 2c** – výběr hran a ploch kliknutím ve 3D → sémantický popis (`picking.py`),
  zaoblení/sražení/skica/skořepina z výběru, zvýraznění hran vybraného prvku. Formát verze 2.
- [x] **Fáze 2d** – [x] přepočet na pozadí u pomalých modelů, [x] šikmé a zakřivené plochy
  pro skicu (tečná rovina).
- [ ] **Fáze 3** – [x] měření ve 3D (vzdálenost, rozteč, úhel, tloušťka stěny v bodě, uložená
  měření; formát verze 9), [ ] řezy modelem, [ ] sweep/loft, [ ] normalizované díly,
  [ ] NDT – mapa tloušťky stěny.
- [ ] **Fáze 4** – AI asistent upravující JSON model, omezené přímé úpravy ploch.
