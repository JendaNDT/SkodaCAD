# P8.2 — rozpad nákladů před optimalizací

Na pokyn autora „Takže můžeme pokračovat?“ z 3. 11. 2026 navazuje profilování
na sloučenou P8.1 (`15ec3d4cbb6bc9b91d89df81f6d301909b57a100`). Produkční
`src`, formát, závislosti i měřiče P8.1 zůstávají stejné. Výstupem jsou měřené
oblasti a návrh jednoho prvního zásahu P8.3; tato dávka jej ještě neprovádí.

## Opakování a význam časů

```bash
python tests/profile_p8.py --output out/p82-profile.json --repeats 3
```

Platí instalace a nativní obrazovka podle [P8.1](p8-1-vykonnostni-baseline.md),
na macOS také `python packaging/build_macos_accessibility.py`. Každý ze dvou
případů běží ve dvou čerstvých procesech: `control` používá původní měření P8.1,
`spans` dočasně obalí vybrané funkce v paměti procesu. Jeden nezapočítaný běh
zahřeje operaci, následují tři vzorky. Importy a instalace sond jsou mimo časování.
Případy: nativní otevření/výběr/náhled 800 kopií a přepočet/přenos historie
122 prvků se 60 skutečnými slepými kapsami. Neprofiluje se worker v jiném procesu.

Sondy měří čas na hodinách hlavního volajícího vlákna včetně nativních volání
a čekání. `inclusive_s` zahrnuje potomky a **nesmí se sčítat**; `self_s` odečítá
vnořené sondy a rozděluje kořenový interval bez překryvu. Rekurzivní/modální volání
stejného jména se agregují; jejich inclusive součet může přesáhnout délku operace.
Zbytek označený `other` není samostatná funkce ani důkaz čisté práce CPU.
U každého vzorku se ověřuje součet self proti kořenu a nezáporné intervaly.
`timer_envelope_s` uchovává malý rozdíl vnějších hodin a kořenové sondy.

Ovládání GUI přebírá přesně P8.1: skutečný výběr c799, otevření editoru tlačítkem,
změna parametru, tlačítko Náhled, připravený OCCT prohlížeč a návrat bez přijetí.
Čas zahrnuje obsluhu Qt, dva časovače s požadavkem 20 ms, čekání na připravený
náhled a ustálení událostí. Není to FPS, latence fyzického kliknutí, měření GPU
ani samotného výpočtu parametrů. `viewer_show_part` obsahuje přípravu celé scény;
`viewer_redraw` nezaručuje dokončení práce GPU. První inicializace hlavního okna
je mimo zahřáté operace; nové okno náhledu vzniká uvnitř každého náhledu.

Každé opakování musí mít stejné fyzické výsledky jako zahřátí. Oba režimy musejí
mít shodné otisky vstupů a všechny výsledky: počty, objemy, mezitvary, výběr a
zachovaný model/výsledek/historii náhledu. Původní zdroje, ukázky a měřiče se
kontrolují SHA-256 před/po. Výjimky a návratové hodnoty sondy nezaměňují, původní
metody se obnoví i při chybě. Další vlákna sondy ignorují.

Pilot s `cProfile` na místním CPythonu 3.12.14 vracel u CAD operací i záporné
kumulativní časy a vlastní časy větší než kumulativní; prokázáno také bez našich
obalů. Takové pořadí bylo odmítnuto, příčina není prokázána. Konečná metoda proto
používá výše popsané explicitní intervaly s ověřovaným účetnictvím. Nejde o opravu
produktu ani o validaci cProfile na jiných verzích Pythonu. Neúspěšné piloty nejsou
výsledky tohoto reportu.

## Místní surový průchod

[Původní JSON bez úprav](baselines/p8-2-macos-arm64.json) vznikl 3. 11. 2026
na Apple M4, macOS 27.2, Python 3.12.14, build123d 0.13.0, OCCT 8.0.1.1.0,
PySide6 6.11.3. Identifikaci produkčního commitu a otisky skutečného měřiče
uchovává přímo JSON. Všechny čtyři procesové záznamy jsou `ok`, oba režimy mají
shodnou geometrii i vstupy. Oba nativní snímky byly prohlédnuty; 800 komponent
je vykresleno a okno zůstává po návratu funkční.

| Operace | Control medián [s] | Spans medián [s] |
|---|---:|---:|
| Otevření 800 kopií se stromem/scénou | 0,360142 | 0,361342 |
| Výběr poslední komponenty | 0,044621 | 0,049056 |
| Editor → náhled → návrat | 0,734639 | 0,767878 |
| Plný přepočet 122 prvků | 2,598472 | 2,611931 |
| Encode/pickle/decode celé historie | 0,100928 | 0,098286 |

Rozdíl režimů zahrnuje režii i běžný rozptyl; záporný rozdíl nedokazuje zrychlení.
Pořadí procesů je pevné (control před spans), pouze tři vzorky nejsou statistická
studie. Neprobíhá současně další místní zátěžový běh. Přenos je v témže procesu,
bez času skutečné roury mezi procesy. Má 7 108 716 bajtů a zachovává 122 mezitvarů,
126 ploch, jedno platné těleso a analytický objem 49 034,513322 mm³.

