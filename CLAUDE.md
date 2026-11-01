# ŠkodaCAD – pravidla projektu pro AI

## Uživatel a účel

- Osobní parametrický 3D CAD **jen pro autora**, nebude se distribuovat. Licence knihoven proto
  nejsou omezením (GPL knihovny jako řešič SolveSpace jsou v pořádku).
- Autor **neprogramuje**, projekt vzniká vibecodingem. Komunikuj česky, jednoduše a bez žargonu:
  co se změnilo, proč, a jak si to může ověřit (náhled, čísla, testy). Zásadní rozhodnutí
  (architektura, nové závislosti, změna formátu) nejdřív promysli, zaznamenej a ověř.
- **Pokyn autora z 28. 10. 2026:** pokračuj v dohodnuté roadmapě samostatně, běžná
  rozhodnutí a sloučení po úspěšných kontrolách nevyžadují další souhlas. Tento pokyn
  má přednost před staršími požadavky na jednotlivá schválení v tomto souboru.
  Související kroky spojuj; v průběhu spouštěj cílené testy, úplnou sadu a kontroly
  obou systémů před sloučením (kde běží úplná sada, říká pravidlo 6 – rozhodnutí autora
  z 30. 10. 2026). Výsledky, omezení a další doporučený krok sděluj autorovi.
- **Pokyn autora z 30. 10. 2026:** na doporučení ruční přejímky P5 ve Windows
  a Excelu odpověděl „to přeskočíme“. Tyto zkoušky zůstávají neprovedené a další
  vývoj P6 neblokují; neoznačovat je za úspěšně ověřené.
- **Pokyn autora z 31. 10. 2026:** přeskočit zkoušku P6 na vlastním dílu a navázat
  ergonomií P7. Na hlavním okně si máme „dát extra záležet“; vzhled má být
  „ve stylu solid edge nebo Inventor“. P6.4 na autorském dílu zůstává neprovedené.
  [P7.1 audit a návrh](docs/p7-1-audit-a-navrh-prostredi.md) odděluje technický
  průzkum, vizuální návrhy a dosud neprovedenou autorskou přejímku.
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
- **Okno: PySide6 6.11.3 + 3D prohlížeč Open CASCADE (V3d/AIS)** (opravná aktualizace při P5.5).
  Windows `.exe` staví
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
- (17. 10. 2026, schváleno) **Opravy 1–3 z rozboru citlivosti V svaru**
  (`docs/ndt/15-rozbor-citlivosti-v-svaru.md`): hrubý běh porovnání kroků hledá s tolerancí
  `max(jemná, krok × √0,5)` (pravidlo `ndt-ut-objemove-porovnani 2`), výslovně malá
  tolerance dostane upozornění; výchozí krok cíle = šestina menšího rozměru průřezu
  (místo 4 mm z 07C); referenční test V svaru (15,18 % průřezu).
- (18. 10. 2026, schváleno) **Stejná oprava porovnání kroků pro plošnou mapu Etapy 06**
  (`docs/ndt/15-rozbor-citlivosti-v-svaru.md`, oddíl 8): `coverage.check_convergence` hledá
  v hrubém běhu s `max(jemná, auto_tolerance hrubých kroků)` (pravidlo `ndt-ut-porovnani 2`),
  malá výslovná tolerance dostane upozornění. Výpočet pokrytí ani formát se nemění.
- (18. 10. 2026, schváleno včetně doporučení 1–7) **NDT etapa 08 – knihovna sond a materiálů
  (jen UT)** (`docs/ndt/16-navrh-etapa-08.md`): `ndt/library.py` – obecné profily sond bez
  značek, materiály s rychlostmi ze dvou zdrojů (litina a titan záměrně chybí), Moje sondy
  v `~/SkodaCAD/ndt-knihovna.json` + kopie hodnot ve studii, původ hodnot, přenos úhlu
  Snellovým zákonem **jen na pokyn**, frekvence jen informativně, formát 17, tvarovaná
  předsádka (08C) odložena. Sloučeno v PR #22 (`afce8c7`); autor 18. 10. 2026 k vydání
  z `afce8c7` napsal „ok funguje to“. Tím je hotový milník M2 (etapy 06–08).
- (18. 10. 2026, schváleno včetně doporučení 1–9) **NDT etapa 09 – návrh poloh UT sondy
  a mapa problémových zón** (`docs/ndt/17-navrh-etapa-09.md`, milník M3): `ndt/access.py`
  zkouší varianty rovinná plocha × směr × β × odrazy (směry po 45° + k cíli/od cíle + kolmo
  na svar, úhel ze studie, jiné 45/60/70° jen na zaškrtnutí, odrazy 0 a 1), vyřadí
  nepřístupné s českým důvodem, pokrytí stávajícím výpočtem krokem analýzy (výchozí
  10 mm, nejvýš 40 variant), pořadí pokrytí → volnost → nejistota → jednoduchost, kombinace
  nejvýš 3 sjednocená vzorek po vzorku, mapy problémových zón (cíl, kontaktní plochy).
  Jen pohled, formát 17; *Použít variantu* = jeden krok Zpět; zakřivené plochy se
  nezkoušejí; CLI `skodacad polohy`, AI bez nového nástroje, souběh procesů odložen.
  Sloučeno v PR #23 (`bbc207f`); autor 18. 10. 2026 k vydání z `bbc207f` napsal „ok funguje
  to“. Otázka „místa pod sondou, když je kontaktní plocha i cílem“ rozhodnuta 19. 10. 2026:
  na ploše přiložení se **nepočítá zásah 1. ramene** (paprsek z ní jen vychází), odražené
  rameno, které se na plochu vrátí, ano (`coverage._on_contact`, algoritmus `ndt-ut-pokryti 2`;
  sloučeno v PR #25, autor k vydání z `3297983` napsal „ok, funguje to“).
- (18. 10. 2026, schváleno včetně doporučení 1–10) **NDT etapa 10 – plán dráhy UT sondy**
  (`docs/ndt/18-navrh-etapa-10.md`, dokončí milník M3): `ndt/plan.py` – průchod = varianta
  etapy 09, řádky cik-cak s roztečí (výchozí 5 mm) ve vzoru *k cíli a zpět* nebo *podél*
  (automaticky: méně přestavení → kratší → méně řádků), úseky jen kde se sonda vejde a paprsek
  míří k cíli, kontrola po 1 mm, přesun po povrchu jen přes platné polohy, jinak přestavení
  s nájezdem kolmo k ploše (výchozí 20 mm), zakázané zóny = kvádry (jen pro plán), hodnocení
  bez skóre (pokrytí, délka, přestavení, boční rezerva, volno, volitelně odolnost), pokrytí
  stávajícím výpočtem v režimu `plan` (pás šířky rozteče = spojitý pojezd), přehrávání,
  tabulka poloh, CSV. Plán a zóny ve studii (**formát 18**), plán se sám nepřepočítá ani
  neposune; ruční úpravy úseků = kroky Zpět; CLI `skodacad draha`, AI bez nového nástroje.
  Sloučeno v PR #24 (`5e59c28`); autor 19. 10. 2026 k vydání z `5e59c28` napsal „ok funguje
  to“. Tím je hotový milník M3 (etapy 09–10).
- (19. 10. 2026, schváleno včetně doporučení 1–9) **NDT etapa 11 – PT, přístupnost povrchu
  pro kapilární zkoušku** (`docs/ndt/19-navrh-etapa-11.md`, otevírá milník M4): závazné
  vymezení PT `docs/ndt/20-vymezeni-pt.md` s povinným upozorněním `ndt.PT_DISCLAIMER`
  (jen geometrická přístupnost – ne smáčivost, vzlínání, citlivost ani detekovatelnost vad).
  `ndt/pt.py`: vzorky = síť ploch PT studie, pevná sada 65 směrů, tři kontroly – **nástřik**
  (volný paprsek do 60° / omezeně do 85° od kolmice), **otření** nástrojem (kulička + dřík
  s libovolným sklonem, hlavní Ø 10 a jemný Ø 3, dřík 100 mm, přesná kolize OCCT), **prohlídka**
  (≥ 30° k povrchu, oko do 600 mm s volnou koulí Ø 50 mm; ASME V čl. 9, BINDT CP25) – plus
  upozornění úzká mezera a otevřenost pod 10 %; čtyři stavy (přístupné / omezené / nepřístupné /
  nelze spolehlivě vyhodnotit) s českými důvody. Postup čištění otřením nebo oplachem. Zvolené
  hodnoty jsou označené „zvoleno pro výpočet“. Nastavení `pt` ve studii (**formát 19**), mapa
  jen pohled. Referenční díl 9 `sterbina.json`, PT studie i v kapse. Okno, CSV, CLI
  `skodacad kapilarni`, AI bez nového nástroje. Sloučeno v PR #25 (`3297983`, spolu
  s rozhodnutím otázky z etapy 09); autor 19. 10. 2026 k vydání z `3297983` napsal „ok,
  funguje to“.
- (19. 10. 2026, schváleno včetně doporučení 1–10) **NDT etapa 12 – MT, přiložení jha
  a směry magnetizace** (`docs/ndt/21-navrh-etapa-12.md`, milník M4): závazné vymezení MT
  `docs/ndt/22-vymezeni-mt.md` s povinným upozorněním `ndt.MT_DISCLAIMER` (jen geometrie –
  ne intenzita ani rozložení pole, citlivost ani detekovatelnost vad). Jen jho: virtuální
  kloubové jho (póly Ø 20, výška 60, tělo 40 × 40 + 20), místo pólu = první dotyk kružnice
  o poloměru d/2 sklápěné od kolmice, pól dosedá jako přímá sonda (mezera do 1 mm),
  nohy nejvýš 90°, spojnice 10 mm nad povrchem bez stěny, kolize těla; rozteč 100 mm se
  zálohou 75 mm (ISO 17638); účinná oblast (d − 50) × d/2, orientační směr pole, 8 směrů
  po 22,5°, všechny orientace vad = dva směry aspoň 60° od sebe (ISO 9934-1, ISO 17638);
  nanesení a prohlídka z PT; kontrola feromagnetického materiálu (nerez a neuvedený jen
  s potvrzením). Nastavení `mt` ve studii (**formát 20**), mapa jen pohled. Okno (mapa,
  směry, klik, Ukázat jho, Přiložit jho sem), CSV, CLI `skodacad magneticka`, AI bez
  nového nástroje. Sloučeno v PR #26 (`5cb6ef4`); autor 19. 10. 2026 k vydání z `5cb6ef4`
  napsal „ok, funguje to“.
- (19. 10. 2026, schváleno včetně doporučení 1–10) **NDT etapa 13 – RT, geometrie projekce
  a expozice** (`docs/ndt/23-navrh-etapa-13.md`, dokončí milník M4): závazné vymezení RT
  `docs/ndt/24-vymezeni-rt.md` s povinným upozorněním `ndt.RT_DISCLAIMER` (jen geometrie – ne
  dávka ani radiační ochrana, expozice, kvalita obrazu, IQI, citlivost ani detekovatelnost
  vad). Bodový zdroj (ohnisko 3 mm, kužel 40°, tělo Ø 120 × 300, f = 500 – zvoleno) a plochý
  tuhý detektor (film 10 × 24 cm) přiložený na plochu, kudy střední paprsek vystupuje
  (odsunutí při nárazu), nebo volně; kolize přesným průnikem. Pro místa oblasti (plochy nebo
  objem svaru): svazek, detektor, prozařovaná tloušťka (všechny úseky), poměr k tloušťce na
  středu svazku 1,1 (B) / 1,2 (A) s ruční jmenovitou tloušťkou, f_min = 7,5 / 15 · d ·
  b^(2/3) (b < 1,2 t → t), zvětšení a neostrost informativně, překryv obrazů. Náhled
  prozařované tloušťky (není radiografický snímek), víc projekcí ručně se sjednocením;
  ohebný film a automatický plán projekcí později. Nastavení a projekce ve studii
  (**formát 21**), výsledky jen pohled. Okno, CSV, CLI `skodacad radiografie`, AI bez
  nového nástroje. Sloučeno v PR #27 (`43187c8`); ruční zkouška autora po vydání čeká.
- (20. 10. 2026, schváleno včetně doporučení 1–10) **NDT etapa 14 – společný předběžný NDT
  audit** (`docs/ndt/25-navrh-etapa-14.md`, otevírá milník M5): jedno tlačítko spustí
  **stávající** výpočty všech studií dílu s jejich uloženým nastavením – nic nového nepočítá,
  model nemění, metodu ani normativní postup nevybírá, nikdy „vyhovuje“. Výstup se jmenuje
  „Předběžný NDT audit – zpráva o geometrickém posouzení“ (ne protokol o zkoušce), nese
  obecné upozornění a povinná upozornění všech zahrnutých metod doslova. UT: uložený plán
  dráhy, jinak výsledek z tohoto sezení, jinak neprovedeno; návrh poloh jen na zaškrtnutí
  (deska přes 22 min). Stavy spočítáno / neprovedeno / nedostupné s důvodem, „nelze
  spolehlivě vyhodnotit“ vždy zvlášť; zastaralou studii audit nepotvrzuje. Problémová místa
  = sousední body se stejným stavem (do 1,6 × krok) s polohou, velikostí a důvody s podílem.
  Dohledatelnost: záznam studie (JSON), verze algoritmů, kroky, otisk dílu, sestavení
  aplikace (commit z GitHub Actions). Export složky: HTML, CSV míst, podrobná CSV studií;
  z okna PDF (Qt) a obrázky 3D. Mapa tloušťky jen s nastavenou mezí. Výsledek je pohled,
  formát zůstává 21. Okno, CLI `skodacad audit`, AI bez nového nástroje s pravidlem.
  Sloučeno v PR #28 (`94a78d7`); ruční zkouška autora po vydání čeká.
- (20. 10. 2026, schváleno včetně doporučení 1–12) **NDT etapa 15 – konstrukční návrhy bez
  automatické změny dílu** (`docs/ndt/26-navrh-etapa-15.md`, dokončí milník M5): varianty =
  1–3 povolené **číselné parametry** (výčet nebo rozsah, všechny kombinace, nejvýš 24, pevné
  pořadí); **zamčené rozměry = uložená měření** (změna nad 0,01 mm / 0,01° nebo měření, které
  nejde spočítat → neprojde) a zamčené parametry (hlídá výrazy); podmínky = uložené měření +
  mez + důvod, limit změny hmotnosti, volitelně mapa tloušťky; bez zámků a podmínek je výsledek
  „informativní“. Každá varianta na **kopii modelu**, oblast studie znovu ukotvená jen v kopii,
  nastavení studie beze změny, **kroky sítě zamčené podle původního dílu**; cíle svaru,
  projekce RT a zóny zůstávají. UT jen s uloženým plánem (sestaví se znovu se stejnými
  průchody; volba jen ověřit), návrh poloh pro varianty ne. Cílová studie vždy, ostatní
  volitelně; neprošlé informativně. Pořadí bez skóre (prošlé → % dobrého stavu → nejisté →
  menší změna parametrů → hmotnosti), vždy i mm² / mm³, upozornění při změně oblasti nad 5 %,
  původní díl první; ověření pořadí polovičním krokem (původní + 3 nejlepší). Náhled je pohled,
  *Použít variantu…* jen u prošlé po potvrzení (jeden krok Zpět), *Uložit variantu jako…*
  nový soubor. Zadání v `ndt.design` (**formát 22**), výsledky pohled; zpráva „Návrh ke
  konstruktérskému posouzení“ (`DESIGN_NOTE`) HTML/CSV, z okna PDF; panel, `skodacad navrh`,
  AI s pravidlem bez nástroje; referenční díl 10 `navrh_kapsa.json`. Jako první krok oprava:
  tvar skici s nulovou plochou = česká chyba (dřív tiše zahodil i ostatní tvary skici).

