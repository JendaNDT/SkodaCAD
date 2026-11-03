# P8.1 — výchozí měření výkonu a odezvy

První měřicí sada P8 navazuje na produkční `main` po P7.36, commit
`7541cd05f0c3ac557390c80d246a4723db8ed179`. Nemění produkční algoritmy,
formát, mezipaměť ani závislosti. Cílem je určit, které případy stojí za profilování
v P8.2, a zachovat opakovatelné vstupy pro srovnání před/po.

## Spuštění a evidence

```bash
python tests/benchmark_p8.py --output out/p8-baseline.json --repeats 3 --timeout 240
```

Vyžaduje instalaci `.[dev,gui]` a pro dva případy GUI skutečnou obrazovku. Nastavení
`QT_QPA_PLATFORM=offscreen` se pro nativní měření nepoužívá. Program vytváří vlastní
profil a vstupy vedle výstupního JSON; neotvírá ani nezapisuje autorské projekty.
Existující výstup a složku evidence odmítne přepsat.

Na macOS před prvním nativním spuštěním sestavit stávající podporu přístupnosti
pomocí `python packaging/build_macos_accessibility.py` (systémový Xcode SDK).
Nové workflow tento krok provádí také; přístupnost se při měření nevypíná.

Výběr části sady:

```bash
python tests/benchmark_p8.py --output out/p8-core.json --cases history-60,assembly-800
python tests/benchmark_p8.py --output out/p8-native.json --cases gui-history,gui-assembly
```

Každý případ je nový samostatný Python proces. Operace má jeden nezapočítaný
zahřívací běh a tři měřené běhy; ukládají se všechny vzorky, minimum, medián a maximum.
Start knihoven se měří třikrát v čerstvých procesech bez zahřátí. OS a diskové cache
se záměrně nemažou: „nový proces“ neznamená studený systém po restartu.

Záznam obsahuje commit a SHA-256 produkčních souborů, měřičů i ukázek, prostředí,
verze knihoven, zatížení a související proměnné vláken. Na konci ověří, že se zdroje,
měřič a původní ukázky během měření nezměnily. Na obou systémech používá stejný
kód. Workflow **P8.1 měření výkonu** má vlastní runner pro Windows i macOS, oddělený
od testů a balení aplikace, a ukládá JSON, logy a nativní snímky na 30 dní.
Řádky `P81_CASE` a `P81_ENV` v logu obsahují také strojově čitelný stručný souhrn.

Čas nemá práh úspěchu v pytest ani CI. Ochranný timeout ukončí vlastní proces
i potomky při zaseknutí; takový případ zůstane v evidenci jako neúspěšný, nikoli
jako falešně rychlý výsledek. Základní fyziku vstupů zvlášť ověřuje
`tests/test_p81_reference.py`.

## Měřené případy

| Případ | Rozsah a měřená práce | Kontrola správnosti |
|---|---|---|
| Start | tři nové procesy, import CAD knihoven | skutečné verze a otisk kódu; není to start GUI |
| Dlouhá historie | 22, 62 a 122 prvků: deska a 10/30/60 skutečných slepých kapes; plný přepočet a encode/pickle/decode | platné jediné těleso, objem podle vzorce, počet prvků a mezitvarů |
| Mnoho kopií | 50, 200 a 800 kopií kvádru 10 × 10 × 10; nová/zahřátá cache a náhled parametrů | úplný výsledek, počet kopií a součet objemů; náhled nemění originál |
| Vazby | 8 a 24 nezávislých skupin krabičky: 48/144 dílů a 56/168 vazeb | všechny vazby splněné, platné tvary, zachovaný objem |
| STEP sestavy | export 200 kopií; opětovný import probíhá mimo měřený čas | 200 těles, stejný objem a validita |
| STEP dílu | import skutečného STEP se 60 kapsami v hlídaném pomocném procesu, převzetí výsledku | jednotky mm, jedno těleso, analytický objem a rozměry; není to soubor zvětšený mezerami |
| Více NDT studií | geometrické mapy PT a MT na referenční kapse, krok 12 mm, MT středy 24 mm, aplikace a inspekce MT vypnuté | stabilní stavy a vážené plochy, skutečné vzorky, nezměněný model; nejde o odbornou validaci NDT |
| Worker | první otevření/převzetí, další přepočty, zrušení zátěže a následný přepočet | správná geometrie, ukončený zrušený proces a funkční obnova |
| Nativní díl | 122 prvků, otevření, worker, převzetí a vykreslení; skutečný příkaz Zastavit a obnova | skutečný OCCT prohlížeč, správný objem a návrat k poslední geometrii |
| Nativní sestava | 800 kopií, otevření se stromem a scénou, výběr poslední komponenty, otevření a zrušení náhledu parametrů | skutečné id výběru a 3D okno, náhled bez změny originálu a historie |