Následující údaje jsou **aritmetické průměry self_s** tří vzorků, nikoli jejich
mediány; díky tomu se rozpad sčítá. Nevyjmenované sondy zůstávají v surovém JSON.

| Operace / sonda | Průměr self [s] | Volání v každém vzorku |
|---|---:|---:|
| Otevření: viewer_show_part | 0,099969 | 1 |
| Otevření: build_level_other | 0,096511 | 1 |
| Otevření: tree_visibility | 0,085467 | 1 |
| Otevření: source_read + source_locate | 0,036041 | 800 + 800 |
| Otevření: tree | 0,010576 | 1 |
| Náhled: build_level_other | 0,200607 | 2 |
| Náhled: source_read + source_locate | 0,089395 | 1 600 + 1 600 |
| Náhled: modal_event_loop_other | 0,096227 | 2 |
| Náhled: viewer_show_part | 0,092510 | 1 |
| Náhled: preview_scene_other | 0,061312 | 1 |
| Náhled: usage_analysis | 0,031959 | 5 |
| Historie: volume_validation | 2,095634 | 242 |
| Historie: boolean_apply_other | 0,337851 | 61 |
| Historie: feature_other | 0,150740 | 122 |
| Přenos: shape_encode / shape_decode | 0,044963 / 0,048227 | 184 / 184 |

Přepočet historie má kořenový průměr 2,613453 s. Objemové kontroly tvoří přibližně
80 %; kopie pracovního kontextu a přijetí prvku dohromady jen 0,002087 s.
To **neopravňuje vypnout kontroly**. `boolean_apply_other` zahrnuje booleovskou
operaci i další práci mimo samostatně zachycené validace, nejde o čistý čas OCCT.

U otevření je hlavní cena rozdělena mezi sestavení, scénu a aktualizaci vzhledu
stromu. Samotné vytvoření řádků stromu má přibližně 11 ms, jejich následná
aktualizace průhlednosti/viditelnosti 85 ms (asi 24 % kořenového průměru 0,363120 s).
V náhledu proběhnou dvě sestavení v rámci bezpečnostních kontrol původního
a zkušebního výsledku. Náklady řešení nelze zaměnit za vykreslení či čekání.
Pět analýz použití parametrů je menší, ale konkrétní opakování práce.

## Jedna první změna pro P8.3

Doporučení: **nejprve agregovat vzhled větví jen po dobu jednoho
`AssemblyWindow._refresh_tree_visibility`**. Zdrojový průzkum ukazuje, že pro
každý řádek `_branch_values` znovu sestaví množinu rodičů a projde všechny stavy;
pro průhlednost se volá dvakrát. Plochých 800 řádků tak vyžaduje opakované průchody
800 stavy (kvadratická práce). Čas celé této oblasti byl přímo změřen; přesný
podíl jednotlivých pomocných funkcí ani budoucí úspora tím ještě nejsou dokázány.

Návrh má nejmenší rozsah: jednorázově připravit agregace listů a větví z aktuálních
stavů, použít je pro písmo a tooltip a na konci je zahodit. **Bez trvalé cache**:
každé obnovení znovu čte aktuální výsledek a pravidla. Nesmí uchovávat geometrii,
měnit session ani přeskočit výpočty/validaci. Ověřit shodný stav všech řádků pro
ploché i vnořené sestavy, děděné výjimky průhlednosti, skrytí, izolaci, chybějící
díly a prázdné větve, výměnu výsledku a Zpět/Znovu. Porovnat stejné control vstupy
před/po na témže stroji; změna musí obstát i ve skutečném nativním okně a plných
kontrolách obou systémů. Tento zásah ještě nebyl proveden.

Zdrojové čtení, dvě sestavení náhledu, konstrukce scény a objemová validace jsou
další náměty až po tomto odděleném zásahu. Trvalé sdílení výsledků validace nebo
zdrojové cache vyžaduje samostatný návrh identity/invalidace; nestačí cesta k souboru
nebo stejný počet ploch. Měření nepotvrzuje bezpečnost takové cache.

## Automatické ověření a meze

`tests/test_p82_profile.py` ověřuje vnoření i rekurzi, součty, původní výjimku,
statické/vázané/třídní metody, obnovu a oddělení dalšího vlákna. Společné fyzické
reference zůstávají v `test_p81_reference.py`. Samostatné workflow **P8.2 profilování
hlavního vlákna** spouští stejné čtyři procesy na Windows a macOS a uchovává raw
JSON, child logy a snímky 30 dní. `P82_CASE`, `P82_RESULT`, `P82_ENV` dovolují
ověřit úplnost, fyzické výsledky, otisky i identitu sestavení. PR používá syntetický
merge commit, po sloučení reálný main; Windows CRLF vyžaduje odpovídající bajtové
otisky. Časy nemají práh úspěchu. Timeout ukončí vlastní procesy, ponechá chybu
a log; žádný případ se kvůli průchodu nevyřazuje.

Před sloučením jsou nutné i běžné úplné testy, build a self-testy stažených aplikací
Windows/macOS. Časy odlišných runnerů nejsou žebříček OS. P8.2 neměří dlouhodobou
stabilitu ani důkaz absence úniků; to zůstává P8.4. Rozpočty a přijetí P8.5,
autorské přejímky P5/P6/P7 i odborná validace NDT se tím neoznačují za provedené.
