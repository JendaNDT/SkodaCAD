# P1.2A — implementace a ověření

Autor 20. 10. 2026 schválil [rozsah A1–A7](p1-2a-navrh-spolecne-kontroly-geometrie.md)
slovy „ok, schvaluji“. Dokumentační PR #32 je sloučený jako `15b8bf4`.
Implementace má vlastní větev `codex/p1-2a-geometry-validation`.
Ke sloučení implementačního PR je nutný další souhlas autora.

## Změna pro uživatele

Každý objemový prvek ověřuje všechny složky tvaru a až potom přijme kandidáta.
Prázdný, otevřený, smíšený nebo neověřitelný tvar a nerozlišitelný přídavek/řez
skončí českou chybou s radou. Zaoblení/sražení zachovají počet těles; mohou
přidávat materiál ve vnitřním rohu. Skořepina musí mít zvolenou otevřenou plochu.

Úspěšný 3D prvek nese zprávu „Počet těles: před → po.“ ve stromu, CLI a místním
souhrnu AI. Ve vlastnostech je konečný počet vždy. Více platných solidů je nadále
úspěch. Přenos používá existující `FeatureStatus.message`; recept a protokol
workeru nemají nové pole. Při chybě se nehlásí smyšlená úspěšná změna počtu.

## Malé kroky a místní výsledky

| Krok | Commit | Skutečné ověření před commitem |
|---|---|---|
| A.1 společná kontrola a `new/add/cut` | `2bd1c86` | Ruff OK; **1 165 testů / 408,34 s**, bez přeskočení |
| A.2 úpravy hran/stěn a závěrečná pojistka | `8de7fde` | Ruff OK; **1 195 testů / 412,41 s**, bez přeskočení |
| A.3 zprávy, rozhraní, přenos, kompatibilita | aktuální větev PR | Ruff OK; **1 265 testů / 413,35 s**, bez přeskočení; samostatná sada GUI **85 testů / 61,04 s** |

Místní prostředí: macOS 27.0.1 arm64 / Apple M4, Python 3.12.14,
build123d 0.13.0, OCCT 8.0.1, PySide6 6.11.2; testy Qt offscreen.
První úplný průchod A.3 odhalil stará očekávání přesného textu stromu GUI.
Očekávání nyní zahrnují schválené hlášení počtu; původní geometrické podmínky
nebyly změněny. První běh skončil 9 selháními / 1 256 úspěchy; po opravě
prošel nový celý průchod uvedený v tabulce. Přírůstek oproti main je 166 případů.

Nativní self-test ze zdrojů skončil **VÝSLEDEK: OK**, včetně kreslení, měření,
NDT ukázek a skutečného přepočtu na pozadí. Snímek skutečného okna na Macu
ukazuje oba samostatné válce, zelené 0→2 a konečný počet 2. První pokus na
zamčeném Macu zachytil pouze plochu; nebyl uznán jako ověření okna. Úspěšný
snímek vznikl po ručním odemknutí. Toto automatizované ověření ze zdrojů
nenahrazuje ruční přijetí konkrétního staženého balíčku autorem.

## Pokrytí schválené matice

