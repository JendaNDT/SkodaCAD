# NDT – referenční díly a ručně spočítané očekávané výsledky

> Etapa 00 plánu `03-implementacni-plan.md`. Podle těchto čísel se budou testovat další etapy
> (paprsek, sonda, kolize, pokrytí). Jde o **geometrii**, ne o detekovatelnost vad ani normu.

**Stav ověření: NEOVĚŘENO** – čeká na kontrolu kolegou NDT technikem. Po kontrole doplň do
tabulky na konci jméno, datum a případné opravy; do té doby jsou hodnoty orientační.

Modely jsou v `examples/ndt/`, v aplikaci *Soubor → Otevřít ukázku → NDT – referenční díly*.
Test `tests/test_ndt_examples.py` hlídá, že každý díl jde postavit, je to jedno platné těleso
s objemem podle vzorce a že sedí rozměry, které jdou změřit už dnes.

## Společné předpoklady

- Materiál ocel. Jednotky mm a stupně. Souřadnice: deska leží na rovině XY, horní plocha je +Z.
- **Paprsek = přímka** (střední paprsek svazku, žádná šířka svazku, žádný útlum).
- β = úhel lomu v materiálu (úhel sondy), měřený od kolmice k ploše přiložení.
- Rovná deska tloušťky t: **půlkrok** p = t·tg β (vzdálenost od výstupního bodu k místu dopadu
  na protější plochu), **celý krok** 2p, dráha k protější ploše s = t / cos β.
- **Virtuální úhlová sonda** (obecná, ne katalogová): kvádr 40 × 20 × 25 mm (délka ve směru
  paprsku × šířka × výška), výstupní bod paprsku 12 mm od čela. Přímá sonda: kruhová kontaktní
  plocha Ø 10 mm, není-li řečeno jinak.
- Sonda smí stát jen na rovné volné ploše; čelo sondy nesmí zasahovat do převýšení svaru, žebra
  ani stojiny. „Manipulační rezerva“ = další volný odstup čela od překážky (výchozí 0 mm).

## 1. Deska – `deska.json`

Deska A × B × t = 200 × 100 × 20. Objem 200·100·20 = **400 000 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Přímá sonda shora (kdekoli ≥ 5 mm od okraje) | dráha **20 mm**, dopad na dolní plochu kolmo (0°) | s = t |
| Po změně t = 30 | dráha **30 mm**; NDT studie na horní ploše **zastaralá**, plocha nalezena, posun 10 mm | s = t |
| Úhlová sonda 45° | půlkrok **20,00 mm**, celý krok 40,00 mm, dráha k dolní ploše **28,28 mm** | 20·tg 45°, 20 / cos 45° |
| Úhlová sonda 60° | půlkrok **34,64 mm**, dráha **40,00 mm** | 20·tg 60°, 20 / cos 60° |
| Úhlová sonda 70° | půlkrok **54,95 mm**, dráha **58,48 mm** | 20·tg 70°, 20 / cos 70° |

## 2. Blok s kapsou – `kapsa.json`

Blok 120 × 80 × 40, kapsa shora 40 × 30 hloubky 25 uprostřed (ostré rohy).
Objem 120·80·40 − 40·30·25 = 384 000 − 30 000 = **354 000 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Přímá sonda zespodu pod kapsou | dráha **15 mm** (koncové echo ode dna kapsy) | H − h = 40 − 25 |
| Přímá sonda zespodu mimo kapsu | dráha **40 mm** | H |
| Přímá sonda Ø 20 na dně kapsy | **vejde se**, střed smí být v poli **20 × 10 mm** | (40 − 20) × (30 − 20) |
| Přímá sonda Ø 32 na dně kapsy | **nevejde se** (32 > 30) | |
| Stěna kapsy | ve směru X **40 mm**, ve směru Y **25 mm** | (120 − 40)/2, (80 − 30)/2 |

## 3. Deska se žebrem – `zebro.json` (první milník UT)

Deska 200 × 100 × 20, žebro tloušťky s = 10 a výšky v = 60 uprostřed (osa x = 0), po celé
délce. Objem 400 000 + 10·100·60 = **460 000 mm³**.

