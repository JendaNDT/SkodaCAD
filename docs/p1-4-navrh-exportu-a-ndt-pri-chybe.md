# P1.4 — návrh exportu a NDT při chybě modelu

**Stav: E1–E9 schválené autorem 24. 10. 2026; implementace E.1–E.4 probíhá.**
Podklad: aktuální `main / f5fbe2cba45d0eab86b1f8fcefa74812c442922c`,
po sloučení [P1.3 / PR #37](https://github.com/JendaNDT/SkodaCAD/pull/37).
Autor odpověděl **„ok, schvaluji“** na předání [návrhového PR #38](https://github.com/JendaNDT/SkodaCAD/pull/38)
a výslovný další krok schválit E1–E9 pro zahájení implementace. Tím jsou schválené
**E1–E9**, kroky **E.1–E.4** a matice **E01–E22**. Implementace má vlastní větev;
[evidence](p1-4-overeni.md) rozlišuje dokončené kroky a zbývající ověření.
Sloučení do `main` zůstává samostatnou branou na pokyn autora.

Navazuje na [roadmapu](roadmapa-vyvoje.md#p1--bezpečná-geometrie),
[smlouvu P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md),
[kontrolu geometrie P1.2A](p1-2a-navrh-spolecne-kontroly-geometrie.md),
[transakce P1.2B](p1-2b-navrh-transakce-kontextu.md),
[reference P1.3](p1-3-navrh-bezpecnych-referenci.md) a R01 v
[auditu P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení).

## 1. Cíl a rozhodnutí ke schválení

Když například selže zaoblení, ponechat poslední dobrý kvádr pro opravu, ale
nevyvézt jej jako hotový díl a nepočítat nad ním NDT výsledky pro chybný recept.
Odmítnutí musí fungovat i mimo okno. Chyba jedné NDT studie na jinak správném
modelu naopak nemá blokovat běžný export geometrie nebo ostatní platné studie.

| Bod | Navržené rozhodnutí |
|---|---|
| **E1 Úplný aktuální model** | Výpočet skončil, výsledek patří současnému dokumentu, všechny prvky jsou `ok` a existuje objemový díl přijatý kontrolami P1.2. Samotné `part is not None`, platnost posledního solidu ani otisk NDT studie nestačí. Více platných solidů zůstává dovoleno. |
| **E2 Export geometrie** | STEP/STL/3MF/GLB/SVG a DXF/SVG řezu povolit pouze pro E1. Při chybě či neaktuálním výsledku odmítnout před prvním zápisem. V P1.4 nepřidávat „Přesto exportovat“, automatické vynechání chybného prvku ani přepínač pro částečný export. |
| **E3 Zachování práce** | JSON recept lze uložit i s chybnou historií. Náhled poslední geometrie, diagnostická měření, opravy a Zpět/Znovu zůstávají. Jasně označit, že zobrazená geometrie je neúplná nebo patří staršímu stavu. Uložení receptu nesmí změnit stav na platný. |
| **E4 NDT nad modelem** | Nad modelem nesplňujícím E1 nespouštět geometrické NDT výpočty, odhady vyžadující těleso, automatickou mapu tloušťky ani potvrzení/odborné ověření studie. Nevytvářet výsledky či zprávy vydávané za posouzení aktuálního dílu. |
| **E5 NDT studie** | Na úspěšném modelu vyžaduje výpočet nad uloženou kontrolovanou oblastí stav `ok`. `stale` vyžaduje kontrolu a výslovné potvrzení, `broken` opravu vazby, `incomplete` doplnění cíle. Potvrzení není odborné ověření a nesmí obejít E1 ani opravit vadnou vazbu náhradním výběrem. |
| **E6 Výsledky a zprávy** | Mapy, přiložení, plány, audit i konstrukční varianty musí patřit aktuálnímu úspěšnému modelu a svému zadání. Zastaralé výsledky nesmějí být znovu viditelné či exportovatelné po chybě/pádu výpočtu. Zastavený audit platného modelu smí dál vytvořit poctivě označenou neúplnou zprávu podle oddílu 5. |
| **E7 Stejná pravidla rozhraní** | Společná kontrola v jádře/session; GUI, přímé session, CLI i offline nástroje AI ji respektují. CLI při odmítnutí nevytvoří export a vrátí nenulový kód. AI dostane stav a důvod, ne pravomoc kontrolu obejít; nevzniká nový AI nástroj pro export či NDT. |
| **E8 Kompatibilita a meze** | Formát 22, uložená pole, worker protokol, závislosti, algoritmy NDT a tolerance zůstávají. Jde o výslovnou změnu dostupnosti operací nad chybným/neaktuálním modelem, ne o migraci dat. R03 (atomické ukládání), zbytek R04 (historická identita), R12 a NDT-17 se tím neuzavírají. |
| **E9 Předání** | Implementovat ve čtyřech malých krocích, po každém Ruff a celý pytest před commitem. Poté oba celé cílové workflow včetně kontroly stažených balíčků; krátký průchod aplikací převezme agent v dostupném rozsahu. Výsledky a skutečné mezery předložit autorovi; sloučení implementace až na jeho samostatný pokyn. |

Doporučujeme schválit E1–E9 jako celek: pouhé vypnutí tlačítka v okně by
nechránilo příkazovou řádku, potvrzení studie ani přímé volání session.
Pokud bude později potřeba export rozpracovaného mezistavu, nejdřív samostatně
navrhnout jeho výslovnou volbu, označení a dohledatelnost. Není součástí P1.4.

## 2. Ověřený výchozí stav a důvod změny

P1.2 a P1.3 jsou na `main`. [Evidence P1.3](p1-3-overeni.md#sloučení-a-vydání-z-main)
uvádí poslední místní sadu 1 451 testů, obě úspěšná následná workflow z `main`,
kontrolu stažených balíčků a vydání. Úplný ruční průchod konečného balíčku ani
odborná NDT-17 se neprohlašují za dokončené. Níže jde o další průzkum nezměněného
produkčního kódu, nikoli o výsledky budoucí implementace P1.4.

| Místo | Dnešní chování a důsledek |
|---|---|
| `rebuild.BuildResult.ok/first_error` | Úspěch historie lze zjistit. Při chybě zůstává poslední přijatý díl; následující prvky jsou `skipped`. To je správné pro obnovu, nikoli doklad dokončeného modelu. |
| `session._require_computed` | Kontroluje jen probíhající úlohu. Po pádu workeru může zůstat předchozí výsledek a jiný dokument; je potřeba také porovnat dokument s `_computed`. |
| `session.export`, `gui.main_window.export_dialog` | Kontrolují běh výpočtu a existenci tělesa, nikoli úspěch celé historie. R01 se týká i této cesty z okna. |
| `cli._build` | Zapíše exporty a až poté vrátí `1` při chybě historie. Nenulový kód tedy dnes nezaručuje, že žádný soubor nevznikl. |
| `cli._ray/_probe/_coverage` | Staví díl přímo, nepoužívají společnou kontrolu úplnosti. Mohou zpracovat poslední dobré těleso; samotné upravení `session.export` je neochrání. |
| `rebuild` po smyčce prvků | Vyhodnocuje studie a případně mapu tloušťky i nad částečným dílem. `ndt.study.evaluate` zná geometrii a otisk receptu, ale ne výsledek celé historie. |
| `session.confirm_ndt_study/verify_ndt_study` | Potvrzení nepožaduje `result.ok`; platnost studie ani shodný `_computed` neprokazují úspěch prvků. U plochového cíle je možné po potvrzení přijmout studii nad neúplným dílem. |
| UT/PT/MT/RT vstupy, audit a návrhy | Kontroly cíle, stavu studie a mezipamětí již existují. Chybí společná podmínka E1 před výpočtem a vydáním výsledku. Některé objemové cesty už přes `_final_part` chybu historie odmítají; nesmí se oslabit. |
| `assistant.MODEL_TOOLS/build_report/view_part` | AI dnes nemá nástroj pro export ani výpočet NDT. Umí upravit recept a prohlédnout náhled; souhrn uvádí chybu, ale také rozměry posledního tělesa. Ty musí být výslovně označené jako diagnostické. |

### Průzkum na skutečné geometrii, 24. 10. 2026

Lokální Python 3.12.14, stejné zamčené jádro jako `main`. Nový zkušební recept:
kvádr 20 × 30 × 40 mm, PT studie horní plochy, následně zaoblení všech hran R50.
Pokusy pracují jen s novými soubory v pracovní evidenci; nemění ukázky ani zdroje.

| Pokus | Skutečný výsledek před P1.4 |
|---|---|
| Přepočet po přidání R50 | `ok=False`, chyba `fillet1`, poslední platné těleso 24 000 mm³ / 1 solid. |
| Přímý `session.export` | STEP vznikl, 15 408 B. |
| `skodacad build … --format step` | Návratový kód 1, ale STEP přesto vznikl, 15 408 B. |
| Potvrdit PT studii na chybném modelu | Původně `stale`, po potvrzení `ok`, chyba zaoblení přitom zůstala. |
| Výpočet PT po potvrzení | Odhad 24 vzorků / krok 10 mm; skutečný výpočet a export CSV 5 339 B prošly. Audit tuto studii nabízí jako `ready/pt`. |
| `skodacad paprsek … --z 0,0,50 --smer 0,0,-1` | Vrátí 0 a spočítá 40 mm materiálu přes neúplný díl. |

To nedokazuje nesprávný výpočet průchodu kvádrem. Dokazuje to záměnu
**správné geometrie mezistavu** za **výsledek celého zadaného receptu**.
V průzkumu nebylo zapisováno žádné odborné ověření studie.

## 3. Společná kontrola použitelnosti

Zavést malou sdílenou kontrolu výsledku, použitelnou také CLI mimo session,
a obal v `ModelSession` pro aktuálnost dokumentu. Neprovádět plošné rozdělení
session, zavádění nového systému stavů ani změnu serializace `BuildResult`.

Pořadí rozhodnutí pro operaci vyžadující hotový díl:

1. Existuje dokument a neběží úloha, při níž podle dosavadních pravidel nesmí
   operace začít. Zachovat stávající rušení a ochranu před souběhem.
2. Existuje výsledek a odpovídá aktuálnímu dokumentu. V session použít `_computed`
   a dokument, ne pouze otisk NDT, objem, počet těles či `failure == ""`.
   CLI při `--set` posuzuje výsledek skutečně přepočteného receptu s těmito hodnotami;
   také parametry a otisk ve výstupu musí odpovídat tomuto receptu.
3. Historie je celá úspěšná: odmítnout `error` i `skipped`. Předat id/název prvního
   chybného prvku a příčinu. Pokud první chyba chybí, použít obecný důvod neúplnosti;
   nespoléhat jen na `first_error`.
4. Existuje objemový díl. Prázdný recept nebo samotné skici nejsou exportovatelný
   díl, i když nemají chybný prvek. Validaci geometrie nadále zajišťuje P1.2;
   nepřidávat opakované drahé průniky při každém čtení mapy ani jiné tolerance.
5. Pro NDT navíc posoudit konkrétní studii, cíl a původ výsledku podle oddílu 5.

Kontrola je před otevřením/zápisem cíle, vytvořením výstupní složky a spuštěním
NDT práce. Při odmítnutí nevznikne nový soubor; existující cíl zůstane byte shodný.
To není záruka atomického zápisu při pozdější chybě disku: taková oprava R03 je
mimo rozsah. Neplatný pokus nesmí změnit dokument, cestu, příznak změn ani historii.

Příklady zpráv:

- „Model není dokončený: prvek fillet1 má chybu — zaoblení R50 se nepodařilo.
  Zobrazené těleso je poslední dobrý mezistav. Oprav prvek nebo použij Zpět;
  potom export zopakuj.“
- „Aktuální změna se nepodařila spočítat. Náhled patří předchozímu stavu.
  Přepočítej model znovu nebo vrať změnu pomocí Zpět.“
- „Studie je zastaralá. Zkontroluj oblast a nastavení a potvrď ji pro aktuální
  díl. Tím se nezapisuje odborné ověření.“

## 4. Co zůstane dostupné pro opravu

| Operace | Chybný nebo neaktuální model | Úspěšný model s vadnou/zastaralou NDT studií |
|---|---|---|
| Zobrazení posledního dílu, otočení, řez jako pohled | Ano, s trvalým upozorněním na neúplný/starší stav; ne pouze krátkým oznámením. | Ano. |
| Vlastnosti a měření viditelného tělesa | Diagnosticky, s označením mezistavu; nezobrazovat je jako vlastnosti dokončeného receptu. | Ano; chyba samostatného uloženého měření nezneplatní geometrii. |
| Opravit recept, parametry, skicu, odstranit prvek; Zpět/Znovu | Ano, přes stávající session a historii. | Ano. |
| Uložit/Uložit jako JSON, znovu otevřít | Ano; uloží skutečný recept včetně chyby, ne automaticky oříznutou historii. | Ano, beze změny platnosti studie. |
| Textové NDT nastavení, poznámka, smazání/kopie studie | Ano, kde nevyžaduje výpočet na tělese; žádné automatické potvrzení. | Ano. |
| Nový výběr NDT cíle z 3D, kontrola cílového objemu | Až po obnovení E1; neukotvovat cíl k částečnému dílu. | Ano; nové ukotvení nemusí samo potvrdit zastaralou studii. |
| Běžné exporty dílu a obrysu řezu | Ne. | Ano; nesouvisející chyba NDT je nezablokuje. |
| NDT mapy, výpočty a zprávy | Ne; staré mapy skrýt a nepoužít jako náhradu. | Jen platné studie; souhrnný audit může neplatné studie uvést jako nedostupné bez čísel. |
| Náhled pro AI (`view_part`) | Ano, s výslovným popisem původu obrázku i čísel; slouží k opravě. | Ano. |

Normální SVG export zůstává exportem a řídí se E2. Obraz v samotném okně nebo
náhled předaný AI je diagnostický pohled. P1.4 nepřidává export diagnostických
obrázků pro uživatele ani nový souborový formát.

## 5. Pravidla pro NDT a výsledky

### Model, studie a odborné ověření jsou tři různé podmínky

- Při neúspěchu historie `rebuild` nepočítá mapu tloušťky a nedokládá platnost
  NDT oblasti na posledním tělese. Použije stávající diagnostické `StudyResult`
  se stavem `broken` a konkrétním důvodem **chyby modelu**, ne tvrzením, že každá
  původní plocha zanikla. V panelu ani souhrnu nesmějí být jako aktuální výsledek
  uvedené objemy cíle či odborná platnost. Žádný nový stav/pole do JSON či IPC.
- Po úspěšné opravě se studie znovu vyhodnotí běžnými pravidly. `stale` se samo
  nepotvrdí; `broken` a `incomplete` nedostanou náhradní oblast. Opětovný výpočet
  neobnovuje odborné ověření platné jen pro jiný díl/cíl.
- Potvrzení vyžaduje E1 a znovu ověří **celou** oblast. Odmítnutí je bez změny
  receptu/historie. U nové volby cíle zachovat oddělený krok potvrzení a Zpět.
- `verify_ndt_study` musí vyžadovat E1 a platnou studii i u plochového cíle.
  Automatické testy ani AI nesmějí za autora/odborníka potvrdit skutečné ověření.
  Pro geometrické výpočty samotné se odborné ověření nevyžaduje; zachovat údaj
  „Neověřeno“ a všechna doslovná upozornění UT/PT/MT/RT.

### Výpočty a pracovní náhledy

Podmínka E1 se vztahuje na UT pokrytí ploch/objemu, návrh poloh, plán a jeho
ověření, PT/MT/RT, mapu tloušťky, audit a výpočet/aplikaci/uložení konstrukčních
variant. Zahrnuje synchronní volání, odhady s geometrií i spuštění na pozadí.
Kontroluje se také při převzetí výsledku a jeho exportu; předchozí úspěšné spuštění
nenahrazuje kontrolu aktuálnosti. Pozdní odpověď zrušené/staré úlohy nesmí oživit mapu.
Mapa tloušťky nemá vlastní studii: vyžaduje E1 a současné nastavení mapy, nikoli
nově založenou NDT studii nebo potvrzení jiné nesouvisející studie.

Na úspěšném modelu zachovat pracovní přiložení sondy/jha nebo náhled projekce
pro nastavování studie. Pokud studie není `ok`, označit náhled jako pracovní;
nenahrazuje výpočet její oblasti a nesmí odemknout mapu nebo potvrzení.
Na neúspěšném modelu skrýt i tyto geometrické výsledky, ponechat nastavení k opravě.

CLI `paprsek`, `sonda` a `pokryti` s výslovným jednorázovým cílem nad úspěšným
modelem nadále fungují i bez uložené studie. Tam není správné vynucovat existenci
studie. Jestli příkaz používá uloženou **kontrolovanou oblast**, potřebuje `ok`;
pouhá kopie rozměrů sondy ze záznamu není potvrzením oblasti. Výstup musí rozlišit
jednorázové zadání a vyhodnocení uložené studie. Předpoklady a upozornění zachovat.

### Mezipaměti, audit a varianty

Neodstraňovat stávající klíče výsledků (přepočet, zadání studie, materiál,
přiložení a další nastavení). Doplnit podmínku E1 také do dostupnosti výsledků,
ne jen tlačítek. Po chybě workeru se mohou změnit dokument i dostupnost, přestože
identita starého `result` zůstane; tuto situaci musí pokrýt regrese.
Oprava, Zpět, Znovu a nové otevření nesmějí vydávat nesouvisející starou mapu za novou.

Na platném modelu audit dál rozlišuje spočítáno/neprovedeno/nedostupné. Vadná,
zastaralá nebo neúplná studie nemá procenta a nesmí se počítat jen její zbývající
plocha. Ostatní zahrnuté platné studie lze vyhodnotit. Zastavený audit lze exportovat
s existujícím označením neúplnosti: hotové studie jsou výsledky, zbytek neprovedeno
s důvodem. Nula procent není náhradou za nedostupnost. HTML/CSV a PDF z okna
musí obsahově souhlasit a nést doslovná upozornění metod.

U konstrukčních variant zůstává výpočet na kopiích a výslovné použití varianty.
Původní model musí splnit E1; varianta s chybnou historií zůstane neúspěšná,
bez cílových procent, použití a uložení jako přijatá varianta. Chyba jedné varianty
nemá rušit ostatní. Částečná zpráva na platném modelu dál pravdivě uvádí stav běhu.

## 6. Konkrétní implementační kroky po schválení

| Krok | Závislost a změna | Výstup a dokončení |
|---|---|---|
| **E.1 Společná kontrola a exporty** | Po schválení E1–E9. Malá společná kontrola v jádře a obal session; zapojit `session.export/export_section`, přímý `cli._build` a jeho větev mapy. Zachovat API nízkoúrovňových zapisovačů přijímajících jen `Part` — ty samy historii neznají. | E01–E08: všechny formáty odmítnuté před zápisem, platný vícesolidový díl funguje, JSON a historie zachované. Ruff + celý pytest; první malý commit. |
| **E.2 NDT a aktuálnost** | Po E.1. Kontrola v `rebuild` pro stavy studií/mapu, session vstupy pro potvrzení/ověření/cíle/sondu/metody/audit/varianty, mezipaměti a jejich exporty. Zvlášť přímé cesty CLI `paprsek/sonda/pokryti`; zachovat jednorázová zadání. | E09–E18 a E22: žádné použití částečného nebo starého tělesa, žádné tiché potvrzení, zachované metody/nejistoty/částečné zprávy. Ruff + celý pytest; druhý commit. |
| **E.3 Okno, AI a obnova** | Po E.2. GUI dostupnost akcí a trvalé označení náhledu, konkrétní příčina odmítnutí, označení čísel/obrázku v offline souhrnu AI. Kontroly v session zůstávají rozhodující i při přímém vyvolání akce. | E19–E21 a opakování souvisejících E04/E07/E09: Qt s náhradním viewerem a skutečným workerem, snímek skutečného okna a návod obnovy. Bez volání placeného AI API. Ruff + celý pytest; třetí commit. |
| **E.4 Přijetí a evidence** | Po E.3. Doplnit mapování matice na testy, výsledky, meze a krátký scénář níže; spustit baseline P0 a oba celé workflow pro konečnou hlavu PR. | Místní Ruff/celý pytest, Windows/macOS sestavení i self-test skutečně staženého artefaktu. Agent provede dostupné funkční kontroly; odliší zdrojové Qt testy, nativní zkoušku a CI. R01 uzavřít jen pro doložené cesty; předat PR, neslučovat bez samostatného pokynu. |

Při implementaci projít všechna volání, která skutečně vydávají výsledek: zejména
`export_thickness_map`, `export_ndt_coverage/pt/mt/rt/rt_png/access/plan/audit/design`,
GUI PDF a přímé `write_csv/write_folder` v CLI. Ochrana nesmí zůstat pouze na
veřejné metodě, kterou jiné rozhraní obchází. Nízkoúrovňové čisté geometrické
funkce a zapisovače nad samostatným `Part` nedostanou umělou závislost na session;
záruka se týká všech podporovaných vstupních cest aplikace s receptem.

Po každém kroku zachovat dosavadní testy. Výslovné změny starého chování
(E2/E4/E5) se doloží novým očekáváním a příčinou; neupravovat nesouvisející
geometrická očekávání, tolerance ani vypínat původní testy kvůli zelenému výsledku.

## 7. Budoucí regresní matice E01–E22

**Specifikace k implementaci; následující případy zatím nejsou vykázané jako hotové testy.**
U odmítnutí kontrolovat absenci nového souboru i byte shodu existujícího cíle,
nezměněný dokument/cestu/historii a srozumitelnou příčinu. Použít skutečnou
geometrii; záměny worker výsledků ověřit řízeně a alespoň jedním skutečným spawn.

| ID | Scénář | Kritérium přijetí |
|---|---|---|
| E01 | Úspěšný kvádr 20×30×40, exporty STEP/STL/3MF/GLB/SVG a řez DXF/SVG. | Platné neprázdné výstupy; u STEP znovunačtení a 24 000 mm³ / rozměry 20×30×40 / 1 solid. Dosavadní testy sítí/náhledu zachované. |
| E02 | Dva oddělené kvádry 20×30×40 a 5×5×10. | Úspěšný recept, 24 250 mm³ / 2 solidy; export nezahodí druhé těleso a nevyžaduje právě jedno. |
| E03 | Kvádr + neproveditelné R50 + následující sražení. | `error/skipped`, zachované 24 000 mm³ a kontext. Všechny exporty dílu i řezu se odmítnou; nevynechat konec historie. |
| E04 | E03 přes přímou session, GUI akci a `build --format …`, nové i existující cíle. | Stejný důvod/prvek, žádný zápis či vytvoření výstupní složky kvůli odmítnutí. CLI má kód 1 pro známou chybu historie; chyba vstupu/I/O dál kód 2. Nepsat „Uloženo“. |
| E05 | Prázdný recept, jen skica a chyba prvního prvku bez tělesa. | Žádná falešná připravenost z prázdného `all(...)`; odmítnutí bez havárie. Chyba samostatného měření na jinak platném modelu neblokuje export. |
| E06 | Nová změna se počítá, starý díl je vidět. | Export/NDT blokované; přímá akce v GUI kontrolu neobejde. Stav po dokončení odpovídá novému receptu. |
| E07 | Worker selže nebo vyprší čekání po změně dokumentu; starý `result.ok=True`. | Odmítnout podle aktuálnosti, i když už `computing=False` a starý díl existuje. Oprava/opakování výpočtu obnoví dostupnost bez trvalého zámku. |
| E08 | Zastavit přepočet s návratem do posledního spočítaného dokumentu. | Je-li vrácený model úspěšný, export jde; je-li vrácený stav s chybou, zůstane blokovaný. Znovu vrátí zrušenou změnu podle dosavadní smlouvy. |
| E09 | PT studie → R50 → potvrzení, odborné ověření, odhad, synchronní/pozadí PT a export. | Vše blokované kvůli modelu; potvrzení ani ověření nemění recept/historii. Žádný aktuální cíl/čísla ani nová mapa. Regrese původního průzkumu z oddílu 2. |
| E10 | E09 pro UT plochový/objemový cíl, návrh poloh a plán; MT a RT včetně PNG. | Stejná modelová podmínka před výpočtem/odhadem, přiložením a exportem; všechny podporované cesty bez náhradního mezistavu. |
| E11 | Chybná historie + zapnutá mapa tloušťky (`with_map=True`, GUI, `build --mapa`). | Nespouštět její výpočet, vrátit důvod nedostupnosti; žádné nové CSV ani stará barevná mapa na aktuálním dílu. |
| E12 | Platná deska: změna t=20→30, studie `stale`, pak kontrola cíle a explicitní potvrzení. | Před potvrzením bez výpočtu oblasti; po úspěšném potvrzení výpočet jde. Odborné ověření pro starý díl neplatí. Pracovní náhled sondy není potvrzením. |
| E13 | `broken` (chybějící/nejednoznačná plocha) a `incomplete`; seznam s jednou vadnou plochou. | Celá oblast odmítnutá, ne pouze její vadný kus. Oprava novým výběrem, případné potvrzení a historie fungují; platná geometrie se stále exportuje. |
| E14 | Hotové výsledky všech metod → změna dílu/nastavení/sondy/materiálu → pád workeru. | Getter, kreslení i export ztratí aktuálnost; změněná identita dokumentu nesmí ponechat starý výsledek platný kvůli stejnému `result`. |
| E15 | Pozdní výsledek po nové úloze, Zpět/Znovu, otevření jiného receptu. | Nepřijmout cizí mapu/audit/variantu; nezměnit dokument ani historii. Po nové úspěšné práci je čerstvý výsledek dostupný. |
| E16 | Audit platného modelu: platná a vadná studie, výběr části studií, zastavení po jedné. | Hotové výsledky zachované; zbytek nedostupné/neprovedeno s důvodem, ne 0 %. Zpráva nese neúplnost, správná čísla a doslovná upozornění. |
| E17 | Audit a konstrukční návrh nad chybným nebo starým modelem. | Odmítnout před spuštěním a zápisem HTML/CSV/PDF; dřívější cache neodemkne export, použití ani uložení varianty. |
| E18 | Návrh na platném modelu s dobrou a geometricky chybnou variantou. | Originál byte/obsahově zachovaný; chybná varianta nemá výsledky oblasti a nejde použít/uložit jako přijatá. Ostatní varianty a pravdivá částečná zpráva zůstávají. |
| E19 | GUI: neúspěch, oprava, náhled řezu a přímé volání zakázané akce. | Trvalé srozumitelné označení mezistavu, důvod a cesta opravy; po opravě akce dostupná. Offscreen testy nahrazují dialogy a mají časovou mez. |
| E20 | Offline AI souhrn a `view_part` pro chybný/starý a pak opravený model. | Obrázek/rozměry označené jako neúplný/starší náhled, chybný prvek uvedený; žádné vymyšlené NDT výsledky, nový nástroj nebo síťový požadavek. |
| E21 | Uložit chybný JSON jako kopii → nové otevření → oprava → Zpět/Znovu. | Formát 22, zachovaná skutečná chyba a originál, funkční historie v sezení; úspěšná oprava export odemkne, návrat k chybě opět zamkne. |
| E22 | CLI `paprsek/sonda/pokryti` a session metody; platný/neplatný recept, `--set`, jednorázový cíl i uložená studie. | Chybná historie odmítnutá před algoritmem/zápisem s kódem 2 (dosavadní větev chyby vstupu NDT); úspěšná jednorázová geometrie dál funguje bez studie. Vadná uložená oblast se neobejde jako částečná. Předpoklady/nejistoty zachované. |

Matice je minimální soubor scénářů, nikoli požadavek na přesně 22 testovacích funkcí.
Všechny dosavadní ukázky, načtení verzí 1–22, P1.2/P1.3, geometrická nejistota a
analytické NDT případy mají zůstat. Časové srovnání použije stávající baseline P0
(zahřátí + 3 opakování), bez nových náhodných prahů v pytest.

## 8. Krátký postup přijetí a obnovy

Po implementaci připravit dva malé recepty a přesné sestavení aplikace. Autor
nemusí znovu potvrzovat dlouhou řadu jednotlivých případů; dostupné zkoušky
provede agent a předá protokol se snímky a případnými omezeními ovládání.

1. Na platném kvádru ověřit 24 000 mm³, 1 těleso a úspěšný STEP export.
2. Přidat chybu R50: kvádr zůstane viditelný s upozorněním, export dílu/řezu a NDT
   se odmítnou s důvodem. Pokus nesmí přepsat dříve vyexportovaný STEP/CSV.
3. Uložit chybný recept pod novým jménem a znovu otevřít; chyba musí zůstat
   opravovatelná. Uložením se výpočet ani studie nestanou platnými.
4. Opravit R50 na podporované R2 nebo použít Zpět; po úspěšném přepočtu export
   funguje. Znovu na chybný stav jej opět zablokuje. Zkontrolovat studii a podle
   jejího stavu opravit oblast/potvrdit aktuální díl; až potom nově spočítat mapu.
5. Na platném modelu ověřit zastaralou studii: export geometrie jde, výpočet její
   oblasti vyžaduje potvrzení. Nedostupný výsledek se nesmí zobrazit jako 0 %.

Při pádu přepočtu zachovat recept, zkusit znovu přepočítat, upravit chybný prvek
nebo použít Zpět. **Zastavit** během přepočtu má dosavadní význam návratu k poslednímu
spočítanému dokumentu. Po opravě vždy vyhodnotit skutečný stav studií; neobnovovat
odborné ověření automaticky. P1.4 nezavádí zálohy ani opravu poškozeného souboru R03.

Označit každou zkoušku jako zdrojovou automatizaci, skutečnou nativní zkoušku,
CI balíček nebo potvrzení autora. Nedostupné ovládání nativního dialogu nesmí být
vydávané za úspěch ani nahrazované vymyšleným ručním přijetím. Windows bez ručního
průchodu tak označit; odborná validace NDT-17 zůstává samostatná.

## 9. Hranice dokončení

P1.4 je připravené k přijetí až po doložení E01–E22, místního Ruff/celého pytest,
obou úplných workflow pro konečnou hlavu implementačního PR, self-testů stažených
balíčků a českého protokolu s konkrétními mezerami. R01 lze uzavřít pro podporované
cesty aplikace, když žádná z nich nevydá neúplný/starý model jako hotový výsledek.
Samostatný pokyn autora je nutný ke sloučení implementace do `main`.

Tento návrh nespouští P1.5, P2 ani nový modelový formát. Neřeší uloženou identitu
ploch, bezpečné ukládání R03, text formátu pro AI R12 ani úplnou kvalifikaci NDT.
NDT-16 je nadále mimo rozsah; NDT-17 na něm nezávisí. Platný geometrický výsledek
ani úspěšné testy nejsou dokladem detekovatelnosti vad či odborného ověření.
