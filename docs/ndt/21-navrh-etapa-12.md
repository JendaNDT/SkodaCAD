# NDT – návrh etapy 12: MT – přiložení jha a směry magnetizace

Stav: **schváleno autorem 19. 10. 2026 („schvaluji etapu 12 včetně doporučení 1–10“);
implementace po krocích ve vývojové větvi.**
Výchozí stav: `main`, commit `3297983` ([PR #25](https://github.com/JendaNDT/SkodaCAD/pull/25)).
Navazuje na [plán, etapa 12](03-implementacni-plan.md), [geometrické jádro (etapa 02)](06-navrh-etapa-02.md),
[virtuální sondu (etapa 03)](07-navrh-etapa-03.md), [PT (etapa 11)](19-navrh-etapa-11.md),
[referenční díly](05-referencni-dily.md) a [závazné vymezení UT](04-zavazne-vymezeni-ut.md).
Vymezení UT v bodě 4 říká, že rozsah PT, MT a RT „podléhá vlastním návrhům a ověřování“.
Tento návrh proto obsahuje i **navržené vymezení MT** (oddíl 1), stejně jako návrh etapy 11
obsahoval vymezení PT. Etapa 12 pokračuje v milníku **M4 – všechny čtyři metody
v geometrické úrovni** (etapy 11–13).

Zadání z plánu: *„Nejprve kolize jha/pólů, vzdálenost pólů a možné orientace magnetizace
vzhledem k požadované orientaci vad. Ukázat potřebu různých směrů magnetizace. Fyzikální
rozložení magnetického pole, demagnetizaci a saturaci vést jako samostatnou budoucí simulaci
s materiálovými charakteristikami a validací.“* Výstup: *„MT mapa geometrické proveditelnosti
a směrového pokrytí; bez tvrzení o dostatečné intenzitě pole.“* Podmínka dokončení: *„Uživatel
vidí oblasti, kam se jho nevejde, a rozdíl při otočení magnetizace.“*

## Co tato etapa přinese

**Dnes:**

- MT studii jde založit (metoda „magnetická prášková“, oblast = vybrané plochy) a uložit do
  modelu. **Nic se pro ni ale nepočítá** – panel NDT ukáže jen obecné upozornění a stav studie.
- Kam se vejde jho, kterým směrem mezi póly povede pole a jestli místo pokryjí dva směry
  magnetizace, dnes program neřekne.

**Po etapě 12:**

1. U MT studie bude v panelu NDT skupina **Přiložení jha a směry magnetizace (MT)**. Tlačítko
   **Spočítat mapu MT** zkusí přiložit virtuální jho na mnoha místech a v **8 směrech** (po
   22,5°). U každého přiložení zjistí:
   - jestli **mají póly kam dosednout** (celý pól na povrchu, mezera pod pólem nejvýš 1 mm),
   - jestli **jho nenaráží** (nohy ani tělo nesmí projít dílem),
   - jestli mezi místem a pólem **není stěna**,

   a které místo plochy leží v **účinné oblasti** mezi póly a jakým orientačním směrem tam
   vede pole.
2. Pro každé místo plochy pak řekne, **které směry magnetizace jdou**. Podle norem se vada
   zobrazí, když je k poli skloněná aspoň o 30°. Dva směry pole, které jsou od sebe aspoň 60°
   (ideálně kolmo), proto pokryjí **všechny orientace vad**.
3. **Mapa ve 3D** ve čtyřech barvách:
   - **zelená** – pokryto ve všech orientacích vad (dva směry magnetizace), nanést i prohlédnout
     jde,
   - **oranžová** – jen část orientací (např. jen pole podél svaru) nebo nanesení či prohlídka jen
     omezeně,
   - **červená** – jho se sem nevejde v žádném směru, nebo nejde nanést či prohlédnout,
   - **šedá** – nelze spolehlivě vyhodnotit.

   Přepínač **Ukázat: celkem / pole 0° / 45° / 90° / 135° / nanesení / prohlídka** ukáže
   **rozdíl při otočení magnetizace**: kde se jho vejde jen podél, jen napříč, nebo vůbec.
4. **Klik na místo mapy** napíše česky, které směry jdou a proč ostatní ne (např. „pole 90°:
   pól přesahuje okraj – menší rozteč 75 mm se nevejde také“). Tlačítko **Ukázat jho** k tomu
   nakreslí jho ve 3D: platné zeleně, nejlepší nevyhovující červeně, i s obrysem účinné oblasti.
5. **Přiložit jho sem**: jho do kliknutého místa s volitelným natočením. Je to jen pohled, jako
   ruční přiložení sondy UT. Otočením je vidět, kdy se jho vejde a kdy ne.
6. **Souhrn**:
   - plocha v mm² a % pro každý stav i každý směr pole,
   - nejčastější důvody,
   - kontrola materiálu (feromagnetický ano / ne / neznámý).

   K tomu export **CSV** s povinným upozorněním MT a příkaz **`skodacad magneticka`**.
7. Nastavení (rozměry jha, rozteč, meze, nanesení a prohlídka) se **uloží do studie** (formát
   **20**). Výsledek mapy se neukládá – vždy se spočítá znovu.

**Co se nemění:** UT a PT (výpočty, výsledky, upozornění), výrobní geometrie, mapa tloušťky.
MT nikdy nemění díl.

## 1. Rozsah a hranice – navržené vymezení MT (k potvrzení)

Po schválení vznikne samostatný závazný dokument `docs/ndt/22-vymezeni-mt.md` se stejnou
stavbou jako vymezení UT a PT. Obsah:

**Co MT modul SMÍ vyhodnocovat:** jen **geometrii zkoušky jhem**:

- kam lze přiložit zjednodušený model jha (dosednutí pólů, kolize nohou a těla, rozteč pólů),
- kterou část povrchu zasáhne účinná oblast mezi póly a jakým **orientačním směrem** tam vede
  pole (směr spojnice pólů sklopený do plochy),
- zda místo pokryjí dva dostatečně odlišné směry magnetizace,
- zda je místo geometricky přístupné pro nanesení detekčního prostředku a pro prohlídku
  (stejné kontroly jako PT),
- zda je materiál dílu podle tabulky feromagnetický.

**Co MT modul NESMÍ tvrdit, že vyhodnocuje:**

- **Magnetické pole:** intenzitu ani skutečné rozložení pole v dílu, sycení, rozptylová pole,
  vliv mezery pod póly, tvaru dílu, tloušťky a materiálu na pole, střídavé ani stejnosměrné
  buzení, demagnetizaci.
- **Zařízení a postup:** zvedací sílu jha, dobu magnetizace, detekční prostředek (barevný,
  fluorescenční), osvětlení a UV-A (ISO 3059).
- **Detekovatelnost vad:** citlivost zkoušky, velikost nebo druh zjistitelné vady, způsobilost
  kontroly podle normy.

„Pokryto ve všech orientacích“ **není** důkaz, že je pole dost silné ani že by se vada našla.

**Povinné upozornění** (konstanta `ndt.MT_DISCLAIMER`, doslova v okně, CLI i CSV):

> ŠkodaCAD provádí pouze geometrické posouzení magnetické práškové zkoušky jhem: kam lze
> přiložit zjednodušený model jha, kterým orientačním směrem by mezi póly vedlo magnetické
> pole, zda lze místo pokrýt dvěma směry magnetizace a zda je místo přístupné pro nanesení
> detekčního prostředku a prohlídku. Nevyhodnocuje intenzitu ani skutečné rozložení
> magnetického pole, vliv materiálu, mezery pod póly a tvaru dílu na pole, citlivost zkoušky
> ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.

**Názvy v okně a protokolech:** „Přiložení jha a směry magnetizace pro MT“ (`MT_ACCESS`),
„Mapa geometrické proveditelnosti a směrového pokrytí MT“ (`MT_MAP`). Test
`tests/test_ndt_scope.py` bude hlídat doslovné znění proti dokumentu a zakázaná označení
(například „mapa magnetického pole“, „mapa intenzity pole“) stejně jako u UT a PT.

**Další hranice etapy:**

- **Jen jho** (elektromagnetické i permanentní – geometrie je stejná). Hroty, cívka, středový
  vodič a stacionární zařízení se nemodelují.
- **Jen povrch dílu jako jednoho tělesa.** Sestavy, upínky a okolí se nemodelují.
- **Jen plochy MT studie.** Studie s cílovým objemem (svar jako objem) MT odmítne česky: „MT
  posuzuje povrch – vyber plochy.“
- **Směr pole je jen orientační:** přímka mezi póly sklopená do plochy. Skutečné siločáry
  kolem otvorů, hran a v rozích se nepočítají. Výstup to napíše.

## 2. Virtuální jho

Jho = **dva póly** na **nohách** a nahoře spojující **tělo**. Je **kloubové**: každá noha se
postaví kolmo ke své ploše, takže jho překlene i vnitřní roh (T-spoj, koutový svar) nebo
převýšení svaru.

| Část | Výchozí | Původ |
|---|---|---|
| Rozteč pólů $d$ (střed–střed) | **100 mm** | **zvoleno pro výpočet** (běžná rozteč jha) |
| Nejmenší rozteč | **75 mm** – zkusí se, když 100 mm nejde | ISO 17638, obr. 4: $d \ge 75$ mm |
| Pól (dosedací plocha) | kruh **Ø 20 mm** | **zvoleno** |
| Noha (výška od plochy k tělu) | **60 mm** | **zvoleno** |
| Tělo | průřez **40 × 40 mm**, přesah **20 mm** za nohy | **zvoleno** |
| Mezera pod pólem | nejvýš **1 mm** | **zvoleno** (norma číslo neuvádí; mezera zeslabuje pole – to se nepočítá) |
| Úhel mezi nohami | nejvýš **90°** | **zvoleno** (kloubové jho přes vnitřní roh) |

Zvolené hodnoty jsou v okně i ve výstupu označené „zvoleno pro výpočet, ne z normy“, stejně
jako virtuální sonda UT a nástroje PT. Uživatel je přepíše podle svého jha.

## 3. Jak se přiložení jha počítá

**Poloha jha** = střed $c$ na povrchu dílu, směr $t$ v tečné rovině (spojnice pólů) a rozteč $d$.

1. **Místo pro pól:** v rovině proložené normálou plochy v $c$ a směrem $t$ se vezme kružnice
   o poloměru $d/2$ kolem $c$. Kružnice se sklápí od kolmice (90° nad místem) dolů a **první
   místo, kde narazí na materiál**, je místo pólu. Totéž na druhou stranu. Na rovné desce jsou
   póly přesně $c \pm (d/2)\,t$. U koutového svaru dosedne jeden pól na stojinu a druhý na
   základní desku (ověřeno zkušebním skriptem, viz oddíl 9).
2. **Mezi místem a pólem není stěna:** spojnice bodů 10 mm nad povrchem (nad $c$ a nad pólem)
   nesmí projít materiálem. Jinak by jho „skákalo“ přes okraj kapsy. Drobné výstupky do 10 mm
   (převýšení svaru) nevadí.
3. **Pól dosedá:** pól se přiloží stejným výpočtem jako přímá sonda UT (etapa 03): paprsky
   otisku, mezera, přesah přes okraj a přesná kolize nohy s dílem. Pól musí ležet celý na
   povrchu a mezera pod ním smí být nejvýš 1 mm.
4. **Nohy:** úhel mezi nohami (normálami pod póly) nejvýš 90°.
5. **Tělo:** kvádr mezi horními konci nohou (s přesahem) se přesně zkontroluje průnikem
   s dílem. Dotyk není kolize – jako u sondy.
6. **Záloha 75 mm:** když poloha s roztečí 100 mm neprojde, zkusí se rozteč 75 mm.

Každá neplatná poloha má **český důvod**:

- „pól nemá kam dosednout – okraj“,
- „pól přesahuje okraj (40 % plochy pólu bez povrchu)“,
- „mezera pod pólem 1,4 mm“,
- „noha naráží do stěny“,
- „nohy svírají 104°“,
- „tělo jha naráží“,
- „mezi místem a pólem je stěna“.

**Kde se jho zkouší:** středy jha tvoří mřížku na plochách studie a na plochách dílu do
vzdálenosti $d/4 + 10$ mm od nich. Například u koutového svaru je to základní deska vedle
svaru, odkud jho podél svaru pokryje i svar. Krok mřížky se volí sám tak, aby poloh jha bylo
asi 1500. **Hranice platných poloh se dohledá půlením na 0,5 mm** (jako konec úseku
v etapě 10), aby hrubší mřížka nezkreslila okraj pokrytí.

## 4. Účinná oblast a směr pole

Podle obrázku 4 normy ISO 17638 (výňatky – viz zdroje) je účinná oblast jha
**obdélník mezi póly**:

- **podél spojnice pólů** délka $d - 50$ mm, tedy u každého pólu se 25 mm **nepočítá** (u pólu
  je pole příliš silné a prášek se tam „chlupatí“),
- **napříč** šířka $d/2$.

Pro $d = 100$ mm je to čtverec 50 × 50 mm, pro $d = 75$ mm obdélník 25 × 37,5 mm.

Místo plochy patří do účinné oblasti polohy jha, když:

1. leží v obdélníku (souřadnice podél $t$ a napříč, měřené od $c$),
2. od roviny v $c$ je nejvýš $d/4$ (převýšení, roh svaru),
3. jeho plocha nemíří od jha pryč (normály svírají nejvýš 90°),
4. a když neleží v rovině $c$ (o víc než 2 mm), musí ho být z $c$ vidět (jeden paprsek).

**Směr pole v místě** = směr $t$ sklopený do tečné roviny místa. Když je sklopený směr kratší
než polovina (pole míří skoro kolmo do plochy, např. stěna kolmá na spojnici pólů), místo se
pro ten směr **nepočítá**.

## 5. Směrové pokrytí

- **8 směrů pole** po 22,5° (0° = průmět osy +X do plochy, u plochy kolmé na X osa +Y – stejně
  jako úhel sondy UT).
- **Orientace vad:** podle ISO 9934-1 je tok účinný pro vady odkloněné až o 60° od optimálního
  směru (optimální = kolmo k poli). Vada se tedy počítá, když je k poli skloněná aspoň o
  **30°**.
- **Všechny orientace vad pokryté**, když má místo **dva platné směry pole aspoň 60° od sebe**.
  To odpovídá ISO 17638: dva směry přibližně kolmé s odchylkou nejvýš 30°.
- **Jen část orientací:** všechny platné směry leží v rozpětí $s < 60°$. Nepokrytý zůstane pás
  orientací vad o šířce $60° - s$ podél pole. Výstup ho napíše, např. „vady ve směru −7,5° až
  +7,5° (téměř podél osy X) nepokryté – chybí pole napříč“.

### Výsledný stav místa (celkem)

1. Žádný platný směr pole, nebo nanesení či prohlídka nejde → **nepokryto** (červená)
   s důvodem. Důvodem je nejčastější chyba poloh, jejichž účinná oblast by místo zasáhla.
2. Jinak jen část orientací, nebo nanesení či prohlídka jen omezeně → **omezené** (oranžová).
3. Jinak, když rozhodla jen nejistá poloha (pól přes hranu, tečně – jádro etapy 02) nebo je
   směr pole nejasný → **nelze spolehlivě vyhodnotit** (šedá). Nejisté se nikdy nepočítá jako
   pokryté.
4. Jinak **pokryto ve všech orientacích** (zelená).

**Mapa pro jeden směr** (přepínač 0° / 45° / 90° / 135°): zelená tam, kde se vejde jho s polem
v tom směru (± 11,25°), jinak červená s důvodem. Tím je vidět rozdíl při otočení magnetizace.

## 6. Nanesení a prohlídka (převzato z PT)

MT potřebuje na místo nanést detekční prostředek (suspenzi nebo prášek) a místo prohlédnout.
Použijí se **beze změny kontroly z etapy 11**:

- **nástřik** – jde do 60° od kolmice, omezeně do 85°,
- **prohlídka** – aspoň 30° k povrchu, oko do 600 mm, volná koule Ø 50 mm.

Obojí lze v nastavení vypnout. Otření nástrojem se pro MT nepočítá (čištění po zkoušce
a odmagnetování nejsou v rozsahu).

## 7. Materiál

| Materiál modelu | Výsledek | Zdroj |
|---|---|---|
| ocel, litina | feromagnetický → MT lze počítat | ASTM E1444 / E3024 (rozsah: feromagnetické materiály) |
| nerez | **nutno potvrdit** – austenitická (např. 1.4301) feromagnetická není, feritická a martenzitická ano | ASTM E1444 / E3024 (austenitické nerezi výslovně nelze) |
| hliník, mosaz, měď, titan, PLA, PETG, ABS | MT nelze – materiál není feromagnetický | tamtéž |
| neuvedený | nutno potvrdit | – |

„Nutno potvrdit“ = mapa se nespočítá, dokud uživatel v nastavení MT nezaškrtne **Materiál je
feromagnetický (potvrzeno uživatelem)**. Potvrzení se uloží do studie a je vidět ve výstupu.
U neferomagnetického materiálu panel napíše „MT nelze použít – hliník není feromagnetický“.
Mapa se nepočítá a potvrdit to nejde.

## 8. Výchozí hodnoty a odkud jsou

| Hodnota | Výchozí | Původ |
|---|---|---|
| Nejmenší rozteč pólů | 75 mm | ISO 17638:2016, obr. 4 ($d \ge 75$) – z výňatků |
| Účinná oblast | $(d - 50) \times d/2$ | ISO 17638:2016, obr. 4 ($b \le d/2$, $b_2 \le d_2 - 50$) – z výňatků; že $b$ je šířka oblasti napříč, je náš výklad obrázku |
| Oblast u pólu se nepočítá | 25 mm | totéž; text normy: „u pólu je oblast, kterou nelze zkoušet“ |
| Úhel vady k poli | ≥ 30° | ISO 9934-1 (tok účinný do 60° od optimálního směru) |
| Dva směry | ≥ 60° od sebe | ISO 17638 (dva směry přibližně kolmé, odchylka nejvýš 30°) |
| Rozteč 100 mm, pól Ø 20, noha 60, tělo 40 × 40 + 20 | – | **zvoleno pro výpočet** |
| Mezera pod pólem 1 mm, úhel nohou 90°, spojnice 10 mm nad povrchem | – | **zvoleno** |
| Nanesení a prohlídka | jako PT | etapa 11 (prohlídka: ASME V čl. 9, BINDT CP25) |

**Neověřeno:** celý text ISO 17638 a ISO 9934-1 je placený. Hodnoty výše pocházejí z veřejných
výňatků a ze sekundárních zdrojů (viz konec). Až budeš mít normy k dispozici, opravíme je podle
nich. Zvedací síla jha (podle sekundárních zdrojů k ASME V čl. 7: střídavé jho aspoň 4,5 kg
při největší rozteči, stejnosměrné 18 kg) se ověřuje na skutečném jhu. Program ji nepočítá.

## 9. Ruční výpočty (podle nich se bude testovat)

**Pravidlo okraje (ve směru pole):** pól musí ležet celý na ploše (střed pólu aspoň 10 mm od
okraje) a účinná oblast končí 25 mm před středem pólu. Pokrytí ve směru pole proto končí
**35 mm od okraje** – stejně pro rozteč 100 i 75 mm. **Napříč** sahá pokrytí až k okraji
($d/4 \ge 10$ mm).

**Deska** (`deska.json`, nová MT studie horní plochy 200 × 100 = 20 000 mm²):

| Směr pole | Výpočet | Pokryto |
|---|---|---|
| 0° (podél X) | středy $\lvert x_c \rvert \le 100 - 50 - 10 = 40$ → $x \in \langle -65; 65 \rangle$, celá šířka | **65 %** |
| 90° (podél Y) | 100 mm se nevejde ($100 + 2 \cdot 10 > 100$); 75 mm: $\lvert y_c \rvert \le 50 - 37{,}5 - 10 = 2{,}5$ → $y \in \langle -15; 15 \rangle$ | **30 %** |
| 45°, jen rozteč 100 (záloha vypnutá) | středy $\lvert x_c \rvert \le 54{,}64$, $\lvert y_c \rvert \le 4{,}64$; sjednocení otočených čtverců 50 × 50 je osmiúhelník $4ab + 4r(a+b) + 2r^2$ ($a = 54{,}64$, $b = 4{,}64$, $r = 35{,}36$) | 11 899 mm² = **59,5 %** |

Místa (celkem):

- **(0; 0)** – pole 0° i 90° → **zelená**.
- **(0; 45)** – jen směry −22,5°, 0°, +22,5° → **oranžová**, nepokryté vady −7,5° až +7,5°
  (podél osy X).
- **(95; 0)** – jen směry 67,5°, 90°, 112,5° → **oranžová**, nepokryté vady 82,5° až 97,5°
  (podél osy Y).

**Trubka** (`trubka.json`, plášť Ø 114,3 × 300, $R = 57{,}15$):

| Směr pole | Výpočet | Pokryto |
|---|---|---|
| mezera pod pólem Ø 20 | $57{,}15 - \sqrt{57{,}15^2 - 10^2}$ = **0,88 mm** ≤ 1 (pól Ø 25 by dal 1,38 mm) | – |
| podél osy | $\lvert x_c \rvert \le 150 - 60 = 90$ → $x \in \langle -115; 115 \rangle$ | **76,7 %** |
| po obvodu, 100 mm | nohy svírají $2 \cdot 2 \arcsin(50 / 114{,}3)$ = 103,7° > 90° → nejde | – |
| po obvodu, 75 mm | nohy $2 \cdot 2 \arcsin(37{,}5 / 114{,}3)$ = 76,6° ✓ | **100 %** |

Celkem: zelená pro $\lvert x \rvert \le 115$ (76,7 %). U obou konců zůstane pás 35 mm oranžový
– „chybí pole podél osy, vady po obvodu nepokryté“.

**Kapsa** (`kapsa.json`, nová MT studie dna 40 × 30 v hloubce 25):

- Jho se do kapsy nevejde. Kružnice o poloměru 37,5 vyjde nad horní plochu za stěnou (napříč
  na $\lvert y \rvert = 27{,}9$ mm) a mezi místem a pólem je stěna.
- Výsledek: **100 % červená** – „jho se do kapsy nevejde – mezi místem a pólem je stěna“.
- Zkušební skript (rozteč 100): ve směru X „stěna“, ve směru Y „bez místa pro pól“ (kružnice
  o poloměru 50 vyjde mimo blok).

**Koutový svar** (`koutovy_svar.json`, nová MT studie obou ploch svaru):

| Případ | Výpočet | Výsledek |
|---|---|---|
| napříč svarem, střed (−8,5; 0; 13,5) | pól na základní desce $x = -8{,}5 - \sqrt{50^2 - 3{,}5^2} = -58{,}38$ ($z = 10$); pól na stojině $z = 13{,}5 + 49{,}88 = 63{,}38$ ($x = -5$); nohy 90° | jho se vejde – **změřeno skriptem přesně** (−58,38; 0; 10) a (−5; 0; 63,38) |
| podél svaru | svar je dlouhý 100 mm: rozteč 100 se nevejde; 75 mm ze základní desky a ze stojiny vedle svaru → pás $\lvert y \rvert \le 15$ | **30 % délky** |

Celkem: zelená jen u středu svaru, jinak oranžová – „jen pole napříč, příčné vady nepokryté“.

**Tupý svar** (`tupy_svar.json`, převýšení svaru): napříč jde přes převýšení (póly na desce
v $x = \pm 49{,}96$, změřeno). Podél jen pás 30 % (svar je dlouhý 100 mm), stejně jako
u koutového svaru.

**Nanesení a prohlídka:** na otevřených plochách výše 100 % (kontroly PT, ověřené v etapě 11).

Mřížka středů a síť míst čísla jen přibližují. Testy porovnávají procenta s tolerancí podle
kroku a hranice ověřují přesně v jednotlivých bodech (jako PT).

## 10. Uložení do souboru (formát 20)

MT studie dostane nepovinnou položku `mt`:

```json
"mt": {
  "step_mm": null, "center_step_mm": null,
  "spacing_mm": 100, "min_spacing_mm": 75, "pole_zone_mm": 25,
  "pole_mm": 20, "leg_mm": 60, "body_mm": 40, "body_overhang_mm": 20,
  "max_gap_mm": 1, "leg_angle_deg": 90, "step_over_mm": 10,
  "detect_deg": 30, "ferromagnetic": null,
  "apply": true, "inspect": true,
  "spray_deg": 60, "spray_limit_deg": 85,
  "view_deg": 30, "view_limit_deg": 5, "view_distance_mm": 600, "eye_mm": 50
}
```

- Chybějící hodnota = výchozí. Studie bez `mt` zůstane totožná a verze 1–19 se načtou beze
  změny.
- Změna nastavení je jeden krok Zpět a mapu zruší. Mapa sama se neukládá. Po změně dílu zmizí
  (jako mapa PT). Zastaralou studii je třeba nejdřív potvrdit.
- `mt` u jiné metody než MT = česká chyba při načtení.
- `ferromagnetic: true` = potvrzeno uživatelem. U neferomagnetického materiálu ho kontrola
  odmítne.

## 11. Okno

- Při výběru **MT studie** ukáže panel NDT místo skupin sondy skupinu **Přiložení jha a směry
  magnetizace (MT)** s povinným upozorněním MT. Kontrola materiálu je nahoře.
- **Nastavení MT…**: dialog s poli z oddílu 10. U zvolených hodnot je poznámka „zvoleno pro
  výpočet“. Čísla jsou jako text a nezměněné *OK* = žádný krok Zpět (jako PT).
- **Spočítat mapu MT** s odhadem doby, průběhem a *Zastavit* (pomocný proces jako PT).
- **Mapa ve 3D** kreslená stávajícím způsobem mapy pokrytí (žádný nový druh kreslení).
  Přepínač **Ukázat: celkem / pole 0° / 45° / 90° / 135° / nanesení / prohlídka** s legendou.
- **Klik na místo mapy** → stav, platné směry, nepokryté orientace vad a důvody.
- **Ukázat jho** (po kliknutí) a **Přiložit jho sem** s natočením. Jho se kreslí jako průhledné
  těleso, stejně jako sonda (self-test „probe“ beze změny). Obrys účinné oblasti se kreslí
  čárou, stejně jako plán dráhy. Je to jen pohled.
- **Souhrn** a **Export CSV…**. Během práce AI je skupina zamčená (jako ostatní).

## 12. Výstupy

- **CSV:**
  - povinné upozornění MT,
  - předpoklady (rozměry jha, rozteče, meze, materiál a jeho potvrzení, 8 směrů, „zvoleno
    pro výpočet“, „směr pole jen orientační“, algoritmus a verze),
  - souhrn,
  - řádek na místo: x, y, z, plocha mm², normála, stav celkem, platné směry, nepokryté
    orientace vad, nanesení, prohlídka, důvody.
- **Příkazová řádka:** `skodacad magneticka model.json --studie s1 [--roztec 100]
  [--nejmensi 75] [--krok …] [--feromagneticky] [--csv mt.csv] [--ulozit]` – vypíše souhrn
  s upozorněním MT.
- **AI asistent** nový nástroj nedostane. Pravidla (`assistant.RULES`) dostanou větu o MT:
  výsledky si nevymýšlí, „pokryto“ nevydává za dostatečné pole ani zjištění vady
  a feromagnetičnost materiálu nepotvrzuje za uživatele.

## 13. Ověření před předáním

1. **Místa pro póly:**
   - deska (± 50 mm),
   - tupý svar přes převýšení (± 49,96),
   - koutový svar přes roh: (−58,38; 0; 10) a (−5; 0; 63,38),
   - trubka: úhel nohou 103,7° / 76,6°,
   - kapsa: stěna.
2. **Deska:** 0° → 65 %, 90° → 30 %, 45° bez zálohy → 59,5 % (s tolerancí sítě). Body (0; 0)
   zelená, (0; 45) a (95; 0) oranžová se správným pásem nepokrytých orientací.
3. **Pravidlo okraje:** pokrytí ve směru pole končí 35 mm od okraje pro rozteč 100 i 75.
4. **Trubka:** podél osy 76,7 %, po obvodu jen s roztečí 75 mm, mezera 0,88 mm.
5. **Kapsa:** dno 100 % červené s důvodem „stěna“.
6. **Koutový a tupý svar:** napříč pokryto, podél 30 %, celkem oranžová „jen napříč“.
7. **Materiál:** hliník → „MT nelze použít“, nerez bez potvrzení → mapa se nespočítá,
   s potvrzením ano.
8. **Nejisté případy:** pól přes hranu nebo tečně je šedý, nikdy zelený.
9. **Formát 20:**
   - načtení verzí 1–19,
   - studie bez `mt` beze změny,
   - chybné `mt` = česká chyba,
   - změna nastavení = jeden krok Zpět.
10. **Stejný vstup = stejný výsledek** (pevná mřížka a směry): dva běhy dají totožné stavy.
11. **Rozsah:**
    - `MT_DISCLAIMER` doslova v panelu, CLI i CSV,
    - shoda s `22-vymezeni-mt.md` (`test_ndt_scope.py`),
    - zakázaná označení,
    - UT a PT výsledky beze změny (regresní testy).
12. **Okno:**
    - offscreen testy (výpočet, přepínač, klik, Ukázat jho, Přiložit jho sem, nastavení,
      Zpět, zámek AI),
    - snímek pod Xvfb,
    - GitHub Actions Windows i macOS.

    Testy krátké kvůli časovému limitu kroku *Testy* (body a malé plochy, hrubý krok).

## 14. Rychlost (změřeno 19. 10. 2026 v cloudu, zkušební skript)

| Dotaz | Doba |
|---|---|
| platné přiložení jha (2 póly jako sonda etapy 03 + tělo) | 35–77 ms |
| odmítnuté přiložení (bez místa, přesah, stěna) | 1–30 ms |
| průměr na střed × směr se zálohou 75 mm – deska 200 × 100 | 13 ms (většina poloh u okraje skončí hned) |
| totéž – koutový svar (576 poloh) | 50 ms |
| totéž – trubka (600 poloh) | 80 ms |

**Odhady doby:**

- Koutový svar (asi 200 středů × 8 směrů) ≈ **80 s**.
- Trubka s krokem 10 mm by trvala asi 11 minut. Proto se krok středů volí sám (asi 1500 poloh
  ≈ 1–2 min) a hranice se dohledají půlením.
- Nanesení a prohlídka z PT stojí asi 10–30 ms na místo.

Při implementaci se zkusí zrychlit přiložení pólu: vůle nad rovinou přiložení není pro pól
potřeba (rezerva 0), a je to nejdražší část přiložení sondy.

## 15. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **12A.1 – vymezení a jádro** | `22-vymezeni-mt.md`, `MT_DISCLAIMER`, `ndt/mt.py` (jho, místa pólů, kontroly, účinná oblast, směry, stavy, materiál, nanesení a prohlídka z PT, souhrn, CSV), MT studie v ukázkách (deska, trubka, kapsa, koutový svar), ruční výsledky do `05-referencni-dily.md` jako NEOVĚŘENO | testy 1–8, 10, 11 |
| **12A.2 – soubor, ModelSession, CLI** | formát 20 (`mt`), `ModelSession` (nastavení jako krok Zpět, mapa a jho jako pohled), pomocný proces, `skodacad magneticka`, AI pravidlo | test 9 |
| **12B – okno** | skupina MT, dialog nastavení, mapa s přepínačem, klik, Ukázat jho, Přiložit jho sem, souhrn, CSV | test 12, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 16. Co etapa 12 nebude

- intenzita a rozložení magnetického pole, sycení, rozptylová pole, vliv mezery a tvaru na
  pole, AC/DC, zvedací síla, demagnetizace,
- hroty, cívka, středový vodič, stacionární zařízení, permanentní magnet jinak než jako jho,
- detekční prostředek, osvětlení a UV-A (ISO 3059), indikátory pole (Berthold, „koláček“),
- skutečné siločáry kolem otvorů a hran – směr pole je jen orientační,
- automatický plán poloh jha s překrytím (jako plán dráhy UT) – možné později,
- sestavy, upínky, okolí dílu; RT (etapa 13),
- cokoli o zjistitelnosti vad, změna geometrie dílu (etapy 14–15).

## 17. Praktická zkouška pro autora (po 12B)

1. Otevři *NDT – referenční díly → Deska*, vyber MT studii a stiskni **Spočítat mapu MT**.
   Přepni **pole 0°** a **pole 90°**: podél X je pokryto 65 %, podél Y jen pruh uprostřed
   (30 %, a to jen s roztečí 75 mm). Tohle je rozdíl při otočení magnetizace.
2. Klikni do oranžového místa u kratší hrany: důvod musí říct, které orientace vad chybí.
   **Ukázat jho** nakreslí, proč se jho v druhém směru nevejde.
3. **Přiložit jho sem** na střed desky a otáčej po 22,5°: od 67,5° do 112,5° jho (100 mm)
   přesahuje okraj.
4. Otevři *Kapsa*: dno kapsy je červené – jho se do kapsy nevejde.
5. Otevři *Koutový svar*: napříč svarem se jho vejde přes roh, podél jen uprostřed.
6. Exportuj CSV a podívej se, že začíná povinným upozorněním MT.

## 18. K rozhodnutí

1. **Vymezení MT a povinné upozornění** v textu z oddílu 1 jako závazný dokument
   `22-vymezeni-mt.md` a konstanta `MT_DISCLAIMER` hlídaná testem. *Doporučeno: ano.* (Je to
   obdoba tvého rozhodnutí o UT a PT.)
2. **Jen jho** v této etapě; hroty, cívka a vodič později. *Doporučeno: ano.* (Jho je
   nejběžnější přenosné zařízení a plán jmenuje právě jho a póly.)
3. **Model kloubového jha** podle oddílu 2: póly Ø 20, nohy 60, tělo 40 × 40, mezera 1 mm,
   nohy nejvýš 90°, spojnice 10 mm nad povrchem. Hodnoty jsou zvolené a lze je změnit.
   *Doporučeno: ano.*
4. **Rozteč 100 mm se zálohou 75 mm** (ISO 17638: $d \ge 75$). *Doporučeno: ano.* (Bez zálohy
   by úzké díly 100 mm vyšly celé červené, i když menší rozteč jde.)
5. **Účinná oblast $(d - 50) \times d/2$** podle obr. 4 ISO 17638 (z výňatků), směr pole jen
   orientačně jako přímka mezi póly. *Doporučeno: ano.* Až budeš mít plný text ISO 17638,
   oblast podle něj opravíme.
6. **Směrové pokrytí:** 8 směrů po 22,5°, „všechny orientace“ = dva směry aspoň 60° od sebe
   (ISO 9934-1, ISO 17638), mapa pro každý směr. *Doporučeno: ano.*
7. **Nanesení a prohlídka převzaté z PT** (stejné meze, lze vypnout). *Doporučeno: ano.*
8. **Kontrola materiálu:** ocel a litina ano, nerez a neuvedený jen s potvrzením, ostatní ne.
   *Doporučeno: ano.*
9. **Nastavení MT ve studii** (formát 20), výsledek mapy se neukládá. *Doporučeno: ano.*
10. **Okno** (mapa, přepínač směrů, klik, Ukázat jho, Přiložit jho sem s otočením), **CSV**
    a **`skodacad magneticka`**, MT studie v ukázkách (deska, trubka, kapsa, koutový svar),
    AI bez nového nástroje. *Doporučeno: ano.*

Schválením se **neschvaluje**:

- výpočet magnetického pole ani jeho intenzity,
- hroty, cívka ani vodič,
- automatický plán poloh jha,
- RT,
- nová knihovna Pythonu,
- sloučení do `main`.

## 19. Provedení a upřesnění

- **12A.1 (hotovo):** závazné vymezení [`22-vymezeni-mt.md`](22-vymezeni-mt.md),
  `ndt.MT_DISCLAIMER`, `MT_ACCESS`, `MT_MAP` (test `test_ndt_scope.py` hlídá doslovné znění
  a zakázaná označení „mapa magnetického pole“, „mapa intenzity pole“). Jádro `ndt/mt.py`:
  - `MtSettings` (kontrola hodnot česky, `pt_settings` pro nanesení a prohlídku),
  - `material_status` (ocel a litina ano, nerez a neuvedený jen s potvrzením, ostatní ne),
  - `Yoker` (místa pólů, stěna, dosednutí pólu stejným výpočtem jako přímá sonda, úhel nohou,
    přesná kolize nohou a těla) a `place_yoke` (jho s tvary a obrysem účinné oblasti pro okno),
  - `compute` / `estimate` / `check_points`, `MtMap` (souhrn, CSV, síť pro přepínač celkem /
    pole 0°, 45°, 90°, 135° / nanesení / prohlídka, `nearest`, `describe`), `study_faces`,
    `self_check` (self-test aplikace).

  Nanesení a prohlídka jsou kontroly PT (`pt.Sampler.access`, výsledky PT beze změny).
  Přiložení sondy dostalo volbu bez výpočtu vůle (`devices.place(measure_clearance=False)`),
  pól jha ji nepotřebuje. MT studie jsou v ukázkách deska (s2), trubka (s2), kapsa (s3)
  a koutový svar (s2); ruční výsledky jsou v `05-referencni-dily.md` jako NEOVĚŘENO.
- **Upřesnění proti návrhu:**
  - **Noha jha:** botka pólu (15 mm) přiléhá ke své ploše, zbytek nohy vede ve směru osy jha
    (půlí úhel mezi normálami pod póly). Kdyby obě nohy stály kolmo ke svým plochám, u rohu
    90° by se překřížily. Úhel mezi nohami se počítá stejně (úhel mezi normálami).
  - **Účinná oblast jen na ploše natočené do 60°** (návrh: do 90°). Jinak jho postavené na
    boční ploše desky „pokrylo“ i horní plochu kolem hrany: deska, pole 0°, vyšlo 70,3 % místo
    65 %. Koutový svar (45°) zůstává pokrytý z obou plechů.
  - **Místo mimo rovinu středu jha nejvýš 45° pod ní nebo nad ní.** Jinak jho stojící na horní
    ploše vedle kapsy „pokrylo“ dno kapsy 25 mm pod sebou. Převýšení svaru a koutový svar
    tím neprojdou o nic hůř.
  - **Místo mimo rovinu (víc než 2 mm) musí patřit k materiálu pod jhem** (12A.2, místo
    původního „musí být vidět“): pod rovinou se počítá, když spojnice se středem jha vede
    materiálem (vypouklá trubka). Nad rovinou se počítá, když je pod místem materiál až
    k rovině jha (koutový svar, převýšení) a místo je vidět. Automatická mapa kapsy totiž
    našla jho stojící na horní ploše 7,9 mm od kapsy, jehož oblast podle pravidla 45°
    zasáhla dno (26 % dna „jen část orientací“). Ručně je dno nepokryté a s novým pravidlem
    vyjde 0 %. Pravidlo jen spojnicí by zase ubralo koutový svar podél svaru (27 % → 11 %),
    protože svar leží na pásnici nad rovinou jha.
  - **Dohledání hranic:** mezi platným a neplatným uzlem mřížky se půlí na 0,5 mm a z nalezeného
    bodu se zkusí i kolmý směr (rohy oblasti platných středů). Dohledání se vynechá, když by
    žádné místo nezískalo nový směr.
  - **Mřížka středů může pokrytí jen podhodnotit**, každá započtená poloha jha je skutečně
    ověřená. U šikmých směrů zůstává zubatý okraj do poloviny kroku středů: deska, pole 45°,
    krok 10 mm → 56,4 %, krok 5 mm → 57,6 %, ručně 59,5 %. Pruh platných poloh užší než krok
    středů se může minout: deska, pole 90° s krokem 20 mm → 0 %, s krokem 25 mm (uzel na ose
    desky) → 30 %. Krok středů proto jde v nastavení zadat.
  - **Šikmé směry dávají druhý směr pole:** u koutového svaru dlouhého 100 mm vychází celkem
    zelená i mimo střed. Jho šikmo na stojině dá pole 73,5° nebo 106,5°, i když pole přesně
    podél svaru jde jen uprostřed. Rozdíl ukáže mapa pro směr 90°. U tupého svaru zůstane
    u konce (y = 45) oranžový jen úzký pás nepokrytých orientací −3,5° až 3,5° (příčné vady).
    Návrh tu odhadoval oranžovou šířeji.
- **Změřeno 19. 10. 2026** (cloud, síť 5 mm, krok středů 10 mm, jen zkoumaný směr):
  - deska, pole 0° → **65,23 %** (ručně 65 %), pole 90° → **29,69 %** (ručně 30 %);
  - body přesně podle oddílu 9: (0; 45) −7,5° až 7,5°, (95; 0) 82,5° až 97,5°;
  - trubka: podél osy jde v x = 114, ne v x = 116 (ručně 115), po obvodu 100 mm nohy 104°,
    75 mm nohy 77°;
  - koutový svar: póly přesně (−58,38; 0; 10) a (−5; 0; 63,38);
  - kapsa: dno nepokryté, důvod stěna.

  Rychlost:
  - platné přiložení jha 25–80 ms,
  - celá mapa desky (8 směrů, automatický krok) asi 1,5 min,
  - 5 bodů desky se všemi směry asi 28 s.
- **12A.2 (hotovo):** nastavení `mt` ve studii (**formát 20**; jen MT studie, změna metody ho
  smaže, `set_ndt_mt_settings` = jeden krok Zpět), `ModelSession`:
  - mapa jen jako pohled (`compute_ndt_mt`, `start_ndt_mt`, `ndt_mt_map`, `ndt_mt_mesh`,
    `ndt_mt_describe`, `export_ndt_mt`), zastaralou studii je třeba potvrdit; materiál je
    v otisku receptu, takže po jeho změně je studie zastaralá,
  - jho jako pohled (`place_ndt_yoke` = Přiložit jho sem, `ndt_mt_yoke_at` = Ukázat jho
    pro místo mapy, `ndt_yoke_drawing` pro prohlížeč).

  Dál: pomocný proces (`worker.submit_mt`, průběh, *Zastavit*), příkazová řádka
  `skodacad magneticka` (souhrn, CSV, `--ulozit`), `skodacad build` vypíše u MT studií
  `MT_DISCLAIMER`, pravidlo pro AI v `assistant.RULES`, README (formát 20, `mt`).

  Zrychlení přiložení: napřed místa a stěna obou pólů, pak rychlá kontrola přesahu
  (4 paprsky), úhel nohou, přesné dosednutí pólu (paměť podle místa – sousední středy
  sdílí místo pólu) a průnik nohou a těla.
- **12B (hotovo):** v panelu NDT u MT studie skupina *Přiložení jha a směry magnetizace*:
  - nahoře `MT_DISCLAIMER`, stav materiálu, zvolené hodnoty,
  - *Nastavení MT…* (`gui/mt_dialog.py`, jeden krok Zpět, nezměněné *OK* nic nemění),
  - odhad, *Spočítat mapu MT* na pozadí s průběhem, *Zastavit*, *Skrýt mapu*, *Export CSV…*,
  - přepínač mapy (celkem, pole 0°, 45°, 90°, 135°, nanesení, prohlídka) s legendou,
  - souhrn, klik do mapy (stav, směry, nepokryté orientace, důvody),
  - *Ukázat jho*, *Přiložit jho sem* s natočením, *Skrýt jho*.

  Jho se kreslí jako průhledná sonda v barvě stavu s obrysem účinné oblasti. Položky jsou
  i v nabídce NDT a během práce AI jsou zamčené. Snímky okna jsou z Xvfb v cloudu; ruční
  zkouška autorem zatím neproběhla.
- **Automatické mapy referenčních dílů** (19. 10. 2026, cloud, výchozí nastavení včetně
  nanesení a prohlídky, automatický krok sítě i středů):
  - deska (1 056 míst, středy 10 mm): celkem 52,7 % pokryto, pole 0° 65,6 % (ručně 65 %),
    pole 90° 29,3 % (ručně 30 %), asi 1 min (dřív 3 min),
  - trubka (1 404 míst): celkem 88,5 %, podél osy 75 % (ručně 76,7 %), 2,3 min,
  - kapsa (dno, 1 024 míst): 0 %, všude důvod stěna (ručně nepokryto), 1,3 min,
  - koutový svar (984 míst): celkem 100 %, pole podél svaru 27,2 % (ručně 30 %, mřížka
    středů podhodnocuje), 1,8 min.

  Odhad doby před spuštěním vychází o 10–50 % vyšší než skutečnost.

## Zdroje (ověřeno vyhledáním 19. 10. 2026; plné texty norem jsou placené)

- ISO 17638:2016 *Non-destructive testing of welds – Magnetic particle testing*:
  - veřejné výňatky [SSAB WeldCalc](https://weldcalc.ssab.com/sisStandards/ISO%2017638.pdf)
    a [iTeh](https://cdn.standards.iteh.ai/samples/67261/f2df11b7ba0e41d6aa9ff89cc310dd95/ISO-17638-2016.pdf),
  - kopie [BS EN ISO 17638:2016](https://www.narsei.com/wp-content/uploads/2023/12/BS-EN-ISO-17638-%EF%BC%9A2016-Non-destructive-testing-of-welds-%E2%80%94-Magnetic-particle-testing.pdf),
  - starší vydání [ISO 17638:2003](https://cdn.standards.iteh.ai/samples/29972/ef435cae24554f11971c8ea14011591b/ISO-17638-2003.pdf).

  Z nich: obr. 4 ($d \ge 75$, $b \le d/2$, $b_2 \le d_2 - 50$, $\beta \approx 90°$), dva směry
  magnetizace s odchylkou nejvýš 30°, u pólů oblast, kterou nelze zkoušet. Text obrázku je
  z převodu PDF porušený – ověřit v normě.
- ISO 9934-1 *Magnetic particle testing – General principles*, výňatek
  [iTeh](https://cdn.standards.iteh.ai/samples/57715/7462835df955404493d4117055390280/ISO-9934-1-2015.pdf):
  tok je účinný pro vady odkloněné do 60° od optimálního směru; plné pokrytí dvěma kolmými
  směry.
- ASTM E1444 ([GlobalSpec](https://datasheets.globalspec.com/ds/astm-international/astm-e1444-05/dfc05bf2-6f01-4a5b-a727-cbd9dfd50990))
  a ASTM E3024 ([Nimonik](https://standards.nimonik.com/products/astm/e3024-e3024m/)):
  MT nelze použít pro neferomagnetické kovy a slitiny, jako jsou austenitické nerezové oceli.
- Sekundární zdroje jen pro informaci:
  - ASME V čl. 7 – zvedací síla jha
    ([open-exam-prep](https://open-exam-prep.com/study-guides/api-570/nondestructive-examination/visual-penetrant-magnetic-testing)),
  - rozpětí nohou běžného jha 50–280 mm
    ([Magnaflux Y6](https://magnaflux.com/EU-Files/Product-Data-Sheets/Equipment--Accessories/Y6-Yoke-PDS-630405.pdf)).
