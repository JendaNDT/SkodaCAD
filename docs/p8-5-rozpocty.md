# P8.5 — ověřitelné rozpočty paměti a odezvy

**Konečný stav:** PR #119 je sloučený, vydání `e7f5e6d` ověřené včetně obou
skutečných veřejných ZIPů. [Protokol vydání](p8-5-overeni-vydani.md) uzavírá
průběžné stavy níže; historické neúspěchy a vynechání hostovaného Mac výkonu
se nepřepisují na úspěch. Autor následně přeskočil doporučenou reprezentativní
NDT přejímku, která zůstává neprovedená.

Autor 4. 11. 2026 odpověděl „ok, udělej to“ na stanovení měřitelných limitů
paměti a odezvy. Výchozí vydání je P8.4 `1d95045418ba5db0b6b028e2f6d80ed1a489f4c7`.
Tato dávka zavádí automatickou technickou přejímku dvou přesně vymezených úloh.
Neprohlašuje přejímku všech modelů autora, NDT výpočtů ani celodenního provozu.

## Úlohy a význam času

Používáme **nezměněné** `soak_p8.py`, `soak_p8_gui.py` a původní tři měřiče P8.1/P8.2.
Nový spouštěč `tests/budget_p8.py` provede původní 2 zahřívací + 20 měřených cyklů,
se 122 skutečnými prvky / 60 kapsami a 800 instancemi sestavy. Všechny analytické
objemy, platnost geometrie, reálné zrušení/pád workeru, STEP limit a obnova,
nativní náhled a zánik oken i PID poolu sestav jsou povinnou podmínkou výsledku.
Bez jejich úplného důkazu se rozpočty nepřijmou, i kdyby čísla byla nízká.

Čas kroku je rozdíl sousedních původních kontrolních bodů. Zahrnuje související
čekání, kontrolu geometrie, 50ms návrat hlavní Qt smyčce a ustálení měřiče.
`edit-undo-redo` obsahuje tři přepočty, `assembly-preview-close` i nové spuštění
poolu, editor, 3D náhled a běžné zavření. Nejde o čas samotné CAD funkce.
Měříme všech 20 hodnot každého kroku; p95 je nearest-rank, tedy 19. ze 20 seřazených
hodnot. Navíc žádná jednotlivá hodnota nesmí překročit 1,5násobek limitu p95.
Zahřívací kroky jsou zachované v raw, ale nejsou v těchto percentilech.

Nová nezávislá sonda v témže GUI procesu používá skutečný přesný Qt časovač 50 ms.
Měří intervaly jeho skutečného doručování, včetně čekání ve vnořených smyčkách,
prvního otevření, diagnostického GC a ukončení. Neprovádí žádný úklid ani změnu modelu.
Pevný histogram dává konzervativní horní hranici p95; zaznamená se i přesné maximum.
Výsledek není latence od kliknutí po zobrazený pixel ani FPS/GPU benchmark.
Sonda drží pevný počet čítačů, nikoli rostoucí seznam vzorků.

**Rozhodnutí autora ze 7. 11. 2026 – vyjmutí kontroly měřiče.** Po
[rozboru pauz](p8-5-rozbor-pauz-noveho-okna.md) autor zvolil „Vyjmout kontrolu
z měření“. Nejdelší pauzu dělala kontrola samotného měřicího programu: ověření
`is_valid` všech 800 kopií sestavy (`inspect_assembly(..., 800)` v
`soak_p8_gui.preview_and_close`) v hlavní smyčce okna, 2–3,5 s podle rychlosti
počítače. Kontrola dál proběhne celá a její selhání zkoušku dál zastaví. Jen její
čas se odečte od právě běžícího intervalu Qt (`LoopProbe.exclude`). Vyjmout jde
pouze tuto jednu pojmenovanou kontrolu (`budget_p8.EXCLUDED_CHECKS`), jiný název
je chyba. Důkaz nese `qt_probe.excluded` (počet, součet a maximum vyjmutého času)
a vyhodnocení vyžaduje přesně jedno vyjmutí v každém z 2 + 20 cyklů. Ostatní
kontroly měřiče (`inspect_history`) se počítají dál jako dřív. Samostatně
spuštěná P8.4 (`soak_p8.py`) měří beze změny. Limity v `p85-budgets.json`
(mez 3 s) se nemění. Starší výsledky bez `excluded` zůstávají historií se svým
původním významem, včetně neúspěchů `c5a6b13` a `ad7fb19`; nepřepočítávají se.

## Limity zmrazené před prvním novým během

Strojově čitelný zdroj je [p85-budgets.json](../tests/p85-budgets.json). Nový kandidát
jej nesmí přepsat podle svého výsledku. Změna limitu znamená novou odůvodněnou
změnu pravidel; nepoužívá se automatická kalibrace, opakování do úspěchu ani průměr
z rychlých a pomalých počítačů. Staré P8.4 výsledky byly při volbě těchto počátečních
technických mezí známé; nejde o nezávislou statistickou studii ani normu ergonomie.