- (25. 10. 2026, schváleno G1–G8 a H1–H8) **Přímé úpravy ploch – P2.3** (návrhy
  `docs/p2-1-navrh-rozsahu-primeho-modelovani.md`, `docs/p2-2-navrh-zapisu-prime-upravy.md`):
  prvky `move_face` (posun rovinné plochy, `distance`) a `face_diameter` (průměr válcové
  plochy, `diameter`) mění hotový díl na konci stromu (`direct_edit.py`, jádro
  `BRepOffset_MakeOffset` + `SetOffsetOnFace`). Odkaz `face` podle P1.3 bez pevného poloměru,
  povinný `origin` = pojistka původu plochy. Formát verze 23. V okně jen zobrazení a změna
  čísla; P2.4 doplňuje výběr ve 3D, náhled a návrhový nástroj AI s potvrzením uživatele.
- (28. 10. 2026, autor schválil sloučení PR #46 a #47) **Import STEP – P3** (návrh
  `docs/p3-2-navrh-ulozeni-step.md`): prvek `step_import` s vloženým zdrojem (bajty STEP
  + SHA-256, obnova jen totožných bajtů), jeden platný uzavřený díl v mm, m nebo palcích;
  kontrola v izolovaném pomocném procesu s dohledem času a paměti (soubor nejvýš 16 MiB).
  Sestavy, více těles, neznámé jednotky a ohlášené opravy jádra se odmítají. **Formát 24.**
- (28. 10. 2026, V1–V9 schválené autorem, další kroky podle pokynu z 28. 10.) **Pracovní
  výkres – P4** (`docs/p4-1-navrh-vykresu.md` až `p4-6-…`): pohledy zepředu, shora a zprava
  (evropské promítání) a jeden osový řez A–A se šrafami; kóty vázané na model (celkový
  rozměr, vzdálenost dvou rovnoběžných ploch, průměr či poloměr otvoru) s umístěním
  a odchylkami; popisové pole, list A4/A3 a měřítko; export PDF/DXF s kontrolní úsečkou
  50 mm; upozornění na možné překrytí kót. Uloženo v `drawing`: **formát 25** kóty,
  **26** tolerance, **27** popisové pole. Není to výrobní výkres ani doklad shody s normou.
- (29. 10. 2026, zadání autora „udělej skrývání pohledů“, podle pokynu z 28. 10.)
  **Skryté pohledy výkresu** – `drawing.views` (neprázdný seznam z front/top/right v pořadí
  na listu; bez klíče všechny tři), **formát 28**. Starší aplikace by skrytý pohled tiše
  ukázala, proto nová verze. List a měřítko (`paper`, `scale`, verze 25) se od téhož dne
  opravdu ukládají (`set_drawing_sheet`); formát se tím neměnil.

- (30. 10. 2026, schváleno S1–S12) **Sestavy – P5.1** (`docs/p5-1-navrh-formatu-sestav.md`):
  sestava = samostatný soubor `"kind": "assembly"`, **formát 29** (díly dál ve verzi 24–28);
  komponenty (`id`, `name`, `source.path` vůči složce sestavy s `/` a `..` jen na začátku,
  informativní `source.fingerprint`, `placement` = posun mm + úhly kolem pevných os X→Y→Z,
  `fixed`) na soubory dílů jen odkazují, sestava díly nikdy nepřepisuje. Neznámý klíč =
  chyba. Stavy ok / chybí / nečitelná / chyba dílu / cyklus, záznam se nikdy nesmaže;
  export jen úplné sestavy. Podsestavy, nejvýš 8 úrovní a 1 000 komponent. NDT, výkres
  a měření zůstávají v dílu. Zdroj se staví jednou, kopie sdílí tvar.

- (30. 10. 2026, schváleno M1–M12) **Vazby v sestavě – P5.3** (`docs/p5-3-navrh-vazeb.md`):
  dotyk, zarovnání, vzdálenost (i výrazem) a souosost mezi plochami komponent (odkaz
  významem v souřadnicích dílu, nebo základní rovina/osa dílu); vlastní řešič tuhých těles
  nad numpy po skupinách propojených komponent, nejmenší posun z dnešní polohy, pokus
  o obrácení o 180°, stupně volnosti z hodnosti; spor = úprava se nepřijme, spor po změně
  dílu = polohy zůstanou a sestava je neúplná; pevné a výrazové polohy řešič neposouvá;
  výsledek do `placement` (jeden krok Zpět); **formát 30** jen pro sestavy s vazbami.
  Sloučeno v PR #65 (`822e3e8`); ruční zkouška vazeb autorem čeká.

- (30. 10. 2026, schváleno K1–K12) **Kontroly sestavy – P5.4** (`docs/p5-4-navrh-kontrol.md`):
  kolize všech dvojic kopií (síto obálek, přesný nedestruktivní průnik, kolize nad 0,001 mm³,
  nespočítaný průnik = „nelze ověřit“), vůle = nejmenší vzdálenost pod mezí (výchozí 0,5 mm),
  dotyk není vada; přijatá kolize s poznámkou a objemem (znovu kolize při změně nad 1 %);
  **formát 31** jen se `checks`; výpočet na tlačítko (v okně na pozadí); rozbalený kusovník
  (řádek = soubor dílu, CSV jen z úplné sestavy); export STEP úplné sestavy se stromem
  výrobek = soubor dílu / kopie = id, názvy bez diakritiky; v sestavě se NDT nepočítá.

- (30. 10. 2026, rozhodnutí autora „Ok“) **Méně zdvojeného testování**: workflow
  „Windows aplikace“ a „macOS aplikace“ spouští `push` jen ve větvi `main` (vydání); pracovní
  větve kontroluje jen `pull_request` – dřív běželo každé nahrání dvakrát nad stejným kódem.
  Úplná sada `pytest -q` běží u každého PR na Windows i macOS; v cloudu se pouští celá jen
  u změn společného jádra (pravidlo 6), jinak jen testy dotčené oblasti.

- (31. 10. 2026, pokyn autora pokračovat) **P6.7 řízený obdélníkový přechod**
  (`docs/p6-7-rizeny-prechod.md`): `guided_loft.py`, prvek `guided_loft`, dvě osově
  orientované XY obdélníkové skici, čtyři kubická rohová vodítka se dvěma XY posuny
  rukojetí. Plné těleso new/add/cut; konvexita po celém intervalu Bernsteinovými mezemi
  s dělením, neprůkazný případ odmítnout. Vlastní čela, P1, analytický objem a body
  konečného pláště. Formát **34** jen s tímto prvkem; staré díly zůstávají v24–33.
  Formulář A–D a vodítka ve 3D přes ModelSession, příklad `rizeny_prechod.json`.
  Kruhy, zaoblení, šikmá čela a duté stěny mimo tento rozsah. Výsledky ověření v PR.

- (31. 10. 2026, pokyn autora) **P6.8 tažení rukojetí ve 3D**
  (`docs/p6-8-tazeni-rukojeti.md`): vybrané vodítko, dvě větší rukojeti v XY při pevné
  výšce, náhled jen čar. Session ověří celý kandidát v pomocném procesu a přijme ho
  přes `_change(computed_result=...)` jako jeden krok, bez druhého přepočtu. Esc,
  ztráta fokusu a přerušení návrh neukládají; selhání zachová původní historii.
  Konverze myši zohledňuje Retinu; téměř boční či překryté body se odmítnou.
  Formát zůstává 34 a výrazy zachovávají parametry. Výsledky kontrol v PR.

- (31. 10. 2026, pokyn autora) **P6.9 nastavitelný krok tažení**
  (`docs/p6-9-krok-tazeni.md`): volba nad vodítky, 0 = Volně (výchozí),
  0,001–1000 mm, posun po X/Y relativně k začátku tahu; poloviny od nuly.
  Stejná funkce pro náhled a uvolnění, desítkové zaokrouhlení bez zbytků v JSON.
  Čistě GUI preference okna, drží se při přepínání a historii, neukládá se do modelu.
  Formát 34 a session/jádro beze změny. Změna kroku rozpracovaný tah zruší.
  Cílené místní testy a úplné kontroly obou systémů v implementačním PR.

- (31. 10. 2026, pokyn autora) **P6.10 omezení směru tažení**
  (`docs/p6-10-smer-tazeni.md`): volba XY / Pouze X / Pouze Y v osách dílu,
  použití stávajícího kroku, pevná druhá souřadnice a Z. Pro jednu osu parametr
  nejbližšího bodu osy vůči pohledovému paprsku, proto X funguje i zepředu a Y zprava;
  zaniklá osa se odmítne. Změna směru tah zruší. Preference otevřeného okna,
  ne dokumentu; formát 34 a jádro/session beze změny. Výsledky kontrol v PR.

## Architektura (`src/skodacad/`)

