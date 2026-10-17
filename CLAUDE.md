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
- (15. 10. 2026, schváleno) **Mapa tloušťky stěny (NDT)** – `thickness_map.py`: povrch se
  rozdělí na trojúhelníky do zvoleného kroku, v každém těžišti tloušťka paprskem (pravidlo
  koncového echa). Škála červená → modrá + minimum fialově, nejtenčí místo, export CSV.
  Nastavení (`limit`, `step`, `scale_max`) se ukládá do modelu, zapnutá mapa se počítá na
  pozadí s každou změnou, příkazová řádka vypíše souhrn. Formát verze 10.
- (16. 10. 2026, schváleno) **Řez modelem** – `section.py`: přesný řez jádrem (díl minus
  velký kvádr za rovinou), rovina X/Y/Z nebo rovnoběžně s vybranou plochou, posuvník,
  otočení, export obrysu řezu DXF/SVG, mapa tloušťky oříznutá rovinou. Řez je **jen pohled**
  (`ModelSession.section_settings`), do modelu se neukládá – formát se nemění.
- (16. 10. 2026, schváleno) **Tažení a přechod** – prvek `sweep`: trasa z bodů [x, y, z] +
  poloměr ohybu (0 = ostré rohy na pokos), profil kruh/trubka, obdélník/jekl nebo skica;
  prvek `loft`: přechod mezi skicami v pořadí, `ruled`, dutý se stěnou `wall` (otevřené
  konce). Formát verze 11.
- (16. 10. 2026, schváleno) **Normalizované díly** – `standards.py`, prvek `standard`:
  šrouby ISO 4762/4017/10642, matice ISO 4032, podložky ISO 7089, kuličková ložiska, kolíky
  ISO 2338, pera DIN 6885, tyče z ocelových profilů (IPE, UPN, L, jekl, trubka); ocelový
  profil i jako tvar skici `steel` a profil tažení. Prvek tělesa (ne sestava), závit
  vyznačený, odebrání = kapsa s vůlí. Tabulky ověřené z více zdrojů. Formát verze 12.
- (16. 10. 2026, schváleno) **AI asistent** – `assistant.py` + panel `gui/assistant_panel.py`
  a `skodacad ai`: Claude API (oficiální knihovna **`anthropic==1.15.0`**), výchozí
  `claude-opus-5-5` (v nastavení i `claude-sonnet-5-5`), důkladnost `high`. Mění model
  rovnou nástroji nad `ModelSession`, celá odpověď = jeden krok Zpět. Klíč v profilu
  (`~/SkodaCAD/nastaveni.json`) nebo `ANTHROPIC_API_KEY`. Umí nový díl z popisu, vysvětlit
  a opravit chyby, prohlédnout si díl (snímek 3D) a příkazovou řádku. Formát se nemění.
- (16. 10. 2026, schváleno) **NDT modul – etapy 00 a 01** podle `docs/ndt/03-implementacni-plan.md`
  (návrh `04-navrh-etapa-00-01.md`): osm referenčních dílů `examples/ndt/` s ručně spočítanými
  výsledky (`05-referencni-dily.md`, ověří kolega NDT technik), virtuální úhlová sonda 40 × 20 × 25
  s výstupním bodem 12 mm od čela. **NDT studie v souboru modelu** (sekce `ndt`, formát
  verze 13), otisk dílu z receptu, stavy platná/zastaralá/neúplná/neplatná vazba, panel NDT.
  NDT nikdy nemění geometrii, výsledky se neukládají, AI není zdroj čísel.
- (16. 10. 2026, schváleno) **NDT etapa 02 – geometrické jádro** (`ndt/geometry.py`, návrh
  `docs/ndt/06-navrh-etapa-02.md`): paprsek s úseky v materiálu, bod plochy se zakřivením,
  uvnitř/vně, viditelnost, kolize tělesa. Hraniční případy (po povrchu, přes hranu, tečně) =
  **nejisté s českým důvodem**, nikdy materiál. Jen přesné těleso OCCT (síť až podle potřeby),
  příkaz `skodacad paprsek`. Formát se nemění.
- (16. 10. 2026, schváleno) **NDT etapa 03 – virtuální sonda** (`ndt/devices.py`, návrh
  `docs/ndt/07-navrh-etapa-03.md`): přímá (válec) a úhlová (kvádr, výstupní bod od čela)
  sonda, přiložení do tečné roviny, mezera pod sondou (mez **0,5 mm** jako EN ISO 17640),
  přesah, kolize, vůle nad rovinou přiložení, manipulační rezerva **výchozí 0 mm**, posun po
  přímce. Sonda se ukládá do studie (`device`, **formát verze 14**); přiložení je jen pohled.
  V okně skupina Sonda v panelu NDT (Přiložit sondu sem, barva podle výsledku), `skodacad sonda`.
