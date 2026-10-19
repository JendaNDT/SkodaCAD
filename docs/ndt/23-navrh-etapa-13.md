# NDT – návrh etapy 13: RT – geometrie projekce a expozice

Stav: **schváleno autorem 19. 10. 2026 („schvaluji etapu 13 včetně doporučení 1–10“);
implementace po krocích ve vývojové větvi.**
Výchozí stav: `main`, commit `5cb6ef4` ([PR #26](https://github.com/JendaNDT/SkodaCAD/pull/26)).
Navazuje na [plán, etapa 13](03-implementacni-plan.md), [geometrické jádro (etapa 02)](06-navrh-etapa-02.md),
[virtuální sondu (etapa 03)](07-navrh-etapa-03.md), [svar a cílový objem (etapa 07)](12-navrh-etapa-07.md),
[MT (etapa 12)](21-navrh-etapa-12.md), [referenční díly](05-referencni-dily.md) a
[závazné vymezení UT](04-zavazne-vymezeni-ut.md).

Vymezení UT v bodě 4 říká, že rozsah PT, MT a RT „podléhá vlastním návrhům a ověřování“.
Návrh proto obsahuje i **navržené vymezení RT** (oddíl 1), stejně jako návrhy etap 11 a 12.
Etapa 13 **dokončí milník M4 – všechny čtyři metody v geometrické úrovni** (etapy 11–13).

Zadání z plánu:

- **Úkoly:** *„Zdroj, aktivní ohnisko, směr svazku a detektor/film s kolizemi; průchod paprsků
  materiálem, geometrické zvětšení, potenciální překryvy a geometrickou neostrost z rozměru
  ohniska. Naplánovat několik projekcí, zkontrolovat, zda se oblast promítne na detektor.
  Dávku, expoziční parametry, IQI a skutečnou citlivost nedopočítávat bez validovaných
  modelů.“*
- **Výstup:** *„RT geometrická simulace s náhledem projekce a upozorněními.“*
- **Podmínka dokončení:** *„Jednoduchá stěna/otvor správně mění projektovanou tloušťku a obraz
  při změně úhlu.“*

## Co tato etapa přinese

**Dnes:**

- RT studii jde založit (metoda „radiografická“, oblast = plochy nebo cílový objem svaru)
  a uložit do modelu. **Nic se pro ni ale nepočítá** – panel NDT ukáže jen obecné upozornění
  a stav studie.

**Po etapě 13:**

1. U RT studie bude v panelu NDT skupina **Geometrie projekce RT**. Jedna **projekce** = jedna
   expozice:
   - **zdroj**: ohnisko o rozměru $d$, kužel svazku a zjednodušené tělo zdroje, v zadané
     vzdálenosti a směru,
   - **detektor**: film v kazetě nebo digitální panel, výchozí film 10 × 24 cm.

   Tlačítko **Zdroj nad vybrané místo**: klikneš na plochu (např. převýšení svaru) a zdroj se
   postaví kolmo nad ni do vzdálenosti 500 mm. Sklon a natočení jde změnit. Detektor se sám
   přiloží na plochu, kudy střední paprsek z dílu vystupuje.
2. Program zkontroluje, že se **zdroj ani detektor nesrazí s dílem**. Pro každé místo oblasti
   (plochy studie nebo objem svaru) pak zjistí:
   - jestli leží **ve svazku** a jestli se **promítne na detektor**,
   - **prozařovanou tloušťku** – kolik milimetrů materiálu projde přímý paprsek z ohniska přes
     místo na detektor,
   - **poměr tloušťky** vůči střednímu paprsku (ISO 17636-1: nejvýš 1,1 pro třídu B, 1,2 pro
     třídu A),
   - **geometrické zvětšení** a **geometrickou neostrost** z rozměru ohniska,
   - jestli se jeho obraz **nepřekrývá** s jinou částí oblasti (např. s protější stěnou
     obvodového svaru).

   Pro celou projekci porovná vzdálenost zdroje s **nejmenší vzdáleností podle ISO 17636-1**
   pro zvolenou třídu.
3. **Mapa ve 3D** na oblasti ve čtyřech barvách:
   - **zelená** – promítne se na detektor a geometrická pravidla normy platí,
   - **oranžová** – promítne se, ale nevyhoví poměr tloušťky nebo vzdálenost zdroje, nebo se
     obraz překrývá,
   - **červená** – mimo svazek, mimo detektor, nebo zdroj či detektor naráží do dílu,
   - **šedá** – nelze spolehlivě vyhodnotit (paprsek přes hranu nebo tečně).

   Mapa jde ukázat **celkem za všechny projekce** i pro **vybranou projekci**.
4. **Náhled projekce** – obraz **prozařované tloušťky** na detektoru: světlejší = víc materiálu
   (jako na filmu), s tečkami promítnuté oblasti. Ukáže se ve 3D přímo na detektoru i jako
   obrázek v panelu (jde uložit jako PNG). Je to jen geometrie – **ne radiografický snímek**.
   Při změně úhlu je vidět, jak se mění tloušťka a obraz otvoru (podmínka dokončení z plánu).
5. **Několik projekcí**: přidat, upravit, zkopírovat posunutou (další film podél svaru),
   smazat. Mapa celkem ukáže, co pokryje aspoň jedna projekce a kolik projekcí každé místo
   pokrylo.
6. **Klik na místo** napíše česky stav v každé projekci a důvody, např. „P1: mimo detektor
   o 12 mm; P2: poměr tloušťky 1,14 > 1,1 (třída B)“. K tomu **souhrn**, **CSV** s povinným
   upozorněním RT a příkaz **`skodacad radiografie`**.
7. Nastavení i projekce se **uloží do studie** (formát **21**). Výsledky (mapa, náhled) se
   neukládají – vždy se spočítají znovu.

**Co se nemění:** UT, PT a MT (výpočty, výsledky, upozornění), výrobní geometrie, mapa
tloušťky. RT nikdy nemění díl.

## 1. Rozsah a hranice – navržené vymezení RT (k potvrzení)

Po schválení vznikne samostatný závazný dokument `docs/ndt/24-vymezeni-rt.md` se stejnou
stavbou jako vymezení UT, PT a MT. Obsah:

**Co RT modul SMÍ vyhodnocovat:** jen **geometrii projekce**:

- kam lze umístit zjednodušený model zdroje a detektoru (kolize s dílem),
- kudy vedou přímé paprsky z ohniska dílem na detektor a jakou tloušťku materiálu prozařují,
- kam se oblast promítne na detektor (ve svazku, na aktivní ploše, překryvy obrazů),
- geometrické zvětšení a geometrickou neostrost z rozměru ohniska,
- geometrická pravidla normy: poměr prozařovaných tlouštěk a nejmenší vzdálenost zdroje od
  předmětu.

**Co RT modul NESMÍ tvrdit, že vyhodnocuje:**

- **Záření a bezpečnost:** dávku, dávkový příkon, radiační ochranu, kontrolované pásmo, stínění
  ani bezpečné vzdálenosti. **Geometrie projekce nenahrazuje posouzení radiační ochrany.**
- **Expozici:** napětí, proud, dobu expozice, aktivitu zdroje, energii záření ani to, zda zdroj
  danou tloušťku vůbec prozáří.
- **Obraz:** rozptýlené záření, zesilující fólie, kontrast, optickou hustotu (zčernání), šum,
  vlastní neostrost a rozlišení detektoru (ISO 17636-2) ani třídu kvality obrazu nad rámec
  geometrických pravidel.
- **Detekovatelnost vad:** viditelnost indikátorů kvality obrazu (IQI, ISO 19232), citlivost
  zkoušky, velikost nebo druh zjistitelné vady ani způsobilost kontroly podle normy.

„Promítne se“ **není** důkaz, že by vada byla na snímku vidět.

**Povinné upozornění** (konstanta `ndt.RT_DISCLAIMER`, doslova v okně, CLI i CSV):

> ŠkodaCAD provádí pouze geometrické posouzení radiografické zkoušky: kam lze umístit zjednodušený model zdroje a detektoru, kudy vedou přímé paprsky z ohniska dílem, jakou tloušťku materiálu prozařují, kam se oblast promítne na detektor a jaké je geometrické zvětšení a geometrická neostrost z rozměru ohniska. Nevyhodnocuje dávku ani radiační ochranu, expoziční parametry, rozptýlené záření, kontrast, zčernání ani kvalitu obrazu, viditelnost indikátorů kvality obrazu, citlivost zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup, odborné posouzení ani posouzení radiační ochrany.

**Názvy v okně a protokolech:**

- „Geometrie projekce RT“ (`RT_ACCESS`),
- „Mapa geometrického promítnutí oblasti RT“ (`RT_MAP`),
- „Náhled prozařované tloušťky – není radiografický snímek“ (`RT_PREVIEW`).

Test `tests/test_ndt_scope.py` bude hlídat doslovné znění proti dokumentu a zakázaná
označení stejně jako u UT, PT a MT: „simulovaný radiogram“, „simulovaný snímek“, „mapa
dávky“, „mapa zčernání“.

**Další hranice etapy:**

- **Bodový zdroj s ohniskem** – směrová i panoramatická rentgenka a gama zdroj mají stejnou
  geometrii. Panoramatický zdroj = kužel 360°.
- **Plochý tuhý detektor** (film v rovné kazetě, digitální panel). Ohebný film obtočený kolem
  trubky se zatím nemodeluje.
- **Jen díl jako jedno těleso.** Sestavy, upínky a okolí se nemodelují.
- **Oblast** = plochy RT studie nebo cílový objem svaru (etapa 07).
- **Projekce zadává uživatel.** Automatický návrh počtu a poloh projekcí (příloha A
  ISO 17636-1 pro obvodové svary, eliptická technika) bude později.

## 2. Virtuální zdroj a detektor

| Část | Výchozí | Původ |
|---|---|---|
| Rozměr ohniska $d$ | **3 mm** | **zvoleno pro výpočet**; skutečný rozměr podle EN 12543 (rentgen) / EN 12679 (gama), u dvou rozměrů větší (ISO 5579) |
| Kužel svazku (vrcholový úhel) | **40°** | **zvoleno**; 360° = panoramatický zdroj |
| Tělo zdroje | válec **Ø 120 × 300 mm** za ohniskem v ose svazku | **zvoleno**; Ø 0 = jen bod (např. gama zdroj v trubce) |
| Vzdálenost zdroj–předmět $f$ | **500 mm** | **zvoleno**; panel vedle ukáže nejmenší vzdálenost podle ISO 17636-1 |
| Detektor (aktivní plocha) | **100 × 240 mm** | běžný formát filmu 10 × 24 cm (např. Foma INDUX) |
| Tloušťka kazety nebo panelu | **2 mm** | **zvoleno** (jen pro kontrolu kolize) |
| Třída zkoušky | **B** | ISO 17636-1 (A základní, B zlepšená) |
| Krok náhledu na detektoru | **2 mm** | **zvoleno** |

Zvolené hodnoty jsou v okně i ve výstupu označené „zvoleno pro výpočet, ne z normy“, stejně
jako sonda UT, nástroje PT a jho MT. Uživatel je přepíše podle svého zařízení.

## 3. Projekce – jak se počítá

**Zadání projekce:**

- **zaměřený bod $A$** – místo na straně zdroje, obvykle střed svaru (kliknutím, nebo číselně),
- **směr ke zdroji $u$** – výchozí kolmo k ploše v $A$; sklon od kolmice a natočení se zadávají
  stejně jako úhel sondy UT (0° = průmět osy +X do plochy),
- **vzdálenost $f$**.

Zdroj je v bodě $S = A + f\,u$. **Střední paprsek** vede ze $S$ přes $A$ dál dílem.

1. **Detektor na ploše (výchozí):** kde střední paprsek z dílu naposledy vystoupí, přiloží se
   detektor do tečné roviny té plochy (jako sonda v etapě 03). Střed detektoru leží na
   paprsku, delší strana je natočená zadaným úhlem. Když deska detektoru do dílu narazí
   (např. vyčnívá kořen svaru), odsune se kolmo od plochy, až nenarazí, a mezera prodlouží
   vzdálenost $b$. Přesah detektoru přes okraj dílu nevadí – film může přečnívat.
2. **Detektor volně:** kolmo ke střednímu paprsku ve zvolené vzdálenosti od zdroje.
3. **Kolize:** tělo zdroje i deska detektoru se přesně zkontrolují průnikem s dílem, jako
   sonda. Dotyk není kolize. Při kolizi je projekce neplatná a všechna místa jsou červená
   s důvodem, např. „tělo zdroje naráží do dílu (průnik 1 200 mm³)“.
4. **Vzdálenosti podle normy:**
   - $f$ = od zdroje po místo, kde střední paprsek vstoupí do dílu,
   - $b$ = od tohoto místa po detektor, po středním paprsku (ISO 17636-1 měří vzdálenost
     předmět–film od strany předmětu u zdroje).

   **Nejmenší vzdálenost zdroje** (ISO 17636-1, ISO 5579):

   $$f_{min} = k \cdot d \cdot b^{2/3}, \qquad k = 7{,}5 \text{ (třída A)}, \quad k = 15 \text{ (třída B)}$$

   Když $b < 1{,}2\,t$, dosadí se místo $b$ jmenovitá tloušťka $t$ (ISO 5579). Za $t$ se bere
   prozařovaná tloušťka středního paprsku $w_0$ (nebo ručně zadaná jmenovitá tloušťka).
   Když $f < f_{min}$, jsou všechna místa projekce nejvýš oranžová.

   Informativně se vypíše **geometrická neostrost** projekce $U_g = d \cdot b / f$
   a **zvětšení** $M = (f + b) / f$.

**Pro každé místo $P$ oblasti** se vede paprsek ze $S$ přes $P$ až na rovinu detektoru:

1. **Svazek:** úhel paprsku od středního paprsku je nejvýš polovina kuželu. Jinak „mimo
   svazek“.
2. **Detektor:** průsečík s rovinou detektoru musí ležet na aktivní ploše. Jinak „mimo
   detektor o … mm“.
3. **Prozařovaná tloušťka $w$:** součet všech úseků v materiálu na celé spojnici zdroj–detektor
   (jádro etapy 02). Úseky podél povrchu nebo přes hranu se započtou, paprsek se ale označí
   jako nejistý.
4. **Poměr tloušťky** $w / w_0$, kde $w_0$ = prozařovaná tloušťka středního paprsku. Podle
   normy smí být poměr na okraji vyhodnocované oblasti k tloušťce na středu svazku nejvýš
   **1,1 (třída B)** a **1,2 (třída A)**. Poměr pod 1 (místo tenčí než střed, např. vedle
   převýšení svaru) nevadí.
   - Když střední paprsek míří do otvoru ($w_0 = 0$), jde přes hranu, nebo je výrazně tenčí
     než oblast ($w_0 < 0{,}8 \times$ medián $w$ míst oblasti), poměr se nepočítá. Místa jsou
     pak šedá s důvodem „střední paprsek nemíří do plného materiálu – zamiř ho do oblasti
     nebo zadej jmenovitou tloušťku“. Jmenovitou tloušťku jde u projekce zadat ručně.
5. **Zvětšení a neostrost místa:** $M_P = (a + b_P) / a$ a $U_{g,P} = d \cdot b_P / a$, kde
   $a$ = vzdálenost zdroje od $P$ a $b_P$ = vzdálenost od $P$ po detektor. Ukáže se v mapě
   „neostrost“, jen informativně – pravidlo normy platí pro celou projekci (bod 4 výše).
6. **Překryv obrazů:** když paprsek projde oblastí ještě na jiném místě (obě stěny
   obvodového svaru, dva svary nad sebou), obrazy se na detektoru překrývají → oranžově
   s důvodem.
7. **Nejistý paprsek** (přes hranu, tečně) → šedá. Nejisté místo se nikdy nepočítá jako
   pokryté.

**Stav místa v jedné projekci:**

1. **červená** – projekce neplatná (kolize), místo mimo svazek nebo mimo detektor,
2. **šedá** – nejistý paprsek nebo poměr tloušťky nelze určit,
3. **oranžová** – promítne se, ale poměr tloušťky je nad mezí, zdroj je blíž než $f_{min}$
   nebo se obraz překrývá,
4. **zelená** – jinak.

**Celkem za projekce:** zelená, když místo pokryje zeleně aspoň jedna projekce; jinak
oranžová, když aspoň jedna oranžově; jinak šedá, když aspoň jedna šedě; jinak červená.
Ke každému místu se uvede, kolik projekcí ho pokrylo zeleně.

## 4. Náhled prozařované tloušťky

- Mřížka na aktivní ploše detektoru s krokem 2 mm: film 10 × 24 cm = 6 000 paprsků.
- Barvy:
  - **šedá škála** od 0 mm (černá) po největší tloušťku (bílá) – světlejší = víc materiálu,
    jako na filmu,
  - **mimo svazek** tmavě modře,
  - **nejistý paprsek** fialově.
- Promítnutá místa oblasti se v obrázku ukážou jako tečky v barvě stavu.
- Náhled se kreslí ve 3D na desce detektoru (stávající kresba mapy) a v panelu jako obrázek
  s měřítkem v mm. Tlačítko **Uložit náhled PNG…**.
- Popisek je vždy „Náhled prozařované tloušťky – není radiografický snímek“.

## 5. Materiál

Prozařovaná tloušťka je v milimetrech materiálu dílu (ocel, hliník …). Zda ji konkrétní zdroj
prozáří, se nepočítá (oddíl 1). Výstup uvede materiál z modelu. Kontrola materiálu jako u MT
tu není potřeba – RT jde na každý materiál.

## 6. Výchozí hodnoty a odkud jsou

| Hodnota | Výchozí | Původ |
|---|---|---|
| Poměr prozařovaných tlouštěk okraj / střed svazku | nejvýš 1,1 (B), 1,2 (A) | ISO 17636-1:2022 i 2013 – z výňatků |
| Nejmenší vzdálenost zdroje | $f_{min} = 7{,}5 / 15 \cdot d \cdot b^{2/3}$ (A / B) | ISO 5579:2013 – z výňatku; ISO 17636-1 stejně podle sekundárních zdrojů (postup Sulzer, článek BAM) |
| $b < 1{,}2\,t$ → dosadit $t$ | – | ISO 5579:2013 – z výňatku |
| $b$ od strany předmětu u zdroje po film, po středním paprsku | – | ISO 17636-1:2022, definice – z výňatku |
| Rozměr ohniska | větší z rozměrů podle EN 12543 / EN 12679 | ISO 5579:2013 – z výňatku |
| Film 10 × 24 cm | 100 × 240 mm | běžný formát (Foma INDUX: 10 × 24, 10 × 48, 30 × 40 cm) |
| Ohnisko 3 mm, kužel 40°, tělo zdroje Ø 120 × 300, $f$ = 500 mm, kazeta 2 mm, krok 2 mm | – | **zvoleno pro výpočet** |

**Jen pro informaci (nepočítá se):**

- ASME V čl. 2, T-274.2 uvádí meze geometrické neostrosti 0,51 / 0,76 / 1,02 / 1,78 mm podle
  tloušťky (ze sekundárního zdroje).
- ISO 17636-2 (digitální detektory) má upravený vzorec s vlastní neostrostí detektoru.
  V této etapě se počítá vzorec pro film a výstup to napíše.

**Neověřeno:** plné texty ISO 17636-1 a ISO 5579 jsou placené. Hodnoty výše pocházejí
z veřejných výňatků a sekundárních zdrojů (viz konec). Až budeš mít normy k dispozici,
opravíme je podle nich.

## 7. Ruční výpočty (podle nich se bude testovat)

Všude ohnisko $d$ = 3 mm, detektor 100 × 240 mm.

**Deska s otvorem** (`otvor.json`: 200 × 100 × 20, otvor Ø 20 uprostřed; nová RT studie horní
plochy). Zdroj nad středem otvoru, $f$ = 500 (zdroj v $z$ = 520), detektor na spodní ploše
($z$ = 0), delší strana podél X. Jmenovitá tloušťka je zadaná ručně 20 mm, protože střední
paprsek míří do otvoru.

| Případ | Výpočet | Hodnota |
|---|---|---|
| plech pod zdrojem | $t$ | **20 mm** |
| okraj desky $x$ = 100 | $20 / \cos(\arctan(100/520))$ | **20,37 mm** (poměr 1,018) |
| otvor kolmo – průhledná část | rozhoduje dolní hrana otvoru (paprsky se rozbíhají) | $x \in \langle -10; 10 \rangle$ |
| zdroj sklopený o 30° k +X, $S$ = (250; 0; 453,0) – průhledná část | horní hrana: $x(1 - 20/453{,}0) + 250 \cdot 20/453{,}0 \le 10$, dolní: $\lvert x \rvert \le 10$ | $x \in \langle -10; -1{,}09 \rangle$ = **8,91 mm** (rovnoběžný svazek by dal $20 - 20 \operatorname{tg} 30°$ = 8,45 mm) |
| plech při sklonu 30°, $x$ = 60 | $20 / \cos(\arctan(190/453{,}0))$ | **21,69 mm** |
| místa horní plochy na filmu | $\lvert y \rvert \le 50 \cdot 500/520$ = 48,08 mm | **96,1 %** zeleně; pruhy u delších hran (3,9 %) mimo detektor |
| nejmenší vzdálenost ($b = t$ = 20) | $7{,}5 \cdot 3 \cdot 20^{2/3}$ / $15 \cdot 3 \cdot 20^{2/3}$ | A **165,8 mm**, B **331,6 mm** → $f$ = 500 vyhoví |
| neostrost, zvětšení | $3 \cdot 20/500$; $520/500$ | **0,12 mm**; **1,04** |

**Zkoušeno skriptem 19. 10. 2026:** kolmo průhledné ±10,00 mm, při sklonu 30° ⟨−10,00;
−1,09⟩, plech 21,688 mm (ručně 21,688). Zkouška zároveň ukázala, že paprsek souběžný se
stěnou otvoru označí jádro jako nejistý a do „délky v materiálu“ ho nezapočte – bez toho vyšla
průhledná část o 0,4 mm širší a při sklonu se nezúžila. Prozařovaná tloušťka proto sčítá
všechny úseky a nejistotu jen vyznačí.

**Tupý svar V** (`cilove_objemy/tupy_svar_objem.json`: plechy 12 mm, převýšení 2, kořen 1,
svar délky 100 mm podél Y; nová RT studie s cílem = objem svaru). Zdroj kolmo nad středem
převýšení, $A$ = (0; 0; 14), $f$ = 500. Střední paprsek vystoupí kořenem v $z$ = −1, tam se
přiloží detektor, delší strana podél svaru (natočení 90°).

| Případ | Výpočet | Hodnota |
|---|---|---|
| střed svaru (převýšení + plech + kořen) | 2 + 12 + 1 | **15 mm** = $w_0$ |
| $x$ = 3 / 6 / 20 mm | skript | 14,03 / 14,00 / 12,01 mm – poměr pod 1 nevadí |
| konec svaru $y$ = 50 | $15 / \cos(\arctan(50/515))$ | **15,07 mm**, poměr 1,005 |
| svar na detektoru | ±50 mm podél, ±10 mm napříč, × 1,03 | celý svar na filmu → **100 % zeleně** |
| nejmenší vzdálenost ($b$ = 15 ≥ 1,2 · 12) | $7{,}5 \cdot 3 \cdot 15^{2/3}$ / $15 \cdot 3 \cdot 15^{2/3}$ | A **136,8 mm**, B **273,7 mm** → při $f$ = 250 třída B oranžově, A zeleně |
| neostrost, zvětšení | $3 \cdot 15/500$; $515/500$ | **0,09 mm**; **1,03** |

**Trubka přes dvě stěny** (`trubka.json`: Ø 114,3 × 6, $R$ = 57,15, $r$ = 51,15; jen v testech
jádra, bez nové ukázkové studie). Zdroj nad osou, detektor dole tečně, delší strana napříč
osou.

| Případ | Výpočet | Hodnota |
|---|---|---|
| střední paprsek | 2 × 6 | **12 mm**, 2 úseky materiálu |
| hranice poměru 1,1 / 1,2 (rovnoběžný svazek) | $(\sqrt{R^2 - x^2} - \sqrt{r^2 - x^2}) / (R - r) = k$ | $x$ = **±22,52 / ±29,87 mm** (oblouk ±23,2° / ±31,5°) |
| totéž přesně ze zdroje, $f$ = 500, na detektoru | skript; zvětšení $(f + 2R)/(f + R)$ = 1,10 | **±24,85 / ±32,98 mm** |
| nejmenší vzdálenost ($b$ = 114,3) | $7{,}5 \cdot 3 \cdot 114{,}3^{2/3}$ / $15 \cdot 3 \cdot 114{,}3^{2/3}$ | A **529,9 mm**, B **1 059,8 mm** → $f$ = 500 nevyhoví ani třídě A |
| neostrost při $f$ = 500 | $3 \cdot 114{,}3 / 500$ | **0,69 mm** |
| překryv | paprsek projde oběma stěnami | když je oblastí celý plášť, obraz se překrývá s protější stěnou → oranžově |
| zdroj uvnitř trubky (panoramatický) | tělo Ø 120 v otvoru Ø 102,3 | **naráží**; bez těla (Ø 0) projde |

Síť míst čísla jen přibližuje. Testy porovnávají procenta s tolerancí podle kroku a hranice
ověřují přesně v jednotlivých bodech (jako PT a MT).

## 8. Uložení do souboru (formát 21)

RT studie dostane nepovinnou položku `rt`:

```json
"rt": {
  "class": "B",
  "focal_mm": 3, "cone_deg": 40,
  "housing_diameter_mm": 120, "housing_length_mm": 300,
  "detector_width_mm": 100, "detector_length_mm": 240, "detector_thickness_mm": 2,
  "step_mm": null, "image_step_mm": 2,
  "projections": [
    {"name": "P1", "aim": [0, 0, 14], "direction": [0, 0, 1], "distance_mm": 500,
     "detector": "contact", "detector_angle_deg": 90, "detector_distance_mm": null,
     "reference_mm": null}
  ]
}
```

- `direction` = jednotkový směr od zaměřeného bodu ke zdroji. `detector` je `contact` (na
  ploše) nebo `free` (volně, pak `detector_distance_mm` = vzdálenost od zdroje).
  `reference_mm` = ručně zadaná jmenovitá tloušťka (`null` = $w_0$ ze středního paprsku).
- Chybějící hodnota = výchozí. Studie bez `rt` zůstane totožná a verze 1–20 se načtou beze
  změny.
- Projekce jsou souřadnice (bod a směr), ne plochy – plochy se dál vybírají jen významem.
  Po změně dílu je studie zastaralá jako dosud a projekce se po potvrzení spočítají znovu
  na novém dílu.
- Změna nastavení nebo projekce je jeden krok Zpět a výsledek zruší. `rt` u jiné metody než
  RT = česká chyba při načtení.

## 9. Okno

- Při výběru **RT studie** ukáže panel NDT místo skupin sondy skupinu **Geometrie projekce
  RT** s povinným upozorněním RT nahoře.
- **Nastavení RT…:** třída, ohnisko, kužel, tělo zdroje, detektor, kroky. Čísla jako text,
  nezměněné *OK* = žádný krok Zpět (jako PT a MT).
- **Projekce:**
  - seznam (P1, P2 …),
  - **Zdroj nad vybrané místo** (po kliknutí na plochu),
  - **Upravit projekci…**: zaměřený bod, sklon, natočení, vzdálenost $f$ (vedle $f_{min}$ pro
    A a B), detektor na ploše nebo volně, natočení detektoru, jmenovitá tloušťka,
  - **Kopírovat posunutou…** (o zadanou vzdálenost ve zvoleném směru, např. podél svaru),
  - **Smazat**.

  Každá změna = jeden krok Zpět.
- **Spočítat** – na pozadí s průběhem a *Zastavit* (pomocný proces jako PT a MT).
- **Přepínač mapy:** celkem / vybraná projekce / prozařovaná tloušťka na detektoru /
  neostrost / poměr tloušťky.
- **3D:**
  - zdroj jako kulička s osou svazku a obrysem kuželu,
  - tělo zdroje a deska detektoru průhledně v barvě stavu (jako sonda),
  - náhled na detektoru a mapa na oblasti.

  Kreslí se stávajícími druhy kreslení (průhledné těleso, čáry, body, mapa) – self-test
  beze změny.
- **Náhled v panelu** jako obrázek, **Uložit náhled PNG…**.
- **Klik na místo oblasti** → stav v každé projekci, prozařovaná tloušťka, poměr, neostrost
  a důvody.
- **Souhrn** a **Export CSV…**. Během práce AI je skupina zamčená (jako ostatní).

## 10. Výstupy

- **CSV:**
  - povinné upozornění RT,
  - předpoklady (zdroj, detektor, třída, $f$, $b$, $f_{min}$, $U_g$, $M$, $w_0$, materiál,
    „zvoleno pro výpočet“, „vzorec pro film“, algoritmus a verze),
  - souhrn po projekcích a celkem,
  - řádek na místo: x, y, z, plocha mm² nebo objem mm³, stav celkem, počet projekcí, a pro
    každou projekci stav, $w$, poměr, $U_{g,P}$, bod na detektoru a důvody.
- **Příkazová řádka:** `skodacad radiografie model.json --studie s2 [--projekce P1]
  [--trida A|B] [--ohnisko 3] [--vzdalenost 500] [--csv rt.csv] [--ulozit]` – vypíše souhrn
  s upozorněním RT.
- **AI asistent** nový nástroj nedostane. Pravidla (`assistant.RULES`) dostanou větu o RT:
  výsledky si nevymýšlí, „promítne se“ nevydává za viditelnost vady a nikdy neradí
  k radiační ochraně ani expozici.

## 11. Ověření před předáním

1. **Deska s otvorem:** hodnoty z oddílu 7. Při změně úhlu se mění prozařovaná tloušťka
   i obraz otvoru (podmínka dokončení z plánu).
2. **Tupý svar:** $w_0$ = 15 mm, konec svaru 15,07 mm, 100 % na filmu, $f_{min}$; při $f$ = 250
   třída B oranžově, A zeleně.
3. **Trubka:** 12 mm a 2 úseky, hranice poměru, $f_{min}$, překryv obrazů.
4. **Kolize:**
   - zdroj v trubce s tělem Ø 120 naráží, bez těla ne,
   - detektor odsunutý kořenem svaru (mezera 1 mm se přičte k $b$).
5. **Mimo svazek a mimo detektor** s českými důvody; nejistý paprsek nikdy zeleně.
6. **Střední paprsek do otvoru:** bez jmenovité tloušťky šedě s důvodem, s ní zeleně.
7. **Více projekcí:** sjednocení, počet projekcí, kopie posunutá podél.
8. **Formát 21:**
   - načtení verzí 1–20,
   - studie bez `rt` beze změny,
   - chybné `rt` = česká chyba,
   - změna nastavení i projekce = jeden krok Zpět.
9. **Stejný vstup = stejný výsledek:** dva běhy dají totožné stavy i náhled.
10. **Rozsah:**
    - `RT_DISCLAIMER` doslova v panelu, CLI i CSV,
    - shoda s `24-vymezeni-rt.md` (`test_ndt_scope.py`),
    - zakázaná označení,
    - UT, PT a MT výsledky beze změny (regresní testy).
11. **Okno:**
    - offscreen testy (projekce, výpočet, přepínač, klik, náhled, nastavení, Zpět, zámek AI),
    - snímek pod Xvfb,
    - GitHub Actions Windows i macOS.

    Testy krátké kvůli časovému limitu kroku *Testy* (teď 9–16 min z 20 min na Windows).

## 12. Rychlost (změřeno 19. 10. 2026 v cloudu, zkušební skript)

| Dotaz | Doba |
|---|---|
| jeden paprsek dílem (průsečíky, úseky, jistota) | **0,24 ms** (6 001 paprsků deskou s otvorem za 1,45 s) |
| náhled filmu 10 × 24 cm po 2 mm (6 000 paprsků) | asi **1,5 s**; po 1 mm asi 6 s |
| oblast asi 1 000 míst × 1–2 paprsky | asi **0,5 s** na projekci |
| kolize zdroje a detektoru | jednotky až desítky ms |

Výpočet poběží na pozadí jako PT a MT, bude ale řádově rychlejší (sekundy, ne minuty).

## 13. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **13A.1 – vymezení a jádro** | `24-vymezeni-rt.md`, `RT_DISCLAIMER`, `ndt/rt.py` (zdroj, detektor a jeho přiložení, kolize, paprsky, stavy, náhled, souhrn, CSV), RT studie v ukázkách (deska s otvorem, tupý svar – objem), ruční výsledky do `05-referencni-dily.md` jako NEOVĚŘENO | testy 1–7, 9, 10 |
| **13A.2 – soubor, ModelSession, CLI** | formát 21 (`rt`), `ModelSession` (nastavení a projekce jako kroky Zpět, mapa a náhled jako pohled), pomocný proces, `skodacad radiografie`, AI pravidlo | test 8 |
| **13B – okno** | skupina RT, dialogy nastavení a projekce, seznam projekcí, 3D, náhled v panelu, klik, souhrn, CSV, PNG | test 11, snímky, balíčky Windows a macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit. Do `main` až na tvůj pokyn.

## 14. Co etapa 13 nebude

- dávka, dávkový příkon, radiační ochrana, kontrolované pásmo, stínění,
- expozice (napětí, proud, čas, aktivita), prozáření dané tloušťky, rozptyl, fólie, kontrast,
  zčernání, šum, rozlišení detektoru, IQI,
- ohebný film obtočený kolem trubky a zakřivené kazety,
- automatický plán projekcí (počet expozic obvodového svaru podle přílohy A ISO 17636-1,
  eliptická technika s odsazením obrazů) – možné později,
- vady (etapa 16), změna dílu (etapy 14–15), společný protokol (etapa 14).

## 15. Praktická zkouška pro autora (po 13B)

1. Otevři *NDT – referenční díly → Deska s otvorem*, vyber RT studii a stiskni **Spočítat**.
   Náhled: černý kruh Ø 20 v bílém plechu.
2. Sklop zdroj o 30°: průhledná část otvoru se zúží asi na 9 mm a plech zesvětlí (šikmo
   prochází víc materiálu). Tohle je podmínka dokončení z plánu.
3. Otevři *Tupý svar – objem*: celý svar zelený, střední paprsek 15 mm. Zmenši vzdálenost na
   250 mm: třída B zoranžoví („zdroj blíž než $f_{min}$ = 273,7 mm“).
4. **Kopírovat posunutou:** druhý film vedle prvního – mapa celkem ukáže, kolik projekcí
   místo pokrylo.
5. Klikni na místo mimo film: „mimo detektor o … mm“.
6. Exportuj CSV a podívej se, že začíná povinným upozorněním RT.

## 16. K rozhodnutí

1. **Vymezení RT a povinné upozornění** v textu z oddílu 1 jako závazný dokument
   `24-vymezeni-rt.md` a konstanta `RT_DISCLAIMER` hlídaná testem. *Doporučeno: ano.* (Obdoba
   tvého rozhodnutí o UT, PT a MT; navíc výslovně bez radiační ochrany.)
2. **Bodový zdroj a plochý tuhý detektor** v této etapě; ohebný film kolem trubky později.
   *Doporučeno: ano.* (Plochý film a panel pokryjí plechy a svary; ohebný film potřebuje
   zakřivenou plochu detektoru.)
3. **Model zdroje a detektoru** podle oddílu 2: ohnisko 3 mm, kužel 40°, tělo zdroje
   Ø 120 × 300, $f$ = 500 mm, film 10 × 24 cm, kazeta 2 mm. Hodnoty jsou zvolené a lze je
   změnit. *Doporučeno: ano.*
4. **Detektor na ploše**, kudy střední paprsek vystupuje (s odsunutím při nárazu), nebo volně
   kolmo ke svazku. *Doporučeno: ano.*
5. **Geometrická pravidla ISO 17636-1:** poměr tloušťky 1,1 (B) / 1,2 (A) vůči střednímu
   paprsku (s ruční jmenovitou tloušťkou), $f_{min} = 7{,}5 / 15 \cdot d \cdot b^{2/3}$
   s pravidlem $b < 1{,}2\,t$, výchozí třída B; neostrost a zvětšení jen informativně.
   *Doporučeno: ano.* Až budeš mít plný text normy, hodnoty podle něj ověříme.
6. **Prozařovaná tloušťka** = všechny úseky v materiálu; nejistý paprsek = nelze spolehlivě
   vyhodnotit; překryv obrazů oblasti = omezené. *Doporučeno: ano.*
7. **Náhled prozařované tloušťky** na detektoru ve 3D i v panelu, uložení PNG, výslovně „není
   radiografický snímek“. *Doporučeno: ano.*
8. **Více projekcí ručně** (přidat, upravit, kopírovat posunutou, smazat), mapa celkem =
   sjednocení s počtem projekcí. Automatický návrh projekcí později. *Doporučeno: ano.*
9. **Nastavení a projekce ve studii** (formát 21), výsledky se neukládají. *Doporučeno: ano.*
10. **Okno, CSV a `skodacad radiografie`**, RT studie v ukázkách (deska s otvorem, tupý svar
    – objem), AI bez nového nástroje. *Doporučeno: ano.*

Schválením se **neschvaluje**:

- výpočet dávky, radiační ochrany ani expozice,
- ohebný film ani automatický plán projekcí,
- nová knihovna Pythonu,
- sloučení do `main`.

## 17. Provedení a upřesnění

- **13A.1 (hotovo):** závazné vymezení [`24-vymezeni-rt.md`](24-vymezeni-rt.md),
  `ndt.RT_DISCLAIMER`, `RT_ACCESS`, `RT_MAP`, `RT_PREVIEW` (test `test_ndt_scope.py` hlídá
  doslovné znění a zakázaná označení „simulovaný radiogram“, „simulovaný snímek“, „mapa
  dávky“, „mapa zčernání“). Jádro `ndt/rt.py`:
  - `RtSettings` a `Projection` (kontrola hodnot česky; směr ke zdroji se ukládá jako
    jednotkový vektor, `tilted` / `angles_of` převádějí sklon a natočení),
  - `prepare` (zdroj, střední paprsek, přiložení detektoru na plochu s odsunutím při nárazu
    nebo volně, kolize těla zdroje a detektoru přesným průnikem, zdroj v materiálu),
  - `compute` / `estimate` / `check_points` / `image_of`, `RtMap` (souhrn, CSV, síť po
    projekcích, `nearest`, `describe`), `RtImage` (náhled prozařované tloušťky),
    `study_target`, `self_check` (self-test aplikace).

  Ruční výsledky jsou v `05-referencni-dily.md` jako NEOVĚŘENO. RT studie v ukázkách přibudou
  v 13A.2 spolu s formátem 21 (bez něj by studie s projekcemi nešla uložit).
- **Upřesnění proti návrhu:**
  - **f a b ze strany předmětu u zdroje u místa oblasti nejblíž středu svazku.** Střední
    paprsek namířený do otvoru by dal nesmyslné b (pod 30° vstoupí do materiálu až ve stěně
    otvoru: b = 3,1 mm). Proto se vezme paprsek k místu oblasti s nejmenším úhlem od
    středního paprsku. Jeho vstup do dílu se převede na střední paprsek průsečíkem s tečnou
    rovinou plochy vstupu, takže na šikmém plechu nezáleží, jak daleko od osy místo leží.
    U plného plechu je to totéž co střední paprsek. Deska s otvorem: kolmo f = 500, b = 20;
    pod 30° f = 500, b = 23,094 (= 20 / cos 30°).
  - **Překryv obrazů jen přes vzduch.** Za překryv se počítá průchod oblastí v jiném kusu
    materiálu na paprsku (protější stěna trubky, druhý svar). Kořen a převýšení téhož V svaru
    leží ve stejném kusu materiálu – dřív to vyšlo jako překryv u 65 % objemu svaru.
  - **Prozařovaná tloušťka sčítá všechny úseky**, nejistotu jen vyznačí (zjištěno zkušebním
    skriptem: jinak by paprsek otřený o stěnu otvoru „prošel vzduchem“).
  - **Místo přesně v rovině detektoru** (spodek trubky na detektoru) se promítne, b = 0.
  - **Ruční odhad u kraje desky pod 30°** počítal s nekonečným plechem. Paprsek od místa
    u kraje vyjde boční stěnou, prozáří méně a poměr tloušťky nepřekročí – program to počítá
    správně.
- **Změřeno 19. 10. 2026** (cloud, testy jádra): deska s otvorem 1 086 míst a 2 projekce
  asi 3 s (náhled po 20 mm); objem V svaru po 5 mm (200 buněk) asi 4 s; 11 testů jádra
  11 s.

## Zdroje (ověřeno vyhledáváním 19. 10. 2026; plné texty norem jsou placené)

- **ISO 17636-1:2022 a 2013** *Non-destructive testing of welds – Radiographic testing –
  Part 1: X- and gamma-ray techniques with film* – veřejné výňatky
  [SSAB WeldCalc (2022)](https://weldcalc.ssab.com/sisStandards/ISO%2017636-1.pdf),
  [iTeh 2022](https://cdn.standards.iteh.ai/samples/78319/a8dc7cf24e0b4326b9420b938d34c6ea/ISO-17636-1-2022.pdf),
  [iTeh 2013](https://cdn.standards.iteh.ai/samples/52981/1cec933aa2494337b2b7479307b9410e/ISO-17636-1-2013.pdf).

  Z nich:
  - poměr prozařované tloušťky na okraji vyhodnocované oblasti k tloušťce na středu svazku
    nejvýš 1,1 (třída B) a 1,2 (třída A),
  - $b$ se měří od strany předmětu u zdroje po film podél osy svazku,
  - eliptická technika jen pro $D_e \le 100$ mm, $t \le 8$ mm a šířku svaru do $D_e / 4$;
    obrazy asi šířku svaru od sebe; dvě expozice po 90° při $t / D_e < 0{,}12$, jinak tři,
  - příloha A: počet expozic obvodového svaru.
- **ISO 5579:2013** *Radiographic testing of metallic materials using film and X- or
  gamma rays – Basic rules* – výňatek
  [iTeh](https://cdn.standards.iteh.ai/samples/57742/3d53a8f0077a403eacf394bd225d4913/ISO-5579-2013.pdf):
  $f/d \ge 7{,}5\,b^{2/3}$ (A) a $f/d \ge 15\,b^{2/3}$ (B); když $b < 1{,}2\,t$, dosadí se $t$;
  rozměr ohniska podle EN 12543 / EN 12679, u dvou rozměrů větší.
- Sekundární zdroje (jen pro kontrolu):
  - postup zkoušení Sulzer TP-0006 ([PDF](https://www.sulzer.com/en/-/media/files/q_documents_pe/tp/tp-0006.pdf))
    – stejný vzorec pro kategorie A a B,
  - článek *New requirements for digital radiographic testing of welds according to ISO
    standards* ([ResearchGate](https://researchgate.net/publication/258739157_New_requirements_for_digital_radiographic_testing_of_welds_according_to_ISO_standards))
    – vzorec s $c$ = 7,5 / 15 je pro film znám desetiletí, ISO 17636-2 má pro digitální
    detektory upravenou rovnici,
  - diskuze na ndt.net: [nejmenší vzdálenost pro třídu B](https://www.ndt.net/forum/thread.php?rootID=73507),
    [příloha A](https://www.ndt.net/forum/thread.php?rootID=86249),
  - ASME V čl. 2, T-274.2 – meze $U_g$
    ([open-exam-prep](https://open-exam-prep.com/study-guides/asnt-ndt-ii/rt-principles/rt-geometry-exposure)),
    jen pro informaci.
- Formáty filmu: Foma INDUX ([foma.cz](https://www.foma.cz/en/ndt-systems)) – 10 × 24,
  10 × 48 a 30 × 40 cm.
