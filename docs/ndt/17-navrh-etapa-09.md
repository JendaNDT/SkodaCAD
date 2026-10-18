# NDT – návrh etapy 09: návrh poloh UT sondy a mapa problémových zón

Stav: **návrh ke schválení (18. 10. 2026).** Nic z toho ještě není naprogramované.
Výchozí stav: `main`, commit `afce8c7` ([PR #22](https://github.com/JendaNDT/SkodaCAD/pull/22)).
Navazuje na [plán, etapa 09](03-implementacni-plan.md), [geometrické pokrytí (etapa 06)](11-navrh-etapa-06.md),
[objemové pokrytí svaru (07B)](13-navrh-etapa-07b.md), [knihovnu sond (etapa 08)](16-navrh-etapa-08.md)
a [závazné vymezení UT](04-zavazne-vymezeni-ut.md), které má přednost. Etapa 09 otevírá
milník **M3 – asistovaný UT** (etapy 09–10).

## Co tato etapa přinese

**Dnes:**

- Sondu přiložíš ručně: vybereš plochu, klikneš na místo a zvolíš směr paprsku. Úhel
  a počet odrazů nastavíš v dialogu *Sonda…*.
- *Spočítat pokrytí* pak spočítá **jednu** kombinaci: jedna plocha pojezdu, jeden směr,
  jeden úhel, jeden počet odrazů. Zkusit jinou stranu, směr nebo celý krok znamená celé to
  zopakovat ručně a čísla si porovnat na papíře.
- Program neřekne, kde se sonda na díl vůbec nevejde, ani co z cíle nepokryje žádný
  rozumný postup.

**Po etapě 09:**

1. V panelu NDT bude skupina **Návrh poloh sondy**. Jedním tlačítkem program sám vyzkouší
   **varianty**: každá rovinná plocha dílu × směr paprsku × úhel × počet odrazů.
2. Nejdřív rychle zjistí, kde se sonda **vejde** (bez kolize, nedosedání a přesahu).
   Varianty, kde se nevejde nebo paprsek k cíli nedosáhne, vyřadí **s českým důvodem**.
3. Zbylé varianty spočítá stávajícím výpočtem pokrytí (etapy 06 a 07B) a seřadí. Ukáže
   **tabulku nejlepších variant** s vysvětlením kompromisu, například: „pokryje 78 %, ale
   jen z úzkého pruhu 20 mm mezi žebrem a okrajem“.
4. Navrhne **kombinaci** (nejvýš 3 varianty), která dohromady pokryje nejvíc, a řekne,
   kolik každá přidá.
5. Ve 3D ukáže **mapu problémových zón** ve dvou podobách:
   - **cíl**: co nepokryje žádná vyzkoušená varianta,
   - **kontaktní plochy**: kde se sonda vejde ve všech směrech, jen v některých, nebo nikde.
6. **Použít variantu** přiloží sondu do nejlepší polohy té varianty. Když varianta mění úhel
   nebo odrazy, změní je ve studii (jeden krok Zpět). Pak *Spočítat pokrytí* udělá
   **nezávislý přepočet** jemným krokem.
7. Když nic nenajde, **poctivě to řekne** a napíše proč, u každé plochy zvlášť. Nikdy
   netvrdí, že kontrola je nemožná, jen že ji nenašel v zadaném rozsahu.

**Co se nemění:** výpočet přiložení, paprsku i pokrytí (analýza volá přesně ty samé
funkce), závazné vymezení UT a povinné upozornění, formát souboru (zůstává **17**), výrobní
geometrie. Analýza je jen **pohled** jako mapa pokrytí: do modelu se neukládá a díl nemění.

## 1. Rozsah a hranice

- **Jen UT, jen geometrie.** Doporučení optimalizuje **přístupnost sondy a geometrické
  pokrytí**, nic jiného. Nikdy nepíše o lepší zjistitelnosti vad (vymezení, bod 3). Každý
  výstup nese `UT_DISCLAIMER` a větu „Pořadí variant vyjadřuje jen geometrické pokrytí
  a přístupnost, nikoli zjistitelnost vad.“
- **Jen rovinné kontaktní plochy.** Na zakřivené ploše dnešní pokrytí umí jen „nelze
  spolehlivě vyhodnotit“ (zásah se tam nedá přesně ověřit). Analýza zakřivené plochy
  proto vynechá a ve výsledku to výslovně napíše.
- **Nemění model.** Návrh změny dílu (sražení, posun žebra) je až v etapách 14–15.
- **Nenalezeno ≠ nemožné.** Výsledek platí pro vyzkoušené plochy, směry, úhly, kroky
  a rozměry sondy. To je v souladu s vymezením: „Geometricky nepokryto … není důkaz, že
  jiný postup kontroly není možný.“
- **Jeden díl, jedna studie, jeden cíl.** Plán kontroly z několika poloh se do studie
  zatím neukládá. Souvislá dráha a tabulka poloh jsou etapa 10.

## 2. Jak analýza hledá

### Varianta

**Varianta** = rovinná kontaktní plocha + směr paprsku na ní + úhel β + počet odrazů.
Ostatní (rozměry sondy, výstupní bod, mez mezery, rezerva, materiál pro UT, rozevření)
se bere ze studie a nemění se.

| Co se zkouší | Výchozí nastavení | Volitelně |
|---|---|---|
| Plochy | všechny rovinné plochy, na které se otisk sondy vejde aspoň rozměrem | vybrané plochy |
| Směry | po 45° (8 směrů) + směr k těžišti cíle a opačný; u svaru navíc kolmo na osu z obou stran | po 30° nebo 90° |
| Úhel β | jen úhel sondy ve studii | i 45°, 60°, 70° (předpoklad: stejné rozměry sondy, jen jiný úhel) |
| Odrazy | 0 a 1 (půlkrok a celý krok) | jen 0, nebo 0–2 |

Úhel z volby „i 45°, 60°, 70°“ se do studie dosadí stejně, jako kdybys ho přepsal v dialogu
*Sonda…*, a upozornění na materiál úhlu z etapy 08 platí dál. Analýza sama nic
nepřepočítává a v tabulce je vždy vidět, který úhel varianta předpokládá.

### Tři kola (aby to netrvalo hodiny)

Změřeno na dnešním kódu 18. 10. 2026 (cloudový počítač, časy kolísají):

- jedno přiložení sondy trvá **18–27 ms**,
- jedna mapa pokrytí trvá **12–30 s** (deska se žebrem, krok 10 mm; výřez V svaru,
  krok 5 mm) a **1–3 min** u desky s krokem 5 mm.

Spočítat přímo desítky map by trvalo desítky minut, proto analýza postupuje ve třech kolech:

1. **Přístupnost (rychlé):** na každé ploše mřížka poloh (výchozí krok = polovina šířky
   sondy, nejvýš 200 poloh na plochu). V každé poloze a každém směru přiloží sondu.
   Variantu bez jediné platné polohy vyřadí s důvodem, například: „koliduje se žebrem
   ve všech 27 polohách“, „přesahuje okraj plochy“, „nedosedá – mezera nad 0,5 mm“.
2. **Dosah (rychlé):** z několika platných poloh spustí paprsek. Když žádné rameno
   nevede blízko cíle (obalový kvádr cíle + tolerance), variantu vyřadí: „paprsek z této
   plochy k cíli nedosáhne“.
3. **Pokrytí (pomalé):** zbylé varianty spočítá stávajícím výpočtem s **dvojnásobným
   krokem** pojezdu (hrubý odhad pro řazení). Krok cíle je pro všechny varianty stejný,
   jinak by nešly sčítat.

Před spuštěním panel ukáže **odhad**: počet variant a poloh a přibližný čas. Výpočet
běží v pomocném procesu, ukazuje „varianta 7 z 24“ a jde zastavit. Hotové varianty
po zastavení zůstanou v tabulce, označené „neúplná analýza“. Ochranné meze jsou stejné
jako dnes (nejvýš 20 000 poloh a 80 milionů porovnání na jednu mapu) a navíc nejvýš
**40 variant** ve třetím kole. Při překročení program poradí, co zúžit.

### Pořadí variant

1. geometricky pokryto (%), u objemu váženo mm³ jako 07B,
2. při rozdílu do 1 p. b. víc platných poloh (větší volnost manipulace),
3. méně „nelze spolehlivě vyhodnotit“,
4. jednodušší postup: méně odrazů, úhel beze změny.

Pořadí je pravidlo, ne „skóre kvality“. V tabulce jsou vidět všechna čísla, aby šlo
rozhodnout jinak.

### Kombinace

Kombinace se skládá postupně. První je nejlepší varianta. Další je ta, která **přidá
nejvíc dosud nepokrytého** cíle. Nejvýš 3 varianty, přidávání skončí, když další přidá
méně než 1 p. b. Sjednocení počítá **vzorek po vzorku** stejné mřížky cíle:

- pokryto, když je pokryto aspoň v jedné variantě,
- nelze spolehlivě vyhodnotit, když není pokryto nikde a aspoň jedna varianta je nejistá,
- jinak nepokryto.

Žádné průměrování, žádné přenormování vah.

## 3. Výsledek

**Tabulka variant** (nejlepších 10, ostatní v CSV):

| # | Plocha | Směr | β | Odrazy | Pokryto | Nejisté | Platné polohy | Nejmenší volno | Poznámka |
|---|---|---|---|---|---|---|---|---|---|
| 1 | horní vpravo | k cíli (180°) | 70° | 1 | 99,9 % | 0 % | 340 / 609 | … | celý krok |

Ukázka používá hodnoty změřené na výřezu V svaru, viz oddíl 6 (volno se tam neměřilo). Poznámka vysvětlí kompromis
krátce česky, například: „jen úzký pruh podél žebra“, „volno jen 0 mm – sonda se dotýká
stěny“, „pokrytí jen přes odraz“, „předpokládá úhel 60° místo 70° ze studie“.

**Kombinace:** „A + B pokryjí 100 % (A 99,9 %, B přidá 0,1 p. b.)“.

**Vyřazené varianty:** počet podle důvodu a u každé plochy jedna věta. Z nich se skládá
poctivé „nenašel jsem“.

**Mapa problémových zón (3D):**

- **Cíl:** sjednocení kombinace kreslené jako dnešní mapa pokrytí (zelená / červená /
  žlutá; u svaru povrch cíle a *Průřez svarem*). Červená = **nepokryto žádnou
  vyzkoušenou variantou**.
- **Kontaktní plochy:** body mřížky prvního kola. Zelená = sonda se vejde ve všech
  vyzkoušených směrech, oranžová = jen v některých, červená = v žádném. Legenda to
  napíše slovy. Kreslí se kuličkami, které už bezpečně používá mapa tloušťky (ne podkladem
  pod popiskem, viz známé pasti).

## 4. Okno

Nová skupina **Návrh poloh sondy** v panelu NDT, pod mapou pokrytí:

- volby: plochy (všechny / vybrané), směry (45° / 30° / 90°), *zkusit i 45°, 60°, 70°*,
  odrazy (0–1 / jen 0 / 0–2),
- řádek s **odhadem** a tlačítka **Navrhnout polohy** / **Zastavit**,
- tabulka variant, řádek kombinace a počet vyřazených s důvody,
- přepínač mapy: *cíl* / *kontaktní plochy* / *nic*,
- **Ukázat variantu** (jen pohled: přiloží sondu, model nemění) a **Použít variantu**
  (případná změna úhlu a odrazů ve studii = jeden krok Zpět).

Během práce AI je skupina zamčená jako ostatní. Změna dílu, studie nebo sondy analýzu
zneplatní, stejně jako dnes mapu pokrytí.

## 5. Výstupy

- **CSV analýzy:** povinné upozornění, věta o pořadí, předpoklady (sonda, materiál,
  kroky, rozsah variant, algoritmus) a všechny varianty včetně vyřazených s důvodem.
- **Příkazová řádka:** `skodacad polohy model.json --studie s1 [--smery 45] [--uhly 45,60,70]
  [--odrazy 0,1] [--csv vystup.csv]` vypíše totéž jako panel.
- **AI asistent** v etapě 09 nový nástroj nedostane. Pravidlo zůstává: čísla ani
  doporučení si nevymýšlí.

## 6. Ověření před předáním

Testy na referenčních dílech s ručně spočítaným nebo dnes změřeným výsledkem:

1. **Obtížný přístup (`pristup.json`), sonda 40 × 20 v mezeře 30 mm.** Dnes změřeno:
   napříč mezerou (0°, 45°, 180°) koliduje **27 z 27** poloh. Podél (90°, 270°) je
   **18 přiloženo** a 9 přesahuje na koncích; volno klesá až na 0 mm u x = ±5
   (30 − 20 = 10 mm napříč). Analýza musí směry napříč vyřadit s důvodem kolize
   a **najít alternativu** podél mezery.
2. **Deska se žebrem (`zebro.json`), 45°, rezerva 5 mm, cíl pod osou žebra.** Ručně:
   půlkrok 20 mm < potřebných 22 mm, mezní úhel 47,7°. Jen se 45° musí analýza oznámit
   **„nenašel“** s důvodem. S volbou *i 60°, 70°* musí najít 60° (34,64 mm ≥ 22 mm).
3. **Výřez V svaru, sonda 70°, krok 5 mm.** Dnes změřeno ručním opakováním:

   | Varianta | Pokryto |
   |---|---|
   | zprava, bez odrazu | 14,74 % (vzorec 15,18 %) |
   | zleva, bez odrazu | 14,74 % |
   | obě strany, bez odrazu | 15,22 % |
   | jedna strana, 1 odraz | **99,91 %** |
   | obě strany, 1 odraz | 100 % |

   Analýza musí dát na první místo variantu **s odrazem** a u druhé strany správně říct,
   že přidá jen 0,09 p. b. Je to i dobrý příklad, proč se vyplatí zkoušet celý krok.
4. **Nic nenajde poctivě:** sonda delší než všechny plochy desky. Výsledek „žádná
   varianta“ s důvodem u každé plochy, nikdy prázdná tabulka bez vysvětlení.
5. **Sjednocení:** procento kombinace je aspoň takové jako u nejlepší varianty a sedí
   se sjednocením spočítaným ručně ze stavů vzorků. Varianta použitá tlačítkem a pak
   spočítaná stejným (hrubým) krokem dá **stejné číslo** jako v tabulce.
6. **Regrese:** všechny dnešní referenční výsledky beze změny (deska 85,5 %,
   V svar 12,2 % / 15,18 %, žebro s rezervou). Povinné upozornění je v panelu, CSV i CLI
   (`test_ndt_scope.py`).
7. **Okno:** offscreen testy (spuštění, zastavení, použití, Zpět, zámek AI), snímek
   pod Xvfb, GitHub Actions Windows i macOS.

## 7. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **09A – jádro bez okna** | `ndt/access.py`: varianty, první a druhé kolo, řazení, kombinace, sjednocení, vysvětlení česky; `ModelSession` (analýza po variantách i v pomocném procesu, zastavení); `skodacad polohy`; CSV | testy 1–6 z oddílu 6 |
| **09B – okno** | skupina *Návrh poloh sondy*: odhad, průběh, tabulka, kombinace, mapy problémových zón, Ukázat / Použít | offscreen testy, snímky, balíčky Windows/macOS |

Každý krok zvlášť: `ruff`, `pytest`, commit; do `main` až na tvůj pokyn.

## 8. Co etapa 09 nebude

- souvislá dráha sondy, nájezdy, zakázané zóny a tabulka poloh (etapa 10),
- zakřivené kontaktní plochy a tvarovaná předsádka (08C zůstává odložená),
- návrhy změny geometrie dílu (etapy 14–15),
- cokoli o zjistitelnosti vad, citlivosti nebo kvalitě signálu (mimo vymezení),
- optimalizace „po kouscích“ mimo vyzkoušené varianty (žádné hledání spojitého optima),
- ukládání analýzy do souboru (formát zůstává 17).

## 9. Praktická zkouška pro autora (po 09B)

1. Otevři *NDT – referenční díly → Obtížný přístup*. Studie s úhlovou sondou, cíl = dno
   pod mezerou. Stiskni **Navrhnout polohy**. Směry napříč mezerou musí být vyřazené
   („koliduje“), podél doporučené. Mapa kontaktních ploch ukáže mezeru oranžově.
2. Otevři ukázku V svaru (*cílové objemy*). Analýza musí na první místo dát 70°
   s odrazem. **Použít variantu** a *Spočítat pokrytí* musí dát stejné číslo jako tabulka.
3. Zastav analýzu uprostřed. Hotové varianty zůstanou s označením „neúplná analýza“.

## 10. K rozhodnutí

1. **Analýza je jen pohled**, neukládá se, formát zůstává 17. Změnu studie udělá jen
   *Použít variantu* (jeden krok Zpět). *Doporučeno: ano.*
2. **Varianty** podle oddílu 2: rovinné plochy, směry po 45° + k cíli (+ kolmo na svar),
   úhel ze studie, odrazy 0 a 1. Jiné úhly jen na zaškrtnutí. *Doporučeno: ano.*
3. **Tři kola** (přístupnost → dosah → hrubé pokrytí dvojnásobným krokem) a přesné číslo
   až nezávislým přepočtem po *Použít variantu*. *Doporučeno: ano.*
4. **Pořadí** podle oddílu 2: pokrytí, pak volnost, nejistota, jednoduchost; bez
   souhrnného „skóre“. *Doporučeno: ano.*
5. **Kombinace** nejvýš 3 variant, sjednocení vzorek po vzorku. *Doporučeno: ano.*
6. **Mapa problémových zón** pro cíl i kontaktní plochy. *Doporučeno: ano.*
7. **Zakřivené kontaktní plochy** v etapě 09 vynechat a říct to ve výsledku.
   *Doporučeno: ano.*
8. **CLI `skodacad polohy`**, AI bez nového nástroje. *Doporučeno: ano.*
9. **Souběh více procesů** pro rychlejší výpočet zatím ne. Rozhodnout po změření 09A
   na tvém počítači. *Doporučeno: odložit.*

Schválením se **neschvaluje**: dráha sondy (etapa 10), změna výpočtu přiložení, paprsku
ani pokrytí, nová knihovna Pythonu, změna formátu ani sloučení do `main`.
