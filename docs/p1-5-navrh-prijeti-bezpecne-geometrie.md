# P1.5 — návrh přijetí bezpečné geometrie

**Stav: schváleno autorem 24. 10. 2026, provedení F.1–F.4 zahájeno.**
Autor po předložení návrhového PR #40 a rozsahu F1–F9, F.1–F.4 a P01–P24
odpověděl **„schvaluji“**. Tím povolil provedení; sloučení do main ani nové
produkční opravy tím schválené nejsou. [Evidence provedení](p1-5-overeni.md).
Základ: `main / e7f9ac6111fa789a7bbaa80aba6e8cfda9c45271`, sloučené
[PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39).

Navazuje na [roadmapu P1](roadmapa-vyvoje.md#p1--bezpečná-geometrie),
[smlouvu P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md),
[P1.2A](p1-2a-overeni.md), [P1.2B](p1-2b-overeni.md),
[P1.3](p1-3-overeni.md) a [P1.4 včetně vydání](p1-4-overeni.md#sloučení-a-vydání-z-main).

## 1. Výsledek pro autora

Jedno dohledatelné přijetí dosavadní P1: které geometrické operace a pracovní
postupy mají ověřené výsledky, jak se zachovají při chybě a co zůstává omezené.
P1.5 má spojit dosavadní důkazy a doplnit skutečné mezery ve zkouškách.
Nepřidává modelovací funkce ani nemění chování aplikace.

Výchozí main prošlo na Windows i macOS všemi **1 549 testy bez chyb a přeskočení**,
Ruff, měřicí baseline, sestavením, kontrolou staženého balíčku a zveřejněním.
Vydaná aplikace prošla i vlastním testem na Macu M4. To je výchozí důkaz,
nikoli tvrzení, že už je celá P1 přijata nebo že neexistují jiné chyby.

## 2. Schválená rozhodnutí F1–F9

| Bod | Doporučené rozhodnutí | Přesná hranice |
|---|---|---|
| **F1 Rozsah** | Přijmout společně pravidla D1–D7 a implementované A1–A7, B1–B7, C1–C8 a E1–E9 v dohodnuté sadě níže. | Stávající `new/add/cut`, hrany, otevřená skořepina, loft, pole/zrcadlení a jejich návaznosti. Budoucí průnik X01–X03 z P1.1 zůstane označen jako neimplementovaná specifikace. |
| **F2 Důkazy místo duplicit** | Nejprve přiřadit každému požadavku existující test nebo protokol; nové regrese jen pro doloženou mezeru. | Žádná druhá rozsáhlá sada NDT map, zlaté binární BREP soubory ani nové testovací prostředí. Starý test se počítá jako důkaz až po ověření jeho skutečných kontrol a spuštění na konečné verzi. |
| **F3 Nezávislé očekávání** | Geometrii posuzovat podle vzorce, rozměrů, počtu těles a materiálu v konkrétních místech; samostatně kompatibilitu se starými modely. | Stejný objem, hash nebo výsledek dvou volání téhož algoritmu není důkaz správné geometrie. Naměřené hodnoty složitých ukázek označit jako kompatibilitní baseline. |
| **F4 Numerika a více těles** | Zachovat schválené tolerance, podporu více solidů a pravdivé hlášení jejich počtu. | Nezvětšovat tolerance, neopravovat mezery a nepožadovat plošně jediný solid. U mezery 10⁻⁸ mm připustit dle D3 počet 1 nebo 2, bez tvrzení o fyzickém spojení. |
| **F5 Vratnost a aktuálnost** | Ověřit celý průchod změna → chyba → kopie → otevření → oprava → Zpět/Znovu, včetně skutečného workeru a neaktuálních výsledků. | Při odmítnutém výstupu původní soubor zůstane shodný; chybný recept je opravitelný. Nejde o ochranu před přerušením zápisu na disk R03. |
| **F6 Způsob ovládání** | Dostupné zkoušky provede agent; autor dostane jeden souhrnný protokol místo potvrzování každého případu. | Odlišit offscreen Qt s náhradním viewerem, skutečné nativní kreslení, programové vyvolání akcí, ovládání myší a autorovo přijetí. Nedostupný krok zapsat jako neověřený. |
| **F7 Cílové balíčky** | Celý pytest, Ruff, baseline a oba úplné workflow pro konečnou hlavu implementačního PR; ověřit právě stažené balíčky. | Windows stačí pro tuto technickou bránu spuštění v CI; fyzický průchod na autorově Windows se tím netvrdí. Na dostupném Macu navíc spustit staženou aplikaci s odděleným profilem a skutečným viewerem. |
| **F8 Nálezy** | Chybějící důkaz doplnit testem; novou produkční vadu zapsat s reprodukcí a předložit omezenou opravu ke schválení. | P1.5 samo neopravňuje měnit `src`, závislosti, modelový formát, worker protokol, NDT algoritmy ani pravidla výsledků. Nezelenit test změnou očekávání nebo přeskočením. |
| **F9 Dokončení a meze** | Uzavřít pouze doložený rozsah po kontrolách z oddílu 7 a předat jej autorovi k přijetí. | R03, historická identita R04, R12, širší ergonomie/GPU a odborná NDT-17 zůstávají samostatné. P2 ani sloučení implementace do main nejsou tímto schválené. |

## 3. Kde už jsou důkazy a co se smí doplnit

| Oblast | Existující podklady v repozitáři | Práce P1.5 po schválení |
|---|---|---|
| Objemová smlouva, fyzický účinek a přímé úpravy | `test_geometry_validation.py`, `test_geometry_modifications.py`, `test_features.py`, `test_sweep_loft.py`, `test_body_counts.py` | Přiřadit případy G/N/A/C/F/H/S/L/M/T z P1.1 a V1–V14 z P1.2A; doplnit jen chybějící kontrolu polohy, materiálu či účinku. |
| Transakce celého prvku | `test_feature_transactions.py`, `test_feature_transaction_interfaces.py`, `transaction_cases.py`, `native_ownership.py` | Přiřadit T01–T14 z P1.2B; rozlišit skutečnou chybu geometrie od řízené injekce poruchy a doklad vlastnictví geometrie od pouhé shody ukazatelů. |
| Reference a skicář | `test_reference_selectors.py`, `test_reference_mapping.py`, `test_reference_consumers.py`, `test_reference_interfaces.py`, `test_reference_sketcher_roundtrip.py`, `test_reference_limits.py` | Přiřadit S01–S20 z P1.3 a zachovat negativní důkazy mezí identity. Ověřit uloženou kopii a návrat promítnutých hran ze skicáře. |
| Výstupy a NDT při chybě | `test_output_guard.py`, `test_output_ndt.py`, `test_output_gui.py`, `test_background.py` | Přiřadit E01–E22 z P1.4; zejména nespoléhat jen na vypnuté tlačítko, ověřit veřejnou cestu session/CLI/AI. |
| Kompatibilita | `test_p12a_compatibility.py`, `test_p0_regressions.py`, `test_document.py`, `test_examples_and_cli.py` | Zachovat 26 rekurzivních ukázek a načítání 1–22. Test jednoduchého kvádru s každou verzí není doklad všech historických kombinací; reálné migrační případy posoudit v `test_document.py`. |
| Dodání a měření | `benchmark_p0.py`, oba workflow, self-test aplikace, protokoly P1.2–P1.4 | Nové výsledky svázat s konečnou hlavou PR, kontrolním merge a otiskem zdrojů; starší protokoly uvést jako historii, ne jako novou ruční zkoušku. |

Cesty testů v tabulce jsou relativní ke složce `tests/`. Základní inventura má
u každé položky stav **doloženo / doplnit / známé omezení / mimo rozsah**,
konkrétní testovací identifikátor a důvod. Chybějící důkaz se nesmí označit za hotový
jen odkazem na celý soubor.

Případné nové jednoduché recepty patří do testovacích pomocníků podle současných
`body_count_cases.py` / `transaction_cases.py`, ne mezi platné ukázky, pokud mají
úmyslnou chybu. Exportovatelné recepty používají stávající formát 22, žádná nová
pole ani nový trvalý datový formát. Protokol a matice jsou Markdown dokumenty.
Změny mohou být v `tests/` a `docs/`, případně v odkazech README/CLAUDE.
Workflow v první sadě zachovat; případnou nutnou změnu zvlášť zdůvodnit předem.

## 4. Minimální přejímací matice P01–P24

Jde o požadavky, nikoli o 24 nových testů. Existující pokrytí se použije znovu.
Přesné geometrické zadání je ve smlouvě P1.1; poloha a výběr se nesmějí zaměnit
za pořadí ploch či hran. Hodnoty jsou v mm/mm³.

| ID | Referenční případ | Podmínka přijetí |
|---|---|---|
| **P01** | Kvádr 20×30×40, první `new` i `add`. | 24 000 mm³, obálka 20×30×40, 1 platný uzavřený solid; druhé `new` je chyba. |
| **P02** | Dvě kružnice Ø10, středy ±15 v X, výška 10; pole tří trubek. | `500π` / existující trojnásobný analytický objem trubky; 2 / 3 skutečné složky, obě/všechny zachované a oznámené. |
| **P03** | Překryv dvou základních kvádrů o 10 v X, přídavek 5×5×10 dotykem nebo odděleně. | 36 000 / 24 250 mm³; obálka a materiál na správném místě, pravdivý počet 1/2; původní těleso beze změny. |
| **P04** | Kapsa 5×5×10 a pásový řez X=9…11. | 23 750 / 21 600 mm³, 1 / 2 solidy; kontrolní bod v kapse/řezu je mimo materiál, okolní materiál zůstane. |
| **P05** | Dvě průchozí díry Ø4 v desce 40×40×10. | `16 000−80π` mm³; skutečně chybí materiál v obou polohách, ne pouze správný součet objemů. |
| **P06** | Přidání bez účinku, řez mimo/jen dotykem, úplné odebrání. | Česká chyba, žádný přijatý nový tvar ani částečný záznam operace; původní kontext/geometrie zachované. |
| **P07** | Prázdný Part, povrch, otevřený shell i s kladným objemem; vadná/nerozlišitelná složka. | Odmítnutí celého kandidáta; žádná tichá ztráta jedné složky. Samotná platná 2D skica zůstane povoleným mezikrokem. |
| **P08** | NaN/∞, nulové a záporné rozměry; účinek 0, 0,5 εV, εV, 2 εV. | Konečné kladné rozměry podle stávajících pravidel; účinek do εV včetně odmítnut. Nad mezí stále platí ostatní postpodmínky. Oddělit test aritmetické hranice od skutečné geometrie. |
| **P09** | Dotyk hranou/bodem, mezery 10⁻⁵ a 10⁻⁸ mm. | Žádné vlastní slučování; počty podle smlouvy (u 10⁻⁸ počet 1 nebo 2) a pravdivá zpráva. Nikdy z toho neodvozovat fyzické spojení. |
| **P10** | Čtyři svislé vnější hrany kvádru: R3 a sražení 2. | `24 000−(4−π)×9×40` / `24 000−4×(4/2)×40` mm³; správné rohy, 1 solid. |
| **P11** | Vnitřní roh L z P1.1: R2 a sražení 2. | `3 000+(4−π)×10` / 3 020 mm³; platná výplň a stejný počet těles. Růst objemu zde není chyba. |
| **P12** | Skořepina 50×30×20, otevřený vršek, t=2; žádné otevřené plochy / nemožná stěna. | 8 472 mm³, původní obálka, správné dno a stěny; vadné zadání odmítnuté bez zmenšeného plného kvádru jako náhrady. |
| **P13** | Loft čtverců 40→20, výška 30; kruhů Ø40→Ø20; vadné profily a duté přechody. | 28 000 / `7 000π` mm³, výška a profily; odmítnutí vadného objemu. Zachovat různé dosavadní významy tloušťky dutých přechodů. |
| **P14** | Chyba poslední podoperace pole/zrcadlení/díry se závitem, skici a její projekce. | Obnoven celý přijatý kontext i nativní geometrie; žádný kus neúspěšného prvku. Následující prvek `skipped`, konkrétní příčina. |
| **P15** | Jednoznačná reference po změně, chybějící či rovnocenní kandidáti, pevný poloměr/normála a úplný fragment. | Správná geometrická vazba nebo výslovné odmítnutí; pořadí enumerace nemění volbu. Vadná část seznamu se nevynechá. |
| **P16** | Zaniklá díra s jinou jedinou shodou, geometrická náhrada a `top+offset`. | Zaznamenat reprodukovanou mez historické identity z `test_reference_limits.py` jako **známé omezení R04**, nikoli úspěšné bezpečné sledování původní plochy. Bez nové identity/formátu. |
| **P17** | Editace promítnutého profilu, kopie JSON, nové otevření a Zpět/Znovu. | Uložené reference a skutečné body přežijí přechod přes skicář; neztratí se jejich kontrola, originální soubor zůstane shodný. |
| **P18** | Platný kvádr a dvě tělesa → export STEP/STL/3MF/GLB/SVG, řez DXF/SVG; následně R50 a konec historie. | Platné výstupy zachované, STEP znovu načten se správným objemem/počtem/rozměry. Při chybě žádný nový soubor, složka ani změna existujícího cíle. |
| **P19** | Chybný recept → Uložit jako → otevřít → R2 → Zpět/Znovu. | Chyba se uloží opravovatelně ve v22; po opravě export dostupný, návrat k chybě jej blokuje. Originál zůstane beze změny, stav NDT se hodnotí znovu. |
| **P20** | Platný/částečný/neaktuální model, studie `ok/stale/broken/incomplete`, mapa tloušťky, audit a varianty. | Jen dovolené výstupy podle E1–E9; žádné staré mapy či falešná 0 %. Technické potvrzení vyžaduje celý cíl, není odborným ověřením. Chyba studie neblokuje jinak platný export geometrie. |
| **P21** | Skutečný spawn a přenos, změna za běhu, Zastavit, pád/timeout, řízeně pozdní odpověď. | Geometrie a stavy odpovídají dokumentu; starý výsledek neoživí výstup. Po opravě lze pokračovat. Jasně označit řízenou poruchu a skutečný proces. |
| **P22** | Tytéž chyby přes session, GUI akci, CLI a offline AI. | Stejná rozhodující podmínka a příčina; dostupnost tlačítka není jediná ochrana. AI obrázek je diagnostický, bez síťových volání; CLI `--set` a jednorázový NDT cíl zachovají správný původ. |
| **P23** | Rekurzivní ukázky, vnořená data dokumentu a soubory verzí 1–22. | Zachované recepty a originální bajty, nezávislé kopie, očekávaná geometrie a existující migrace. Po uložení v22 bez nových polí; nepředstírat úplný historický archiv. |
| **P24** | Konečná verze na Windows/macOS, stažená aplikace a měřicí baseline. | Celý pytest/Ruff, obě úlohy obou workflow úspěšné pro správnou verzi; shodné fyzické podpisy. Kontrola stažení a místní Mac podle F7, přesně přiznané neověřené prostředí. |

Použít dosavadní **εL=10⁻⁶ mm**, **εV=10⁻⁹×max(1,|VA|,|VR|) mm³**
a mez jednotlivé složky z D3. Složitější povrchy si ponechají zdůvodněné tolerance
svých testů. NDT a výběrové tolerance se nesjednocují. Nový hraniční případ,
který smlouvu nesplní, je nález; není důvod tiše povolit širší interval.

## 5. Schválené pořadí provedení

| Krok | Závislost a omezený rozsah | Výstup a dokončení |
|---|---|---|
| **F.1 Inventura přijetí** | Po výslovném schválení F1–F9, F.1–F.4 a P01–P24. Zafixovat aktuální main a prostředí, přečíst skutečné testy a doplnit mapování všech předešlých matic. | `docs/p1-5-overeni.md`: žádný požadavek bez stavu a konkrétního důkazu; samostatný seznam mezer/omezení. Ruff + celý pytest, výchozí baseline P0; malý dokumentační commit. |
| **F.2 Doplnění chybějících regresí** | Po F.1; jen mezery v dohodnutém rozsahu. Využít existující případy a malé deterministické pomocníky; nové testy např. `tests/test_p15_acceptance.py` jen pokud jsou potřebné. | Každý nový případ má nezávislé očekávání a vazbu na P01–P24; zachované původní testy a tolerance. Nález v produkci znamená reprodukci a samostatný návrh opravy podle F8. Ruff + celý pytest před každým malým commitem. Pokud mezery nejsou, nevyrábět prázdný testovací commit. |
| **F.3 Pracovní postup a balíčky** | Po F.2 bez nevyřešeného selhání v povinném rozsahu. Agent provede krátký průchod z oddílu 6, oba celé workflow konečné hlavy PR a self-test stažených balíčků. | Český protokol s verzí, metodou ovládání, snímky a mezerami. Žádné tiché přeskočení nedostupného kroku, žádné předstírané fyzické Windows přijetí. Zprávy a balíčky svázat se skutečnými SHA, test merge výslovně odlišit od hlavy větve. |
| **F.4 Souhrn a předání** | Po F.3. Dokončit matici, omezení, srovnání baseline a kontrolu diffu; uvést přesné výsledky pro konečný commit. | Implementační PR ke kontrole autora a závěrečný český protokol. Dokončení podle oddílu 7; žádné sloučení ani automatický přechod na P2. Případný evidenční commit znovu zkontrolovat, konečné CI nesmí patřit starší hlavě. |

Místní baseline P0: 1 zahřátí + 3 měření, tentýž stroj, knihovny a vstupy před/po;
fyzické podpisy musí souhlasit. Časy uvést jako měření, bez nového časového prahu
v pytest. Rozptyl CI není důvod zvyšovat časové limity ani měnit závislosti.
Zachovat omezené čekání testů GUI a nahrazení blokujících dialogů.

V implementačním PR mohou artefakty nést SHA kontrolního merge GitHubu. Doložit
jeho rodiče a shodu produkčních zdrojů s hlavou PR; počet testů a případy ověřit
v JUnit, nikoli jen zelenou ikonou. Uložit verze knihoven, otisky vstupů/zdrojů,
výsledky baseline, obě úlohy, self-testy a SHA-256 stažených ZIPů. Rozdílné
časování ani komprese nejsou rozdílem geometrie. Důležitou evidenci uchovat mimo
dočasné CI artefakty (balíčky mají nyní retenci 7 dní, zprávy 14).

## 6. Krátký průchod aplikací, který převezme agent

Připravit malou sadu pracovních kopií ve stávajícím formátu, do protokolu uvést
jejich SHA-256 a sestavení aplikace. Odborné ověření NDT se při tom nezapisuje.

1. Otevřít kvádr, ověřit 24 000 mm³ / 1 těleso a STEP. Změnit rozměr, ověřit
   odpovídající objem, Zpět/Znovu a původní hodnotu. Zvlášť ukázat podporovaná dvě tělesa.
2. Vyvolat neproveditelné R50, ověřit viditelný důvod a označený poslední náhled;
   přímý export dílu i řezu a NDT musí odmítnout bez přepsání existujícího výstupu.
3. Uložit chybnou pracovní kopii, znovu otevřít, opravit na R2. Ověřit obnovení
   výstupů i návrat blokace přes Zpět/Znovu. Originál se nezmění.
4. Otevřít případ nejednoznačné hrany a profil s promítnutými referencemi;
   ověřit odmítnutí/opravu přes výběr a návrat reference ze skicáře i po uložení.
5. Na úspěšném modelu změnit tloušťku NDT studie. Geometrie se exportuje,
   zastaralá oblast se nevydá za platnou. Po kontrole cíle a výslovném technickém
   potvrzení lze spočítat novou mapu. Zpět neobnoví cizí výsledek z mezipaměti.
6. Při přepočtu použít Zastavit a zopakovat změnu. Ověřit obnovu práce a ukončení
   aplikace bez pádu. Samostatně spustit self-test právě staženého balíčku.

Jestli ovládání nativního okna nebo dialogu není dostupné, agent dál provede
nezávislé automatické zkoušky a přesně označí neprovedený krok. Předání nesmí
zaměnit programovou náhradu dialogu za skutečné ovládání dialogu. Případnou
nezbytnou pomoc autora soustředit do jednoho krátkého seznamu, nikoli série potvrzení.

## 7. Brána dokončení a zbývající omezení

**Technické předání P1.5 je hotové pouze pokud:**

- P01–P15 a P17–P24 i všechny povinné podbody předchozích matic mají konkrétní
  úspěšný důkaz pro konečnou verzi; neimplementovaný průnik a P16 nejsou vydávány
  za úspěšnou podporu. Mezery nejsou tiše přeznačené na „mimo rozsah“.
- V dohodnutých podporovaných případech není tiché přijetí vadné geometrie,
  ztráta dílčího materiálu/kontextu ani vydání starého/částečného výsledku jako hotového.
  Selhání povinného případu tuto bránu blokuje až do samostatně schválené opravy.
- Celé místní testy a Ruff projdou; obě konečná CI včetně balíčků projdou a jejich
  evidence souhlasí se správnou verzí. Očekávané přeskočení kvůli chybějícímu
  volitelnému GUI v kontrolované variantě se odliší od úplného běhu s GUI;
  v úplných cílových bězích se žádný povinný případ nevynechá.
- Kompatibilita, formát 22, původní testy/tolerance a fyzické baseline zůstanou
  zachované. Rozdíl v měření se vysvětlí, geometrická odchylka se nezamete.
- Protokol odděluje automatické testy, dostupnou nativní zkoušku, chybějící fyzické
  ovládání a odbornou validaci. Autor dostane výslovný seznam otevřených rizik.

**P1 přijatá autorem** je až následné autorovo rozhodnutí nad tímto souhrnem;
samotné schválení plánu ani zelené CI jej nepředjímají. Přijetí se může týkat
jen takto doloženého a výslovně omezeného rozsahu, ne všech možných CAD vstupů.

R03 (atomické ukládání a obnova), zbytkové R04 (historická identita), R12 (text
modelového formátu předávaný AI), širší Retina/trackpad/GPU/Windows ergonomie a
NDT-17 se tím neuzavřou. R01/R02/R05 lze v závěrečném registru označit za pokryté
jen v rozsahu konkrétních úspěšných regresí a schválených pravidel, nikoli plošně.
P16 zůstává přiznaná mez: úspěšná geometrická shoda není důkaz téže původní plochy.
NDT výsledky jsou geometrické; úspěšná P1 není fyzikální ani odborná validace metod.

## 8. Rozsah schválení

Schválení **F1–F9, F.1–F.4 a P01–P24** opravňuje provést inventuru,
doplnit potřebné regrese a dokumentaci, provést uvedené zkoušky a předat výsledné
implementační PR. Produkční nález vyžaduje postup F8. Tento návrhový PR ani budoucí
implementační PR se neslučují do main bez výslovného pokynu autora.

Schválení tohoto dokumentu nedokládá hotové výsledky ani autorovo konečné přijetí P1.5.
P2, nové závislosti, architektura a modelový formát vyžadují vlastní konkrétní návrh.
NDT-16 zůstává mimo rozsah; NDT-17 na něm nezávisí.