Cíl: dno desky přímo pod osou žebra (x = 0, z = 0), sonda na horní ploše, paprsek k žebru.
Čelo sondy musí zůstat mimo žebro → výstupní bod **≥ s/2 + 12 = 17 mm** od osy (+ rezerva).

| Úhel | Půlkrok | Bez rezervy (≥ 17 mm) | S rezervou 5 mm (≥ 22 mm) |
|---|---|---|---|
| 45° | 20,00 mm | **ano** (zbývají 3 mm) | **ne** (chybí 2 mm) |
| 60° | 34,64 mm | **ano** | **ano** |
| 70° | 54,95 mm | ano | ano |

Další kontroly: žebro z boku 10 mm; pod žebrem (zespodu) dráha **80 mm**; vedle žebra 20 mm.
Mezní úhel pro rezervu r: tg β ≥ (17 + r) / 20 → bez rezervy β ≥ 40,4°, s 5 mm β ≥ 47,7°.

## 4. Deska s otvorem – `otvor.json`

Deska 200 × 100 × 20, průchozí otvor Ø 20 uprostřed.
Objem 400 000 − π·10²·20 = **393 716,81 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Paprsek shora blíž než 10 mm od osy otvoru | **žádný materiál** (paprsek prochází otvorem) | r < d/2 |
| Paprsek shora 10–15 mm od osy, sonda Ø 10 | materiál 20 mm, ale sonda **nedosedá celou plochou** (přesahuje nad otvor) | d/2 < r < d/2 + 5 |
| Sonda Ø 10 ≥ 15 mm od osy | dosedá celou plochou, dráha **20 mm** | r ≥ d/2 + 5 |
| Ze stěny otvoru radiálně ve směru ±Y | **40 mm** k okraji desky | B/2 − d/2 |

## 5. Trubka – `trubka.json`

Trubka D × s = 114,3 × 6, délka 300 (osa X). Vnější poloměr R = 57,15, vnitřní r = 51,15.
Objem π/4·(114,3² − 102,3²)·300 = **612 422,07 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Přímá sonda radiálně | dráha **6 mm** | s |
| Rovná kontaktní plocha šířky 20 napříč obvodem | **nedosedá**, mezera na krajích **0,88 mm** | R − √(R² − 10²) |
| Rovná kontaktní plocha podél osy | dosedá v přímce | |
| Obvodový paprsek (sonda mířící po obvodu) | vnitřní stěnu zasáhne jen pro **β ≤ 63,5°**; 70° ji mine | sin β ≤ r / R = 0,895 |

## 6. Tupý svar V – `tupy_svar.json`

Dva plechy t = 12 (dohromady 300 × 100), tupý svar V s úhlem rozevření 60° v ose x = 0 podél Y.
Převýšení: lichoběžník šířky c = 20 u plechu a 14 nahoře, výška h = 2. Podkořen: šířka k = 6
u plechu a 4 dole, výška p = 1. Díl je **jedno těleso** – hranice úkosu v něm není (cílový objem
svaru bude v etapě 07). Šířka úkosu nahoře při mezeře 2 mm by byla 2 + 2·12·tg 30° = 15,86 mm,
převýšení ji tedy překrývá.
Objem 300·100·12 + (20 + 14)/2·2·100 + (6 + 4)/2·1·100 = **363 900 mm³**.

Cíl: kořen (x = 0, z = 0), sonda na horní ploše plechu. Čelo sondy mimo převýšení → výstupní
bod **≥ c/2 + 12 = 22 mm** od osy.

| Úhel | Půlkrok (t = 12) | Kořen přímým paprskem? |
|---|---|---|
| 45° | 12,00 mm | **ne** |
| 60° | 20,78 mm | **ne – chybí 1,22 mm** (hraniční případ) |
| 70° | 32,97 mm | **ano** |

Mezní úhel: tg β ≥ 22 / 12 → **β ≥ 61,4°**. Další kontroly: v ose svaru shora (z převýšení)
dráha 12 + 2 + 1 = **15 mm**; v plechu 12 mm.

