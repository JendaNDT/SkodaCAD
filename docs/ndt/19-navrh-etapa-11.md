# NDT – návrh etapy 11: PT – přístupnost povrchu pro kapilární zkoušku

Stav: **schváleno autorem 19. 10. 2026 („schvaluji etapu 11 včetně doporučení 1–9“);
implementace po krocích ve vývojové větvi.**
Výchozí stav: `main`, commit `5e59c28` ([PR #24](https://github.com/JendaNDT/SkodaCAD/pull/24)).
Navazuje na [plán, etapa 11](03-implementacni-plan.md), [NDT studie (etapa 01)](04-navrh-etapa-00-01.md),
[geometrické jádro (etapa 02)](06-navrh-etapa-02.md), [referenční díly](05-referencni-dily.md)
a [závazné vymezení UT](04-zavazne-vymezeni-ut.md). Vymezení UT v bodě 4 říká, že rozsah PT, MT
a RT „podléhá vlastním návrhům a ověřování“ – tento návrh proto obsahuje i **navržené vymezení
PT** (oddíl 1), které po schválení platí stejně závazně jako vymezení UT. Etapa 11 otevírá
milník **M4 – všechny čtyři metody v geometrické úrovni** (etapy 11–13).

Zadání z plánu: *„Samostatný PT modul: povrchové oblasti, dostupnost pro aplikaci, čištění,
odstranění přebytku a vyhodnocení. Vyhledat úzké štěrbiny, uzavřené kapsy a zakrytá místa;
upozornit na možné falešné indikace a nemožnost čištění. Nepředstírat predikci skutečného
vzlínání či citlivosti bez experimentálních dat.“* Výstup: *„PT mapa přístupnosti a seznam důvodů
omezení.“* Podmínka dokončení: *„Ručně definované otevřené a nepřístupné oblasti správně
odlišeny.“*

## Co tato etapa přinese

**Dnes:**

- PT studii jde založit (metoda „kapilární“, oblast = vybrané plochy) a uložit do modelu.
  Ukázka koutového svaru ji už má. **Nic se pro ni ale nepočítá** – panel NDT ukáže jen obecné
  upozornění a stav studie.
- Mapa tloušťky a výpočty UT se PT netýkají. Kam se dostane hadřík, kam jde nastříkat vývojka
  a kam je vidět okem, dnes program neřekne.

**Po etapě 11:**

1. U PT studie bude v panelu NDT skupina **Přístupnost povrchu pro PT**. Tlačítko **Spočítat
   mapu PT** rozdělí plochy studie na drobné plošky. Pro každou zjistí tři věci:
   - **Nástřik** – jde na místo nastříkat penetrant, čistič nebo vývojku přímou čarou zvenku?
   - **Otření nástrojem** – dostane se tam hadřík na prstu nebo štětec (hlavní nástroj),
     případně aspoň vatová tyčinka (jemný nástroj)? Platí pro čištění a odstranění přebytku.
   - **Prohlídka** – je místo vidět okem z rozumné vzdálenosti a pod rozumným úhlem?
2. K tomu dvě **upozornění**: **úzká mezera** (štěrbina, kam se nástroj nevejde a kde může
   zůstat penetrant – riziko falešné indikace) a **hluboké nebo zakryté místo** (je otevřené
   jen do malé části směrů).
3. **Mapa ve 3D** ve čtyřech barvách:
   - **zelená** – přístupné pro všechny zvolené kroky,
   - **oranžová** – omezené, jde jen s omezením (jen jemný nástroj, jen šikmo),
   - **červená** – nepřístupné, některý krok nejde vůbec,
   - **šedá** – nelze spolehlivě vyhodnotit.

   Mapu jde přepnout na jednotlivé kroky (nástřik / otření / prohlídka). **Klik na místo mapy**
   napíše česky **proč** (např. „nástroj Ø 10 se nevejde – blíž než 5 mm ke stěně“).
4. **Souhrn**: plocha v mm² a % pro každý stav i krok, nejčastější důvody, nejužší mezera.
   K tomu export **CSV** s povinným upozorněním PT a příkaz **`skodacad kapilarni`**.
5. Nastavení (velikost nástrojů, úhly, vzdálenost prohlídky, postup čištění) se **uloží do
   studie** (formát **19**). Výsledek mapy se neukládá – vždy se spočítá znovu.

**Co se nemění:** UT (výpočty, výsledky, upozornění), výrobní geometrie, mapa tloušťky. PT nikdy
nemění díl.

## 1. Rozsah a hranice – navržené vymezení PT (k potvrzení)

Po schválení vznikne samostatný závazný dokument `docs/ndt/20-vymezeni-pt.md` se stejnou
stavbou jako vymezení UT. Obsah:

**Co PT modul SMÍ vyhodnocovat:** jen **geometrickou přístupnost povrchu** pro jednotlivé kroky
kapilární zkoušky – zda na místo vede volná přímka zvenku (nástřik, výhled), zda se tam vejde
zadaný nástroj a jak široká je mezera proti protější stěně. Kroky zkoušky podle EN ISO 3452-1:
příprava a předčištění, nanesení penetrantu, odstranění přebytku, nanesení vývojky, prohlídka,
závěrečné čištění.

**Co PT modul NESMÍ tvrdit, že vyhodnocuje:** smáčivost, vzlínání ani odstranitelnost
penetrantu, dobu penetrace a vyvolání, kvalitu vrstvy vývojky, vliv materiálu, drsnosti, teploty
a znečištění, osvětlení a UV (podmínky prohlídky podle ISO 3059), citlivost zkoušky ani
detekovatelnost vad. „Přístupné“ **není** důkaz, že by se tam vada našla.

**Povinné upozornění** (konstanta `ndt.PT_DISCLAIMER`, doslova v okně, CLI i CSV):

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti povrchu pro jednotlivé kroky
> kapilární zkoušky (nanesení, čištění a odstranění přebytku, vývojka, prohlídka) na základě
> zjednodušených modelů nástrojů a výhledu. Nevyhodnocuje smáčivost, vzlínání ani odstranitelnost
> penetrantu, citlivost zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT
> postup ani odborné posouzení.

**Názvy v okně a protokolech:** „Přístupnost povrchu pro PT“ (`PT_ACCESS`), „Mapa geometrické
přístupnosti PT“ (`PT_MAP`). Test `tests/test_ndt_scope.py` bude hlídat doslovné znění proti
dokumentu a zakázaná označení (například „mapa citlivosti“) stejně jako u UT.

**Další hranice etapy:**

- **Jen povrch dílu jako jednoho tělesa.** Sestavy, upínky a okolí se nemodelují. Styčná plocha
  dvou dílů se v jednom tělese projeví jen jako úzká mezera.
- **Jen plochy PT studie.** Studie s cílovým objemem (svar jako objem) PT odmítne česky: „PT
  posuzuje povrch – vyber plochy.“
- **Jen geometrie, žádný čas ani technika práce.** Doby penetrace, tlak vody, vzdálenost spreje
  ani pořadí kroků program neřeší.
- **Ostrý vnitřní roh modelu je ideální.** Skutečný přechod (pata svaru) má zaoblení, výsledek
  v úzkém pásu u ostrého rohu je proto přísnější než skutečnost. Výstup to napíše.

## 2. Jak se přístupnost počítá

### Vzorky povrchu

Plochy studie se rozdělí na trojúhelníky stejným postupem jako mapa tloušťky (`thickness_map`,
půlení nejdelší strany do zvoleného kroku). Vzorek = těžiště trojúhelníku, váha = jeho plocha
v mm². Procenta jsou podíly plochy, ne počtu vzorků. Výchozí krok se volí tak, aby vzorků bylo
nejvýš asi 2000. Před spuštěním se ukáže odhad doby.

### Pevná sada směrů

Z každého vzorku se zkouší **65 pevných směrů**: kolmice k ploše a 64 směrů rozložených
rovnoměrně po polokouli nad místem (spirála; stejná sada vždy, žádná náhoda). Na každý směr
jde jeden paprsek jádra (`PartGeometry.visible`).

Když je nejlepší volný směr blízko meze úhlu, dohledá se půlením po poledníku k normále
s přesností 0,5° (podobně jako dohledání konce úseku v etapě 10). Velmi úzký volný kužel,
užší než rozestup směrů (asi 13°), se přesto může minout. Výstup proto píše „odhad
z 65 směrů“.

### Tři kontroly

| Kontrola | Kroky zkoušky | Jde | Omezeně | Nejde |
|---|---|---|---|---|
| **Nástřik** | penetrant, vývojka, čistič ze spreje, oplach | volný paprsek do **60°** od kolmice | volný jen **60–85°** od kolmice | žádný volný směr do 85° |
| **Otření nástrojem** | předčištění, odstranění přebytku, závěrečné čištění (postup *otřením*) | vejde se **hlavní nástroj Ø 10** | vejde se jen **jemný nástroj Ø 3** | nevejde se ani jemný |
| **Prohlídka** | prohlídka okem | volný výhled pod úhlem **≥ 30° k povrchu**, oko do **600 mm** | výhled jen pod ostrým úhlem (5–30° k povrchu) | žádný výhled |

- **Nástřik** = volná přímka zvenku. Vzdálenost trysky se neřeší: v modelu je jen díl, a když je
  paprsek volný, je volný do libovolné dálky.
- **Nástroj** = **kulička** o průměru nástroje (špička, hadřík na prstu, štětec) dotýkající se
  místa a **dřík** (válec stejného průměru, výchozí délka 100 mm) vycházející z jejího středu
  ven. Dřík smí mít libovolný sklon v polokouli nad místem, i rovnoběžně s plochou (vatová
  tyčinka zasunutá do otvoru). Kulička se kontroluje vzdáleností středu od dílu (≥ poloměr).
  Dřík se napřed rychle prověří pěti paprsky a pak **přesně** průnikem s dílem (jádro OCCT,
  dotyk není kolize – jako u sondy). O výsledku vždy rozhoduje přesná kontrola, paprsky jsou
  jen síto.
- **Prohlídka** = volný paprsek pod povoleným úhlem a místo pro oko. Na paprsku do 600 mm od
  místa se musí najít bod, kde je kolem volná koule **Ø 50 mm** (oko, objektiv). Tak program
  pozná, že se oko nemůže dívat zevnitř úzkého otvoru. Zrcátko a endoskop se nemodelují.
  Místo „jen pod ostrým úhlem“ výstup popíše slovy „prohlídka jen šikmo nebo se zrcátkem“.

**Postup čištění a odstranění přebytku** se volí ve studii:

- **otřením** (výchozí; rozpouštědlový postup ze spreje, v ISO 3452-1 metoda C) – platí
  kontrola *Otření nástrojem*;
- **oplachem** (vodou omyvatelný postup, metoda A) – oplach se posuzuje jako *Nástřik* proudem
  a kontrola nástroje se vypne.

### Upozornění (mění zelenou na oranžovou, nikdy samo na červenou)

- **Úzká mezera:** paprsek z místa po kolmici ven narazí na protější stěnu dílu blíž, než je
  průměr hlavního nástroje. Hlášení: „mezera 1,0 mm – nástroj Ø 10 se nevejde“. Pod průměrem
  jemného nástroje: „úzká štěrbina 1,0 mm – přebytek penetrantu z ní nejde spolehlivě
  odstranit, hrozí falešná indikace“. Šířka je čistá geometrie, věta je jen upozornění, ne
  výpočet vzlínání.
- **Hluboké nebo zakryté místo:** **otevřenost** = podíl volných směrů z 65, vážený jako podíl
  prostorového úhlu polokoule. Pod **10 %** (lze změnit) přijde upozornění: „otevřené jen do
  1,1 % směrů – nanesení vývojky a prohlídka jsou obtížné“. Zkouška na dně kapsy (40 × 30,
  hloubka 25): 14 z 64 volných směrů = 21,9 %, ručně prostorový úhel otvoru 1,309 sr = 20,8 %
  polokoule.

### Výsledný stav vzorku

1. Kterákoli zvolená kontrola **nejde** → **nepřístupné** (červená) s důvodem.
2. Jinak kterákoli **omezeně** nebo upozornění → **omezené** (oranžová).
3. Jinak, když byl rozhodující paprsek nejistý (přes hranu, tečně – jádro etapy 02) →
   **nelze spolehlivě vyhodnotit** (šedá). Nejisté se nikdy nepočítá jako přístupné.
4. Jinak **přístupné** (zelená).

Důvody se ukládají ke vzorku jako krátké české věty. Souhrn je sečte podle druhu (plocha v mm²).

## 3. Výchozí hodnoty a odkud jsou

| Hodnota | Výchozí | Původ |
|---|---|---|
| Úhel prohlídky k povrchu | **≥ 30°** | ASME BPVC V čl. 9 (přímá vizuální kontrola: oko do 24 in = 600 mm, úhel ≥ 30°) a BINDT CP25, příloha A (stejné meze); příručky ke zkoušce IWI je přisuzují i EN ISO 17637. Placený text EN ISO 17637 a EN 13018 jsme **neověřili**. |
| Vzdálenost oka | **≤ 600 mm** | totéž |
| Nástřik „jde“ / „omezeně“ | 60° / 85° od kolmice | **zvoleno pro výpočet**, ne z normy (stejné meze jako výhled kvůli jednoduchosti) |
| Hlavní nástroj | Ø 10 mm, dřík 100 mm | **zvoleno** (hadřík na prstu, štětec); změň podle skutečného nástroje |
| Jemný nástroj | Ø 3 mm, dřík 100 mm | **zvoleno** (vatová tyčinka) |
| Volný prostor pro oko | Ø 50 mm | **zvoleno** |
| Upozornění na otevřenost | pod 10 % | **zvoleno** |

Zvolené hodnoty jsou označené v okně i ve výstupu („zvoleno pro výpočet, ne z normy“), stejně
jako u virtuální sondy 40 × 20 × 25. Osvětlení a UV-A pro prohlídku stanoví ISO 3059. Program je
nepočítá a v souhrnu na ně jen upozorní.

## 4. Ruční výpočty (podle nich se bude testovat)

Pás u vnitřního rohu, kam se kulička o poloměru $r$ nedostane: $x_0 = r \cdot \cot(\theta/2)$,
kde $\theta$ je úhel mezi plochami na straně vzduchu (90° = kapsa, 135° = koutový svar).
**Zkouška jádrem (19. 10. 2026, cloud):** kulička nad dnem kapsy je dosažitelná od 5,0 mm od
stěny (ručně 5 mm). Na ploše koutového svaru vyšlo dosažitelných 58,15 % délky pro Ø 10
(ručně 58,16 %) a 87,45 % pro Ø 3 (ručně 87,45 %).

**Koutový svar** (`koutovy_svar.json`, studie s1 – obě plochy svarů, délka plochy
z·√2 = 9,90 mm, rohy 135°):

| Nástroj | Pás u každého rohu | Otření jde | Výsledek |
|---|---|---|---|
| Ø 10 | 5 · cot 67,5° = 2,07 mm | 58,16 % | zelená 58,16 % |
| Ø 3 | 1,5 · cot 67,5° = 0,62 mm | 87,45 % | oranžová 29,29 %, červená 12,55 % |

Nástřik i prohlídka: 100 % (plochy svaru jsou otevřené).

**Blok s kapsou** (`kapsa.json`, nová PT studie dna a stěn, kapsa 40 × 30, hloubka 25):

| Plocha | Ø 10 jde | Ø 3 jde | Výsledek |
|---|---|---|---|
| Dno 40 × 30 | (40−10)(30−10) = 600 mm² = **50 %** | 37 · 27 = 999 mm² = 83,25 % | zelená 50 %, oranžová 33,25 %, červená 16,75 % |
| Delší stěna 40 × 25 | (40−10)(25−5) = **60 %** | 37 · 23,5 = 86,95 % | zelená 60 %, oranžová 26,95 %, červená 13,05 % |
| Kratší stěna 30 × 25 | (30−10)(25−5) = **53,33 %** | 27 · 23,5 = 84,6 % | |

Prohlídka stěn: místo v hloubce $d$ vidí přes kapsu šířky $W$ pod úhlem ≥ 30°, když
$d \le W \cdot \tan 60^\circ$ (30 · 1,732 = 52 mm > 25) → 100 %. Otevřenost středu dna 20,8 %.

**Nový referenční díl č. 9 – blok se štěrbinou a slepým otvorem** (`examples/ndt/sterbina.json`,
po schválení i do `05-referencni-dily.md` jako NEOVĚŘENO pro kolegu NDT technika). Blok
100 × 60 × 30. Uzavřená štěrbina délky 40, šířky **w = 1** a hloubky 20 v x = −25. Slepý otvor
**Ø 6** hloubky 20 v x = +25. Objem 100·60·30 − 40·1·20 − π·3²·20 = **178 634,51 mm³**.
Tři PT studie: horní plocha, dlouhé stěny štěrbiny a slepý otvor (dno a stěna).

| Plocha | Otření | Nástřik i prohlídka | Upozornění |
|---|---|---|---|
| Horní plocha | jde 100 % | jde 100 % | – |
| Stěny štěrbiny (2 × 40 × 20) | **nejde 100 %** (1 mm < Ø 3) | jde, když $d \le w \tan 60^\circ$ = 1,73 mm (**8,66 %**); omezeně do $w \tan 85^\circ$ = 11,43 mm (**48,49 %**); nejde **42,85 %** | úzká štěrbina 1 mm |
| Dno otvoru (π · 3² = 28,27 mm²) | Ø 10 nejde; Ø 3 jen do 1,5 mm od osy = **25 %** (oranžová), zbytek nejde | jde 100 % (kolmo nahoru, oko nad ústím) | otevřenost středu dna 1 − cos(atan(3/20)) = **1,1 %** |
| Stěna otvoru (π · 6 · 20 = 376,99 mm²) | Ø 10 nejde; Ø 3 jde kromě pásu 1,5 mm u dna = **92,5 %** (oranžová) | jde, když $d \le 6 \tan 60^\circ$ = 10,39 mm (**51,96 %**), jinak omezeně (**48,04 %**) | mezera 6 mm < Ø 10 |

**Deska** (`deska.json`, PT na horní ploše): vše přístupné, otevřenost 100 %.

Mřížka vzorků čísla jen přibližuje. Testy proto porovnávají s tolerancí podle kroku sítě
(řádově ± 2 procentní body při kroku 1 mm u úzkých pásů). Přesně se ověřuje i hranice pásu
v jednotlivých bodech, jako ve zkoušce výše.

## 5. Uložení do souboru (formát 19)

PT studie dostane nepovinnou položku `pt`:

```json
"pt": {
  "step_mm": 2, "cleaning": "wipe",
  "tool_mm": 10, "fine_tool_mm": 3, "tool_length_mm": 100,
  "spray_deg": 60, "spray_limit_deg": 85,
  "view_deg": 30, "view_limit_deg": 5, "view_distance_mm": 600, "eye_mm": 50,
  "open_warning": 10
}
```

- Chybějící hodnota = výchozí. Studie bez `pt` zůstane totožná, verze 1–18 se načtou beze změny.
- Změna nastavení je jeden krok Zpět a mapu zruší. Mapa sama se neukládá. Po změně dílu zmizí
  (jako mapa pokrytí). Zastaralou studii je třeba nejdřív potvrdit.
- `pt` u jiné metody než PT = česká chyba při načtení.

## 6. Okno

- Při výběru **PT studie** ukáže panel NDT místo skupin sondy skupinu **Přístupnost povrchu pro
  PT** s povinným upozorněním PT. Skupiny UT zůstanou pro UT studie beze změny.
- **Nastavení…**: dialog s poli z oddílu 5, u zvolených hodnot poznámka „zvoleno pro výpočet“.
  Čísla jako text (bez zaokrouhlení), nezměněné *OK* = žádný krok Zpět.
- **Spočítat mapu PT** s odhadem doby, průběhem a *Zastavit* (pomocný proces jako u pokrytí).
- **Mapa ve 3D** (čtyři barvy, legenda) kreslená stávajícím způsobem mapy pokrytí – žádný nový
  druh kreslení. Přepínač **Ukázat: celkem / nástřik / otření / prohlídka**.
- **Klik na místo mapy** → pod souhrnem stav a důvody nejbližšího vzorku.
- **Souhrn** (plocha a % po stavech a krocích, nejčastější důvody, nejužší mezera, nejnižší
  otevřenost) a **Export CSV…**.
- Během práce AI je skupina zamčená (jako ostatní).

## 7. Výstupy

- **CSV:** povinné upozornění PT, předpoklady (nástroje, úhly, postup, krok, 65 směrů, „zvoleno
  pro výpočet“, ostré rohy ideální, algoritmus a verze), souhrn, pak řádek na vzorek: x, y, z,
  plocha mm², normála, stav celkem, nástřik, otření, prohlídka, mezera, otevřenost, důvody.
- **Příkazová řádka:** `skodacad kapilarni model.json --studie s1 [--krok 1] [--nastroj 10]
  [--jemny 3] [--delka 100] [--oplach] [--csv pt.csv] [--ulozit]` – vypíše souhrn
  s upozorněním PT.
- **AI asistent** nový nástroj nedostane. Pravidla (`assistant.RULES`) dostanou větu o PT:
  výsledky PT si nevymýšlí a přístupné místo nevydává za zaručené zjištění vady.

## 8. Ověření před předáním

1. **Koutový svar:** Ø 10 → 58,16 %, Ø 3 → 87,45 % (s tolerancí sítě); přesná hranice pásu
   2,07 / 0,62 mm v bodech.
2. **Kapsa:** dno 50 % / 83,25 %, delší stěna 60 % / 86,95 %, prohlídka 100 %, otevřenost
   středu dna 20,8 % ± 3 p. b.
3. **Štěrbina a slepý otvor (díl 9):** čísla z tabulky oddílu 4, upozornění „úzká štěrbina
   1 mm“ a „otevřené jen do 1,1 % směrů“.
4. **Deska:** 100 % přístupné.
5. **Oko nemůže do otvoru:** slepý otvor Ø 6 hluboký 700 mm (pomocný díl v testu) → dno bez
   prohlídky („oko se nevejde blíž než 600 mm“).
6. **Postup oplachem:** kontrola nástroje vypnutá, štěrbina pak jen podle nástřiku.
7. **Nejisté případy:** vzorek, kde rozhoduje paprsek přes hranu, je šedý, nikdy zelený.
8. **Formát 19:** načtení verzí 1–18, studie bez `pt` beze změny, chybné `pt` = česká chyba,
   změna nastavení = jeden krok Zpět.
9. **Stejný vstup = stejný výsledek** (pevné směry): dva běhy dají totožné stavy.
10. **Rozsah:** `PT_DISCLAIMER` doslova v panelu, CLI i CSV; shoda s `20-vymezeni-pt.md`
    (`test_ndt_scope.py`), zakázaná označení. UT výsledky beze změny (regresní testy).
11. **Okno:** offscreen testy (výpočet, přepínač, klik, nastavení, Zpět, zámek AI), snímek pod
    Xvfb, GitHub Actions Windows i macOS. Testy krátké kvůli časovému limitu kroku *Testy*.

## 9. Rychlost (změřeno 19. 10. 2026 v cloudu, zkušební skript)

| Dotaz | Doba |
|---|---|
| vzdálenost středu kuličky od dílu | 0,34 ms |
| paprsek výhledu | 0,44 ms |
| přesná kolize dříku (válec Ø 10 × 100) | 7,2 ms |

Na vzorek asi 65 paprsků (≈ 29 ms) + kontrola nástrojů (2–4 přesné kolize, ≈ 15–30 ms) + oko
(≈ 2 ms) = **asi 45–60 ms**. Tisíc vzorků trvá asi minutu, proto pomocný proces a odhad
předem. Výchozí krok sítě drží počet vzorků do asi 2000.

## 10. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **11A.1 – vymezení a jádro** | `20-vymezeni-pt.md`, `PT_DISCLAIMER`, `ndt/pt.py` (vzorky, směry, nástřik, nástroje, prohlídka, mezera, otevřenost, stavy, souhrn, CSV), referenční díl 9 | testy 1–7, 9, 10 |
| **11A.2 – soubor, ModelSession, CLI** | formát 19 (`pt`), `ModelSession` (nastavení jako krok Zpět, mapa jako pohled), pomocný proces, `skodacad kapilarni` | test 8 |
| **11B – okno** | skupina *Přístupnost povrchu pro PT*, dialog nastavení, mapa, přepínač, klik, souhrn, CSV | test 11, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 11. Co etapa 11 nebude

- vzlínání, smáčivost, odstranitelnost, doby penetrace a vyvolání, kvalita vrstvy vývojky,
- osvětlení a UV (ISO 3059) jinak než připomínkou, zrcátko, endoskop, kamera s optikou,
- odtékání a hromadění kapaliny podle polohy dílu (vyžaduje směr tíže a stékání – možná později),
- sestavy, upínky, okolí dílu; MT a RT (etapy 12 a 13),
- citlivost zkoušky, srovnávací vzorky ISO 3452-3, cokoli o zjistitelnosti vad,
- změna geometrie dílu (etapy 14–15).

## 12. Praktická zkouška pro autora (po 11B)

1. Otevři *NDT – referenční díly → Koutový svar*, vyber studii „PT koutových svarů“
   a stiskni **Spočítat mapu PT**. Plochy svaru mají být uprostřed zelené a u obou rohů
   oranžové a červené. Klikni do červeného pásu – důvod musí říct, že se nástroj nevejde do rohu.
2. V *Nastavení…* zmenši hlavní nástroj na Ø 3 a přepočítej: zelený pás se rozšíří, *Zpět*
   vrátí Ø 10.
3. Otevři díl 9 (štěrbina a slepý otvor): stěny štěrbiny musí být červené s upozorněním
   na úzkou štěrbinu, dno otvoru s upozorněním na hluboké místo.
4. Exportuj CSV a podívej se, že začíná povinným upozorněním PT.

## 13. K rozhodnutí

1. **Vymezení PT a povinné upozornění** v textu z oddílu 1 jako závazný dokument
   `20-vymezeni-pt.md` a konstanta `PT_DISCLAIMER` hlídaná testem. *Doporučeno: ano.* (Je to
   obdoba tvého rozhodnutí o UT; bez něj by chyběla hranice, co PT výsledek znamená.)
2. **Tři kontroly** (nástřik, otření nástrojem, prohlídka) a dvě upozornění (úzká mezera,
   otevřenost); čtyři stavy podle pořadí v oddílu 2. *Doporučeno: ano.*
3. **Model nástroje** = kulička + dřík s libovolným sklonem, **dva nástroje** (hlavní Ø 10,
   jemný Ø 3, dřík 100 mm). Hodnoty jsou zvolené, lze je změnit. *Doporučeno: ano.*
4. **Prohlídka** ≥ 30° k povrchu a oko do 600 mm (ASME V čl. 9, BINDT CP25), volný prostor pro
   oko Ø 50 mm; osvětlení se nepočítá. *Doporučeno: ano.* Až budeš mít přístup k EN ISO 17637
   nebo EN 13018, meze podle nich opravíme.
5. **Postup čištění** otřením (výchozí) nebo oplachem. *Doporučeno: ano.*
6. **Pevná sada 65 směrů** s dohledáním u meze úhlu; výsledek je označený jako odhad z konečného
   počtu směrů. *Doporučeno: ano.*
7. **Nastavení PT ve studii** (formát 19), výsledek mapy se neukládá. *Doporučeno: ano.*
   (Bez uložení by se velikosti nástrojů po zavření ztratily.)
8. **Referenční díl 9** (štěrbina a slepý otvor) a PT studie v ukázce kapsy, ruční výsledky
   v `05-referencni-dily.md` jako NEOVĚŘENO pro kolegu. *Doporučeno: ano.*
9. **Okno, CSV a `skodacad kapilarni`**, AI bez nového nástroje. *Doporučeno: ano.*

Schválením se **neschvaluje**: fyzikální výpočty PT, odtékání kapaliny, sestavy, MT a RT, nová
knihovna Pythonu ani sloučení do `main`.