Etapa 06 (schválena autorem, sloučena v PR #15): `ndt/coverage.py` počítá plochy
nebo body z pojezdu `face`/`line`, tři stavy, CSV a citlivost na krok. `ModelSession` drží
mapu pouze jako pohled; výpočet v okně používá `BackgroundRebuilder` a jde zrušit. Formát
zůstává 15. `skodacad pokryti` vyžaduje `--plocha` a cíle (`--cil`, `--cil-plocha`, `--studie`).
Numerická tolerance nesmí obejít otisk, kolizi ani rezervu: na rovině se mezilehlá poloha
sondy skutečně přiloží a paprsek znovu spočítá. Na zakřivené ploše je pouhá numerická
blízkost nejistá. Citlivost porovnává krok a 2× krok; hrubý běh hledá s `max(jemná tolerance,
`auto_tolerance` hrubých kroků)` (oprava 18. 10. 2026); v panelu *Ověřit citlivost na krok*
i pro plochy (`compute_ndt_coverage(convergence=True)`, i v pomocném procesu) a CLI
`--konvergence`. Povinné upozornění
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
sloučeno do `main` v PR #19 na pokyn autora bez ruční zkoušky). 07C.1 hotovo:
`gui/target_dialog.py` (editor svaru/hranolu, směry jen ±X/±Y/±Z, šikmý směr ze souboru se zachová,
nákres průřezu Qt), `ModelSession.check_ndt_volume_target` (bez změny modelu), `ndt_target_outline`,
`ndt_frame_from_edge`, `ndt_target_preview` (v řezu rozříznutý), podnabídka *NDT – cílové
objemy*. 07C.2 hotovo: panel zná krok cíle, toleranci (automaticky / číslo) a citlivost na
krok (`compute_ndt_coverage(convergence=True)`, i v pomocném procesu), odhad před spuštěním
`ndt_coverage_estimate` se stejnými ochranami jako 07B; nepovedené porovnání nechá jemný
výsledek a napíše „nepodařilo ověřit“. 07C.3 hotovo: `ndt/volume_drawing.py` obarví povrch
cíle (i rozříznutého) podle buněk 07B, `VolumeSample.piece_bounds` rozliší kusy v buňce,
nejednoznačné = šedě; *Průřez svarem* = `set_section_target`. Formát zůstává 16. Po
sloučení autor 17. 10. 2026 k vydání z `e898575` napsal „ok funguje to“. Rozbor citlivosti
V svaru (`docs/ndt/15-rozbor-citlivosti-v-svaru.md`): reference 12,2 %; na rovinném pojezdu je
tolerance jen poloměr hledání (zásah se přesně ověří), porovnávací běh 07B ji ale bere
z jemného běhu → nenajde část paprsků; buňka 4 mm je pro 12mm plech velká. Opravy 1–3
schválené a provedené (`auto_tolerance`, `recommended_target_step`, `CONVERGENCE_RULE`,
`tests/test_ndt_volume_reference.py`); totéž pravidlo má od 18. 10. 2026 i plošná mapa
Etapy 06 (`coverage.CONVERGENCE_RULE`, sdílená `coverage.auto_tolerance`).
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
| `direct_edit.py` | přímé úpravy ploch (P2): `move_face`, `set_diameter` (posun jen vybrané plochy jádrem, kontroly vstupu G6 a výsledku G5), pojistka původu `face_origin` / `check_origin` nad `BuildContext.history` |
| `geometry_validation.py` | společná kontrola všech objemových složek a účinku operace; místní číselné výsledky, bez oprav tvaru a bez změny receptu |
| `rebuild.py` | přepočet seznamu prvků, stavy `ok` / `error` / `skipped`, záznam operací prvků |
| `properties.py`, `materials.py` | objem, povrch, hmotnost, těžiště |
| `export.py` | STEP, STL, 3MF, GLB, SVG náhled |
| `step_probe.py`, `step_task.py`, `step_source.py` | import STEP (P3): kontrola souboru (jednotky, počet těles, platnost, ohlášené opravy; nejvýš 16 MiB), zrušitelný izolovaný pomocný proces s dohledem času a paměti (`StepTask`), vložené bajty se SHA-256 a obnova zdroje; prvek `step_import` je ve `features.py` |
| `drawing_data.py` | kontrola uložených dat výkresu (`drawing`: list, měřítko, pohledy, řez, popisové pole, kóty s umístěním a tolerancí) |
| `drawing_geometry.py` | pohledy zepředu, shora a zprava a osový řez se šrafami; skrývání čar OCCT na kopii se zapsanou plynulostí hran |
| `drawing_dimensions.py` | vazby kót na model (celkový rozměr, vzdálenost rovnoběžných ploch, průměr/poloměr otvoru) s pojistkou původu a receptu |
| `drawing_sheet.py`, `drawing_section_mark.py` | rozvržení pohledů na listu A4/A3 v měřítku (evropské promítání), označení roviny řezu A–A |
| `drawing_annotations.py`, `drawing_collisions.py` | kóty v pohledech (umístění, odchylky, náhradní pohled za skrytý), odhad možného překrytí kót |
| `drawing_export.py` | export jednostránkového pracovního výkresu do PDF/DXF (kontrolní úsečka 50 mm, popisové pole; při chybě zůstane starý soubor) |
| `assembly.py` | sestava (P5, formát 29, s vazbami 30, s kontrolami 31): `Assembly`, `Component`, `Constraint` (dotyk / zarovnání / vzdálenost / souosost, `check_reference`: plocha `plane`/`cylinder` bez poloměru, rovina `XY`/`XZ`/`YZ`, osa), kontrola struktury (neznámý klíč = chyba, `check_path` podle S4), `Checks` (mez vůle, přijaté kolize `Accepted` s cestami id a objemem), načtení a uložení přes `document.write_json`, `fingerprint` receptu podsestavy (vazby jen když jsou) |
| `assembly_check.py` | kontroly sestavy (P5.4): `check` (síto obálek s rezervou meze vůle, kolize nedestruktivním průnikem nad 0,001 mm³ s objemem a těžištěm, nespočítané = „nelze ověřit“, dotyk do 1e-6 mm, vůle pod mezí), `CheckResult.with_accepted` (přijaté kolize bez nového výpočtu, změna nad 1 % = znovu kolize), `geometry_key`, kusovník `bill` / `write_bill` (CSV), `export_step` (XCAF strom, názvy `ascii_name`) |
| `assembly_solve.py` | řešič vazeb (P5.3): tuhá tělesa nad numpy, `groups` (skupiny propojených komponent, kotva bez pevné), LM s krokem nejmenší normy v měřítku mm a návratem volných pohybů (`_pull_back`), obrácení o 180° (`_with_flips`), `Freedom` z jádra Jacobiho matice, `SATISFIED` 1e-6 mm |
| `assembly_build.py` | sestavení sestavy: `locate` (přesná velikost písmen, jinak upozornění), `read_source` (díl / podsestava), stavy `ComponentStatus` (ok / missing / unreadable / error / cycle), otočení kolem pevných os X→Y→Z (`rotation_matrix`, `angles_of`, `turned`, `location`), `Cache` dílů podle souboru a SHA-256 bajtů, `build` → `AssemblyResult` (kopie `Instance`, objem, hmotnost, obálka, `complete`, stavy vazeb `ConstraintStatus`, nové polohy `solved`, tvary komponent `local_shapes`, polohy komponent `locations`, tvar bez polohy `Instance.base`), po úrovních nejdřív díly ve vlastních souřadnicích, pak `_solve_level`, pak umístění; `feature_of` (bod a směr odkazu), `reachable` (kontrola cyklu) |
| `assembly_session.py` | `AssemblySession` – sestava bez okna: nová (hned uložená), otevřít, uložit (otisky zdrojů; *Uložit jako* přepočítá cesty), vložit díl/podsestavu, smazat, přejmenovat, poloha, posun, otočení ±90°, pevná, *Najít soubor* s upozorněním na jiný recept, parametry, Zpět/Znovu; vazby `add_constraint` / `set_constraint` / `remove_constraint` (spor = nepřijato), polohy z řešiče v téže změně, `notice` po změně dílu, `reference_at` (kliknutá plocha → odkaz v souřadnicích dílu), `gap`, `constraint_kinds`, `constraint_faces`; kontroly `set_clearance`, `accept_collision` / `unaccept_collision` (krok Zpět), `check`, `check_key`, `store_check`, `last_check` (pohled), `bill`, `write_bill`, `export_step` |
| `cli.py` | příkazová řádka `skodacad build`, `ai`, `paprsek`, `sonda`, `pokryti`, `polohy` (návrh poloh UT sondy), `draha` (plán dráhy UT sondy), `kapilarni` (mapa PT), `magneticka` (mapa MT), `radiografie` (geometrie projekce RT), `audit` (předběžný NDT audit) a `sestava` (komponenty, stav, volnost, vazby, objem, hmotnost; `--kontrola`, `--vule`, `--kusovnik`, `--export`) |
| `assistant.py` | AI asistent: nastavení a klíč, nástroje nad `ModelSession` (`ModelTools`), souhrn přepočtu pro AI, systémový pokyn (README „Formát modelu“ + schéma + ukázky), rozhovor s Claude (`Assistant.ask`), cena, `offline_client` (přehrané odpovědi bez sítě) |
| `session.py` | `ModelSession` – otevřený model: úpravy prvků a parametrů, Zpět/Znovu, uložení, export (bez Qt); s `runner` přepočet na pozadí (`poll`, `wait`, `cancel`) |
| `worker.py` | přepočet v pomocném procesu (`BackgroundRebuilder`), přenos výsledku přes BinTools; mapa pokrytí, návrh poloh, plán dráhy (`submit_plan`), mapa PT (`submit_pt`), mapa MT (`submit_mt`), mapa RT (`submit_rt`) a kontrola sestavy (`submit_assembly_check`), průběžné zprávy `Finished.update` |
| `schema.py` | popis polí každého prvku a tvaru skici (česky) + výchozí hodnoty nových prvků |
| `inspection.py` | český popis vybrané plochy/hrany |
| `measure.py` | měření: rozměry, vzdálenost, rozteč, úhel, tloušťka stěny; uložená měření (odkazy významem, `evaluate`); `RayCaster` (paprsek s pravidlem koncového echa) |
| `thickness_map.py` | mapa tloušťky stěny: síť povrchu (půlení nejdelší strany v u, v), tloušťka v těžištích, barvy, souhrn, CSV |
| `section.py` | řez modelem: rovina řezu, přesný řez, plochy řezu, export DXF/SVG, ořez sítě mapy rovinou |
| `ndt/__init__.py`, `ndt/study.py` | NDT: upozornění na předběžnost a povinné upozornění UT (`UT_DISCLAIMER`, názvy `UT_ACCESS`, `UT_COVERAGE`); studie (kontrola struktury, otisk dílu, stav po přepočtu `StudyResult`, nová studie, oblast z výběru, znovuukotvení, kopie) |
| `ndt/geometry.py` | NDT geometrické jádro (`PartGeometry`): `cast` (průsečíky, úseky v materiálu, jistota), `classify`, `surface_at` (normála, zakřivení), `visible`, `collision` (průnik, vůle), `faces_of`; konstanty `ALGORITHM`, tolerance |
| `ndt/devices.py` | virtuální sonda (`Probe` přímá/úhlová, `beam_angle`, `bounces`, meze), `place` (souřadný systém, mezera a přesah z paprsků otisku, kolize, vůle nad rovinou přiložení, stavy), `scan_line` (posun po přímce) |
| `ndt/library.py` | knihovna NDT (etapa 08, jen UT): vestavěné materiály `MATERIALS` (rychlosti ze 2 zdrojů, zdroje v docstringu) a obecné sondy `PROBES`, `transfer_angle` / `check_angle` / `transferred` (přepočet úhlu jen na pokyn), `describe` pro výstupy, Moje sondy (`ndt-knihovna.json`) |
| `ndt/access.py` | návrh poloh UT sondy (etapa 09): `Analysis` (varianty, 1. a 2. kolo `prepare`, 3. kolo `evaluate` stávajícím výpočtem pokrytí, `run`), `finish` (pořadí `rank`, kombinace, `union` vzorek po vzorku), `AccessResult.summary` / `write_csv`, mapa kontaktních ploch `ContactPoint` |
| `ndt/plan.py` | plán dráhy UT sondy (etapa 10): `Planner` (`build` – mřížka, dosah, úseky, cik-cak, oprava po 1 mm; `check` – kroky jízdy `PlanStep`, nájezd, ústup po projeté dráze, tabulka `PlanPosition`, boční rezerva; `coverage` – režim `plan`, sjednocení průchodů, srovnání, odolnost; `run`/`evaluate`), `Plan`/`PlanPass`/`PlanSegment` (JSON), `Zone`, `PlanResult.summary`/`write_csv` |
| `ndt/pt.py` | PT – geometrická přístupnost povrchu (etapa 11): `PtSettings` (nástroje, úhly, oko, postup čištění), `Sampler` (nástřik, otření nástrojem – kulička + dřík s přesným průnikem –, prohlídka s okem, mezera, otevřenost), `compute` / `estimate`, `PtMap` (souhrn, CSV, síť po kontrolách, `nearest`, `describe`), `study_faces`, `self_check` |
| `ndt/mt.py` | MT – přiložení jha a směry magnetizace (etapa 12): `MtSettings`, `material_status` (feromagnetický materiál), `Yoker` (místa pólů kružnicí, stěna, póly jako přímá sonda bez vůle, nohy, přesná kolize nohou a těla), `place_yoke`, `compute` / `estimate` / `check_points` (středy na mřížce ploch v dosahu, 8 směrů, dohledání hranic a rohů), `MtMap` (souhrn, CSV, síť po směrech, `nearest`, `describe`), `study_faces`, `self_check`; nanesení a prohlídka přes `pt.Sampler.access` |
| `ndt/rt.py` | RT – geometrie projekce (etapa 13): `RtSettings` a `Projection` (zaměřený bod, směr ke zdroji, vzdálenost, detektor na ploše / volně, jmenovitá tloušťka), `tilted` / `angles_of`, `prepare` (zdroj, střední paprsek, přiložení detektoru s odsunutím, kolize těla zdroje a detektoru → `Setup`), `compute` / `estimate` / `check_points` / `image_of`, `RtMap` (souhrn, CSV, síť po projekcích, `nearest`, `describe`), `RtImage` (náhled prozařované tloušťky), `study_target`, `self_check` |
| `ndt/audit.py` | předběžný NDT audit (etapa 14): `layer_of` (výsledek metody → jednotná místa `Spot`: UT pokrytí plochy/objem, návrh poloh, plán, PT, MT, RT, mapa tloušťky), `find_places` (spojení sousedních míst se stejným stavem do 1,6 × krok → `Place` s důvody a podílem), `AuditEntry` (studie: spočítáno / neprovedeno / nedostupné), `AuditResult` (souhrn, `write_csv`, `html`, `write_folder`, náhledy RT); `AuditItem` (co se spočítá, odhad, důvod proč ne) |
| `ndt/design.py` | konstrukční návrh pro NDT (etapa 15): `Design` (zadání, `check`, `combinations`), `baseline` (původní díl, zamčené kroky, odhad), `evaluate` (varianta na kopii modelu: přepočet, zámky a podmínky `Check`, studie znovu ukotvená, výpočet metody), `rank_and_verify` (pořadí, ověření polovičním krokem), `run`, `DesignResult` (závěr, `row`, souhrn, CSV, HTML); `DESIGN_NOTE` |
| `buildinfo.py` | verze, sestavení (commit z GitHub Actions v `_build.py`, při vývoji `git describe`) a knihovny – do zprávy auditu |
| `ndt/ut.py` | geometrický model UT paprsku: `refract` (Snellův zákon s výslovnými rychlostmi, kritický úhel), `trace_beam` (`BeamPath`, `BeamLeg`, zrcadlové odrazy na plochách, půlkrok, celý krok, jistota, předpoklady) |
| `gui/app.py` | spuštění okna, log `~/SkodaCAD/skodacad.log`, `--self-test`, `--screenshot` |
| `gui/main_window.py` | hlavní okno: díl, parametry, strom prvků, vlastnosti, menu, panely Měření, Mapa tloušťky a Řez |
| `gui/feature_editor.py` | panel „Úprava prvku“ – formuláře sestavené ze `schema.py` |
| `gui/sketcher.py` | skicář – 2D editor obrysu (kreslení, vazby, kóty, stav určenosti) |
| `gui/ndt_panel.py` | panel NDT: seznam studií se stavem, nová z výběru, úpravy, potvrzení, ověření, zvýraznění oblasti; skupina *Návrh poloh sondy* (etapa 09: volby, odhad, průběh, tabulka, kombinace, Ukázat/Použít, mapa ve 3D); skupina *Plán dráhy sondy* (etapa 10: sestavení, stav, tabulka úseků s přínosem, úpravy, zóny, přehrávání); u PT studie místo skupin sondy skupina *Přístupnost povrchu pro PT* (etapa 11: nastavení, odhad, výpočet, přepínač kontrol, souhrn, důvod místa po kliknutí, CSV); u MT studie skupina *Přiložení jha a směry magnetizace* (etapa 12: materiál, nastavení, odhad, výpočet, přepínač celkem / pole 0°–135° / nanesení / prohlídka, souhrn, důvod místa, Ukázat jho, Přiložit jho sem s natočením, CSV); u RT studie skupina *Geometrie projekce RT* (etapa 13, `gui/rt_box.py`) |
| `gui/audit_panel.py` | panel *NDT audit* (etapa 14): seznam studií se zaškrtávátky a odhadem (`AuditItem`), volba návrhu poloh u UT, spuštění na pozadí a zastavení, přehled, tabulka míst, klik = studie v panelu NDT + mapa ve 3D (`focus`, kulička `MARK`), export složky + PDF (`write_pdf`, QTextDocument + QPdfWriter) + obrázky map z 3D (`capture_images`) |
| `gui/rt_box.py` | skupina *Geometrie projekce RT* v panelu NDT (etapa 13): nastavení, seznam projekcí (Zdroj nad vybrané místo, Upravit, Kopírovat posunutou, Smazat), výpočet na pozadí, přepínač mapy celkem / projekce, klik do mapy, náhled prozařované tloušťky (QImage z `rt.preview_rgb`, PNG), CSV; `drawing()` = zdroj a detektor vybrané projekce pro prohlížeč |
| `gui/rt_dialog.py` | dialogy *Nastavení RT…* a *Upravit projekci…* (čísla jako text bez zaokrouhlení, sklon a natočení vůči kolmici k ploše nebo nejbližší ose – nezměněné úhly = původní směr) |
| `gui/mt_dialog.py` | dialog *Nastavení MT…* (jho, rozteče, meze, kroky, nanesení a prohlídka, potvrzení feromagnetického materiálu; čísla jako text s původem hodnoty, kontrola `MtSettings`) |
| `gui/pt_dialog.py` | dialog *Nastavení PT…* (nástroje, úhly, oko, postup čištění; čísla jako text, u zvolených hodnot „zvoleno pro výpočet“, kontrola `PtSettings`) |
| `gui/zone_dialog.py` | dialog *Zakázané zóny…* plánu dráhy (tabulka kvádrů jako text, *Z výběru*, kontrola `Zone.from_dict`) |
| `ndt/volume_drawing.py` | kresba objemového pokrytí: povrch cíle (i v řezu) rozřezaný podél mřížky 07B a obarvený podle kusů, šedá = nerozlišeno v kresbě, plochy podle barvy |
| `gui/probe_dialog.py` | dialog *Sonda…* (etapy 03, 04, 08): profil z knihovny, původ hodnot, *změřeno*, materiál úhlu, informativní frekvence/měnič, zdroj, úhel ze Snellova zákona, *Uložit do Mých sond*; nezměněné OK = totožný záznam |
| `gui/target_dialog.py` | editor cílového objemu NDT studie (svar V, koutový, hranol): pole, nákres průřezu, objem ze vzorce, kontrola v dílu |
| `gui/assistant_panel.py` | panel AI asistenta: rozhovor v pomocném vlákně, kroky s modelem v hlavním vlákně, dialog Nastavení AI |
| `gui/assembly_window.py` | okno sestavy (P5.2B, P5.3B, P5.4B): strom komponent se stavy a volností, vazby ve stromu (výběr, *Přidat vazbu…* klikem a Ctrl+klikem na dvě plochy, panel *Vazba*: název, vzdálenost, smazat), hláška o přepočtu poloh, formulář polohy (čísla i výrazy, ±90°, *Pevná*), *Vložit díl*, *Najít soubor*, *Otevřít díl* (hlavní okno), Zpět/Znovu, díly na pozadí (`Cache(builder=None)` + vlastní `BackgroundRebuilder`), klik ve 3D vybere kopii (`IsSame`), ukázka jako šablona; dolní panel *Kontrola sestavy* (kolize a vůle na pozadí, klik = obě kopie + kulička průniku, přijetí s poznámkou, kusovník s CSV), *Exportovat STEP…* |
| `gui/direct_edit_dialog.py` | náhled přímé úpravy plochy (P2.4); model se změní až po potvrzení |
| `gui/drawing_preview.py` | náhled listu pracovního výkresu (jen pohled, nenahrazuje export) |
| `gui/design_panel.py` | panel *Konstrukční návrh pro NDT* (etapa 15B): srovnání variant na kopiích modelu, použití jen po potvrzení |
| `gui/viewer_views.py` | názvy a klávesové zkratky standardních pohledů 3D (bez OCCT) |
| `gui/viewer.py` | 3D prohlížeč OCCT (jediné místo GUI, které sahá na OCCT – jen kvůli kreslení a výběru); hlásí vybrané tvary, Ctrl+klik, pravý klik, zvýraznění; barevné body `show_points` (mapa kontaktních ploch); plán dráhy `show_plan` (čáry po barvách, začátek, zóny) |
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
6. Související kroky lze spojit. V cloudu průběžně spouštěj cílené testy dotčené oblasti
   (moduly, které změna mění, a testy, které je používají) a úplné `ruff check src tests`.
   **Úplnou sadu `pytest -q` v cloudu pusť jen u změn společného jádra** – přepočet dílu
   (`rebuild.py`, `features.py`, `geometry_validation.py`), hledání ploch a hran
   (`selectors.py`, `picking.py`), formát dílu (`document.py`), `session.py`, pomocný proces
   (`worker.py`) a `ndt/geometry.py`. Jinak ji spouští GitHub u každého PR na Windows i
   macOS (workflow „Windows aplikace“ a „macOS aplikace“, včetně ruff) a **sloučit jde jen
   po jejím úspěchu na obou systémech** včetně kontroly staženého balíčku (rozhodnutí
   autora 30. 10. 2026). Když GitHub ohlásí chybu, oprav ji a cílené testy spusť znovu.
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
- Testy: `pytest -q` (celá sada v cloudu jen u změn jádra – pravidlo 6; cíleně např.
  `pytest -q tests/test_assembly*.py`)  ·  Kontrola kódu: `ruff check src tests`
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

## Známé pasti (skica s nulovou plochou)

- Mnohoúhelník s body na jedné přímce dá v build123d **neplatnou plošku s plochou 0**. Plocha
  celé skici je přitom kladná (ostatní tvary) a vysunutí pak tiše zahodilo **i ostatní tvary**
  (tupý svar – objem, h = 0: 360 000 místo 360 500 mm³, všechny prvky „ok“). `build_sketch`
  proto kontroluje plochu každého tvaru (`MIN_AREA` 1e-6 mm²) → česká chyba „Tvar N skici
  (mnohoúhelník) má nulovou plochu“ a `ctx.apply` odmítne přidané těleso s nulovým objemem.

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
- Průnik v NDT jen přes `geometry._common` (`SetNonDestructive(True)`). Výchozí
  `BRepAlgoAPI_Common(a, b)` zapisuje do hran vstupů a posunuté kopie sondy sdílejí hrany:
  každé přiložení přidalo záznam, kolize se zpomalovala úměrně počtu přiložení (deska,
  6 000 přiložení: 4 → 45 ms, výpočet 202 s místo 54 s). Hlídá
  `test_repeated_placements_do_not_write_into_shared_probe_edges`. Přes `_common` jde
  i ořez buněk objemu (`volume_coverage._intersection` místo build123d `cell & target`,
  se stejným `clean`): buňka 2,9 místo 4,8 ms (UT objem i RT objem svaru).
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
- Objemová mapa se kreslí také `Topmost` (`show_coverage_map(..., topmost=True)`) a plochy
  řezu dílu pod ní **šedě** (`fill`) – průřez cíle leží v rovině řezu dílu, v jedné vrstvě by
  se plochy praly (z-fighting). Červená výplň by se pletla s „nepokryto“.
- Kresba nepotřebuje geometrii z pomocného procesu: `resolve_target` + `section.cut` v okně,
  povrch se rozřeže podél mřížky (`grid_min`, `target_step_mm`, `grid_frame` z předpokladů).
  Úlomek na konci mřížky (čelo svaru) patří poslední buňce – indexy se omezují na počet buněk,
  jinak by čelo zešedlo.
- Kus buňky se pozná jen podle `piece_bounds`; když nejde rozhodnout (kvádry se překrývají,
  meze chybí) a stavy se liší, úlomek je šedý – **nikdy nehádat zelenou**.
- `SectionSettings` se mění přes `dataclasses.replace` – ruční konstruktor by ztratil
  `target` (*Průřez svarem*) při posunu nebo otočení řezu.
- Snímek přiblíženého řezu: `V3d_View.SetAt` drží oko na místě a kameru nakloní – nastav
  i `SetEye` a `SetUp`; `app._screenshot` pohled před snímkem přizpůsobí celému dílu.

## Známé pasti (NDT – citlivost objemového pokrytí)

- Na **rovinném** pojezdu je tolerance zachycení jen **poloměr hledání**: každé místo blízko
  osy se přesně ověří (`coverage._resolve_axis_hit` dopočítá polohu sondy, přiloží ji
  a trasuje). Větší tolerance tam nevyrobí falešné „pokryto“ (na zakřivené ploše jen
  „nelze spolehlivě vyhodnotit“), menší než `krok × √0,5` ale část paprsků nenajde.
  Platí pro objem (07B) i plochy/body (Etapa 06): deska se starým porovnáním 84,5 % /
  32,4 %, s novým 84,5 % / 85,7 %. Hrubý běh nikdy nedědit toleranci jemného běhu.
- Porovnání kroků je zkouška, ne důkaz: chyba buňky nekončí plynule, záleží i na poloze
  mřížky vůči hranici (V svar: 5 mm náhodou přesně, 4 mm −3,4 p. b.).
- Referenční V svar: výřez 10 mm, sonda 70° zprava bez odrazů, platné přiložení od
  x0 = 22 mm (čelo 12 mm před výstupem naráží na převýšení), Y ±40 mm; průřez 15,18 %,
  celý svar 12,2 %.

## Známé pasti (NDT knihovna)

- Úhel v jiném materiálu: $\sin\beta / c$ je při stejné předsádce stálé → stačí rychlost
  v materiálu úhlu (obvykle ocel) a v materiálu pro UT. **Nikdy nepřepočítávat samo** –
  `check_angle` jen hlásí (`differs`), přepočet dělá `transferred` / `apply_ndt_angle_transfer`
  / CLI `--prepocet-uhlu` (jeden krok Zpět, původ `transferred`, `angle_note`).
- Údaje o původu (`profile`, `origins`, `angle_material` …) jsou v `Probe` jen nepovinné:
  `to_dict` je zapíše, jen když jsou vyplněné – starý záznam zůstane totožný. `origins` drží
  dataclass jako n-tici dvojic (hashovatelné), z JSON přichází dict.
- Studie si drží **kopii** hodnot sondy i materiálu; změna Mých sond studii nezmění.
  Poškozený `ndt-knihovna.json` se nikdy nepřepíše (`LibraryError`), vestavěné profily jdou dál.
- Bez profilu, původu a materiálu je `describe` prázdné → výstupy starých modelů beze změny.
- Vestavěná data nesmí tvrdit ověření/certifikaci (hlídá `test_ndt_library`); litina a titan
  chybí záměrně (rozptyl / neshoda zdrojů) – přidat jen se dvěma zdroji.
- Dialog *Sonda…* určuje původ podle **referenční sondy** (původní ze studie, nebo zvolený
  profil): stejná hodnota = původ reference, jiná = „zadáno ručně“ (jen když reference
  původ sleduje – ruční sonda bez profilu zůstane bez `origins`, starý test na přesný záznam).
  Poznámka k úhlu (`angle_note`) platí jen pro úhel a materiál, ke kterým vznikla.
- Panel čte Moje sondy znovu jen po změně souboru (`NdtPanel._user_library`, čas změny).

## Známé pasti (NDT – návrh poloh sondy)

- Dosah se zjišťuje **před** přiložením: `devices.aim` (stejný výpočet směru jako `place`,
  sdílený `_frame`) + `trace_beam` ~1 ms, přiložení ~30 ms. `Aim` nikdy nenahrazuje
  `Placement` – platnost polohy rozhoduje jen `place`.
- Mřížka 1. kola = mřížka pojezdu 3. kola (`coverage._grid_face`, krok analýzy). Přiložení
  se sdílí jen uvnitř `devices.reuse_placements` (klíč: rozměry a meze sondy, bod, úhel,
  plocha; úhel β a odrazy přiložení nemění, sonda se v uloženém výsledku jen vymění).
  Mimo analýzu se nic nepamatuje (tažení myší by jinak plnilo paměť).
- Výchozí poloha výpočet pokrytí v ploše neovlivní, jen se přidá k mřížce, když v ní není.
  Nejlepší poloha je proto **uzel mřížky** (`Analysis._best`) a odkaz na plochu nese bod
  bez zaokrouhlení – přepočet z něj dá totéž číslo. Zásahy z mezipoloh (`_resolve_axis_hit`)
  mají původ mimo mřížku, přičtou se nejbližšímu uzlu.
- Sjednocení (`access.union`) jen pro mapy téže mřížky cíle (stejný krok cíle) – jinak
  česká chyba. Váhy se nepřenormovávají.
- Rezerva dosahu je velkorysá (tolerance + krok): poloha u cíle „míří k cíli“ i směrem od
  něj. Je to jen síto; o pokrytí rozhoduje 3. kolo.
- ModelSession: analýza platí pro díl (otisk receptu), cíl studie a **rozměry a meze sondy**
  (`_access_key`) – úhel a odrazy ne, aby tabulka po *Použít variantu* zůstala. *Ukázat
  variantu* je jen pohled: `_probe_override` (sonda s úhlem a odrazy varianty) platí pro
  přiložení, paprsek i mapu pokrytí, dokud uživatel sondu ručně nepřiloží jinam
  (`place_ndt_probe`, posun `keep_preview=True` ji zachová) nebo neupraví sondu studie.
- Pomocný proces posílá `progress` / `prepared` / `variant` průběžně; `session.poll` je
  vybírá ve smyčce. *Zastavit* (`cancel`) složí z hotových variant neúplný výsledek
  (`complete=False`), nic nezahodí.
- Okno: průběžná zpráva (`session.poll()` vrátí True, ale `computing` trvá) obnoví jen panel
  návrhu a ukazatel průběhu, ne celé okno. Mapa ve 3D: mapa ze *Spočítat pokrytí* má přednost
  před sjednocením kombinace (`MainWindow._refresh_coverage`); body kontaktních ploch kreslí
  `viewer.show_points` (kuličky `Aspect_TOM_BALL` po barvách, vrstva `Topmost`, self-test
  „points“), prohlížeč je maže s dílem → `_shown_points = None`.
- Plocha, na které sonda stojí: zásah **1. ramene** se na ní nepočítá (`coverage._on_contact`,
  rozhodnutí autora 19. 10. 2026, algoritmus `ndt-ut-pokryti 2`) – paprsek z ní jen vychází.
  Dřív tam výpočet hlásil pokrytí (žebro, sonda na dně, cíl dno: 56,35 % → 0 %; s 1 odrazem
  64,6 % → 41,94 % – zůstává jen celý krok) a návrh poloh takovou polohu řadil nahoru.
  Běžný případ (sonda nahoře, cíl dno) beze změny. Souhrn a CSV pak nesou `CONTACT_NOTE`.

## Známé pasti (NDT – plán dráhy)

- Plán počítá s polohami **zaokrouhlenými na 1 nm** (`plan._r`) – uložený JSON pak dá při
  přepočtu tytéž polohy a paměť přiložení (`reuse_placements`) je pozná. Nové výpočty
  polohy v `plan.py` vždy přes `_r` / `_checks_along` / `_spaced`.
- Mřížka průchodu je zarovnaná se směrem paprsku a ukotvená v bodě přiložení; **oba vzory
  řádků sdílejí tutéž mřížku** (řádky jen po jiné ose), proto se vzory porovnávají levně
  z mřížky a jemně se počítá jen zvolený.
- Konec úseku se dohledává jen u **překážky** (sousední uzel neplatný nebo mimo plochu);
  konec oříznutý dosahem zůstane na uzlu. Síto dosahu má rezervu tolerance + rozteč.
- Režim pokrytí `plan`: mezipolohy (`_resolve_axis_hit`) jen v pásech úseků
  (`PlanRegion.contains`) a mimo zóny (`PlanRegion.allows` i pro polohy plánu). Polohy plánu
  jdou do výpočtu v pořadí jízdy – první zásah vzorku je tak nejdřívější poloha
  (přehrávání `PlanCoverage.until`).
- Nájezd = tělo sondy prodloužené nahoru o výšku nájezdu (`_approach`, jen průnik OCCT, bez
  paprsků otisku). Zvednutí, které na místě nejde, se vrátí po projeté dráze (`_retreat`);
  spuštění hledá jen v rámci úseku (`_entry_point`) – jinak úsek `build` vynechá.
- ModelSession: plán je ve studii (`plan`, `zones`, formát 18) s otisky `part` / `target` /
  `probe` (`plan.probe_fingerprint` – rozměry a meze, ne úhel). Stav `ndt_plan_state`: none /
  stale (jiný otisk) / unchecked / invalid / ok. Ověřený výsledek (`ndt_plan_result`) platí
  pro klíč `_plan_key` (recept, JSON plánu, zón, cíle a sondy) – uložení plánu ho nezruší.
  Zastaralou **studii** je třeba nejdřív potvrdit (plánovač chce platnou UT studii), pak
  `check_ndt_plan(confirm=True)` převezme otisky jen u platného plánu (jeden krok Zpět).
- Sestavení v pomocném procesu vrátí `PlanResult` a **uloží ho až `poll`** (`_plan_finished`
  → `_store_plan` → `_change`, tedy i přepočet dílu). Plán bez úseků se neuloží, důvody jsou
  v `failure`. Úpravy úseků (`_edit_plan`) nastaví `edited` a plán je pak *neověřený*.
- Síto dosahu: napřed obalový kvádr (levné), pak body skutečného cíle (`_target_points`,
  numpy; objem = mřížka po kroku cíle klasifikovaná `PartGeometry(cíl).classify`). Jen
  kvádr pouštěl u V svaru řádky, ze kterých paprsek svar mine.
- **Úsek bez přínosu** = žádný vzorek nemá první zásah z jeho polohy
  (`PlanCoverage.segment_hits`). Smazání všech takových úseků pokrytí nezmenší (první zásah
  každého vzorku zůstane) – `remove_ndt_useless_segments`, pak nový výpočet to ověří.
- Zóny platí jen pro plán: ruční přiložení v zóně panel jen upozorní
  (`ndt_placement_zone` přes sdílené `plan.zone_hit`), *Spočítat pokrytí* a návrh poloh je
  nezohledňují.
- Okno: po úpravě plánu panel nastaví `_plan_recheck` a ověření (bez pokrytí) spustí až
  v `refresh`, když neběží přepočet dílu (`ndt_planner` chce spočítaný díl). Přehrávání
  přikládá sondu `show_ndt_plan_position` (jen pohled, jako *Ukázat variantu*) a mapa je
  `ndt_plan_view_map(index)` (stavy `PlanCoverage.until`); prohlížeč maže plán s dílem →
  `_shown_plan = None`. Mapa ze *Spočítat pokrytí* má přednost před mapou plánu.

## Známé pasti (NDT – PT přístupnost povrchu)

- Směry: kolmice + spirála 64 (rovnoměrně po polokouli – jen z ní se počítá **otevřenost**)
  + **prstenec 16 směrů 88° od kolmice** (úzký volný pruh podél stěny štěrbiny a otvoru,
  spirála ho mezi 85° a 90° míjela). Nejmenší volný úhel: půlení po poledníku s přesností
  0,1° od nejbližšího volného směru i od středu volných, pak **natáčení kolem kolmice**
  (`Sampler._climb`) – u čela štěrbiny jinak hledání vybralo šikmou rovinu.
- Nástroj = kulička (vzdálenost středu od dílu `BRepExtrema` ≥ r − 0,001 a střed vně) + dřík
  o 2 % užší (`SHANK`) – přesný dotyk dříku se stěnou otvoru je pro `BRepAlgoAPI_Common`
  nejistý. Paprsky dříku (osa + 4 přímky v 0,9 r) jsou jen síto, rozhoduje `geometry.overlap`.
- Pás u vnitřního rohu, kam kulička r nedosáhne: r · cot(θ/2) (θ na straně vzduchu) –
  koutový svar 135° → 2,07 / 0,62 mm, kapsa 90° → r.
- Rychlost 20–95 ms na vzorek (stěny kapes a štěrbin pomalu: dohledání úhlu a dříku). Testy
  proto zkoušejí body (`Sampler.sample`), celou mapu jen na malé ploše.
- ModelSession: nastavení `pt` ve studii (formát 19, `set_ndt_pt_settings` = jeden krok Zpět,
  stejné nastavení = žádná změna; `pt` smí mít jen PT studie, změna metody ho smaže). Mapa
  (`compute_ndt_pt` / `start_ndt_pt`, `ndt_pt_map`) platí pro výsledek přepočtu a nezměněný
  záznam studie (`_pt_key`), zastaralou studii je třeba potvrdit.
- Okno: mapa PT se kreslí stávajícím `viewer.show_coverage_map` (žádný nový druh kreslení);
  klíč kresby je n-tice (mapa, kontrola, rovina řezu) – `_refresh_coverage` ji porovnává
  rovností, ne totožností. UT mapa pokrytí má přednost. U PT studie je nahoře
  `PT_DISCLAIMER` a skupina sondy UT (`probe_box`) skrytá. Klik do mapy: `show_pt_pick`
  z `_selection_changed` (bod `viewer.picked_point`). Se spočítanou mapou PT se oblast studie
  **nezvýrazňuje** (`_update_highlight`) – průsvitné zvýraznění by barvy mapy vybělilo
  (zelená šedla, červená růžověla; u UT to dělá přiložená sonda).
- Výsledek je pohled. `PT_DISCLAIMER` a „zvoleno pro výpočet, ne z normy“ u zvolených hodnot
  jsou v souhrnu i CSV; meze prohlídky 30° a 600 mm jsou z ASME V čl. 9 a BINDT CP25 (EN ISO
  17637 a EN 13018 neověřené – placené).

## Známé pasti (NDT – MT jho)

- Místo pólu: kružnice o poloměru d/2 v rovině (normála, směr jha) se sklápí **od kolmice
  dolů** a bere se první vstup do materiálu (`Yoker._site`). Hledání od tečny by u koutového
  svaru našlo vzdálenou stranu stojiny. Spojnice místa a pólu 10 mm nad povrchem nesmí
  narazit do dílu (stěna kapsy); na vypouklé trubce by spojnice bez zvednutí vedla materiálem.
- Botka pólu (15 mm) = přímá sonda `devices.place(..., measure_clearance=False)` – vůle nad
  rovinou je nejdražší část přiložení a pól ji nepotřebuje. Noha pokračuje ve směru osy jha
  (půlí úhel normál), jinak se nohy u rohu 90° kříží. Nohy a tělo = jeden průnik OCCT
  (`geometry.overlap` se složeným tvarem); nespočítaný průnik = nejisté, nikdy pokryté.
- Účinná oblast: obdélník (d − 2 · 25) × d/2 v tečné rovině středu, hloubka do d/4, plocha místa
  natočená do **60°** (`FACING`) a místo nejvýš **45°** pod nebo nad rovinou středu; mimo rovinu
  (> 2 mm) musí patřit k materiálu pod jhem (`_reaches`, paměť podle středu a místa): pod
  rovinou spojnice se středem vede materiálem (vypouklá trubka), nad rovinou je pod místem
  materiál až k rovině jha (koutový svar na pásnici) a místo je vidět (spojnice zvednutá
  o 10 mm). Jen „vidět“ pouštělo dno kapsy od jha vedle kapsy (26 % místo 0 %), jen spojnice
  materiálem ubírala koutový svar podél svaru (27 % → 11 %). `covers` s `geo` to kontroluje
  také (Ukázat jho).
- Středy jha jen na plochách v dosahu míst (d/4 + poloměr pólu) a natočených k nim do 60° –
  spodek desky by jinak zdvojnásobil výpočet. Dohledání hranic jen tam, kde by místo získalo
  nový směr (`_Field._gain`); jinak by 5 bodů trvalo 2,5 min místo 28 s.
- Mřížka středů pokrytí jen podhodnotí (zubatý okraj šikmých směrů, úzký pruh platných
  poloh mezi uzly se mine – deska 90° s krokem 20 mm = 0 %). Testy proto volí krok středů,
  jehož uzel leží na ose desky (25 mm).
- Úhly směrů pole jsou v rámu místa (0° = průmět +X, u plochy kolmé na X osa +Y): jho
  „0°“ na boční ploše kolmé na X dá na horní ploše pole 90°. `directions` v `compute` zužuje
  směry v rámu **středu** (jen pro testy).
- Ukázky deska (s2), trubka (s2), kapsa (s3) a koutový svar (s2) mají MT studii – testy okna
  a ModelSession počítají s druhou studií desky (nová studie je s3, „UT studie 3“).
- Rychlost přiložení: pořadí v `Yoker.place` je místa a stěna obou pólů → rychlý přesah
  (`_overhangs`, 4 paprsky, bez průniku OCCT) → úhel nohou → přesné dosednutí pólu (`_pole`,
  paměť podle zaokrouhleného bodu a plochy – sousední středy sdílí místo pólu) → průnik nohou
  a těla. Automatická mapa desky tím 3 min → 50 s. Přehozené pořadí změní jen důvod
  (přesah × nohy), test hrany čeká „přesah“.
- ModelSession: nastavení `mt` ve studii (formát 20, `set_ndt_mt_settings` = jeden krok
  Zpět, stejné nastavení = žádná změna; `mt` smí mít jen MT studie, změna metody ho smaže).
  Materiál je v otisku receptu → po jeho změně je studie zastaralá a mapa chce potvrzení;
  klíč mapy (`_mt_key`) materiál nese také. Mapa i jho (`place_ndt_yoke`, `ndt_mt_yoke_at`,
  `_yoke_view`) jsou jen pohled – po změně dílu zmizí. `start_ndt_mt` volá napřed odhad,
  aby chyba materiálu přišla hned, ne z pomocného procesu.
- Testy ModelSession a okna volí rychlé nastavení (síť 25 mm, středy 50 mm, bez nanesení
  a prohlídky) – mapa desky asi 15 s. Mapu počítá jen pár testů (Windows limit 20 min).
- Okno: jho se kreslí stávajícím `viewer.show_probe` (průhledné botky, nohy a tělo v barvě
  stavu, obrys účinné oblasti jako čára „paprsku“) – žádný nový druh kreslení. Přiložená UT
  sonda má přednost; `_shown_probe` drží sondu **nebo** jho. Mapa MT jde přes
  `show_coverage_map`, klíč kresby je n-tice („mt“, mapa, pohled, rovina řezu); UT mapa
  pokrytí i mapa PT mají přednost. Se spočítanou mapou MT nebo jhem se oblast studie
  nezvýrazňuje (jako u PT).
- V panelu je přepínač `mt_view` (QComboBox) – metoda pro okno se proto jmenuje
  `mt_map_view` (stejné jméno by atribut přepsalo: „QComboBox is not callable“).
- *Ukázat jho* hledá jho jen pro směr z přepínače (u *celkem* první platný směr místa).
  V pohledu směru, který místo nemá (deska u kraje, pole 90°), jho nenajde, vypíše jen důvod
  pro jho se středem v místě a nic nenakreslí – při zkoušce vydání to autora zmátlo.
  Srozumitelnější hláška (který směr místo nemá, které má, přepni na *celkem*) je navržená,
  neprovedená.

## Známé pasti (NDT – RT projekce)

- Prozařovaná tloušťka = **součet všech úseků** paprsku (`sum(segment.length)`), ne
  `RayResult.material_length` – ta počítá jen jisté úseky a paprsek otřený o stěnu otvoru by
  „prošel vzduchem“ (otvor vyšel o 0,4 mm širší a při sklonu se nezúžil). Nejistotu nese
  `ray.certain` → místo šedě.
- f a b (ISO: od strany předmětu u zdroje po středním paprsku) se berou z paprsku k místu
  oblasti s nejmenším úhlem od středního paprsku (`_distances`), vstup převedený na střední
  paprsek tečnou rovinou plochy vstupu (`_entry`). Střední paprsek do otvoru by dal b = 3 mm
  místo 23,09. Bez míst oblasti s materiálem se použije střední paprsek.
- Poměr tloušťky je vůči **střednímu paprsku** (ISO 17636-1). Když míří do otvoru, přes hranu
  nebo je tenčí než 0,8 × medián oblasti, poměr se nepočítá (šedě, „zadej jmenovitou
  tloušťku“); `reference_mm` u projekce ho nahradí. U šikmé projekce je jmenovitá tloušťka
  ta šikmá (deska 20 mm pod 30° → 23,09).
- Překryv obrazů jen přes **jiný kus materiálu** na paprsku (`_own`): kořen a převýšení téhož
  svaru překryv nejsou, protější stěna trubky ano.
- Detektor na ploše: rovina = tečná rovina plochy, kudy střední paprsek z dílu naposledy
  vystoupí; při nárazu se odsune po středním paprsku (půlení do 0,01 mm, nejvýš 50 mm).
  Střední paprsek bez materiálu (do otvoru) → detektor na ploše nejde, jen volně.
- Jednotkový směr ke zdroji se v `Projection` nepřenormovává – načtený a uložený záznam musí
  být totožný (nezměněné *OK* = žádný krok Zpět).
- Testy: náhled jen na úzkém detektoru (1 × 30 mm, krok 0,2) a mapa s krokem náhledu 20 mm
  – výchozí náhled 10 × 24 cm po 2 mm je 6 000 paprsků (asi 1,5 s na projekci).
- Objem svaru: skoro celý čas je přesný ořez buněk 07B (`_sample_volume`, asi 11 ms na buňku;
  V svar po 2,5 mm asi 20 s), paprsky jsou zlomek. `rt.estimate` proto u objemu buňky jen
  spočítá z mřížky (`grid_extent`) a ořez nedělá – jinak by odhad trval stejně jako výpočet.
- ModelSession: nastavení a projekce `rt` ve studii (formát 21) – každá úprava jeden krok Zpět,
  stejné = žádná změna; `rt` smí mít jen RT studie, změna metody ho smaže. Mapa
  (`compute_ndt_rt` / `start_ndt_rt`, `ndt_rt_map`) platí pro výsledek přepočtu, nezměněný
  záznam studie, materiál a výběr projekcí (`_rt_key`); zastaralou studii je třeba potvrdit.
  *Zdroj nad vybrané místo* (`ndt_rt_projection_at`) projekci jen vrátí, uloží ji až
  `add_ndt_rt_projection`.
- CLI `--vzdalenost` posune zdroj; volný detektor zůstane na místě
  (`detector_distance_mm` se posune o stejný rozdíl), jinak by se změnilo i b.
- Okno: zdroj a detektor vybrané projekce kreslí `viewer.show_probe` (tělo zdroje + deska
  detektoru jako jeden průhledný tvar, čára zdroj → zaměřený bod, „paprsek“ = lomená čára
  zdroj → roh → zdroj … do čtyř rohů detektoru) – žádný nový druh kreslení. Přednost má UT
  sonda, pak jho MT, pak projekce RT (`_refresh_probe`, `_shown_probe`). Neúspěšné přiložení
  detektoru (náraz) nese polohu desky, aby se nakreslila červeně (`prepare`, `failed(...)`).
- Mapa RT jde přes `show_coverage_map` s klíčem („rt“, mapa, pohled, rovina řezu); objem
  svaru kreslí `volume_drawing.volume_mesh` s barvami RT (`colors`) z mřížky 07B, kterou si
  `RtMap.volume_grid` pamatuje (buňky `volume_samples` jsou 1 : 1 s místy mapy), navrch
  a s plochami řezu šedě jako objem UT. UT, PT a MT mapa mají přednost.
- Náhled: `rt.preview_rgb` (bez Qt) – buňka náhledu patří k oblasti, je-li nejbližší místo
  oblasti blíž než `PREVIEW_REACH` × krok sítě × zvětšení (plochy 0,45 – těžiště trojúhelníků
  jsou hustší než krok, objem 0,75); místa mimo detektor se vynechají. Tečky po místech dělaly
  rušivé oblouky (moiré) a dosah 0,75 u ploch zakryl otvor. PNG zapisuje `rt.write_png`
  (zlib, bez Qt) – CLI i okno stejně.
- Dialog projekce: sklon a natočení vůči kolmici k ploše v zaměřeném bodě, jen když bod na
  ploše leží (do 0,01 mm, `ON_SURFACE_MM`); jinak nejbližší osa souřadnic. Zaměřený bod
  uprostřed otvoru má nejbližší plochou stěnu otvoru → sklon by vyšel 120°.

## Známé pasti (NDT – předběžný audit)

- Problémová místa se spojují **jen podle stavu a vzdálenosti** (1,6 × krok sítě), ne podle
  důvodu – u štěrbiny (PT) mají body různé první důvody a místo by se rozpadlo. Důvody místa
  se vypíšou s podílem plochy; jeden bod může mít víc důvodů, součet podílů může přes 100 %.
- Místa bez polohy (vnitřní bod buňky objemu nenalezen) tvoří jedno místo „poloha neurčena“
  na stav, nikdy se nepřilepí k jinému.
- Zpráva nese obecné upozornění a upozornění každé metody, která je ve zprávě (i u neprovedené
  studie), v pevném pořadí UT, PT, MT, RT. Slova „vyhovuje“, „protokol o zkoušce“
  a „zkušební protokol“ ve zprávě být nesmí (test) – RT souhrn smí „vyhoví třídě B“ (pravidlo
  geometrie ISO 17636-1, ne shoda).
- Náhledy RT dělá jádro (`rt.png_bytes`), takže jsou i ve zprávě z příkazové řádky. Obrázky
  map ve 3D dodá jen okno (`html(images=…)`).
- Čísla ve zprávě přes `audit._dec` – bez „-0,0“ u bodů na ose.
- ModelSession: `ndt_audit_items` rozhodne u každé studie výpočet (`AuditItem.action`: pt, mt,
  rt, plan, access, session, thickness) nebo důvod. UT: uložený plán (kromě zastaralého) →
  `check_ndt_plan(coverage=True)`; jinak výsledek z tohoto sezení (`_ut_session_result`:
  ověřený plán, mapa pokrytí se žádostí o přiložení téže studie, návrh poloh se sjednocením);
  návrh poloh jen se zaškrtnutím (`access`). Zastaralá / neúplná / neplatná studie =
  `STUDY_PROBLEMS`, audit ji nikdy nepotvrdí.
- Audit je pohled (`_audit_cache`, klíč: výsledek přepočtu, JSON sekce `ndt`, materiál,
  nastavení mapy tloušťky). Synchronní výpočet metod plní i jejich vlastní mezipaměti (mapa
  RT je pak hned v panelu); po výpočtu na pozadí ji převezme `adopt_ndt_audit_map`.
- Na pozadí (`start_ndt_audit`, úloha „audit“) se počítají jen studie s výpočtem; ostatní
  (a výsledek ze sezení, hotová mapa tloušťky) se zapíšou v okně hned. Pomocný proces posílá
  každou hotovou studii zprávou `entry` (`AuditEntry` s mapou, i s místy) – *Zastavit* je
  ponechá, zbytek dostane `STOPPED`. Konečná odpověď je jen počet studií (mapy už odešly).
- Chyba výpočtu jedné studie (i neočekávaná výjimka) audit nezastaví: studie je „nedostupné“
  s textem chyby.
- Okno: místo z auditu má ve 3D **přednost před všemi mapami** (`MainWindow._refresh_coverage`,
  klíč („audit“, mapa, řez); síť `ModelSession.ndt_audit_mesh` pro každý druh výsledku) a kresba
  projekce RT se přitom skryje (deska detektoru by mapu zakryla) – panel proto po změně volá
  `_refresh_probe`. Střed místa = kulička `show_points` (žádný nový druh kreslení).
- Mapy metod mají v session **jednu mezipaměť na metodu** (PT, MT, RT) – mapy všech studií
  z auditu proto převezme až výběr studie v panelu NDT (`NdtPanel._row_changed` →
  `adopt_ndt_audit_map`); platnou mapu téže studie nepřepíše.
- PDF: `QTextDocument.print_` stránkuje sám (okraj 2 cm). Vlastní `setPageSize` dokumentu
  v pixelech zapisovače (1200 dpi) zmenšil text na nečitelný. Obrázky `data:` se předávají
  jako zdroje dokumentu (`addResource`). Obrázky map pořídí `viewer.dump` po `fit_all`.
- Sestavení: GitHub Actions zapíše `src/skodacad/_build.py` (COMMIT, DATE) až **po testech**
  a před PyInstallerem; soubor je v `.gitignore` a spec ho přidá do `hiddenimports`, jen když
  existuje. Testy proto vidí „vývojová verze“.

## Známé pasti (NDT – konstrukční návrh)

- Varianta se počítá **na kopii** modelu (`design._session` = nová `ModelSession` bez
  pomocného procesu): studie se v kopii potvrdí (`confirm_ndt_study`), originál zůstává.
  Do kopie se doplní **zamčené kroky** (`_with_steps` přímo do JSON záznamu studie –
  `set_ndt_pt_settings` s neúplným slovníkem by ostatní nastavení vrátil na výchozí).
- Automatický krok PT/MT/RT se řídí velikostí oblasti – bez zamčení by každá varianta měla
  jinou síť. Kapsa 100 × 40, MT: středy jha po 12 mm 0 %, po 6 mm 53,1 %. Proto ověření
  polovičním krokem (u MT jen krok středů).
- Zlepšení = víc dobrého stavu, při shodě víc „omezeně“ (`DesignResult.better`, `_level`).
  Procenta se počítají z oblasti varianty – když se oblast změní o víc než 5 %, tabulka
  upozorní (PT kapsa, mělčí kapsa: 53,9 → 43,0 %, ale nepřístupné 556 → 438 mm²).
- Zámky a podmínky se kontrolují **před** NDT; měření, které nejde spočítat, je neprošlé.
  Neprošlé varianty se počítají jen informativně (`rejected`), *Použít* u nich nesmí jít.
- Cíle svaru jsou čísla → nižší převýšení = „cíl vyčnívá“ (*nelze vyhodnotit*), ne chyba
  návrhu. UT jen s uloženým plánem: ve variantě `_run_plan` se stejnými průchody (bod
  průchodu = `at` odkazu na plochu) a `PlanOptions.for_plan`.

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
- Krok *Testy* má časový limit (Windows 30 min, macOS 35 min – proti zaseknutému dialogu).
  Etapa 09 původní 10 min na Windows překročila (testy 7:55 → přes 10 min, sestavení
  selhalo „timed out“). Při etapě 14 trvaly testy na Windows 15:42 (14A.1) a 18:25 (14A.2)
  při limitu 20 min – rozptyl běžců GitHubu je několik minut, proto 20. 10. 2026 limit
  30 min (celá úloha 55 min). Na Windows běží testy zhruba stejně dlouho jako v cloudu na
  Linuxu (cloud 17–18 min). Nové pomalé testy drž krátké: hrubý krok, málo směrů, jedna
  kontaktní plocha, sdílené fixtures.
- 29. 10. 2026 trvaly testy na Windows už 26:55 z 30 min (cloud 25:42). Po opravě průniků
  NDT a zrychlení dvou testů (PR #59, #60) Windows 14:53, macOS 19:30, cloud 18:56.
  Nejdelší testy jsou teď konstrukční návrhy, audit a návrh poloh (20–35 s, poctivý
  výpočet paprsků a kolizí).

## Známé pasti (macOS)

- Souborové dialogy dílu a sestavy používají sdílené `gui/file_dialogs.FILE_OPTIONS`:
  **systémové panely**, včetně macOS (`FILE_OPTIONS = 0`). P7.7 ruší starší
  náhradu dialogem Qt: nepředávala systémové oprávnění k vybranému souboru
  v Dokumentech a čtení čekalo v `open`. Výběr konkrétního souboru musí proběhnout
  systémovým panelem; nepřidávat plošná oprávnění ani vracet DontUseNativeDialog
  kvůli omezení automatizačního klienta. [Evidence](docs/p7-7-otevirani-dokumentu-macos.md).
- P7.8: výběr JSONu sestavy nezpřístupní složky komponent. Interaktivní Otevřít
  na Macu proto přes `gui/assembly_access.py` nejdřív vyžádá společnou složku
  projektu; před panelem nesmí vypisovat adresáře ani číst díly (`locate` by
  čekalo v `os_listdir` / `opendir`). Zrušení nepřepíše model, souhlas se pamatuje
  jen v procesu. U podsestav vybrat celý projekt včetně jejich zdrojů.
- Běžný přepočet nesmí plošně mazat strom položek:
  Cocoa přístupnost drží odkazy na buňky a `tree.clear()` vedlo k pádu `libqcocoa`
  i v Qt 6.11.3. Hlavní okno i sestava proto opakovaně používají řádky podle id.
- P7.3 zopakovalo pád Cocoa AX i v seznamu tvarů skici. Příčina odpovídá
  QTBUG-149612: nativní buňky uvolňovaly rozhraní vlastněná Qt. Přesný backport
  sémantiky `invalidate/dealloc` z Qt `8148c48` staví
  `packaging/build_macos_accessibility.py`; spec přibalí dylib automaticky.
  Při vývoji na Macu jej sestav před spuštěním Cocoa GUI. Oprava je omezená
  na Qt 6.11.3, používá introspekci ivarů a ponechává přístupnost zapnutou.
  Při aktualizaci Qt ověř upstream opravu a shim odstraň; nerozšiřuj slepě
  seznam verzí. Self-test „Přístupnost macOS“ čte skutečnou nativní AX strukturu
  a kontroluje životnost Qt ID. [Evidence](docs/p7-3-overeni-workflow-2026-11-01.md).
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

## Známé pasti (přímé úpravy ploch)

- `BRepOffset_MakeOffset` chce **jedno těleso** (`TopoDS_Solid`): se složeninou vrátí jen
  skořápku. `Part(TopoDS_Solid)` hlásí objem 0 – výsledek se obalí `Compound` (ostatní
  tělesa dílu beze změny vedle).
- Plocha, která k tělesu nepatří, jádro **tiše přeskočí** a vrátí nezměněný díl; zaniklé
  sražení nechá jako plochu s výměrou 0 a tečně navazující zaoblení „projde“ s rozbitou
  tečností. Proto `_owner`, kontrola počtu ploch, `MIN_FACE_AREA` a předběžné
  `tangent_neighbours` (spojitost hrany nebo úhel normál pod 1°; chytí i plošky závitu).
- `OffsetFaces`/`Modified` historie u tohoto režimu nic nevrací – poloha upravené plochy
  se ověřuje geometricky (`_has_plane`, `_has_cylinder`).
- `Face.radius` vrací u některých válců (díra protínající okraj, kopie) **None** – poloměr
  vždy přes `BRepAdaptor_Surface(...).Cylinder().Radius()` (`_cylinder_radius`). Stejná
  past v `selectors.find_face` s `radius` je zapsaná jako nález N1 (`docs/p2-3-overeni.md`).
- Díra, která protíná okraj dílu, je jen částečný válec – změna průměru tam mění topologii
  a správně se odmítne (testy proto drží kopie děr celé uvnitř).
- Pojistka původu prochází `ctx.history` odzadu: díl po každém přijatém prvku drží
  `rebuild`; nový kód, který staví díl mimo `rebuild`, ji musí naplnit, jinak úprava
  ohlásí chybějící původ.

## Známé pasti (výkres)

- Pohledy a řez počítá skrývání čar OCCT (`project_to_viewport`) z **kopie** dílu se
  zapsanou plynulostí hran (`drawing_geometry._with_regularity`, `BRepLib.EncodeRegularity`).
  Šev válce u díry řezané skrz a u trubky z receptu nese neplatný záznam „ostrá“ (C0) – bez
  přepočtu plynulosti se kreslil jako hrana (čárkovaná čára v ose otvoru v pohledu zprava,
  u trubky dvě čáry navíc). Hladké hrany (C2 a víc) se nekreslí, ostré a tečné (zaoblení)
  zůstávají. Do originálu nezapisovat – 3D okno kreslí hrany dílu do C1.
- Skryté pohledy (`drawing.views`, formát 28): kóta **bez** `placement` se ze skrytého
  výchozího pohledu přesune do prvního zobrazeného, kde ji lze nakreslit; kóta s
  `placement` ve skrytém pohledu se nepřesouvá (upozornění = export stojí). Označení řezu
  potřebuje pohled shora (řez X/Y) nebo zepředu (řez Z), jinak česká chyba.
- Primitiva build123d (`Box - Cylinder`) mají šev zapsaný správně a chybu neukážou: testy
  výkresu stavět z receptu (`rebuild(Document)`) a kontrolovat přesný seznam čar (i že žádná
  nepřebývá), ne jen `any(...)`.

## Známé pasti (sestavy)

- `Document.from_dict` dřív neznámé klíče přeskočil – soubor sestavy by otevřel jako
  **prázdný díl** a uložením přepsal. Proto kontrola `kind` hned po `format` a sestava má
  vlastní verzi 29 (díly se dál ukládají v nejnižší potřebné verzi 24–28).
- build123d `Location((x, y, z), (rx, ry, rz))` má výchozí pořadí `Intrinsic.XYZ` – to je
  **jiná poloha** než naše pevné osy X → Y → Z. Matice se proto skládá ručně
  (`assembly_build.location`, R = Rz·Ry·Rx) a násobky 90° mají přesné hodnoty (`_cos_sin`),
  jinak vyjde obálka 4,4·10⁻¹⁵ místo 0 a úhly zpět 89,999999999999986.
- Kopie téhož dílu **sdílí tvar** (`moved` = jen poloha). Průnik mezi kopiemi (kolize v P5.4)
  smí jít jen přes `ndt.geometry._common` – výchozí průnik zapisuje do sdílených hran.
- Mezipaměť dílů má klíč skutečný soubor + SHA-256 bajtů: soubory se čtou při každém
  sestavení, staví se jen změněné. Díl s chybou přepočtu je stav `error` (pravidlo P1.4 E1).
- Pevnou komponentu odmítne `move_by` (tažení), výslovná poloha `set_placement` projde (S8).
- Uložení zapíše otisky zdrojů (S5) do souboru a aktuálního stavu, ne do historie Zpět.
- Okno sestavy je samostatné okno; hlavní okno ho otevře z *Otevřít* podle `kind`
  (`is_assembly_file`) a má pro sestavy vlastní `BackgroundRebuilder` – sdílený by se
  s přepočtem dílu navzájem rušil (`submit` ukončí běžící výpočet). Id komponent ve stromu
  jsou JSON text: Qt by n-tici v datech položky převedl na seznam.
- Ukázka sestavy je šablona: *Uložit* ji uloží jinam s `copy_parts=True` – díly se zkopírují
  do `dily/` vedle sestavy (stejné bajty se použijí, cizí soubor se nepřepíše, kopie dostane
  číslo). Bez toho na Windows (ukázky na D:, dočasná/uživatelská složka na C:) relativní cesta
  nejde a uložení skončí chybou „jiném disku“ – odhalilo CI.
- `QWidget.grab()` 3D prohlížeč nezachytí (černá plocha) – snímek okna přes
  `screen.grabWindow`, 3D zvlášť `viewer.dump`.
- P5.5 na macOS 27.2 odhalilo pády v Cocoa přístupnosti při obnově stromu a zadávání
  souboru. Zachovávat řádky a buňky při běžné obnově, nerozbalovat celý strom znovu;
  regrese drží trvalý index vazby i sbalenou skupinu. PySide6 je zamčené na 6.11.3.
  P5.5 použilo na Macu dialogy Qt kvůli potížím nativních panelů s přístupnostním
  klientem. P7.7 je vrací na systémové panely kvůli předání přístupu k souborům
  v Dokumentech; Windows stále používá původní systémové dialogy.
- Řešič vazeb: rovnice směrů se násobí ramenem (`scale`), krok je nejmenší normy (SVD)
  v měřítku mm s **jednotným** útlumem a na konci se vrátí volné pohyby (`_pull_back`).
  Marquardtův útlum podle sloupců zlevnil téměř volný pohyb (krabička ujela o 43 mm), bez
  SVD numerický šum o 536 mm. Volné otočení se při narovnání nakloněného dílu změní o zlomek
  stupně (nožička 4°/3° → 0,1° kolem Z) – je to opravdu nejmenší otočení, ne chyba.
- Polohy z řešiče se porovnávají maticí, ne čísly úhlů: [0, 0, 270] a [0, 0, −90] je táž
  poloha a zapsat se nesmí (sestava by po každém otevření byla „neuložená“). Vazby splněné
  už v uložené poloze (zbytek do 1e-7) se neřeší vůbec.
- Spor se posuzuje jen u vazeb, které **předtím ve sporu nebyly** – jinak by spor po změně
  dílu zablokoval každou další úpravu. Vazba na komponentu, jejíž díl se počítá, je
  „počítá se“ a přidat ji nejde.
- Testy, které procházejí `examples/` rekurzivně, soubory sestav vynechávají (`"kind":
  "assembly"`). Ukázka `examples/sestavy/krabicka_s_vickem.json` odkazuje i na
  `../krabicka.json`; díly víčka a nožičky jsou v `examples/sestavy/dily/`.
- Kontrola (P5.4): průnik kopií **jen** přes `ndt.geometry._common` (kopie sdílí tvar).
  Nejmenší vzdálenost se počítá jen u dvojic bez kolize; dvojice, která se jinde dotýká,
  má vzdálenost 0 – místní vůle uvnitř dotýkající se dvojice (lem víčka) se nehlásí.
- Export STEP sestavy jde přes XCAF (`assembly_check.export_step`), ne `build123d.export_step`:
  ten kopiím sdílejícím tvar dal stejné jméno a češtinu rozbil. Výrobek = soubor dílu
  (`Instance.base`, jednou), kopie = id s `result.locations[ids]`; zpětné čtení v testech přes
  `STEPCAFControl_Reader` (`OCP.collections.Sequence_TDF_Label`, `TDF_LabelSequence` v OCP není).
- Výsledek kontroly je pohled s klíčem `check_key` (díly, polohy kopií, mez vůle – přijaté
  kolize ne, ty přehodnotí `with_accepted`). Výsledek z pomocného procesu se převezme jen se
  stejným klíčem jako při spuštění (`store_check(outcome, key)`).
- Okno sestavy sdílí jeden `BackgroundRebuilder` pro díly i kontrolu: `_submit` ukončí běžící
  úlohu, proto `_start_next` při nových dílech kontrolu výslovně zruší a `_poll` rozlišuje
  `_check_job`. Řádky tabulky nálezů jsou v `_finding_rows` (ne slovník v datech položky Qt).
  `show_part` maže kuličky – značka průniku se kreslí v `_refresh_selection`.
- Kusovník ukazuje materiál českým názvem (`materials.DISPLAY_NAMES`), v dílu může být klíč
  („hlinik“).

## Jak přidat nový prvek

1. Funkce v `features.py` s dekorátorem `@feature("typ", "Český název")`.
2. Číselné hodnoty čti přes `ctx.num` / `ctx.positive` (umí výrazy), chyby hlas `FeatureError`.
3. Pole prvku popiš v `schema.py` (`FEATURE_SCHEMAS`) a doplň výchozí hodnoty v `new_feature`
   – podle toho okno postaví formulář (test `test_schema.py` hlídá shodu s jádrem).
4. Test v `tests/test_features.py` s očekávaným objemem podle vzorce.
   Objemový typ patří také do `features.VOLUME_FEATURES`; závěrečnou kontrolu
   `geometry_validation.inspect_volume` nesmí obejít ani přímá úprava dílu.
5. Doplň tabulku prvků v README.md.

## Plán

**Stav k 31. 10. 2026** ([schválená roadmapa P0–P8 a NDT-17](docs/roadmapa-vyvoje.md)):

| Etapa | Stav | Co zbývá |
|---|---|---|
| P0 stabilizace | sloučeno (PR #30) | – |
| P1 bezpečná geometrie | **přijato autorem** 25. 10. | R03, R04/P16, R12, historická identita |
| P2 přímé modelování | sloučeno (PR #44, #45) | ruční zkouška a přijetí autorem |
| P3 import STEP | sloučeno (PR #46–48) | přijetí autorem, soubory z jiných CADů |
| P4 výkresy | pracovní výkres sloučen (PR #49–58) | **P4.5 přejímka**: tisk, DXF v jiném CADu, oba OS |
| P5 sestavy | polohy, vazby a kontroly sloučeny (PR #63, #65, #68); [technické ověření Macu a opravy](docs/p5-5-overeni-macos-2026-10-30.md) v PR #69 | ruční Windows/Excel přeskočeny pokynem autora; známé meze platí |
| P6 pokročilé modelování | [Řízený přechod](docs/p6-7-rizeny-prechod.md) s vodítky (v34); [Lineární proměnné zaoblení](docs/p6-2-promenne-zaobleni.md): omezený pravoúhlý roh, formát 32, směr/původ, session a GUI; výsledky úplných kontrol v implementačním PR | P6.4 na autorském dílu, další operace z P6.1 |
| P7 ergonomie | [P7.1 technický audit a návrh prostředí CAD](docs/p7-1-audit-a-navrh-prostredi.md), dvě varianty a nativní průzkum | volba rozložení, nativní implementace a přejímka |
| P8 výkon/stabilizace | nezahájeno | – |
| NDT-17 validace | nezahájeno | NDT-16 je mimo rozsah |

Slučování do main: podle pokynu autora z 28. 10. 2026 po úspěšných kontrolách (úplná sada
v obou workflow na GitHubu včetně kontroly staženého balíčku, v cloudu podle pravidla 6);
výsledek a další krok vždy sdělit autorovi.
Ruční přijetí etap (P2, P3, P4.5) a odbornou validaci NDT nikdy neprohlašovat za hotové
bez autora.

Podrobná historie: P0 je sloučené v PR #30 (`e58d628`). Autor 20. 10. 2026 schválil P1.1:
[smlouvu geometrických operací](docs/p1-1-navrh-smlouvy-geometrickych-operaci.md), rozhodnutí **D1–D7 a matici testů**.
P1.1 je tím dokončeno; dokumentace je sloučená v PR #31 (`6e38d06`).
Autor 20. 10. 2026 schválil [konkrétní rozsah P1.2A](docs/p1-2a-navrh-spolecne-kontroly-geometrie.md):
body A1–A7, kroky A.1–A.3, testy V1–V14 a ruční přijetí. Plán je sloučený v PR #32
(`15b8bf4`); implementace A.1–A.3 je sloučená v PR #33 (`edf9b8e`).
[Protokol z 21. 10. 2026](docs/p1-2a-rucni-overeni-macos-2026-10-21.md) dokládá sedm
vedených zkoušek na Macu a samostatný souhlas se sloučením; [evidence](docs/p1-2a-overeni.md)
rozlišuje automatické a ruční ověření. Autor 21. 10. 2026 schválil
[konkrétní návrh P1.2B](docs/p1-2b-navrh-transakce-kontextu.md), B1–B7, kroky
B.1–B.3 a T01–T14, slovy „ok, schvaluji“. Plán je sloučený v PR #34 (`cbf19b1`).
B.1–B.3 jsou dokončené a sloučené v [PR #35](https://github.com/JendaNDT/SkodaCAD/pull/35)
jako `3a8deff`; [evidence](docs/p1-2b-overeni.md) a
[protokol autora z 22. 10. 2026](docs/p1-2b-rucni-overeni-macos-2026-10-22.md)
rozlišují automatické ověření, 17 vedených kontrol na Macu a samostatný pokyn „ok, sluč to“.
[Konkrétní návrh P1.3](docs/p1-3-navrh-bezpecnych-referenci.md) autor 22. 10. 2026
schválil slovy **„ok, schvaluji vše“**: C1–C8, C.1–C.3, S01–S20 a sloučení
návrhového PR #36 (`c46d0e2`). Implementace C.1–C.3 včetně opravy přenosu
promítnutých hran ze skicáře je sloučená v [PR #37](https://github.com/JendaNDT/SkodaCAD/pull/37)
jako `f5fbe2c` po výslovném pokynu autora „sluč PR #37 do main“.
[Evidence sloučení a obou vydání z main](docs/p1-3-overeni.md#sloučení-a-vydání-z-main)
uvádí 1 451 testů, obě celé CI a self-testy stažených balíčků.
[Protokol z 23. 10. 2026](docs/p1-3-agent-overeni-macos-2026-10-23.md) rozlišuje
autorova potvrzení příruby, převzetí dalších zkoušek agentem a meze automatizace.
Úplné ruční přijetí konečného balíčku ani odborná NDT-17 se neprohlašují za hotové.
Zbytkové riziko historické identity zůstává otevřené.
**P1.4 — E1–E9 schválené autorem 24. 10. 2026 slovy „ok, schvaluji“:**
[export a NDT při chybě modelu](docs/p1-4-navrh-exportu-a-ndt-pri-chybe.md),
kroky E.1–E.4, E01–E22. Schválení návrhu v PR #38 opravňuje tyto kroky implementovat;
[evidence](docs/p1-4-overeni.md) rozlišuje postup a skutečné výsledky.
Implementace je v [PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39),
[nativní ověření](docs/p1-4-agent-overeni-macos-2026-10-24.md) odděluje skutečné
kreslení od programového ovládání. Po předání autor schválil sloučení slovy
„ok, schvaluji“; P1.4 je na main jako `e7f9ac6`.
[Evidence obou vydání](docs/p1-4-overeni.md#sloučení-a-vydání-z-main) dokládá
1 549 testů na každém systému, kontrolu stažení a místní self-test vydání na M4.
Zachovat formát 22; R03/R04/R12 a odbornou validaci nepovažovat za vyřešené.
**P1.5 — dokončeno a sloučeno:**
[přijetí bezpečné geometrie](docs/p1-5-navrh-prijeti-bezpecne-geometrie.md),
F1–F9, F.1–F.4 a P01–P24 (autor po návrhovém PR #40: „schvaluji“).
[Evidence](docs/p1-5-overeni.md) vede konkrétní testy, mezery, měření a postup;
sedm nových regresí, 1 556 místních případů a
[nativní protokol](docs/p1-5-agent-overeni-macos-2026-10-24.md) s 15 kroky.
Autor sloučil [PR #41](https://github.com/JendaNDT/SkodaCAD/pull/41) jako `fe2a087`;
obě workflow z main včetně kontroly stažení prošla.
**P1 přijato autorem 25. 10. 2026** slovy „Přijímám P1“
([zápis](docs/p1-5-overeni.md#sloučení-a-přijetí-p1-autorem)).
R03, R04/P16, R12, zbytkové riziko historické identity, širší ruční matice
Windows/macOS a odborná NDT-17 zůstávají otevřené.
Nový produkční nález předložit se samostatným návrhem opravy; neupravovat
`src`, tolerance, závislosti ani očekávání jen kvůli úspěšnému přijetí.
[Audit a evidence P0](docs/p0-audit-a-overeni.md) obsahují rizika a postup ověření.
Autor 20. 10. 2026 potvrdil [funkční průchod na Macu M4](docs/p0-rucni-overeni-macos-2026-10-20.md);
rozsah a nepotvrzené podbody jsou v protokolu.
**P2.1 — schváleno autorem 25. 10. 2026** slovy „schvaluji G1–G8“:
[rozsah přímého modelování](docs/p2-1-navrh-rozsahu-primeho-modelovani.md), G1–G8,
Q01–Q24 a [průzkum jádra](docs/p2-1-pruzkum-jadra.py) (`BRepOffset_MakeOffset`
se `SetOffsetOnFace`), návrhové PR #42. Implementaci nezahajovat: P2.2 formát,
P2.3 výpočet, P2.4 okno a P2.5 přijetí mají každý vlastní schválení.
**P2.2 — schváleno autorem 25. 10. 2026** slovy „schvaluji H1–H8“:
[zápis přímé úpravy](docs/p2-2-navrh-zapisu-prime-upravy.md), H1–H8 (`move_face`,
`face_diameter`, pole `origin` = pojistka původu plochy, formát 23, oprava R12), W01–W16
a [průzkum pojistky](docs/p2-2-pruzkum-puvodu.py), PR #43. P2.3 (výpočet) se smí
implementovat podle G1–G8 a H1–H8; P2.4 okno a P2.5 přijetí dál vyžadují schválení.
**P2.3 — sloučeno v PR #44 (`e1cb3bc`):** `direct_edit.py`, formát 23, README, testy
Q01–Q23 a W01–W16 (`tests/test_direct_edit.py`), [evidence](docs/p2-3-overeni.md).
**P2.4–P2.5 — sloučeno v PR #45 (`5cbab6f`):** výběr plochy ve 3D, zadání hodnoty,
náhled na kopii, potvrzení či zrušení; nástroj AI jen s dialogem uživatele
([evidence P2.4](docs/p2-4-overeni.md), [přejímka P2.5](docs/p2-5-overeni.md)).
Otevřené: ruční zkouška a výslovné přijetí P2 autorem, živé volání AI, zbytkové riziko
W12 (kopie stejného pole), náhled počítaný v hlavním vlákně (u složitého dílu okno chvíli stojí).
**P3 — sloučeno v PR #46–48:** [sada vstupů P3.1](docs/p3-1-step-vstupy.md) (PR #46),
návrh [P3.2](docs/p3-2-navrh-ulozeni-step.md), omezený import jednoho tělesa s vloženým
STEP, náhledem a formátem 24 (PR #47, `59cfb8c`, [evidence](docs/p3-3-5-overeni.md)),
jednotky metry (PR #48, `731d0c2`, [evidence](docs/p3-step-metry.md)). Sestavy, více těles
a ohlášené opravy se odmítají; paměťový dohled je vzorkovaný, ne pevný limit OS. Přenos
modelu mezi Windows a macOS hlídá workflow `p35-cross-os.yml`. Otevřené: přijetí autorem
a skutečné soubory z jiných CADů.
**P4 — pracovní výkres sloučen v PR #49–58, chybí přejímka P4.5:** autor schválil
[návrh P4.1](docs/p4-1-navrh-vykresu.md) (V1–V9, „schvaluji vše“).
[P4.2 geometrie pohledů a řezu](docs/p4-2-geometrie-pohledu.md) (PR #49, `067860c`);
[kóty s vazbami a náhled listu](docs/p4-3-vazby-kot.md), formát 25 (PR #50, #51,
[kóty na listu](docs/p4-4-koty-na-listu.md)); [řez A–A a export PDF/DXF](docs/p4-5-rez-export.md)
(PR #52); [upozornění na překrytí kót](docs/p4-6-kontrola-prekryti.md) (PR #53); odchylky
kót, formát 26 (PR #54); popisové pole, formát 27 (PR #55); šev válce se nekreslí jako hrana
(PR #56); list a měřítko se ukládají (PR #57); skryté pohledy, formát 28 (PR #58, `cb2f7d5`).
Otevřené (P4.5): fyzický tisk a změření kontrolní úsečky, kót a měřítka; otevření DXF
v jiném CADu; ruční průchod na Windows i macOS. Mimo první verzi: kóty hran a dalších typů
prvků, drsnost, geometrické tolerance, značky svarů a závitů, více listů.
**Výkon (29.–30. 10. 2026):** průniky NDT bez zápisu do vstupů – kolize se už
nezpomaluje s počtem přiložení (PR #59, `d7b2963`); rychlejší ořez buněk objemu
(PR #60, `7e138d6`). Výsledky NDT beze změny; testy na Windows 26:55 → 14:53 min.
**P5 sestavy — návrh P5.1 schválen autorem 30. 10. 2026 („schvaluji S1–S12“, PR #62):**
[formát sestav](docs/p5-1-navrh-formatu-sestav.md) S1–S12 (samostatný soubor `kind:
"assembly"` ve verzi 29 s odkazy na soubory dílů vůči složce sestavy, poloha = posun
+ úhly kolem pevných os X→Y→Z, stavy chybějících komponent, cykly, díly se nikdy
nepřepisují), [průzkum](docs/p5-1-pruzkum-sestav.py) a matice A01–A22 pro P5.2.
P5.2 se implementuje podle S1–S12: **P5.2A jádro** (formát 29, `assembly.py`,
`assembly_build.py`, `AssemblySession`, `skodacad sestava`, ukázka, testy A01–A22
v `tests/test_assembly.py`) a **P5.2B okno** (`gui/assembly_window.py`, *Nová sestava*,
*Otevřít* pozná sestavu, díly na pozadí, self-test, balíček, přenos sestavy v
`p35-cross-os.yml`, `tests/test_assembly_gui.py`), [evidence](docs/p5-2-jadro-sestav.md).
Sloučeno v PR #63 (`91f8a70`); autor 30. 10. 2026 k vydání z `91f8a70` napsal
„Ok, funguje to“ (průchod ukázkou: otočení, poloha, uložení s díly, chybějící díl, *Otevřít
díl*). **P5.3 vazby – návrh předán 30. 10. 2026:** [vazby](docs/p5-3-navrh-vazeb.md) M1–M12
(dotyk, zarovnání, vzdálenost, souosost; odkazy na plochy významem a základní roviny/osy
dílu; vlastní řešič tuhých těles nad numpy po skupinách, nejmenší posun, obrácení o 180°,
spor = úprava se nepřijme; formát 30 jen se vazbami), [průzkum](docs/p5-3-pruzkum-vazeb.py),
matice B01–B20. **Schváleno autorem 30. 10. 2026 („schvaluji M1–M12“, PR #64).**
**P5.3A/B sloučeno v PR #65 (`822e3e8`):** formát 30, `assembly_solve.py`, vazby
v `AssemblySession`, `skodacad sestava`, ukázka `krabicka_s_vazbami.json`, okno (B20),
self-test „✓ Vazby“, [evidence](docs/p5-3-vazby-overeni.md). Ruční zkouška autorem čeká.
**P5.4 kontroly – návrh předán 30. 10. 2026:** [kontroly](docs/p5-4-navrh-kontrol.md) K1–K12
(kolize přesným nedestruktivním průnikem nad 0,001 mm³, vůle = nejmenší vzdálenost pod
mezí 0,5 mm, přijaté kolize s poznámkou a objemem, formát 31 jen s `checks`, výpočet na
tlačítko v pomocném procesu, rozbalený kusovník s CSV, export STEP se stromem výrobek =
soubor / kopie = id bez diakritiky, v sestavě žádné NDT), [průzkum](docs/p5-4-pruzkum-kontrol.py),
matice C01–C20. **Schváleno autorem 30. 10. 2026 (odpověď „K1–K12“, PR #67).**
**P5.4A/B implementováno:** formát 31, `assembly_check.py`, kontroly v `AssemblySession`,
úloha pomocného procesu, `skodacad sestava --kontrola/--kusovnik/--export`, ukázka
`deska_se_sroubem.json`, panel *Kontrola sestavy* (C20), self-test „✓ Kontrola sestavy“,
[evidence](docs/p5-4-kontroly-overeni.md). Ruční zkouška autorem čeká.
**P5.5 — technické ověření a opravy sloučeny v PR #69 (`c8e4746`):**
[místní Mac M4](docs/p5-5-overeni-macos-2026-10-30.md), stabilní obnova položek okna
a PySide6 6.11.3; 1 942 testů na každém systému, oba self-testy balíčků a STEP přenos
prošly. Autor na navazující ruční Windows/Excel odpověděl „to přeskočíme“; tyto
zkoušky nejsou provedené a pokračování neblokují.
**P6.1/P6.2 — zahájena příprava:** [výběr a průzkum](docs/p6-1-vyber-operaci.md)
proměnného zaoblení: šest případů v OCCT na Macu, včetně geometrie konců a orientace.
Původní dvouhodnotové volání OCCT má nelineární vnitřní průběh.
**P6.2/P6.3 — první operace implementována 31. 10. 2026** po „ok pokračuj“:
[návrh a meze](docs/p6-2-promenne-zaobleni.md), `variable_fillet.py`, typ
`variable_fillet` (v32), přímkový loft čtvrtkruhového řezacího profilu, jeden přímý
vypouklý pravoúhlý roh s kolmými rovinnými konci; směr a původ/boky uložené,
objem podle vzorce, průběh a tečnost ověřené. Session, výběr ve 3D, formulář R1/R2,
obrácení, značky konců, ukázka a self-test. Úplné kontroly jsou podmínkou sloučení. P6.4 na vlastním
dílu a další kandidáti z P6.1 zůstávají otevřené. Ostatní díly zůstávají v24–28,
sestavy v29–31; výslovný režim stěny loftu dále vyžaduje formát 33.
**P6.2 skořepiny — průzkum 31. 10. 2026:** [tři reference a návrh opravy](docs/p6-3-skorepiny-overeni-a-navrh.md),
spustitelný `docs/p6-3-pruzkum-skorepin.py`, samostatné časově omezené workflow pro oba OS.
Kvádr, šikmé stěny a zaoblený kryt souhlasí s analytickým objemem a ve vzorcích
pravidelných stěn mají 3/3/2 mm. Rozlišovat geometrickou délku materiálem kolmo
od měřidla s filtrem 60°: klíny a zaniklé vnitřní zaoblení tvoří zesílené rohy,
nikoli automaticky chybu. Výsypka potvrzuje 2,61–2,77 mm kolmo při zadaných 3 mm
v rovinách skic; přímý offset vrací nezměněný solid. Navazuje výslovný režim stěny
loftu a oddělený CAD přehled.
**P6.3 režimy stěny — implementace 31. 10. 2026:** [návrh a meze](docs/p6-4-rezim-steny-loftu.md),
`loft.wall_mode` normal / sections (v33), nové lofty normal, staré bez pole beze změny.
Výslovný režim nesmí přepínat algoritmus. Normálový výsledek ověřuje P1 a
`loft_wall.check_normal_wall` (ponechané stěny, otevření, normálové délky a odstup
vnitřních ploch); validita samotná nezachytila obrácený kužel při příliš velké stěně.
2D režim vyžaduje jeden menší profil a celý vnitřní loft uvnitř vnějšího. Formulář
zachovává chybějící volbu při jiné úpravě; ukázka, historie a self-test balíčku.
Nejnovější formát je 33 (čtení 1–33), ostatní díly nadále 24–32 a sestavy 29–31.
Výsledky kontrol v implementačním PR.
**P6.3 CAD přehled stěny — implementace 31. 10. 2026:** [význam a meze](docs/p6-5-prehled-steny-loftu.md),
`loft_inspection.py`, 5 × 5 bodů původního pláště / boční plocha, v aktuálním hotovém dílu.
Geometrické délky přes PartGeometry bez NDT filtru 60°, hrany/tečnost a změněný povrch
nejisté. Pod/u zadání, delší průchod a nejisté; číselná tolerance není výrobní přejímka,
vzorky nejsou globální minimum. Dočasná zpráva přes session a samostatnou úlohu workeru,
zastavení bez změny receptu; změna modelu, historie a otevření ji zneplatní. Panel pod
loftem, tabulka a výběr měřicí úsečky/bodu ve 3D, žádná změna formátu ani NDT.
Analytické reference, výsypka, navazující odebrání, chyby a platnost, proces, GUI a
self-test; konkrétní úplné výsledky před sloučením v implementačním PR.
**P6.2 vodicí křivky — průzkum 31. 10. 2026:** [výsledky a první návrh](docs/p6-6-vodici-krivky-overeni-a-navrh.md),
spustitelný `docs/p6-6-pruzkum-voditek.py`, devět sítí v oddělených časově omezených
procesech a workflow pro oba OS. Již dostupný Gordon i Bézier: analytické obdélníky,
výkyv/ohnutí, více profilů a obrácené křivky; dva kruhové profily nezaručují kruhový
meziřez ani G1, třetí profil v konkrétní referenci pomohl. P1 může přijmout křížení
vodítek, proto nezávislá kontrola konvexity průřezů v celém intervalu. Návrh první
produkční operace: dvě obdélníková čela, čtyři kubická vodítka s implicitními konci
v geometrických rozích, pevný parametr výšky, plný solid a přímé Bézierovy plochy.
Produkční kód a formát 33 se nemění; `guided_loft`/v34 je zatím pouze návrh.
Výsledky cílených a úplných systémových kontrol v PR průzkumu.
**P7.1/P7.2 — návrh a nativní prototyp:** autor vybral směr strojního CADu
ve stylu Solid Edge / Inventor a pokynem „ok, udělej to“ navázal implementací
varianty Strom a pravý editor. [P7.2](docs/p7-2-nativni-prostredi.md): pás činností
se sdílenými QAction, jeden pravý panel, skládací strom, samostatný sloupec počtu
těles, plná pole X/Y rukojetí a profil `okno.json`. UI bez změny jádra/formátu 34,
přepínání bez změny modelu; Enter/ztráta fokusu potvrzuje jako dosud. Self-test
„✓ Prostředí CAD“ musí projít v obou balíčcích. Rozšířená nativní zkouška
odhalila i přeuvolnění QNSView přes kapslový Cocoa_Window; Mac teď předává
Qt handle přes nevlastnící Aspect_NeutralWindow a aktualizuje jeho rozměry.
Self-test „✓ Životnost 3D ploch“ ověřuje čtyři cykly v obou balíčcích.
P7.4 přijetí autorem čeká.
**P7.3 — technické ověření modelování:** [deska od nuly](docs/p7-3-overeni-workflow-2026-11-01.md),
80 × 50 × 10, čtyři Ø6, vnější R2; parametry, historie, uložení a exporty.
Oprava Cocoa AX, potvrzení souřadnic Tabem, editor po vytvoření z výběru/skicáře,
čitelnější rozbalený strom. Self-test „Modelování desky“ také kliká na skutečnou
plochu a čtyři hrany přes Qt a OCCT projekci. Úplné výsledky v implementačním PR;
nejde o autorskou přejímku P7.4.
**P8 a NDT-17 — nezahájeno.** NDT-16 mimo rozsah; NDT-17 na něm nezávisí.
**P7.5 — náhled nového prvku:** autor schválil Potvrdit/Zrušit.
[Provedení a evidence](docs/p7-5-nahled-noveho-prvku.md): pracovní ModelSession,
vlastní runner, potvrzení přes `_change(computed_result=…)`, jediný krok historie,
zrušení bez změny zdroje. Všechny uživatelské příkazy nového prvku vedou přes
`start_feature_preview` / `start_selection_preview` / `start_profile_preview`.
Interní okamžité metody okna slouží pro přípravu hotových modelů v regresích;
nové příkazy ověřují zvláštní interakční testy a self-test „Náhled nového prvku“.
P7.4 přijetí autorem zůstává otevřené. Formát 34.
**P7.6 — náhled úprav hotových prvků:** [provedení](docs/p7-6-nahled-uprav-prvku.md).
`begin_feature_edit` sdílí potvrzovací postup s novým prvkem; může opravit i
aktuálně chybný model. Potvrzení vyžaduje platnost celého přepočtu následníků,
shodu zdroje a změnu právě cílového prvku. Běžný formulář je jen pro čtení,
Upravit prvek / dvojklik / Ctrl+E otevře pracovní kopii. Výběr hran pro existující
prvek také vede do náhledu. Interní `_feature_edited` zůstává pro programovou
přípravu regresí; uživatelský tok ověřuje self-test „Úprava prvku“ a interakční
testy. Tažení ve 3D si ponechává potvrzení puštěním myši; parametry, mazání
a pořadí prvků mají dosavadní ovládání. Bez změny formátu 34 a bez nové závislosti.
Historické fáze níže nejsou etapy P0–P8.

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
- [x] **Fáze 4** – [x] AI asistent upravující model (Claude API, panel v okně, `skodacad ai`),
  [x] omezené přímé úpravy ploch (P2, sloučeno; přijetí autorem čeká).
- [ ] **NDT modul** (plán `docs/ndt/03-implementacni-plan.md`) – [x] etapa 00 referenční díly,
  [x] etapa 01 NDT studie v modelu (formát v13, panel), [x] etapa 02 společné geometrické jádro,
  [x] 03 virtuální sonda a její přiložení (formát v14), [x] sladění se závazným vymezením UT,
  [x] 04 geometrický model UT paprsku (lom jen se zadanými předpoklady, odrazy, formát v15),
  [x] 05 ruční pohyb sondy (milník M1), [x] 06 geometrické pokrytí (sloučeno),
  [ ] 07 svar a cílová oblast: [x] 07A datový základ (sloučeno v PR #16),
  [x] 07B objemové pokrytí (sloučeno v PR #17), [x] 07C ovládání a demonstrace
  (sloučeno v PR #19, autor po vydání: „ok funguje to“) …,
  [x] 08 knihovna sond a materiálů (formát v17, sloučeno v PR #22, autor po vydání: „ok funguje
  to“; 08C tvarovaná předsádka odložena) – milník M2 hotov,
  [x] 09 návrh poloh UT sondy (sloučeno v PR #23, autor po vydání: „ok funguje to“),
  [x] 10 plán dráhy UT sondy (formát v18, sloučeno v PR #24, autor po vydání: „ok funguje
  to“) – milník M3 hotov,
  [x] 11 PT přístupnost povrchu (formát v19, sloučeno v PR #25, autor po vydání: „ok, funguje
  to“; otevírá milník M4), [x] 12 MT přiložení jha a směry magnetizace (formát v20,
  sloučeno v PR #26, autor po vydání: „ok, funguje to“), [ ] 13 RT geometrie projekce
  a expozice (schváleno 19. 10. 2026; dokončí milník M4): [x] 13A.1 vymezení RT a jádro
  `ndt/rt.py`, [x] 13A.2 formát 21, ModelSession, pomocný proces, CLI, [x] 13B okno (sloučeno
  v PR #27, čeká na ruční zkoušku autora), [ ] 14 společný předběžný audit (schváleno
  20. 10. 2026; otevírá milník M5): [x] 14A.1 jádro zprávy `ndt/audit.py`, [x] 14A.2 spuštění
  (ModelSession, pomocný proces, CLI, sestavení), [x] 14B okno (panel *NDT audit*, PDF; sloučeno
  v PR #28; funkční export potvrzen v protokolu P0), [ ] 15 konstrukční návrhy (schváleno
  20. 10. 2026; dokončí milník M5): [x] 15A.0 oprava skici s nulovou plochou, [x] 15A.1 jádro
  `ndt/design.py`, [x] 15A.2 formát 22, ModelSession, CLI, příklad a testy (CI Windows/macOS úspěšná), [x] 15B panel, dialog, náhled, potvrzení a PDF (sloučeno v PR #29; funkční průchod potvrzen v protokolu P0, odborná validace zůstává otevřená).
- [ ] **macOS Apple Silicon** (`docs/ndt/05-podpora-macos.md`) – [x] audit knihoven, prohlížeč přes
  `Cocoa_Window`, `SkodaCAD.app` v ZIP, workflow „macOS aplikace“ (self-test na Macu GitHubu OK,
  softwarové OpenGL), [x] funkční průchod na M4 / macOS 27.0.1 (protokol P0),
  [ ] doplnit širší matici Retiny, trackpadu, GPU a porovnání s Windows.