- (16. 10. 2026, rozhodnutí autora) **Závazné vymezení UT** (`docs/ndt/04-zavazne-vymezeni-ut.md`,
  má přednost před plánem `03-…`): UT posuzuje jen **přístupnost sondy** a **geometrické
  pokrytí** – nikdy prozvučitelnost materiálu, detekovatelnost vad ani virtuální signály
  (A/B-scan, etapa 16 mimo rozsah). Povinné upozornění `ndt.UT_DISCLAIMER` doslovně v okně
  (skupina „Přístupnost UT sondy“) i v každém výstupu a protokolu. Výsledky pokrytí: geometricky
  pokryto / nepokryto / nelze spolehlivě vyhodnotit; procento pokrytí není pravděpodobnost
  nálezu. Lom a odraz jen s výslovně zadanými předpoklady, skutečně spočítané a testované.
- (16. 10. 2026, rozhodnutí autora) **macOS Apple Silicon** (`docs/ndt/05-podpora-macos.md`):
  hned po etapě 03 první spustitelná verze pro MacBook Air M4 (16 GB) – **ZIP se `SkodaCAD.app`**
  z GitHub Releases, data a log v **`~/SkodaCAD`** jako ve Windows, samostatná úloha GitHub
  Actions na macOS arm64, Windows beze změny. Stejné jádro, formát i NDT. Podepsání a
  notarizace až při rozhodnutí o distribuci. Kompatibilitu netvrdit, dokud ji uživatel neověří
  na skutečném Macu.
- (16. 10. 2026, schváleno) **NDT etapa 04 – geometrický model UT paprsku** (`ndt/ut.py`, návrh
  `docs/ndt/09-navrh-etapa-04.md`): přímá ($\beta = 0^\circ$) a úhlová ($\beta \in [1^\circ, 85^\circ]$)
  sonda, lom podle Snellova zákona (`refract`) **jen s výslovně zadanými rychlostmi** $c_1, c_2$
  a kritickým úhlem, zrcadlové odrazy na plochách (`trace_beam`, půlkrok `half_skip`, celý krok
  `full_skip`, hloubka, jistota; nejistý dopad zastaví další odrazy). U sondy `beam_angle` a
  `bounces` (**formát verze 15**), v `skodacad sonda` volby `--uhel`, `--snell`, `--vlna`,
  `--odrazy`, `--dosah`; v okně vykreslení lomené dráhy paprsku ve 3D i v řezu.
- (16. 10. 2026, schváleno) **NDT etapa 05 – ruční pohyb sondy v okně, milník M1** (návrh
  `docs/ndt/10-navrh-etapa-05.md`): mezipaměť poloprostoru nad tečnou rovinou (`_upper_part`
  v `ndt/devices.py`), interaktivní posun a přímá dráha v `ModelSession` (`move_ndt_probe`,
  `shift_ndt_probe`, `scan_ndt_line`, `select_ndt_scan_index`), v okně přepínač *Jezdit sondou
  myší* + `Alt`+tažení a `Alt`+kolečko ve 3D prohlížeči, krokování **◀ / ▶** a tlačítko *Projet
  čáru* s posuvníkem. Formát se nemění (verze 15).
- (17. 10. 2026, schváleno) **NDT etapa 07C – cílový objem v okně** (návrh
  `docs/ndt/14-navrh-etapa-07c.md`, doporučení 1–4): číselný editor svaru/hranolu se směry
  jen ±X/±Y/±Z, průhledný náhled cíle, objemový výpočet z panelu s citlivostí na krok
  zapnutou ve výchozím stavu, výchozí kroky pojezd 5 mm / cíl 4 mm, barevný povrch cíle
  a tlačítko *Průřez svarem*. Výpočet 07B ani formát (16) se nemění.

## Architektura (`src/skodacad/`)