## 7. Koutový svar (T-spoj) – `koutovy_svar.json`

Pásnice 200 × 100 × 10, stojina tloušťky 10 a výšky 80 uprostřed, oboustranné koutové svary
s ramenem z = 7 (účinná tloušťka a = z / √2 ≈ 4,95). Jedno těleso.
Objem 200 000 + 80 000 + 2·(7·7/2)·100 = **284 900 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Paty svarů na pásnici | **12 mm** od osy stojiny (obě strany) | s/2 + z |
| Úhlová sonda na pásnici, paprsek ke stojině | výstupní bod **≥ 12 + 12 = 24 mm** od osy | |
| Přímá sonda zespodu pod stojinou | rovina styku stojiny s pásnicí v hloubce **10 mm**; v tělese pokračuje až na 90 mm | t, t + v |
| Stojina z boku | **10 mm** | s |

## 8. Obtížný přístup – `pristup.json`

Deska 200 × 100 × 15, dvě žebra tloušťky 10 a výšky 50 po celé délce, světlá mezera
m = 30 mm (vnitřní plochy žeber x = ±15). Objem 300 000 + 2·10·100·50 = **400 000 mm³**.

| Otázka | Očekávaný výsledek | Výpočet |
|---|---|---|
| Sonda 40 × 20 v mezeře podélně (40 podél žeber) | **vejde se**, vůle napříč **10 mm** | 30 − 20 |
| Sonda 40 × 20 napříč mezerou | **koliduje** se žebry | 40 > 30 |
| Úhlový paprsek napříč mezerou (k žebru) | **nejde** (sonda se tak nevejde) | |
| Úhlový paprsek podél žeber | jde | |
| Přímá sonda zespodu pod mezerou / pod žebrem | **15 mm / 65 mm** | t, t + v |
| Výška sondy 25 < výška žeber 50 | manipulace jen shora mezi žebry – poznámka pro etapu 03 | |

## 9. Blok se štěrbinou a slepým otvorem – `sterbina.json` (PT, etapa 11)

Blok A × B × H = 100 × 60 × 30. Uzavřená štěrbina délky l = 40, šířky **w = 1** a hloubky
h = 20 ve x = −25 (dlouhé stěny x = −25,5 a −24,5). Slepý otvor **Ø d = 6** hloubky 20 ve
x = +25. Objem 100·60·30 − 40·1·20 − π·3²·20 = **178 634,51 mm³**. Tři PT studie: s1 horní
plocha, s2 dlouhé stěny štěrbiny, s3 dno a stěna otvoru.

**Předpoklady PT** (návrh `19-navrh-etapa-11.md`, jen geometrie): nástroj = kulička o průměru
nástroje dotýkající se místa + dřík 100 mm; hlavní nástroj Ø 10, jemný Ø 3. Nástřik jde do 60°
od kolmice, šikmo do 85°. Prohlídka aspoň 30° k povrchu (šikmo aspoň 5°), oko do 600 mm.
Pás u vnitřního rohu, kam se kulička poloměru r nedostane: x₀ = r · cot(θ/2), θ = úhel mezi
plochami na straně vzduchu (90° → x₀ = r, 135° → 0,414 r).

| Plocha | Otření | Nástřik i prohlídka | Upozornění |
|---|---|---|---|
| Horní plocha | jde 100 % | jde 100 % | – |
| Stěny štěrbiny (2 × 40 × 20) | **nejde** (w = 1 < 3) | jde do hloubky w·tg 60° = **1,73 mm** (8,66 %), šikmo do w·tg 85° = **11,43 mm** (48,49 %), hlouběji **nejde** (42,85 %) | úzká štěrbina 1 mm |
| Dno otvoru (28,27 mm²) | Ø 10 nejde; Ø 3 jen do 1,5 mm od osy = **25 %** | jde 100 % | otevřenost středu 1 − cos(atan(3/20)) = **1,1 %** |
| Stěna otvoru (376,99 mm²) | Ø 10 nejde; Ø 3 kromě pásu 1,5 mm u dna = **92,5 %** | jde do hloubky 6·tg 60° = **10,39 mm** (51,96 %), hlouběji šikmo | mezera 6 mm < Ø 10 |