| Sady | Regrese a důkaz |
|---|---|
| V1 | `test_geometry_validation.py`: prázdný tvar, otevřený shell, volné neobjemové složky, malá složka, kontejnery, platná dutina a víceobjemový nástroj |
| V2 | Stejný soubor: NaN/±Inf přímo, v parametru a výrazu; záporný konečný posun projde. Existující testy rozměrů zůstaly zachované. |
| V3–V5 | Analytické objemy prvního tělesa, překryvu, dotyků, odděleného přídavku, kapsy, rozdělení a dvou řezaček; materiál v konkrétních místech, odmítnutí bezúčelného přídavku i řezu celého dílu. Dvě kružnice také v `test_body_counts.py`. |
| V6–V7 | `test_geometry_modifications.py` + původní testy: vnější/vnitřní rohy, L podle vzorců, stěny a dno skořepiny 8 472 mm³; chybné rozměry, velký poloměr, chybějící hrany/otevření |
| V8 | Registr všech 11 objemových typů musí projít závěrečnou pojistkou; zachované analytické testy loftu, tažení, rotace, normalizovaných dílů a vymodelovaného závitu. |
| V9 | Existující pole tří tažení plus zprávy 1→3; nová regrese pozdní chyby pole dvou děr ověřuje původní objem i materiál v místě první nepřijaté kopie. |
| V10 | Přesná numerická hranice 0 / 0,5 ε / ε / 2 ε odděleně od OCCT; měřítka 0,1/1/10, dvě mikromezery a skutečné mělké řezy podle změřeného účinku jádra. |
| V11 | `test_body_counts.py`, `test_gui.py`: stejné 0→1, 0→2, 1→2, 2→1, 1→3, 1→1 v jádře, CLI, offline AI a Qt; chybný/přeskočený prvek nemá úspěšnou zprávu. |
| V12 | BinTools/pickle i skutečný `BackgroundRebuilder` se spawnem zachovají geometrii a zprávy; Zpět/Znovu, oprava nových chyb a uložení kopie zachovají zdrojové bajty. |
| V13 | `test_p12a_compatibility.py`: všech 26 rekurzivních ukázek, výchozí objemy/plné obálky/počty, uložení a otevření kopie; jednoduché historické recepty verzí 1–22. Původní testy novějších sekcí zůstávají. |
| V14 | Řízeně vadný výstup builderu (i obejití `apply` či nezměněná identita) nesmí projít; samotné skici bez tělesa jsou platné. |

Simulace jádra slouží pro řízeně vadné kandidáty; nenahrazují skutečné analytické
tvary. Goldeny 26 ukázek jsou podklad kompatibility zachycený před změnou jádra,
nikoli analytický důkaz. Úplná obnova slovníků kontextu se netvrdí (P1.2B).

## Výkon ve stejném prostředí

Před změnou produkčního kódu vznikla baseline `tests/benchmark_p0.py` na main
`15b8bf48f12b6d59ac6ea554def414f8d4ae4979`, jehož produkční zdroje jsou shodné
s `6e38d06` z návrhu. Stejný měřič, vstupy, stroj a knihovny; zahřátí + 3 měření,
mediány v sekundách. Bez prahů rychlosti v CI.

| Scénář | Před | Kandidát | Poměr |
|---|---:|---:|---:|
| Příruba | 0,014008 | 0,032118 | 2,29× |
| Krabička | 0,029631 | 0,066769 | 2,25× |
| Rám | 0,131218 | 0,148474 | 1,13× |
| Tupý svar – objem | 0,033960 | 0,043854 | 1,29× |
| Encode/pickle/decode | 0,000936 | 0,000951 | 1,02× |
| 1 000 kolmých NDT paprsků | 0,071584 | 0,073827 | 1,03× |

Kontroly všech vstupů, kandidátů a konečných 3D prvků mají skutečnou cenu,
u krátkých přepočtů přibližně 18–37 ms navíc. První kandidát krabičky měl
0,308 s: profil ukázal opakované hledání přesné obálky. Validátor pro konečnost
používá konzervativní `bounding_box(optimal=False)` a stále kontroluje vrcholy,
celý tvar i každý solid. Přesná obálka pro vlastnosti/kompatibilitu se nemění.
Žádná kontrola nebyla vypnuta, nevznikla trvalá cache ani oprava geometrie.

Vstupní SHA a geometrické/NDT podpisy všech scénářů souhlasí. Přenos příruby
vzrostl **57 108 → 57 204 B** kvůli textům zpráv, se stejnými klíči protokolu.
Otisk zdrojů konečného měření je
`57858ce1b5e27bd11a2e5f73c52e090b2f1616de9d9c04d2c1dad45c4ee8988e`.
Paměťové maximum obou procesů bylo 431 980 544 B; jde o celoživotní maximum
včetně importů, nikoli spotřebu scénáře/workerů. Tři opakování nejsou statistická
záruka; měření nezahrnuje start, GUI, spawn ani export. Windows/macOS CI baseline
není s místním strojem přímo srovnatelná.

## Cílové sestavení a přijetí