Etapa 06 (schválena autorem, sloučena v PR #15): `ndt/coverage.py` počítá plochy
nebo body z pojezdu `face`/`line`, tři stavy, CSV a citlivost na krok. `ModelSession` drží
mapu pouze jako pohled; výpočet v okně používá `BackgroundRebuilder` a jde zrušit. Formát
zůstává 15. `skodacad pokryti` vyžaduje `--plocha` a cíle (`--cil`, `--cil-plocha`, `--studie`).
Numerická tolerance nesmí obejít otisk, kolizi ani rezervu: na rovině se mezilehlá poloha
sondy skutečně přiloží a paprsek znovu spočítá. Na zakřivené ploše je pouhá numerická
blízkost nejistá. Citlivost porovnává krok a 2× krok při stejné toleranci. Povinné upozornění
UT a význam procenta jsou v panelu, CLI i CSV. V `devices.place` nelze ořez odsazený o 0,001 mm
použít k vyloučení kolize; mohl by přehlédnout nízkou překážku (hlídá regresní test).

Etapa 07A (schválena 17. 10. 2026, sloučena v PR #16, `main` / `0dea6f8`): `ndt/welds.py`
validuje a staví pomocné cíle `volume` / `weld` (rovný V bez otupení a koutový svar).
Formát 16 zachovává načtení verzí 1–15. Obecný hranol se protíná s materiálem,
nominální svar se musí celý vejít do dílu. Vektory `axis` a `across` jsou kolmé,
výška průřezu = `across × axis`; body pro build123d.Polygon předávat jako tuple,
seznamy souřadnic mohou tiše vytvořit nulovou plochu. Jen číselné rozměry v mm/°.
`set_ndt_volume_target` / `ndt_target_volume` jsou veřejná rozhraní ModelSession;
studie drží jen JSON, výsledek přepočtu jen číselné objemy, nikdy pomocný OCCT tvar.
Změna dílu vyžaduje potvrzení, cíl se sám neposouvá; změna cíle ruší mapu a ověření.
Ověření objemu nese i `verified.target` (otisk cíle), kontroluje se i při načtení souboru.
07B (schváleno 17. 10. 2026, sloučeno v PR #17, `35f1507`): `ndt/volume_coverage.py`
dělí skutečný cíl na oříznuté buňky a oddělené kusy, váhy v mm³. `VolumeCoverageMap`
nikdy nezaměňovat za `CoverageMap.areas`; ověřuje se součet vah bez přenormování.
Neurčený vnitřní bod ponechá známý objem nejistý. Zásahy sdílí Etapu 06, výsledek
je přenosný pomocným procesem, CLI/CSV a citlivost mají úplná upozornění UT.
Pojezd `line` s nulovým rozevřením objem odmítne (osy nevymezují kladný objem).
07C (schváleno 17. 10. 2026 včetně doporučení 1–4, návrh `docs/ndt/14-navrh-etapa-07c.md`,
implementace po krocích ve vývojové větvi). 07C.1 hotovo: `gui/target_dialog.py` (editor
svaru/hranolu, směry jen ±X/±Y/±Z, šikmý směr ze souboru se zachová, nákres průřezu Qt),
`ModelSession.check_ndt_volume_target` (bez změny modelu), `ndt_target_outline`,
`ndt_frame_from_edge`, `ndt_target_preview` (v řezu rozříznutý), podnabídka *NDT – cílové
objemy*. 07C.2 hotovo: panel zná krok cíle, toleranci (automaticky / číslo) a citlivost na
krok (`compute_ndt_coverage(convergence=True)`, i v pomocném procesu), odhad před spuštěním
`ndt_coverage_estimate` se stejnými ochranami jako 07B; nepovedené porovnání nechá jemný
výsledek a napíše „nepodařilo ověřit“. Do 07C.3 `visible_ndt_coverage` pro objem vrací
prázdnou kresbu. Formát zůstává 16.
Podrobný návrh je v `docs/ndt/13-navrh-etapa-07b.md`. Ukázky jsou v `examples/ndt/cilove_objemy/`,
balíček a self-test je musí přibalit/prověřit. Ruční zkouška vydání Etapy 06 po sloučení
je stále odložená; nenahrazovat ji tvrzením o provedeném ručním ověření.

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
| `standards.py` | normalizované díly: tabulky (šrouby, matice, podložky, ložiska, kolíky, pera, ocelové profily), tvary v místních souřadnicích, kapsy, průřezy profilů |
| `features.py` | prvky modelu; registrace dekorátorem `@feature("typ", "Český název")`; tažení a přechod; pole a zrcadlení |
| `rebuild.py` | přepočet seznamu prvků, stavy `ok` / `error` / `skipped`, záznam operací prvků |
| `properties.py`, `materials.py` | objem, povrch, hmotnost, těžiště |
| `export.py` | STEP, STL, 3MF, GLB, SVG náhled |
| `cli.py` | příkazová řádka `skodacad build`, `skodacad ai`, `skodacad paprsek` a `skodacad sonda` |
| `assistant.py` | AI asistent: nastavení a klíč, nástroje nad `ModelSession` (`ModelTools`), souhrn přepočtu pro AI, systémový pokyn (README „Formát modelu“ + schéma + ukázky), rozhovor s Claude (`Assistant.ask`), cena, `offline_client` (přehrané odpovědi bez sítě) |
| `session.py` | `ModelSession` – otevřený model: úpravy prvků a parametrů, Zpět/Znovu, uložení, export (bez Qt); s `runner` přepočet na pozadí (`poll`, `wait`, `cancel`) |
| `worker.py` | přepočet v pomocném procesu (`BackgroundRebuilder`), přenos výsledku přes BinTools |
| `schema.py` | popis polí každého prvku a tvaru skici (česky) + výchozí hodnoty nových prvků |
| `inspection.py` | český popis vybrané plochy/hrany |
| `measure.py` | měření: rozměry, vzdálenost, rozteč, úhel, tloušťka stěny; uložená měření (odkazy významem, `evaluate`); `RayCaster` (paprsek s pravidlem koncového echa) |
| `thickness_map.py` | mapa tloušťky stěny: síť povrchu (půlení nejdelší strany v u, v), tloušťka v těžištích, barvy, souhrn, CSV |
| `section.py` | řez modelem: rovina řezu, přesný řez, plochy řezu, export DXF/SVG, ořez sítě mapy rovinou |
| `ndt/__init__.py`, `ndt/study.py` | NDT: upozornění na předběžnost a povinné upozornění UT (`UT_DISCLAIMER`, názvy `UT_ACCESS`, `UT_COVERAGE`); studie (kontrola struktury, otisk dílu, stav po přepočtu `StudyResult`, nová studie, oblast z výběru, znovuukotvení, kopie) |
| `ndt/geometry.py` | NDT geometrické jádro (`PartGeometry`): `cast` (průsečíky, úseky v materiálu, jistota), `classify`, `surface_at` (normála, zakřivení), `visible`, `collision` (průnik, vůle), `faces_of`; konstanty `ALGORITHM`, tolerance |
| `ndt/devices.py` | virtuální sonda (`Probe` přímá/úhlová, `beam_angle`, `bounces`, meze), `place` (souřadný systém, mezera a přesah z paprsků otisku, kolize, vůle nad rovinou přiložení, stavy), `scan_line` (posun po přímce) |
| `ndt/ut.py` | geometrický model UT paprsku: `refract` (Snellův zákon s výslovnými rychlostmi, kritický úhel), `trace_beam` (`BeamPath`, `BeamLeg`, zrcadlové odrazy na plochách, půlkrok, celý krok, jistota, předpoklady) |
| `gui/app.py` | spuštění okna, log `~/SkodaCAD/skodacad.log`, `--self-test`, `--screenshot` |
| `gui/main_window.py` | hlavní okno: díl, parametry, strom prvků, vlastnosti, menu, panely Měření, Mapa tloušťky a Řez |
| `gui/feature_editor.py` | panel „Úprava prvku“ – formuláře sestavené ze `schema.py` |
| `gui/sketcher.py` | skicář – 2D editor obrysu (kreslení, vazby, kóty, stav určenosti) |
| `gui/ndt_panel.py` | panel NDT: seznam studií se stavem, nová z výběru, úpravy, potvrzení, ověření, zvýraznění oblasti |
| `gui/target_dialog.py` | editor cílového objemu NDT studie (svar V, koutový, hranol): pole, nákres průřezu, objem ze vzorce, kontrola v dílu |
| `gui/assistant_panel.py` | panel AI asistenta: rozhovor v pomocném vlákně, kroky s modelem v hlavním vlákně, dialog Nastavení AI |
| `gui/viewer.py` | 3D prohlížeč OCCT (jediné místo GUI, které sahá na OCCT – jen kvůli kreslení a výběru); hlásí vybrané tvary, Ctrl+klik, pravý klik, zvýraznění |
| `packaging/` | PyInstaller (`skodacad.spec`) pro sestavení `SkodaCAD.exe` a na Macu `SkodaCAD.app` |
| `.github/workflows/` | `windows.yml` (vydání „nejnovejsi“) a samostatný `macos.yml` (Apple Silicon, předběžné vydání „nejnovejsi-mac“) |

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
- Stav sestavení sleduj v GitHub Actions (workflow „Windows aplikace“ a „macOS aplikace“).

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

## Známé pasti (měření a mapa tloušťky)

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
- Mapa tloušťky (`AIS_Triangulation` s barvou v uzlech) se kreslí jen v režimu 0
  (`SetDisplayMode(0)`, okno má výchozí 1 = nic se nenakreslí) a **bez osvětlení**
  (`Graphic3d_TypeOfShadingModel_Unlit`) – jinak OCCT přimíchá výchozí materiál mosaz a
  modrá vyjde olivově. Barva uzlu je `R + G<<8 + B<<16` (`HArray1_int`, bez alfa – int32).
- Díl se pod mapou kreslí drátově (`AIS_WireFrame`, izočáry vypnuté) a zvýraznění výběru
  jen obtahuje – plochy jde dál vybírat kliknutím a měřit, ale barvy mapy zůstanou vidět.
- `ThicknessMap` počítá souhrn (`scale`, `nominal` …) přes `cached_property` – barvení
  uzlů ho volá pro každý uzel a bez paměti by řadilo všechny body pořád dokola (minuty).
- Paprsek tloušťky platí jen při „koncovém echu“ (`measure.RayCaster`): první protější stěna
  musí být k paprsku natočená do 60°. Jinak (okraj jamky, drážky) by vyšlo nesmyslně malé
  číslo – místo zůstane šedé („nejde změřit“), měření v bodě to řekne česky.
- Self-test okna musí otevřít ukázku přes `MainWindow.open_model` (ne jen `show_part`) –
  měření i výběr jdou přes `ModelSession`, bez výsledku přepočtu se nic nezměří.

## Známé pasti (řez modelem)

- Řez = díl minus kvádr za rovinou (`section.cut`), ne `split` – výsledek je obyčejné těleso,
  plochy řezu jsou rovinné plochy s normálou rovnou `normal` řezu ležící v rovině.
- Řez je pohled: okno ukazuje `session.display_part` (rozříznutý díl), ale **model, měření,
  mapa i prvky pracují s celým dílem**. Kliknuté plochy/hrany rozříznutého dílu převádí
  `ModelSession._model_shapes` na celý díl (plocha: bod uvnitř + stejný směr, hrana:
  `map_edges`); plocha řezu tak neprojde → česká chyba.
- Rozříznutý díl se pamatuje podle (díl, rovina) – posuvník ho počítá až po puštění
  (`sliderReleased`), při tažení jen ukazuje číslo.
- Okno kreslí díl znovu, když se změní výsledek **nebo řez** (`_shown_key`); prohlížeč přitom
  smaže mapu, proto `_shown_map = None`.
- Mapa v řezu: `section.clip_mesh` trojúhelníky přes rovinu rozdělí přesně na ní (nové uzly
  s dopočtenou barvou) – jen vyhazování trojúhelníků dávalo zubatý okraj.
- `AIS_ColoredShape` (barva po plochách) se chová jako `AIS_Shape` – výběr ploch a hran,
  drátěný režim pod mapou; self-test ho kreslí jako druh „accent“.

## Známé pasti (tažení a přechod)

- Trasa je `Polyline` (2 body nebo poloměr 0) nebo `FilletPolyline` (ohyby). Ostré rohy chtějí
  `Transition.RIGHT` (spoj na pokos, objem = průřez × délka osy), oblouky `TRANSFORMED`.
- Profil stojí na rovině s `z_dir` = tečna na začátku trasy a `x_dir` = Z × tečna (u svislého
  začátku osa X) – šířka jekl je tak vodorovně a skica na XY u svislé trasy nezmění polohu.
- Dutý přechod: `offset` (skořepina s otevřenými konci) je přesný jen u ploch, které OCCT umí
  odsadit (kužel, válec, rovina). U přechodu kruh ↔ hranatý tvar (B-spline plochy) se **tiše
  nepovede** – vrátí nezměněné těleso. Proto `_hollow_loft` výsledek ověří (objem ≈ plocha
  pláště × stěna) a jinak odečte vnitřní přechod ze skic zmenšených 2D offsetem – stěna je
  pak měřená v rovinách skic (kolmo tenčí, u výsypky 3 → 2,7 mm). Zkoušeno bez úspěchu:
  `MakeThickSolidByJoin` s jinými parametry, zesílení pláště (`thicken`) i prodloužení
  pláště + uzavřený offset (jádro vrátí prázdný tvar nebo dojde paměť).
- Mapa tloušťky na ostrém okraji plechu (konce výsypky) ukáže nesmyslně malé číslo – paprsek
  z úzké čelní plošky hned narazí na šikmou stěnu pod úhlem do 60°.
- **Uzavřenou trasu** (poslední bod = první) OCCT protáhne jako poškozené těleso. Proto
  `_sweep_paths` začne uprostřed první strany a trasu rozdělí na dvě poloviny, které se
  potkají uprostřed rovné strany; obě se táhnou zvlášť a sečtou (všechny rohy na pokos).
  Body uprostřed rovné části (`_without_straight`) se vynechají – `FilletPolyline` na nich
  padá.
- Hotové pole formuláře, které patří k jiné volbě (`when`), se při úpravě nečte
  (`FieldsForm._commit`) – skryté hodnoty (šířka jeklu u kruhu) zůstanou v modelu.

## Známé pasti (normalizované díly)

- Díl se staví v místních souřadnicích „jak sedí na ploše“ (rovina z = 0, +Z ven): šroub
  hlavou nahoru a dříkem do materiálu, matice/ložisko/kolík/tyč na ploše, pero spodkem
  v hloubce t1. `direction: reverse` = zrcadlení podle roviny (kapsa do materiálu).
- Kapsa (`operation: cut`) bere **obrys bez děr** zvětšený o vůli na každou stranu – jinak
  by v kapse na matici či ložisko zůstal sloupek uprostřed (`part_shape(pocket=True)`).
- Velikost má ve formuláři víc polí se stejným klíčem `size` (každé pro jiné druhy, `when`
  s n-ticí hodnot). `FieldsForm.widget(key)` vrací to viditelné, `_commit` čte jen viditelná.
- UPN: sklon vnitřní strany pásnice 8 %, tf platí v polovině šířky pásnice od hřbetu (b/2) –
  jen tak plocha sedí s tabulkou (jinde o 1–1,5 % vedle). Nad UPN 300 by to bylo 5 % a
  (b − tw)/2 od kraje – v tabulce zatím nejsou.
- Úhelník L: r2 = r1/2 (výpočtová hodnota EN 10056-1). Jekly: rohy 2t/2,5t/3t vně, o t méně
  uvnitř (EN 10219-2, výpočtové hodnoty).
- Ložisko 688 otevřené je 8 × 16 × **4** (688ZZ se krytkami 5 mm) – zdroje se v tom pletou.

## Známé pasti (AI asistent)

- API se volá **jen přes knihovnu `anthropic`** (žádné ruční HTTP). Proudově
  (`client.beta.messages.stream` + `get_final_message`), `max_tokens` 64000, `output_config`
  s důkladností, horní `cache_control` (celá historie se ukládá do mezipaměti),
  `fallbacks="default"` s betou `server-side-fallback-2026-07-01` (odmítnutý dotaz zkusí
  záložní model). U Opus 5.5 / Sonnet 5.5 **nejde vynutit nástroj** (`tool_choice` any/tool
  = chyba 400) a parametr `thinking` se neposílá (myšlení je vždy zapnuté).
- Historie rozhovoru je **jen přidávací**: odpověď se ukládá celá (`response.content`, i bloky
  myšlení a „fallback“), nic se zpětně neupravuje. Useknutý nebo odmítnutý tah s nástroji
  se uzavře `tool_result` s chybou (`_close_tools`), jinak by další dotaz vrátil 400.
- Nástroje mají `eager_input_streaming` – vstup se nekontroluje na serveru, proto ho
  kontrolují handlery (`ToolInputError`) a `stop_reason == "max_tokens"` se nástroje nespouští.
- Model se Claudovi posílá jen v prvním dotazu a pak, když ho uživatel mezitím změnil
  (`Assistant.seen`); po každém kroku dostane souhrn přepočtu (`build_report`).
- Okno: síť běží v `QThread`, ale **každý krok s modelem v hlavním vlákně**
  (`_MainThread.call` přes `BlockingQueuedConnection`) a vlákno čeká, až okno převezme
  přepočet z pozadí (`session.computing`). Hlavní vlákno nesmí na vlákno čekat blokujícím
  `wait()` bez zpracování událostí – zablokovalo by se (`AssistantPanel.shutdown`).
- Během práce AI se zamknou panely, nabídky **i zkratky** (`MainWindow._assistant_lock`,
  hlídá i `_refresh_actions`) – jinak by Delete/Ctrl+Z mezi kroky AI rozbily skupinu Zpět
  (`ModelSession.begin_group`/`end_group`).
- Testy a self-test nevolají síť: `assistant.offline_client` je skutečný klient knihovny
  s `httpx2.MockTransport`, který přehraje připravené proudové odpovědi a zapíše dotazy.
  Self-test tak ve Windows ověří, že je `anthropic` (+ httpx2, pydantic, jiter) v exe celá.
- V exe musí být `README.md` (popis formátu pro AI) – `skodacad.spec` ho přibaluje.
- Vlastní id nového prvku jde jen parametrem `feature_id` (`add_feature`); id v hodnotách
  se dál nepřebírá (hlídá test skicáře).

## Známé pasti (NDT studie)

- Otisk dílu (`study.part_fingerprint`) je z **receptu** (parametry, prvky bez `name`,
  materiál), ne z tvaru – posunutá díra nemění objem ani obalový kvádr. 20 a 20.0 jsou totéž
  (`_canonical`). Jen **založení a potvrzení** studie mění její `part`; přejmenování ani
  poznámka zastaralou studii nesmí „opravit“.
- Potvrzení (`confirm_ndt_study`) plochy oblasti znovu ukotví (`refresh_target`) – jinak by
  hláška „plocha se posunula o …“ zůstala navždy. Chybějící plocha = potvrzení odmítnuto.
- Ověření (`verified`) nese otisk dílu, pro který platí; změna metody/oblasti ho smaže,
  ověřit jde jen platnou studii (ne během přepočtu).
- Panel NDT čte záznamy přes `_record` (bez výjimky): po smazání studie se seznam obnoví až
  po překreslení dílu a mezitím ho volá `_selection_changed` se starým výběrem.
- Klik na studii má při zvýraznění přednost před prvkem ve stromu; výběr prvku ve stromu
  výběr studie zruší (`_update_highlight`, `_tree_selection_changed`).
- AI `replace_model` bez klíče `ndt` studie uživatele **ponechá** (přestavba je jen označí
  jako zastaralé). `RULES`: výsledky NDT AI nevymýšlí a studie mění jen na přání.
- Referenční díly jsou v podsložce `examples/ndt/` – test ukázek, nabídka (`_reference_parts`,
  řazení podle čísla v názvu), self-test i `skodacad.spec` ji procházejí zvlášť.

## Známé pasti (NDT geometrické jádro)

- `IntCurvesFace_ShapeIntersector` hlásí **vstup i výstup u přímky ležící v ploše** (deska
  „naplocho“ → 200 mm „v materiálu“) a průsečík na hraně dvakrát. Úseky se proto nikdy
  nepárují z přechodů – každý kousek mezi průsečíky ověří `classify` bodem uprostřed;
  „na povrchu“ = `ALONG_SURFACE`, nejistý úsek se do `material_length` nepočítá.
- Šev válce/koule (`BRep_Tool.IsClosed_s(edge, face)`) a degenerované hrany na pólech nejsou
  hrany – `_edge_distance` je přeskočí, jinak by paprsek osou otvoru byl „přes hranu“.
  Dvakrát **táž** plocha v jednom bodě = šev, ne hrana.
- Na pólu koule dává `BRepGProp_Face.Normal` nulový vektor → `_outward_normal` použije
  `BRepLProp_SLProps` (orientaci plochy otočí ručně). Normála z intersectoru je jinak už
  ven z materiálu i u vnitřní stěny.
- Zakřivení z `SLProps` je vůči normále plochy (kladné = ohýbá se k ní); znaménko se srovná
  podle normály ven: + vypouklá (vnějšek trubky), − vydutá (díra).
- `BRepAlgoAPI_Common` v OCCT 8 nemá `HasErrors` – jen `IsDone`. Nespočítaný průnik =
  kolize se nevylučuje (`NO_OVERLAP`, `colliding=True`). Dotyk (objem pod 0,001 mm³) není
  kolize; vůle se měří k plochám dílu bez té, na které těleso stojí (`ignore_faces`).
- Rychlost: paprsek ~0,25–0,4 ms (průsečíky + kontrola hran + `classify` úseků; mimo obalový
  kvádr se `classify` přeskočí), kolize 3–6 ms.
- `skodacad paprsek --z -150,0,20`: argparse by zápornou trojici vzal jako volbu – `cli.
  _glue_negative` ji přilepí (`--z=-150,0,20`).

## Známé pasti (NDT sonda)

- Vůle k překážkám se měří jen k části dílu **nad** rovinou přiložení (`_clearance_above`:
  průnik dílu s velkým kvádrem 0,001 mm nad rovinou) – jinak by sonda na trubce měla „vůli
  6 mm“ k vnitřní stěně a sonda u otvoru k jeho stěně. Dotyk (vůle 0, průnik 0) je přiloženo.
- Krajní body otisku jsou 0,01 mm uvnitř (`INSET`) – hrana sondy přesně na hraně otvoru
  nesmí vyjít jako přesah. Paprsky otisku startují 1 mm nad rovinou (`LIFT`) a povrch hledají
  do 10 mm (`SEARCH_DEPTH`); hlouběji = přesah přes okraj.
- Rovná sonda ve vyduté ploše (díra) se do materiálu zařízne → kolize – je to správně.
- Přiložení je pohled (`ModelSession.ndt_placement_request`: studie, odkaz na plochu
  významem, úhel); po změně dílu se plocha najde `find_face` a sonda přiloží znovu
  (`_placement_cache` podle výsledku, sondy a úhlu). Nový model žádost smaže.
- Úhel paprsku: 0° = průmět osy +X do plochy (u plochy kolmé na X osa +Y), kladně proti
  směru hodin při pohledu zvenku (`devices.place(angle=…)`).
- Při přiložené sondě okno nezvýrazňuje oblast studie (zvýraznění kreslené navrch přes celý
  díl by sondu přebilo). Prohlížeč maže sondu s dílem (`show_part`) → `_shown_probe = None`.
- Self-test kreslí druh „probe“ (průhledné těleso) zvlášť a přikládá sondu na desku.
- V `examples/ndt/tupy_svar.json` je kořenové převýšení ($k = 6\text{ mm}, p = 1\text{ mm}$)
  součástí téhož tělesa (žádné vnitřní rozhraní na $z = 0$): paprsek dopadající do kořene
  ($x \in [-3, 3]$) tak pokračuje až na spodní plochu kořene $z = -1\text{ mm}$ (hloubka 13 mm).
- Odraz paprsku (`ut.trace_beam`) startuje v bodě dopadu `hit.point`; protože v `geometry.cast`
  začíná 1. úsek v materiálu na `0.0 <= EDGE_TOL`, není potřeba bod odrazu posouvat. Při
  nejistém dopadu (`THROUGH_EDGE`, `GRAZING`) nemá odraz jednoznačnou normálu a dráha skončí
  se `STOPPED_UNCERTAIN`.

## Známé pasti (NDT cílový objem v okně)

- Náhled cíle (`viewer.show_target`) se kreslí ve vrstvě **`Topmost`**: svar je uvnitř
  neprůhledného dílu a jeho stěny (převýšení, řez) splývají se stěnami dílu – v běžné vrstvě
  nebyl na snímku vidět. Prohlížeč ho maže s dílem (`show_part`) → `_shown_target = None`.
- `QComboBox.findData` **nenajde položku podle n-tice** (data jsou PyObject) – vrátí −1 a
  nabídka by tiše zůstala na první položce. Data položek nabídek jsou proto text
  (`target_dialog.KINDS`, klíče směrů `"+X"` …); šikmý směr ze souboru je položka navíc.
- Čísla v dialogu jsou `QLineEdit` (ne `QDoubleSpinBox`), aby se nezaokrouhlila na pevný
  počet desetinných míst – nezměněné *OK* musí vrátit identický JSON (bez kroku Zpět).
- Dialog *OK* nejdřív zavolá `check_ndt_volume_target`; když jádro cíl odmítne, dialog
  zůstane otevřený s chybou (`TargetDialog.accept`).

## Známé pasti (NDT – závazné vymezení UT)

- Každý nový UT výstup (skupina v okně, výpis `skodacad`, export protokolu) musí nést
  `ndt.UT_DISCLAIMER` beze změny slova. `tests/test_ndt_scope.py` ho porovnává s citací
  v `docs/ndt/04-zavazne-vymezeni-ut.md` – kdo změní jedno, musí změnit obojí.
- Tentýž test hledá ve všech `src/**/*.py` a README zakázaná označení („mapa
  prozvučitelnosti“, „pravděpodobnost detekce“, A-scan, B-scan) – **i v komentářích**.
  Názvy brát z `UT_ACCESS` / `UT_COVERAGE`.
- Doporučení (poloha sondy, změna dílu) optimalizují jen přístupnost a pokrytí – ne „lepší
  detekci“. Totéž platí pro AI (`assistant.RULES`).

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

## Známé pasti (macOS)

- 3D okno: Qt `winId()` je na Macu **NSView** → `Cocoa_Window(_as_capsule(handle))` (jako HWND
  ve Windows). Větve podle systému jsou jen v `viewer._initialize` a `pixel_ratio`.
- Klik myší: na Macu se poměr pixelů **měří** (šířka okna OCCT / šířka plochy v Qt) – OCCT
  v cizím NSView může počítat v bodech i v pixelech Retina. Windows a Linux beze změny
  (`devicePixelRatioF`). Self-test vypisuje „okno OCCT … Qt … poměr myši“.
- Trackpad nemá prostřední tlačítko → posun pohledu i **Shift + levé tažení** (všude).
  Qt na Macu bere `Cmd` jako `Ctrl` (Cmd+klik, Cmd+Z); fyzický Control+klik je pravý klik.
- `.app` se balí **`ditto -c -k --keepParent`** – `upload-artifact` by ztratil práva
  a symbolické odkazy uvnitř balíčku. Kontrola stažení rozbalí ZIP přes `ditto -x -k`.
- Vydání „nejnovejsi-mac“ je `--prerelease --latest=false` – jinak by `releases/latest`
  (odkaz pro Windows v README) ukázal na Mac a stažení Windows by přestalo fungovat.
- Aplikace je podepsaná jen „ad-hoc“ (PyInstaller, bez certifikátu): u uživatele ji
  Gatekeeper zablokuje, povolí se v *Soukromí a zabezpečení → Přesto otevřít*
  (macOS 15+ už bez pravého kliku). Notarizace až při rozhodnutí o distribuci.
- Mac na GitHubu (`macos-15`, virtuál bez GPU) **nevytvoří akcelerovaný NSOpenGLContext**
  („NSOpenGLContext creation failed“). `OccViewer._open_view` to na Macu zkusí znovu se
  `OpenGl_Caps.contextNoAccel` → „Apple Software Renderer / 2.1“; tím projde celý self-test
  (kreslení, výběr, mapa, řez, sonda). Self-test píše „– softwarové kreslení“.
- Bez té zálohy proces po nepovedeném OpenGL **spadl při zavírání okna** (segfault v
  `window.close()`). Nepovedené objekty OCCT proto drží `OccViewer._failed` až do konce okna;
  jestli pád spravila tahle pojistka, nebo jen to, že se OpenGL podaří, zatím nevíme (cesta
  „OpenGL nejde vůbec“ se na Macu netestuje). Při pádu vypíše workflow nativní zásobník
  z hlášení macOS (`~/Library/Logs/DiagnosticReports/SkodaCAD*.ips`).
- Kompatibilita platí, až ji uživatel ověří na MacBooku (seznam v `docs/ndt/08-navrh-macos.md`).

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
- [x] **Fáze 3** – [x] měření ve 3D (vzdálenost, rozteč, úhel, tloušťka stěny v bodě, uložená
  měření; formát verze 9), [x] NDT – mapa tloušťky stěny (formát verze 10), [x] řez modelem
  (jen pohled, export DXF/SVG), [x] tažení a přechod (formát verze 11),
  [x] normalizované díly (formát verze 12).
- [ ] **Fáze 4** – [x] AI asistent upravující model (Claude API, panel v okně, `skodacad ai`),
  [ ] omezené přímé úpravy ploch.
- [ ] **NDT modul** (plán `docs/ndt/03-implementacni-plan.md`) – [x] etapa 00 referenční díly,
  [x] etapa 01 NDT studie v modelu (formát v13, panel), [x] etapa 02 společné geometrické jádro,
  [x] 03 virtuální sonda a její přiložení (formát v14), [x] sladění se závazným vymezením UT,
  [x] 04 geometrický model UT paprsku (lom jen se zadanými předpoklady, odrazy, formát v15),
  [x] 05 ruční pohyb sondy (milník M1), [x] 06 geometrické pokrytí (sloučeno),
  [ ] 07 svar a cílová oblast: [x] 07A datový základ (sloučeno v PR #16),
  [x] 07B objemové pokrytí (sloučeno v PR #17), [ ] 07C ovládání a demonstrace
  (návrh `14-navrh-etapa-07c.md` čeká na schválení) …
- [ ] **macOS Apple Silicon** (`docs/ndt/05-podpora-macos.md`) – [x] audit knihoven, prohlížeč přes
  `Cocoa_Window`, `SkodaCAD.app` v ZIP, workflow „macOS aplikace“ (self-test na Macu GitHubu OK,
  softwarové OpenGL), [ ] ruční test na MacBooku Air M4 (Retina, trackpad, GPU).