Syntetické kapsy nejsou pouhé prázdné záznamy historie. Jejich objem je
`(4N+8) × 20 × 10 − N × π × 1² × 3` mm³. Sestavy s vazbami neměří jednu hustě
spojenou soustavu o 168 vazbách, ale 24 nezávislých sedmivazbových skupin.

## Význam paměti a odezvy

RSS se vzorkuje přibližně po 100 ms, samostatně pro měřicí rodič a každý známý
worker. Zachová se časová řada, nejvyšší pozorované hodnoty a nejvyšší součet
v jednom sběrovém cyklu. Čtení procesů je postupné, krátké špičky mohou uniknout;
nejde o tvrdou mez paměti ani o paměť GPU. Maxima jednotlivých PID se nesčítají
jako současná spotřeba. RSS zahrnuje importy, přípravu, validace a opakování případu,
nikoli pouze alokaci jedné operace. Samotné vzorkování má režii zahrnutou v časech.

Nativní okno zaznamenává mezery skutečného Qt časovače s intervalem 5 ms. Jsou
orientačním důkazem, kdy hlavní smyčka nestíhala, nikoli FPS nebo změřenou latencí
kliknutí. Ukládá se počet vzorků, medián/p95/maximum a maximum v každé jednotlivé
operaci; první položka operace je zahřátí. U krátké synchronní operace mohou být
jen dva vzorky — její p95 proto nelze vykládat jako statistiku běžného používání.

`first_window_ready_s` začíná až po importech GUI; samostatný údaj
`first_window_from_case_entry_s` zahrnuje CAD i GUI importy a přípravu, nikoli start
interpretu před vstupem do případu. Čas otevření obsahuje sestavení, strom, předání
scény a zpracování událostí Qt. Není to měření dokončení všech příkazů na GPU.

Běžný přepočet workeru neposílá průběžnou zprávu po každém prvku. Zátěž se proto
ruší po 100 ms na již použitých procesech. Pokud by skončila před požadavkem,
rušení se označí za nezměřené; rychlejší hardware tím neselže. Nativní zkouška
navíc skutečně spouští příkaz Zastavit a ověřuje zachování původní geometrie.

## Výchozí výsledek na zařízení autora — 3. 11. 2026

[Úplný nezměněný JSON](baselines/p8-1-macos-arm64.json) obsahuje 14 názvů případů,
16 samostatných procesů (start třikrát), všechny vzorky a otisky měřičů. Všech
16 záznamů je `ok`; čtyři samostatné reference vstupů prošly. Produkční zdroj je
výše uvedený `7541cd0`; měřič vznikl následně v této dávce a jeho přesnou verzi
určují samostatné SHA-256 v JSON, nikoli pole `commit` produkčního základu.

Apple M4, 10 logických CPU, 16 GiB RAM, arm64, Darwin 27.2.0, Python 3.12.14,
build123d 0.13.0, OCCT balíček 8.0.1.1.0, PySide6 6.11.3. Bez vynuceného počtu
vláken a bez souběžných místních testů nebo balení. Ostatní systémové procesy
nebyly vypnuté; jejich okamžité zatížení zachycuje prostředí v JSON.