Obě kompletní kontroly Windows a macOS jsou povinné na aktuální hlavě implementačního PR.
Při vytvoření třetího commitu ještě výsledky jeho workflow nejsou známé.
Jejich skutečný konečný stav, odkazy na pytest a self-test stažených balíčků
jsou součástí předání v popisu implementačního PR. Starší úspěšné běhy A.1/A.2
nejsou důkazem konečného sestavení. PR automaticky nezveřejňuje nové Releases.

**Ruční přijetí autorem dosud neproběhlo.** Použít artefakt z posledního zeleného
macOS běhu implementačního PR. Zapsat commit, macOS, architekturu, datum a výsledek
každého bodu. Případný Windows průchod zaznamenat zvlášť.

1. Příruba: u 3D prvků i ve vlastnostech počet 1. Změnit rozměr, Zpět/Znovu,
   uložit kopii a otevřít; správné rozměry i hlášení.
2. Dvě kružnice Ø10 vzdálené 30 mm, vysunutí 10 mm: obě části ve 3D,
   úspěch **0→2**, celkem 2 tělesa a **500π ≈ 1 570,80 mm³**.
3. Kvádr 20×30×40 + oddělený 5×5×10 na X=100: **1→2 / 24 250 mm³**.
   Odebrat celý malý kvádr: **2→1 / 24 000 mm³**. Srazit čtyři svislé rohy 2 mm:
   **1→1 / 23 680 mm³**.
4. Přidat celý přídavek uvnitř dílu: česká chyba bez účinku, předchozí geometrie
   zachovaná; Zpět/Znovu a oprava rozměru/polohy vrátí platný stav.
5. Kvádr 50×30×20, skořepina t2 s vrškem: **8 472 mm³**, dutina a dno.
   Prázdné otevřené plochy odmítnout; vršek znovu vybrat, použít Zpět/Znovu.
6. Tři oddělené trubky (lineární pole tažení): úspěch **1→3**, všechny části ve 3D.
   Chybné velké zaoblení/sražení zachová předchozí díl a přeskočí další prvky.
7. Stejnou kopii přepočítat na pozadí a porovnat s CLI/offline souhrnem AI;
   shodné počty, úspěchy i chyby. Původní soubor zůstane beze změny.

Tři platné modely pro body 2/3/6 a dvě úmyslně chybné ukázky pro body 4/5
jsou při předání přiložené v chatu.
Generátory totožných analytických případů jsou v `tests/body_count_cases.py`.
Pro vývojáře: `ruff check src tests`, `QT_QPA_PLATFORM=offscreen pytest -q`,
`python tests/benchmark_p0.py --output <nová-evidence.json>`;
`skodacad-gui --self-test <zpráva.txt>` a nativní
`skodacad-gui <dva-válce.json> --screenshot <okno.png>`.

## Omezení a otevřená rizika

build123d 0.13.0 čte `Compound.volume` přes přímé solidy/shelly. Uměle vnořený
compound může mít dva solidy o celkovém objemu 24 250 mm³, ale vlastnost `volume`
vrátí jen 250 mm³. Validátor proto kontroluje shodu se součtem všech skutečných
složek a rozpor odmítá. Kontejnery prochází, žádnou složku nevybírá ani potichu
nepřeskupuje. Běžné platné vícesolidové tvary a uzavřené dutiny jsou podporované.
Obecná oprava rozhraní knihovny není součástí P1.2A.

Objemové nerovnosti jsou nutné postpodmínky, nejsou formálním důkazem prostorové
správnosti jádra. Regrese proto kontrolují také polohu materiálu. Tolerance
mikromezer/řezů OCCT se nezaměňuje za přesnou numerickou hranici aplikace.

R02 má implementované pravidlo a viditelnost počtu; konečné přijetí čeká.
R01 (export/NDT při chybě), R03 (ukládání), R04 (reference), R05 (úplná obnova
kontextu), R12 (popis formátu používaný AI) a odborná NDT-17 zůstávají otevřené.
**Formát modelu je stále 22**, oddíl README předávaný AI, závislosti, zdrojové
ukázky a NDT vymezení se nemění. Nový průnik, P1.2B, P2 a NDT-16 nejsou implementované.