**PT u dalších dílů** (stejné předpoklady):

| Díl, plocha | Ø 10 jde | Ø 3 jde | Poznámka |
|---|---|---|---|
| Kapsa (`kapsa.json`, studie s2): dno 40 × 30 | (40−10)(30−10) = **50 %** | 37 · 27 = **83,25 %** | nástřik a prohlídka 100 %, otevřenost středu dna 20,8 % |
| Kapsa: delší stěna 40 × 25 | (40−10)(25−5) = **60 %** | 37 · 23,5 = **86,95 %** | prohlídka 100 % (25 < 30 · tg 60°) |
| Kapsa: kratší stěna 30 × 25 | (30−10)(25−5) = **53,33 %** | 27 · 23,5 = **84,6 %** | |
| Koutový svar (`koutovy_svar.json`, studie s1): plochy svarů 9,90 mm | 9,90 − 2 · 2,07 = **58,16 %** | 9,90 − 2 · 0,62 = **87,45 %** | rohy 135°; nástřik a prohlídka 100 % |

## MT – přiložení jha u dílů 1, 2, 5 a 7 (etapa 12)

**Předpoklady MT** (návrh `21-navrh-etapa-12.md`, vymezení `22-vymezeni-mt.md`, jen geometrie):
kloubové jho s póly Ø 20 (botka 15 mm přiléhá k ploše), výška nohy 60 mm, tělo 40 × 40;
rozteč d = 100 mm, záloha 75 mm (ISO 17638: d ≥ 75). Místo pólu = první dotyk kružnice
o poloměru d/2 sklápěné od kolmice nad místem. Účinná oblast (d − 50) × d/2 kolem středu jha
(u pólu 25 mm ne). Vada se počítá, když je k poli skloněná aspoň o 30°; všechny orientace vad
pokryjí dva směry pole aspoň 60° od sebe. Úhel 0° = průmět osy +X do plochy.

**Pravidlo okraje:** ve směru pole končí pokrytí 10 + 25 = **35 mm od okraje** (pól celý na
ploše, 25 mm u pólu se nepočítá) – pro rozteč 100 i 75 mm.

| Díl, studie | Případ | Ručně | Pozn. |
|---|---|---|---|
| Deska (`deska.json`, s2 horní plocha 200 × 100) | pole 0° (podél X) | x ∈ ⟨−65; 65⟩ = **65 %** | |
| | pole 90° (podél Y) | 100 mm nejde (100 + 2·10 > 100), 75 mm: y ∈ ⟨−15; 15⟩ = **30 %** | |
| | pole 45°, jen rozteč 100 | osmiúhelník 4ab + 4r(a+b) + 2r² = 11 899 mm² = **59,5 %** (a = 54,64, b = 4,64, r = 35,36) | mřížka středů dá méně (zubatý okraj) |
| | místo (0; 0) | směry 0° i 90° → všechny orientace | |
| | místo (0; 45) | jen −22,5°, 0°, 22,5° → nepokryté vady **−7,5° až 7,5°** | |
| | místo (95; 0) | jen 67,5°, 90°, 112,5° → nepokryté vady **82,5° až 97,5°** | |
| Trubka (`trubka.json`, s2 plášť Ø 114,3 × 300) | podél osy | ⟨−115; 115⟩ = **76,7 %** | mezera pod pólem Ø 20: 57,15 − √(57,15² − 10²) = **0,88 mm** |
| | po obvodu | 100 mm: nohy 2·2·asin(50/114,3) = **103,7° > 90°**; 75 mm: **76,6°** ✓ | |
| Kapsa (`kapsa.json`, s3 dno 40 × 30) | celé dno | **nepokryto** – mezi místem a pólem je stěna (kapsa menší než rozteč) | |
| Koutový svar (`koutovy_svar.json`, s2 plochy svarů) | napříč, střed (−8,5; 0; 13,5) | póly (−8,5 − √(50² − 3,5²); 0; 10) = (**−58,38**; 0; 10) a (−5; 0; **63,38**), nohy 90° | jho přes roh |
| | podél svaru (svar 100 mm) | 100 mm nejde; 75 mm jen \|y\| ≤ 15 (**30 %** délky) | |