| Operace | Medián ze tří běhů [s] | Minimum–maximum [s] |
|---|---:|---:|
| Plný přepočet, 22 prvků / 10 kapes | 0,110 | 0,110–0,111 |
| Plný přepočet, 62 prvků / 30 kapes | 0,647 | 0,645–0,650 |
| Plný přepočet, 122 prvků / 60 kapes | 2,356 | 2,350–2,360 |
| Encode/pickle/decode, 122 prvků | 0,100 | 0,091–0,101 |
| Zahřátá sestava, 50 kopií | 0,008 | 0,008–0,008 |
| Zahřátá sestava, 200 kopií | 0,031 | 0,030–0,031 |
| Zahřátá sestava, 800 kopií | 0,125 | 0,124–0,125 |
| Oddělený výpočet náhledu, 800 kopií | 0,158 | 0,158–0,161 |
| Zahřátá sestava, 144 dílů / 168 vazeb ve 24 skupinách | 0,224 | 0,222–0,252 |
| STEP export, 200 kopií | 0,014 | 0,010–0,014 |
| STEP import/převzetí v pomocném procesu, 60 kapes | 1,245 | 1,244–1,253 |
| Geometrické mapy PT a MT dohromady | 3,619 | 3,616–3,634 |
| Zahřátý worker/převzetí, 62 prvků | 0,709 | 0,703–0,726 |
| Nativní díl, otevření/worker/převzetí/scéna, 122 prvků | 2,637 | 2,634–2,710 |
| Nativní sestava, otevření/strom/scéna, 800 kopií | 0,368 | 0,364–0,387 |
| Nativní sestava, výběr poslední komponenty | 0,048 | 0,040–0,050 |
| Nativní sestava, editor/náhled/návrat bez potvrzení | 0,757 | 0,752–0,783 |

Import CAD knihoven v novém procesu měl medián 1,097 s. První pracovní přepočet
a převzetí 62 prvků trvalo jednorázově 1,963 s. Nativní první okno od vstupu do
případu včetně importů trvalo 1,938 s u dílu a 1,850 s u sestavy. Tyto jednorázové
údaje nejsou mediány opakovaných startů GUI.

Zrušení již použitého workeru po požadavku: 8 ms, následná obnova 731 ms;
skutečný příkaz Zastavit v nativním okně 18 ms. Oba případy ověřily mrtvý zrušený
proces a správný následující výsledek. Nativní historie zaznamenala přibližně
797 MiB maximálního pozorovaného RSS rodiče a 1606 MiB součtu sledovaného poolu;
nativní sestava přibližně 759 MiB rodiče bez workerů. Jde o maxima celého případu,
včetně přípravy a validace, nikoli přírůstek přepočtu nebo důkaz úniku paměti.

V měřených bězích nativního otevření sestavy byly nejdelší mezery Qt časovače
357–371 ms; v otevření náhledu 439–457 ms. Při otevření dílu s workerem 157–174 ms.
Tyto mezery ukazují blokovanou hlavní smyčku; neurčují, kolik z ní spotřeboval
strom, převod tvarů či kreslení. Do globální statistiky vstupuje i konstrukce okna
a čekání před snímkem, proto se pro toto srovnání používají jednotlivé operace.

**Pořadí pro P8.2:** nejprve rozdělit náklady hlavního vlákna při otevření/náhledu
800 kopií na přípravu, strom a scénu. Výpočet sestavy samotný má zde 0,125 s,
celý tok náhledu 0,757 s; rozdíl není čistý čas vykreslování. Potom profilovat
122prvkovou historii: růst 0,110 → 0,647 → 2,356 s je rychlejší než růst počtu
prvků, ale bez profilu neprokazuje konkrétní složitost ani nutnost nové cache.
Otevření STEP je první referencí hlídaného procesu a PT/MT první referencí více
studií; jejich fyzikální použitelnost tím není potvrzena. Před změnou algoritmů
nejprve získat srovnatelné výsledky i na CI Windows a macOS.

## Meze a pokračování

Výsledky porovnávat pouze pro stejný případ, zařízení, knihovny a zatížení. CI běží
na jiném hardwaru; čísla Windows a macOS nejsou žebříček operačních systémů.
Tři vzorky nejsou dlouhodobý provoz ani důkaz absence úniku paměti. P8.4 prověří
dlouhé opakování a poruchové scénáře samostatně. Ani velké syntetické vstupy
nenahrazují rozmanité skutečné projekty a soubory STEP z jiných CADů.

P8.1 nemění toleranci ani kvalitu geometrie a nepřidává cache či částečný přepočet.
P8.2 má profilovat konkrétní naměřené náklady; návrh změn a jejich invalidace
musí vycházet z těchto důkazů. Odborná validace NDT-17 zůstává oddělená.