| Dokončený pracovní krok, p95 v sekundách | Autorův Apple M4 | GitHub macOS / Windows |
|---|---:|---:|
| Otevření historie | 5 | 10 |
| Editace + Zpět + Znovu | 15 | 30 |
| Uložit a znovu otevřít | 5 | 10 |
| Zastavit a obnovit | 6 | 12 |
| Pád workeru a obnova | 6 | 12 |
| STEP limit a úspěšná obnova | 4 | 6 |
| Sestava, náhled a zavření | 7 | 12 |
| Ustálený konec cyklu | 0,75 | 1 |
| Celý pracovní cyklus | 45 | 90 |
| Interval obsluhy Qt, horní hranice p95 | 0,25 | 0,5 |
| Nejdelší interval obsluhy Qt, včetně prvního otevření | 2 | 3 |

M4 má vlastní profil s ověřeným názvem CPU; hostované profily ověřují systém,
protože GitHub může změnit přidělený procesor. CI je kontrola technického obalu,
nikoli náhrada času na M4. Zvolené časy umožňují ve vymezené úloze přibližně minutu
na M4 a nejvýš minutu a půl na hostovaných serverech; zahrnují náklady obnovy poolů.
Meze pauzy Qt jsou samostatným požadavkem, nelze je odvodit z rychlého průměru cyklu.

Pro všechny tři profily:

| Paměť v rozsahu 20 měřených cyklů | Horní mez |
|---|---:|
| Vzorkované maximum RSS hlavního procesu | 1536 MiB |
| Vzorkované současné maximum součtu všech vlastněných procesů | 3072 MiB |
| Rozdíl mediánů poslední a první třetiny koncových RSS rodiče | +384 MiB |
| Medián párových sklonů koncových RSS rodiče | +24 MiB/cyklus |

Paměťový rámec ponechává pro tuto úlohu na 16GiB M4 prostor operačnímu systému
a další práci; RSS se sdílenými stránkami není měření volné fyzické RAM.
384 MiB je čtvrtina rodičovského rámce 1536 MiB. Sklon 24 MiB/cyklus je další
samostatná pojistka, nikoli extrapolace přijatelného růstu za hodinu nebo za den.
Ochranné ukončení měřiče zůstává 3072 MiB a 2400 s. Jeho stejná číselná mez
součtu nenahrazuje nové kontroly rodiče, růstu, času a Qt. Záporný trend se vykáže
se znaménkem, nikoli jako úspora připsaná této dávce. Kladný trend se nezamlčuje.
Neúplné průběžné RSS není nula; všechny kontrolní body musí být úplné a kladné.

## Výsledek a obnova

Spuštění: `python tests/budget_p8.py --profile author-m4 --output out/p85.json`.
V CI se používají oddělené profily `ci-macos` a `ci-windows`. Raw obsahuje skutečný
checkout, úplné otisky zdrojů včetně obou nezměněných soak skriptů, nového spouštěče
a souboru limitů. Původní JSONL, footer, Qt histogram, STEP, uložený model a čtyři
nativní snímky zůstávají vedle reportu. Existující výstup se nikdy nepřepisuje.

`status: ok` znamená dokončenou fyzikální zkoušku; teprve `evaluation.status: pass`
znamená splněné rozpočty. Dokončená, ale nadlimitní zkouška má exit 1 a jednotlivé
neúspěšné položky. Neúplná měření jsou odmítnutá. Výsledek P8.5 čeká na kontroly
aktuální dávky na obou OS; původní P8.4 nesmí nahradit Qt sondu.

## Původní úplné měření na autorově M4 před PR #118

[Původní raw JSON](baselines/p8-5-macos-arm64.json) dokončil 2 zahřívací a 20 měřených
cyklů, všech 180 kontrolních bodů, za **598,567 s**, normální exit 0. Všech **23 mezí
prošlo** beze změny předem uložené politiky. M4 / macOS 27.2 arm64, Python 3.12.14,
build123d 0.13.0 / OCP 8.0.1.1.0 / PySide6 6.11.3; stejné prostředí jako místní P8.4.

| Ukazatel | Naměřeno | Limit M4 |
|---|---:|---:|
| Otevření historie, p95 | 3,077 s | 5 s |
| Editace + Zpět + Znovu, p95 | 8,699 s | 15 s |
| Uložit a znovu otevřít, p95 | 3,075 s | 5 s |
| Zastavit a obnovit, p95 | 3,264 s | 6 s |
| Pád workeru a obnova, p95 | 3,302 s | 6 s |
| STEP limit a obnova, p95 | 1,649 s | 4 s |
| Sestava, náhled a zavření, p95 | 3,996 s | 7 s |
| Konec cyklu, p95 | 0,300 s | 0,75 s |
| Celý cyklus, p95 | 27,145 s | 45 s |
| Horní hranice p95 intervalu Qt | 0,075 s | 0,25 s |
| Nejdelší interval Qt v celé zkoušce | **1,383 s** | 2 s |
| Vzorkované maximum rodiče | 1198,656 MiB | 1536 MiB |
| Vzorkované současné maximum součtu procesů | 2801,891 MiB | 3072 MiB |
| Rozdíl koncových mediánů rodiče | **−0,039 MiB** | +384 MiB |
| Párový sklon | −0,283 MiB/cyklus | +24 MiB/cyklus |