## RT – geometrie projekce u dílů 4, 5 a 6 (etapa 13)

**Předpoklady RT** (návrh `23-navrh-etapa-13.md`, vymezení `24-vymezeni-rt.md`, jen geometrie):
bodový zdroj s ohniskem d = 3 mm, kužel svazku 40°, plochý detektor 100 × 240 mm (film
10 × 24 cm). Prozařovaná tloušťka w = všechny úseky v materiálu na spojnici ohnisko–detektor.
Poměr w / w₀ (w₀ = tloušťka na středu svazku) nejvýš 1,1 (třída B) / 1,2 (třída A); nejmenší
vzdálenost zdroje f_min = 7,5 / 15 · d · b^(2/3), když b < 1,2 t, dosadí se t (ISO 17636-1,
ISO 5579, vzorec pro film). f a b se měří po středním paprsku od strany předmětu u zdroje.

| Díl, studie | Případ | Ručně | Pozn. |
|---|---|---|---|
| Deska s otvorem (`otvor.json`, horní plocha) | zdroj kolmo nad otvorem, f = 500, detektor v rovině spodní plochy, jmenovitá tloušťka 20 | plech u x = 50: 20 / cos(arctg(50/500)) = **20,10 mm**; u x = 95: poměr **1,018** | |
| | otvor kolmo | průhledné **x ∈ ⟨−10; 10⟩** (rozhoduje dolní hrana) | |
| | zdroj sklopený o 30° k +X, S = (250; 0; 453,0), detektor na spodní ploše | průhledné **x ∈ ⟨−10; −1,09⟩ = 8,91 mm** (rovnoběžně by 8,45) | podmínka dokončení z plánu |
| | vzdálenosti | f = 500, b = 20 (kolmo) / b = 20 / cos 30° = **23,09** (30°); f_min A **165,8**, B **331,6 mm**; U_g **0,12 mm**; zvětšení **1,04** | |
| | okraj filmu | horní plocha na filmu do \|y\| ≤ 50 · 500/520 = **48,08 mm** (96,1 % plochy) | |
| Tupý svar V (`cilove_objemy/tupy_svar_objem.json`, objem svaru) | zdroj kolmo nad převýšením, f = 500, detektor na kořeni (z = −1) podél svaru | w₀ = 2 + 12 + 1 = **15 mm**; f_min A **136,8**, B **273,7 mm**; U_g **0,09 mm**; celý svar na filmu | při f = 250 třída B nevyhoví, A ano |
| | konec svaru y = 49 | poměr 1 / cos(arctg(49/507)) = **1,005** | |
| | detektor vedle svaru (x = 30) | kořen vyčnívá 1 mm → detektor odsunut o **1 mm** | |
| Trubka (`trubka.json`, plášť Ø 114,3 × 6) | zdroj nad osou, f = 500, detektor dole tečně | w₀ = 2 × 6 = **12 mm** (dvě stěny); poměr 1,1 rovnoběžně x = ±22,52 mm, ze zdroje na detektoru **±24,85 mm** | |
| | vzdálenost | b = 114,3: f_min A **529,9**, B **1 059,8 mm** → f = 500 nevyhoví ani A | |
| | obraz | paprsek projde oběma stěnami → **překryv obrazů** (oblast = celý plášť) | |
| | zdroj v ose trubky | tělo zdroje Ø 120 se do otvoru Ø 102,3 **nevejde**; bez těla projde | |

## Záznam ověření

| Díl | Ověřil | Datum | Poznámka / oprava |
|---|---|---|---|
| 1–8 | *čeká na kolegu NDT technika* | | |
| 9 a PT u dílů 2 a 7 | *čeká na kolegu NDT technika* | | |
| MT u dílů 1, 2, 5 a 7 | *čeká na kolegu NDT technika* | | |
| RT u dílů 4, 5 a 6 | *čeká na kolegu NDT technika* | | |
