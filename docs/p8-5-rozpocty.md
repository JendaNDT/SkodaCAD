# P8.5 — ověřitelné rozpočty paměti a odezvy

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

Původní měřiče P8.1–P8.4, fyzikální případy, vstupy, politika a ochranný rozpočet
zůstávají nezměněné. Oprava čeká na nové úplné 2 + 20 měření a celé kontroly obou
systémů. Přejímka NDT ani celodenního provozu se tím neprohlašuje.

Při běžné práci lze rozpočítaný přepočet zastavit akcí Zastavit; zachová se poslední
výsledek. Po pádu pomocného procesu se ohlásí chyba, poslední geometrie zůstane
a změnu lze vrátit pomocí Zpět. Po odmítnutí STEP kvůli limitu lze pokračovat jiným
souborem. Před ukončením dlouhé práce uložte model. Náhlé ukončení celé aplikace
nebo stroje, obnova neuloženého dokumentu a modely mimo tento rozsah nejsou touto
zkouškou garantované.