Téměř nulová změna mediánů tohoto běhu neruší dřívější kladné trendy P8.4 a není
důkaz úspory způsobené P8.5: produkční kód se vůbec nezměnil. Pauza 1,383 s zůstává
viditelná i při nízkém p95. RSS dohled měl 1256 odběrů a jeden neúplný průběžný
vzorek; není nahrazen nulou. Všech 180 kontrolních bodů je úplných. V každém konci
zůstaly pouze dva workery hlavního dílu, žádná zavřená okna ani parametrické dialogy;
po běžném ukončení žádný worker. Čtyři nativní snímky prvního a posledního cyklu
byly prohlédnuty: stejná skutečná 800členná sestava a deska s 60 kapsami / t=12.

Raw je bajtově shodná kopie výstupu, SHA-256
`62630752ff8fc363443da2180da8bae6bd2924419d061ae4cdacec437ea3ed47`.
Uvádí commit `1d95045`, protože P8.5 spouštěč a politika byly při měření ještě
necommitnuté. Identitu skutečných zdrojů dokládá všech 150 otisků: všech 148 zdrojů
P8.4 zůstalo přesně stejných, navíc nový spouštěč a politika.
Politika měla před i po běhu SHA-256
`fad48b7a7106447834897f7670fe4ef1bf9f0a449d0cd347f0b3f1f81f7b34f4`.
První pokus spouštěče skončil před zahájením nativních cyklů kvůli chybě konstrukce
sondy. Byla opravena a přibyla izolovaná regrese se skutečným Qt časovačem;
neúplný pokus je zachován pouze v ignored out, není přejímkovým výsledkem.

Konečná cílená sada P8.5/P8.4 a fyzikálních referencí prošla: **69 testů za 3,55 s**,
normální exit 0, celé Ruff src/tests, diff check a YAML parse. Celá sada má 2936
testů; její běh patří před sloučením na oba systémy GitHubu. Ve zdrojích aplikace
této původní dávky nebyly žádné změny; úplná sada podle pravidla 6 patřila do CI.

## Navazující oprava odezvy v PR #119

PR #118 byl sloučen, ale následné měření na skutečném `main` překročilo na macOS
časové limity. Dokončené fyzikální cykly ani zveřejnění instalačních ZIPů proto
neznamenaly přijetí P8.5. Původní raw výše zůstává zachovaný a nenahrazuje nové
ověření produkčních změn.

Diagnostika oddělila dvě konkrétní zbytečné režie. Dohled paměti na macOS opakovaně
spouštěl `ps`. Nyní čte aktuální RSS přímo přes `libproc.proc_pidinfo`
(`PROC_PIDTASKINFO`). Každé čtení má nový buffer; ukládá se jen vazba na API,
nikoli hodnota RSS nebo PID. Úplný nulový záznam se odlišuje od chyby či neúplného
čtení. Shoda s nezávislým `ps`, souběžná čtení, zánik procesu a skutečné odmítnutí
STEP při nedostatečné paměti mají regresní testy. Čtečky Windows a Linuxu se nemění.
Nejde o snížení spotřeby RAM ani o důkaz příčiny všech původních překročení.

Při otevření okna se navíc řetězilo sestavení rozhraní se spuštěním 3D ovladače.
Nativní plocha nyní naplánuje inicializaci vlastněným jednorázovým Qt časovačem;
skrytí nebo zrušení plochy požadavek zastaví. Čekající model zůstane zachován.
Žádné vnořené `processEvents` se nepřidává. Samotné oddělení inicializace ještě
neprokázalo splnění všech limitů.

Nativní sonda se softwarovým vykreslováním a [zdroj OCCT 8](https://github.com/Open-Cascade-SAS/OCCT/blob/V8_0_0/src/Visualization/TKV3d/V3d/V3d_View.cxx)
potvrdily další mechanismus: `FitAll(false)` při zapnutém immediate režimu přesto
volá aktualizaci pohledu. Následoval další výslovný `Redraw`. Při nastavení kamery
a počátečního vzhledu je nyní immediate režim dočasně vypnutý a obnoví se i při
výjimce. Hotový pohled se vykreslí celý. Geometrie, výběr ploch a hran, antialiasing,
hardwarový ovladač i jeho macOS softwarová záloha zůstávají stejné.

Krátká diagnostika `tests/diagnose_p85.py --output <nová-složka>` je určena pro
macOS a obsahuje právě jeden cyklus bez zahřívání. Zaznamenává časové a CPU úseky
a skutečné mezery Qt, ale **nikdy není přejímkou rozpočtů**. Vnořené úseky se
nesčítají; rozdíl wall a CPU ani vysoký load average neprokazují vytížení hostitele.
Dočasný workflow pracovní větve se do dokončené dávky neponechává.

Úplné navazující PR ověření této verze na hostovaném macOS znovu překročilo
časové meze, ačkoli fyzikální případy a paměťové meze prošly. PR proto zůstává
rozpracovaný. Místní M4 raw níže platí pro tehdejší zdroje, nikoli automaticky
pro další úpravy.

Cílená sonda přepočtu poté lokalizovala další opakovanou práci: kontrola celého
tvaru a každého jeho solidu zakládala oddělený analyzátor OCCT. Nyní každé volání
`inspect_volume` vytváří jeden čerstvý `BRepCheck_Analyzer`; jeho vlastní mapa
podtvarů slouží pro kontrolu celku **i výslovnou kontrolu každého solidu**.
Použití pro podtvary je součástí [API OCCT 8](https://github.com/Open-Cascade-SAS/OCCT/blob/V8_0_0/src/ModelingAlgorithms/TKTopAlgo/BRepCheck/BRepCheck_Analyzer.hxx).
Mezi voláními se výsledek neukládá. Kontroly uzavřených shellů, konečných
souřadnic, všech složek, objemového součtu a účinku operace se nemění.
Regrese zahrnují i změnu nativního tvaru ve stejném Python objektu a odmítnutí
neověřitelného podtvaru. Diagnostika nyní zaznamenává také skutečný worker,
identitu požadavku a CPU/wall úseky přepočtu, validace, kódování a odeslání.
Tato úprava má cílené ověření a nové úplné místní měření uvedené níže;
nové hostované přejímky aktuálního sestavení ještě zbývají.

Další záznamy rozlišily opakované explicitní snímky při obnově sestavy. Signál
výběru během `show_part` synchronně obnovuje zvýraznění a pohybové rukojeti;
každá obsluha dříve kreslila zvlášť. Krátká synchronní dávka nyní zachová všechny
změny scény i signály a vykreslí až hotový stav. Platí i pro vnořenou obnovu;
po výjimce se dávka ukončí a mimo ni se kreslí bez odkladu. V nativní sondě stejné
sestavy přešla izolace i obnovení 800 kopií ze sedmi explicitních snímků na jeden,
se stejnou geometrií, výběrem, receptem a historií. Počet snímků není měření FPS
ani přejímka rozpočtů.

Načítání systémových ikon už netvoří součást konstrukce hlavního okna. Vlastní
Qt časovač po ustálení viditelného okna a spuštění 3D doplňuje jednu akci v každém
průchodu smyčkou. Akce, nabídky a klávesové zkratky zůstávají stejné; při změně
palety se starý čekající výsledek nepoužije. Přijaté zavření nebo zánik vlastníka
čekající práci zruší. Vektorové CAD ikony zůstávají synchronní a používají svou
původní cache. Místní nativní sonda nezopakovala dlouhé čekání hostitele, proto
se nepřisuzuje jediné konkrétní ikoně ani vytížení hostitelského stroje.

GUI regrese tehdejší opravy prošly v cílené sadě **313 testů**; tehdejší kolekce měla **2969
případů**. Zachované geometrické a transakční pojistky mají samostatné cílené
ověření. Jeden místní nativní diagnostický cyklus potvrdil všechny původní
fyzikální případy, zavření oken a procesů; nepředstavuje úplnou přejímku.

Původní měřiče P8.1–P8.4, fyzikální případy, vstupy, politika a ochranný rozpočet
zůstávají nezměněné. Úplné místní měření opravy je uvedené níže; před přijetím stále zbývají nové
kontroly skutečného aktuálního sestavení obou systémů. Přejímka NDT ani celodenního
provozu se tím neprohlašuje.


## Vrácení z izolace s již vytvořenou prezentací sestavy

Následná diagnostika Windows ukázala konkrétní cenu opětovného vytvoření
prezentace při návratu na stejnou plnou sestavu. Samotný diagnostický cyklus
nezopakoval dřívější překročení maximálního intervalu Qt a neurčuje jeho
historickou příčinu. Původní kontrola platnosti všech 800 dílů i celé pořadí
pracovních kroků zůstávají nezměněné.

Okno sestavy nyní může ponechat právě jednu skrytou prezentaci plné sestavy
a při návratu ji obnovit. Skrytý objekt je vyřazený z výběru; obnovení znovu
aktivuje plochy i hrany, nastaví aktuální průhlednost a podle původního požadavku
přizpůsobí kameru. Každá změna geometrie nebo nové načtení ji zruší. Přijaté
zavření ji odstraní z nativního kontextu; zrušené zavření ji zachová. Nejde
o rostoucí cache pohledů a neukládají se předchozí výsledky sestavy.

Osm nových regresí ověřuje skutečný AIS a jeho vzhled, omezení na jeden uložený
objekt, čekající inicializaci, chybný vstup i neúspěšné obnovení, změnu modelu
a Zpět se stejnými id komponent a přijaté/zrušené zavření. Související sady mají
celkem **615 úspěšných testů**, úplná kolekce **2978 případů**. Samostatná omezená
nativní zkouška skutečné implementace zachovala 800 dílů, původní objem, výběr
plochy c799, průhlednost a jeden hotový snímek každé operace. Ověřila také,
že úprava a Zpět nepoužijí starou geometrii a přijaté zavření odstraní skrytý AIS.
Tato zkouška operací není úplná výkonnostní přejímka.

Změněné jsou dva produkční zdroje, proto předchozí úplná M4 baseline níže
zůstává pouze historií. Nová úplná místní přejímka této opravy prošla; aktuální
CI a vydání ještě zbývají. Politika, fyzikální měřiče a všechny historické raw
výsledky zůstávají beze změny. Dočasný Windows diagnostický workflow je z hotové
dávky odstraněný.

## Aktuální místní oprava životnosti 3D ploch

Po dotazu autora „A nemůžeš to ověřit tady lokálně?“ byly zbývající zkoušky
provedeny na jeho skutečném M4. Původní balíček `1187ae7` dokončil self-test
s chybou kontroly životnosti 3D ploch: po jediném `processEvents` ještě nemusela
doběhnout záměrně odložená inicializace. V protokolu byly také tři výjimky
události Qt bez Python vlastníka plochy. Původní neúspěšný výsledek
a jeho ZIP zůstávají zachované; nejde o nový úspěšný výsledek této verze.

Oprava čeká omezeně na skutečnou připravenost 3D pohledu, zachovává všechny
čtyři zkoušky plného vykreslení a zničí zkušební okno i při chybě. Událost
plochy bez Python vlastníka se předá základnímu Qt widgetu. Šest nových regresí
před opravou selhalo, po opravě prošlo spolu se souvisejícími **299 testy**.
Úplná místní sada má **2984 úspěšných případů, žádné přeskočené ani chyby**,
normální exit 0. Prošly Ruff a všech šest původních referenčních případů P0.

Samostatná aplikace byla sestavena oficiálním spec, zabalena a znovu rozbalena
pomocí `ditto`. Skutečný arm64 spustitelný soubor, podpis, jeho podmínka
a vložený commit byly ověřené na disku. Self-test této rozbalené aplikace
skončil **VÝSLEDEK: OK, exit 0**, bez Python override/AttributeError/Traceback
chyb. Zachoval skutečná Qt tlačítka a 3D náhled, desetinnou čárku, závislé
výrazy a přejmenování, zdvih víčka o 12,5 mm se sedmi splněnými vazbami,
návrat a zrušení bez změny modelu/výsledku/receptu/historie/zdrojů/kamery,
použití jedním Zpět/Znovu a odmítnutí chybného nebo zastaralého náhledu.

[Aktuální samostatný raw JSON](baselines/p8-5-native-lifecycle-macos-arm64.json)
měří skutečný místní commit `b9df4585679d058c415ba33de6e4c1a0e1d5c170`
(tree `703a303e49ec258bbfd66be79b986f134063454d`), SHA-256 raw
`0eb469eb82813a23668911d6d861d4b2a2c69395810e1dfd13074503c5c3fdfb`. Dva měřené zdroje se proti `1187ae7` změnily,
proto vznikla tato nová přejímka. Všech **150 otisků zdrojů a tři vstupy**
odpovídají měřenému snapshotu; politika, pracovní kroky a fyzika se neměnily.
Dokončil **2 zahřívací + 20 měřených cyklů, 180 kontrolních bodů a všech
23 zmrazených mezí** za **490,755 s**. Nativní i přímo
pozorovaný návrat spouštěče mají exit 0. Apple M4 / macOS 27.2 arm64,
Python 3.12.14, build123d 0.13.0 / OCP 8.0.1.1.0 / PySide6 6.11.3.

| Ukazatel | Naměřeno | Limit M4 |
|---|---:|---:|
| Otevření historie, p95 | 2,409 s | 5 s |
| Editace + Zpět + Znovu, p95 | 6,711 s | 15 s |
| Uložit a znovu otevřít, p95 | 2,403 s | 5 s |
| Zastavit a obnovit, p95 | 2,585 s | 6 s |
| Pád workeru a obnova, p95 | 2,650 s | 6 s |
| STEP limit a obnova, p95 | 1,592 s | 4 s |
| Sestava, náhled a zavření, p95 | 3,651 s | 7 s |
| Konec cyklu, p95 | 0,253 s | 0,75 s |
| Celý cyklus, p95 | 22,152 s | 45 s |
| Horní hranice p95 intervalu Qt | 0,100 s | 0,25 s |
| Nejdelší interval Qt | 0,840 s | 2 s |
| Vzorkované maximum rodiče | 1322,891 MiB | 1536 MiB |
| Vzorkované současné maximum součtu procesů | 2927,578 MiB | 3072 MiB |
| Rozdíl koncových mediánů rodiče | −42,766 MiB | +384 MiB |
| Párový sklon | −1,315 MiB/cyklus | +24 MiB/cyklus |

Qt sonda měřila celou nativní zkoušku včetně inicializace, vnořených smyček,
diagnostiky GC a běžného zavření: **8520 doručení,
žádná chyba**. RSS dohled má **1130 průběžných
odběrů, z toho 3 s neúplným RSS workerů**.
Nejsou nahrazené nulou. Všech **180 kontrolních bodů** má úplné kladné RSS
a vzorkovaná maxima je pokrývají. Agregovaný čítač neurčuje místo ani příčinu
neúplných průběžných odběrů. Původní validátor tento rozdíl mezi průběžným
odběrem a povinným úplným kontrolním bodem zachovává; meze se nepovolovaly.

Ve všech 22 koncích cyklů zůstali pouze dva konkrétní workery hlavního dílu,
žádné okno sestavy ani parametrický dialog. Po běžném zavření nezůstal žádný
vlastněný worker. Původní validátor ověřil analytickou geometrii historie,
Zpět/Znovu, uložení/otevření, zrušení, skutečný pád, STEP limit a obnovu,
800 dílů, výběr c799 a skutečný náhled. Čtyři nativní snímky byly prohlédnuté:
čistá sestava 800 kopií / c799 a historie s 60 kapsami / t=12; obě dvojice
první/poslední jsou bajtově shodné.

Samostatné aktuální místní P8.3 prošlo původním přísným porovnáním před/po.
Řízená reference má jako jediného rodiče tento měřený snapshot a vrací pouze
historickou metodu obnovy vzhledu z `93843f4`; všech 146 otisků, skutečné
vstupy, intervaly i fyzika jsou ověřené. Aktuální místní P8.4 dokončilo
2 + 20 cyklů / 180 bodů s původní validací, 148 otisky a třemi vstupy;
normální exit 0 a běžné zavření bez workerů. Všech osm snímků obou zkoušek
bylo skutečně prohlédnutých. P8.4 se neoznačuje za P8.5 rozpočtový výsledek.

Jde o místní důkazy na tomto M4, nikoli úspěšný hostovaný workflow nebo
self-test staženého artefaktu GitHubu. Nová úplná kontrola Windows, aktuální
PR/MAIN a skutečné vydání ještě zbývají. Výslovné přeskočení hostovaného
Mac **výkonu** se nemění a není přeskočením testů správnosti. Současný
vzorkovaný součet RSS není unikátní RAM nebo GPU paměť. Záporný trend není
úspora připsaná opravě, důkaz absence úniků, celodenní stability nebo přejímka NDT.
Všechny starší baselines a neúspěšné výsledky zůstávají historií.

## Předchozí úplné měření obnovené prezentace na autorově M4

[Nový samostatný raw JSON](baselines/p8-5-retained-presentation-macos-arm64.json)
měří commit `64f5a8db4a8bddb9217341b6f7b230fba62bb1fb`. Jeho SHA-256 je
`6246304e4ef9833459dc1bbb23bc3c0d4105e08569166b0da9921a7f192644a8`.
Dokončil **2 zahřívací + 20 měřených cyklů, 180 kontrolních bodů a všech 23
zmrazených mezí** za **488,773 s**, nativní exit 0. Prostředí je Apple M4 /
macOS 27.2 arm64, Python 3.12.14, build123d 0.13.0 / OCP 8.0.1.1.0 / Qt 6.11.3.



| Ukazatel | Naměřeno | Limit M4 |
|---|---:|---:|
| Otevření historie, p95 | 2,475 s | 5 s |
| Editace + Zpět + Znovu, p95 | 6,712 s | 15 s |
| Uložit a znovu otevřít, p95 | 2,406 s | 5 s |
| Zastavit a obnovit, p95 | 2,605 s | 6 s |
| Pád workeru a obnova, p95 | 2,652 s | 6 s |
| STEP limit a obnova, p95 | 1,586 s | 4 s |
| Sestava, náhled a zavření, p95 | 3,659 s | 7 s |
| Konec cyklu, p95 | 0,252 s | 0,75 s |
| Celý cyklus, p95 | 22,246 s | 45 s |
| Horní hranice p95 intervalu Qt | 0,100 s | 0,25 s |
| Nejdelší interval Qt v celé zkoušce | 1,187 s | 2 s |
| Vzorkované maximum rodiče | 1163,391 MiB | 1536 MiB |
| Vzorkované současné maximum součtu procesů | 2767,266 MiB | 3072 MiB |
| Rozdíl koncových mediánů rodiče | −29,422 MiB | 384 MiB |
| Párový sklon | +0,880 MiB/cyklus | 24 MiB/cyklus |

Qt časovač pokrývá celou nativní zkoušku včetně inicializace, vnořených smyček,
oddělené diagnostiky GC a zavření: **8523 doručení, žádná chyba**. RSS dohled má
**1126 odběrů, žádné chybějící čtení**; maxima pokrývají všech 180 úplných
kladných kontrolních bodů. Současný vzorkovaný součet není unikátní RAM ani GPU
paměť. Rozdíl mediánů **−29,422 MiB** a sklon **+0,880 MiB/cyklus** zachovávají
svá znaménka; nejsou důkazem absence úniků, celodenní stability ani přejímky NDT.

Všech 22 konců cyklů má nula oken sestav a parametrických dialogů a pouze dva
konkrétní workery hlavního dílu. Oba workery každé zavřené sestavy jsou ukončené;
po běžném zavření nezůstává žádný vlastněný worker. Původní validátor znovu ověřil
fyziku historie, Zpět/Znovu, uložení/otevření, zrušení, skutečný pád, STEP limit
a obnovu i sestavu 800 dílů s nativním náhledem. Čtyři snímky prvního a posledního
měřeného cyklu byly skutečně prohlédnuté: čistá sestava 800 kopií / c799 a historie
s 60 kapsami / t=12; odpovídající dvojice jsou bajtově shodné. Všech 150 měřených
otisků a tři vstupy odpovídají tomuto commitu. Aktuální úplné CI Windows včetně
P8.5 a kontroly správnosti, sestavení a stažených aplikací obou OS ještě zbývají.

## Úplné měření předchozí opravy na autorově M4

[Samostatný raw JSON](baselines/p8-5-gui-response-macos-arm64.json) měří commit
`04692953aa1b4b260e111c3e1c6d5ce30da5e39f`, tedy novou validaci, sloučení snímků
i frontu systémových ikon spolu s předchozími opravami RSS a 3D inicializace.
Dokončil **2 zahřívací + 20 měřených cyklů, 180 kontrolních bodů a všech 23
zmrazených mezí** za **488,615 s**, normální exit 0. Prostředí je Apple M4 /
macOS 27.2 arm64, Python 3.12.14, build123d 0.13.0 / OCP 8.0.1.1.0 / Qt 6.11.3.

| Ukazatel | Naměřeno | Limit M4 |
|---|---:|---:|
| Otevření historie, p95 | 2,404 s | 5 s |
| Editace + Zpět + Znovu, p95 | 6,746 s | 15 s |
| Uložit a znovu otevřít, p95 | 2,402 s | 5 s |
| Zastavit a obnovit, p95 | 2,591 s | 6 s |
| Pád workeru a obnova, p95 | 2,667 s | 6 s |
| STEP limit a obnova, p95 | 1,601 s | 4 s |
| Sestava, náhled a zavření, p95 | 3,708 s | 7 s |
| Konec cyklu, p95 | 0,251 s | 0,75 s |
| Celý cyklus, p95 | 22,251 s | 45 s |
| Horní hranice p95 intervalu Qt | 0,100 s | 0,25 s |
| Nejdelší interval Qt v celé zkoušce | 1,255 s | 2 s |
| Vzorkované maximum rodiče | 1264,047 MiB | 1536 MiB |
| Vzorkované současné maximum součtu procesů | 2867,656 MiB | 3072 MiB |
| Rozdíl koncových mediánů rodiče | −77,188 MiB | +384 MiB |
| Párový sklon | −4,114 MiB/cyklus | +24 MiB/cyklus |

Qt sonda běžela po celou nativní zkoušku a zaznamenala **8486 doručení bez chyby**;
maximální pauza 1,255 s zůstává součástí výsledku. Ze 1124 průběžných odběrů
RSS chyběla dvě čtení workeru; nejsou nahrazena nulou. Všech 180 kontrolních bodů
má úplné kladné RSS. Záporný trend tohoto běhu není důkaz úspory RAM, absence
úniků ani celodenní stability; historické kladné trendy zůstávají platné.

Všech 22 konců cyklů má nula oken sestav a parametrických dialogů a pouze dva
konkrétní workery hlavního dílu. Oba konkrétní workery sestavy jsou ukončené;
po běžném zavření nezůstává žádný worker. Přepočet, Zpět/Znovu, uložení/otevření,
rušení, skutečný pád, STEP limit a obnova i náhled sestavy prošly původními
fyzikálními podmínkami. Všechny čtyři snímky prvního a posledního měřeného cyklu
byly prohlédnuté: čistá sestava 800 kopií a historie s 60 kapsami / t=12.

Raw je bajtově shodná kopie nového výstupu, SHA-256
`2e5fdb84fc80c28770a151eb8030e1e3518815345d1d991b1e7d2d01e1cba701`.
Původní dvě baselines zůstávají beze změny. Všech 150 otisků zdrojů, politika,
tři vstupy a shoda JSONL, footeru a Qt záznamu byly ověřené. Následný commit
baseline a dokumentace měřené zdroje nemění. Tehdejší cílená sada GUI měla **313 úspěšných
testů**, úplná kolekce **2969 případů**; geometrické a transakční pojistky mají
samostatné cílené ověření. Úplný Ruff a kontrola diffu prošly.

Navazující úplná sada macOS odhalila jeden neúspěšný regresní test opětovného
zobrazení plochy: po pevném čekání 20 ms ještě nebyl zavolaný mock inicializace.
Tento jednotkový test nyní čeká omezeně na skutečný signál vlastněného Qt časovače,
potom stále vyžaduje právě jednu inicializaci. Nadále ověřuje okamžitý návrat ze
show bez inicializace, zachování čekajícího modelu, zastavení časovače při hide
a bezpečné zrušení při zániku. Přidaný případ se záměrným doručením za 50 ms
ověřuje, že správnost nestojí na pevném spánku. Všech **6 testů inicializace prošlo**;
nová úplná kolekce má **2970 případů**, její celé CI ověření ještě zbývá.
Produkční plánování, všech 150 měřených zdrojů, native přejímka i zmrazené časové
rozpočty a sonda Qt se touto úpravou testu nemění.

Toto je místní přejímka omezené zátěže modelování a sestav. Nejde o přejímku NDT
nebo celodenního provozu.

### Výslovně zúžená přejímka autora z 4. 11. 2026

Po vysvětlení, že čeká vzdálený Mac GitHubu a nikoli jeho zapnutý počítač,
autor rozhodl hostovanou výkonnostní zkoušku Macu přeskočit a znovu to potvrdil.
Aplikace je určená pro něj a případně jeho kolegy, ne pro obecnou distribuci
na všech konfiguracích Macu. Podmínkou P8.5 na Macu je výše uvedená úplná místní
M4 přejímka, při doložené shodě všech 150 měřených zdrojů, politiky a vstupů.
Samotné úpravy testovacího čekání, porovnávacího workflow a dokumentace tyto
zdroje nemění, proto nevyžadují nové měření stejných místních cyklů.

Hostovaný profil `ci-macos` ani jeho následná diagnostika už nejsou podmínkou
tohoto vydání a automatická P8.5 matice spouští pouze Windows. Politika a meze
obou původních profilů se nemění. Historický hostovaný Mac běh zůstal neúspěšný
kvůli maximální prodlevě Qt a sklonu RSS; nebyl opraven ani označen za úspěch.
Výjimka autora nezaručuje výkon nebo dlouhodobou stabilitu na jiném Macu.

Vydání stále vyžaduje nové úplné kontroly aktuálního PR i následného MAIN:
Windows P8.5 a standardní testy správnosti, sestavení a self-test skutečně
stažených aplikací obou OS. Dočasný diagnostický workflow byl odstraněn;
jeho případný již čekající běh není přejímkou ani blokující podmínkou.
Vydání zatím dokončené není.

## Historické úplné měření první opravy na autorově M4

[Nový raw JSON](baselines/p8-5-response-macos-arm64.json) na commitu `7a5c7b1`
dokončil **2 zahřívací + 20 měřených cyklů a všech 180 kontrolních bodů** za
**583,318 s**, normální exit 0. Všech **23 předem uložených mezí prošlo**.
Původní raw se nepřepisuje. Apple M4 / macOS 27.2 arm64, Python 3.12.14,
build123d 0.13.0 / OCP 8.0.1.1.0 / PySide6 6.11.3.

| Ukazatel | Naměřeno | Limit M4 |
|---|---:|---:|
| Otevření historie, p95 | 3,017 s | 5 s |
| Editace + Zpět + Znovu, p95 | 8,555 s | 15 s |
| Uložit a znovu otevřít, p95 | 3,004 s | 5 s |
| Zastavit a obnovit, p95 | 3,188 s | 6 s |
| Pád workeru a obnova, p95 | 3,252 s | 6 s |
| STEP limit a obnova, p95 | 1,594 s | 4 s |
| Sestava, náhled a zavření, p95 | 3,777 s | 7 s |
| Konec cyklu, p95 | 0,259 s | 0,75 s |
| Celý cyklus, p95 | 26,671 s | 45 s |
| Horní hranice p95 intervalu Qt | 0,075 s | 0,25 s |
| Nejdelší interval Qt v celé zkoušce | **1,314 s** | 2 s |
| Vzorkované maximum rodiče | 1243,734 MiB | 1536 MiB |
| Vzorkované současné maximum součtu procesů | 2846,844 MiB | 3072 MiB |
| Rozdíl koncových mediánů rodiče | **−3,086 MiB** | +384 MiB |
| Párový sklon | −1,196 MiB/cyklus | +24 MiB/cyklus |

Záporný trend tohoto omezeného běhu není důkaz úspory RAM ani záruka absence
úniku. Starší kladné trendy zůstávají platnou součástí evidence. Dva z 1313
průběžných odběrů postrádaly RSS workeru; nejsou nahrazené nulou. Všech 180
kontrolních bodů má úplné kladné RSS. Qt sonda zaznamenala 10340 doručení bez
chyby; i pauza 1,314 s zůstává viditelná vedle nízkého p95.

Ve všech 22 koncích cyklů zůstaly jen dva konkrétní workery hlavního dílu,
žádné okno sestavy ani parametrický dialog; oba konkrétní workery sestavy byly
ukončené. Po běžném zavření nezůstal žádný worker. Všechny čtyři snímky prvního
a posledního měřeného cyklu byly prohlédnuty: skutečná sestava 800 kopií a historie
s 60 kapsami / t=12. Přepočet, Zpět/Znovu, uložení/otevření, skutečné rušení a pád,
STEP limit/obnova i nativní náhled proběhly původními fyzikálními zkouškami.

Nový raw je bajtově shodná kopie výstupu, SHA-256
`a422c9cf0d10958f570a2e8bf95d65ab5c5a9d35bde2b4f68c0fe60922e2de27`.
Jeho commit je pravdivý HEAD měřené opravy. Dokumentační commit `0836200`
nezměnil žádný ze 150 měřených souborů. V této zaznamenané verzi se vůči původnímu měření liší jen dva
produkční soubory (čtečka RSS a 3D prohlížeč) a vysvětlující docstring spouštěče;
politika má stále SHA-256
`fad48b7a7106447834897f7670fe4ef1bf9f0a449d0cd347f0b3f1f81f7b34f4`.

Cílené regrese opravy prošly: **122 testů za 13,65 s**, normální exit 0, celý Ruff
src/tests a kontrola diffu. Tato zaznamenaná sada obsahovala 2954 testů. Standardní
PR buildy a stažené aplikace prošly, přejímkové meze hostovaného Macu však ne.
Po další úpravě validace se musí ověřit nové sestavení. Jediný krátký
diagnostický cyklus ani tento místní výsledek sám neznamená dokončené vydání.

Při běžné práci lze rozpočítaný přepočet zastavit akcí Zastavit; zachová se poslední
výsledek. Po pádu pomocného procesu se ohlásí chyba, poslední geometrie zůstane
a změnu lze vrátit pomocí Zpět. Po odmítnutí STEP kvůli limitu lze pokračovat jiným
souborem. Před ukončením dlouhé práce uložte model. Náhlé ukončení celé aplikace
nebo stroje, obnova neuloženého dokumentu a modely mimo tento rozsah nejsou touto
zkouškou garantované.
