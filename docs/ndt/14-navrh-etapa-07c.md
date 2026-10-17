# NDT – návrh etapy 07C: cílový objem a jeho pokrytí v okně

Stav: **schváleno autorem 17. 10. 2026 včetně doporučení 1–4 z oddílu 10; implementováno
ve vývojové větvi `claude/magical-hawking-h944yz` (07C.1, 07C.2, 07C.3) a 17. 10. 2026 na
pokyn autora („PR sloučit hned bez ruční zkoušky“) sloučeno do `main` v PR #19. Ruční
zkouška autorem v okně zatím neproběhla.**
Co se při implementaci upřesnilo, je v [oddílu 11](#11-provedení-a-upřesnění).
Výchozí stav: `main`, commit `35f1507` ([PR #17](https://github.com/JendaNDT/SkodaCAD/pull/17),
sloučené 07B). Navazuje na [Etapu 07 a krok 07A](12-navrh-etapa-07.md),
[07B – objemové pokrytí](13-navrh-etapa-07b.md), [Etapu 06](11-navrh-etapa-06.md)
a [závazné vymezení UT](04-zavazne-vymezeni-ut.md), které má přednost.
Ruční zkouška vydání Etapy 06 po sloučení zůstává odložená; tento návrh ji nenahrazuje.

## Co tento krok přinese

Dnes (po 07B) jde svar nebo jiný cílový objem zadat **jen ručně v JSON**, objemové pokrytí
spočítat **jen příkazovou řádkou** a v okně je tlačítko *Spočítat pokrytí* pro objem
záměrně vypnuté. Ve 3D se z objemu nic nekreslí.

Po 07C půjde celý postup naklikat v okně:

1. Ve studii UT dáš **Cílový objem…**. V dialogu vybereš *Tupý svar V*, *Koutový svar*
   nebo *Obecný hranol*, vyplníš polohu, směr, délku a rozměry. Vedle se kreslí
   **průřez** s osami a pod ním **zadaný objem ze vzorce** (průřez × délka).
2. Tlačítkem **Zkontrolovat v dílu** uvidíš účinný objem v materiálu nebo českou chybu
   („Zadaný svar není celý v materiálu dílu – chybí … mm³.“) dřív, než se cokoli uloží.
3. Ve 3D se cíl ukáže jako **průhledné modré těleso** uvnitř dílu, sonda zůstane vidět.
4. Přiložíš sondu jako dosud a v části *Mapa geometrického pokrytí UT* nastavíš krok pojezdu,
   **krok cíle** a necháš zapnuté **Ověřit citlivost na krok**. Panel před spuštěním ukáže
   odhad velikosti výpočtu. Výpočet běží na pozadí a jde zastavit.
5. Výsledek: v panelu procenta a mm³ všech tří stavů a citlivost na krok; ve 3D
   **obarvený povrch cíle** a tlačítkem **Průřez svarem** řez kolmo na osu svaru –
   posuvníkem řezu jedeš podél svaru a vidíš, kde uvnitř zůstává slepé místo.
6. **Export CSV** funguje jako v 07B (objem každého kusu v mm³, stav, důvod, předpoklady).

**Co se nemění:** výpočet a čísla 07B, výrobní geometrie, hmotnost a STEP, formát souboru
(zůstává **verze 16**), žádné nové knihovny, výsledky pokrytí se do souboru neukládají.
Plochy a jednotlivé body (Etapa 06) fungují beze změny.

## 1. Rozsah a hranice

| Patří do 07C | Nepatří do 07C (případně později a po dalším schválení) |
|---|---|
| Dialog pro cíl `weld` (tupý V, koutový) a `volume` (hranol z polygonu) | Automatické rozpoznání svarů z modelu |
| Kontrola cíle v dílu bez uložení, uložení jedním krokem Zpět | Obvodové a zakřivené svary, svary trubek |
| Průhledný náhled cíle ve 3D (i v řezu) | Odhad tepelně ovlivněné oblasti, rozsahy podle norem |
| Objemový výpočet z panelu: krok cíle, citlivost, odhad, zastavení | Rozměry svaru jako výrazy s parametry dílu |
| Barevná kresba výsledku na povrchu cíle a v řezu, tlačítko *Průřez svarem* | Slučování studií a sčítání procent |
| Ukázky cílových objemů v nabídce *Otevřít ukázku* (dnes chybí, nabídka nečte podsložku `examples/ndt/cilove_objemy/`) | Hledání nejlepší polohy sondy (etapa 09), protokol (PDF) |
| Self-test, testy okna, snímek okna, balíčky Windows a macOS | Nové nástroje AI asistenta pro cíl (pravidla `assistant.RULES` beze změny) |
| — | Hledání příčiny citlivosti na krok a změna výpočtu 07B (viz oddíl 4) |

## 2. Editor cílového objemu

### Kde a kdy

V panelu NDT přibude vedle *Oblast z výběru* tlačítko **Cílový objem…**. Je dostupné pro
vybranou studii, když je díl spočítaný a AI zrovna nepracuje. Dialog upravuje cíl vybrané
studie. Má-li studie zatím plochy, dialog začne výchozími hodnotami, které je nutné
přepsat (tupý V, počátek 0; 0; 0, podél +Y, napříč +X, délka 100 mm), a po potvrzení plochy
nahradí objemem (panel to řekne; jde to vrátit *Zpět*). Opačně *Oblast z výběru* nahradí
objem plochami jako dosud.

### Pole dialogu

| Pole | Hodnoty | Poznámka |
|---|---|---|
| Typ cíle | Tupý svar V · Koutový svar · Obecný hranol | `weld/butt_v`, `weld/fillet`, `volume` |
| Počátek X, Y, Z [mm] | čísla | význam podle typu, viz níže |
| Směr podél svaru (osa) | +X, −X, +Y, −Y, +Z, −Z | `frame.axis` |
| Směr napříč | jen směry kolmé na osu | `frame.across` |
| Výška průřezu míří do | jen ukázáno, např. „+Z“ | dopočte se jako napříč × osa (pravidlo 07A) |
| Délka [mm] | kladné číslo | `length_mm` |
| Rozměry tupého V | tloušťka, rozevření úkosu, kořenová mezera; převýšení (šířka u plechu, šířka vrcholu, výška); podkořen (totéž) | popisky z `welds.DIMENSION_LABELS`; převýšení a podkořen mohou být 0 |
| Rozměry koutového | rameno napříč, rameno na výšku | |
| Průřez hranolu | tabulka vrcholů (napříč, výška), *Přidat* / *Odebrat* | 3 až 256 vrcholů |

**Směry jen ±X/±Y/±Z** (doporučení, viz rozhodnutí 1): obě ukázky i běžné svařence
mají svar podél osy. Šikmý směr uložený v souboru dialog nezmění – ukáže ho jako
„vlastní směr ze souboru (0,6; 0,8; 0)“ a ponechá, dokud ho uživatel sám nepřepne.

**Co znamená počátek** (dialog to vypíše pod nákresem a zvýrazní počátek v nákresu):

- *Tupý svar V*: počátek = **střed kořenové mezery na straně kořene**. Tělo svaru sahá
  od 0 do tloušťky plechu ve směru výšky; převýšení je nad ním, podkořen pod ním.
  V `tupy_svar_objem.json`: počátek (0; −50; 0), podél +Y, napříč +X → výška +Z.
- *Koutový svar*: počátek = **kořen koutu** (kde se potkají obě plochy). Rameno napříč
  leží podél jedné plochy, rameno na výšku podél druhé. V `koutovy_svar_objem.json`:
  pravý svar (5; −50; 10), podél +Y, napříč +X; levý (−5; 50; 10), podél −Y, napříč −X.
- *Obecný hranol*: vrcholy průřezu se zadávají v rovině (napříč, výška) od počátku.

V ukázkových dílech je svar **součástí tělesa**, takže kořen svaru nemá vlastní hranu
ani plochu, na kterou by šlo kliknout. Proto je editor **číselný**. Pomůcka
**Podle vybrané rovné hrany** (aktivní, když je ve 3D vybraná právě jedna rovná hrana)
vyplní jen směr podél, délku a počátek na začátku hrany; počátek napříč a na výšku
je pak potřeba posunout do kořene ručně. Výpočet směru a délky z hrany dělá
`ModelSession` (okno samo geometrii nepočítá, pravidlo 8).

### Nákres průřezu a objem ze vzorce

Nákres je obyčejné 2D kreslení Qt (bez OCCT): polygony průřezu, osy „napříč →“
a „výška ↑ (+Z)“, počátek jako tečka a měřítko. Pod ním **Zadaný objem
(průřez × délka)**: obsah polygonů (Gaussův vzorec) × délka. Tělo, převýšení a podkořen
se dotýkají jen hranou, jejich obsahy se proto sčítají přesně. Pro ukázky vyjde
**14 613,843876 mm³** (tupý V) a **2 450 mm³** (koutový) – stejně jako analytické
hodnoty z 07A. Nesprávné zadání (nulový obsah, protínající se polygon, záporný rozměr,
rozevření mimo 0–180°) se ukáže česky hned pod polem a tlačítko *OK* zůstane vypnuté.
Kontrolu dělá táž funkce jako při načtení souboru (`welds.normalize_target`, přes
`ModelSession`).

### Zkontrolovat v dílu a uložení

- **Zkontrolovat v dílu** zavolá novou metodu `ModelSession.check_ndt_volume_target(target)`:
  `resolve_target` na aktuálním dílu **bez změny modelu**. Ukáže „Účinný objem v materiálu
  X mm³ (zadaný Y mm³, mimo materiál Z mm³)“ nebo českou chybu (svar mimo materiál,
  prázdný průnik hranolu s dílem).
- **OK** volá existující `set_ndt_volume_target` z 07A: jeden krok *Zpět*, zruší mapu
  i odborné ověření studie. Když jádro zadání odmítne, dialog zůstane otevřený
  s vyplněnými hodnotami a chybou.
- Dialog zapisuje **přesně tentýž JSON jako 07A** (formát 16 se nemění). Test ověří,
  že dialog otevřený na ukázkách a potvrzený beze změny vrátí identický cíl.

## 3. Náhled cíle ve 3D

- Cíl vybrané studie se kreslí jako **průhledné modré těleso** (účinný objem v materiálu).
  U hranolu, který částečně vyčnívá z dílu, se zadaný tvar navíc ukáže jen tenkým
  šedým obrysem hran – je vidět, co se do výpočtu nepočítá.
- Modrá se liší od barev tří stavů (zelená, červená, žlutá) i sondy (zelená, oranžová,
  červená), aby se náhled nepletl s výsledkem.
- U objemového cíle dnes ve 3D není vidět nic (zvýraznění oblasti umí jen plochy);
  náhled to doplní. Na rozdíl od zvýraznění ploch se kreslí **i s přiloženou sondou** –
  je průhledný, takže sondu ani dráhu paprsku nepřekryje.
- Kreslí se **navrch** (vrstva `Topmost`, jako zvýraznění): cíl leží uvnitř neprůhledného
  dílu a jeho stěny splývají se stěnami dílu, takže by jinak nebyl vidět (zjištěno snímkem
  při 07C.1).
  Když je zobrazená mapa pokrytí, náhled se skryje (mapa ho nahradí).
- Při zapnutém řezu se rozřízne i náhled (`section.cut` na tělese cíle).
- Tvar pro kreslení dá `ModelSession.ndt_target_preview(study_id)`; prohlížeč ho jen
  nakreslí (`gui/viewer.py`, jediné místo okna s OCCT).
- Jde o **nový druh kreslení „target“**: self-test ho podle známé pasti kreslí zvlášť
  (`_self_test_drawing`). Používá totéž, co sonda (`AIS_Shape` s průhledností), která už
  prošla na základním ovladači Windows (GDI Generic) i na softwarovém OpenGL Macu GitHubu.
  Popisky bez podkladu (`Aspect_TODT_SUBTITLE` se nepoužije).

## 4. Objemový výpočet v panelu

Skupina *Mapa geometrického pokrytí UT* pro studii s objemovým cílem:

| Pole | Výchozí | Poznámka |
|---|---|---|
| Zdroj poloh sondy | Po ploše přiložení | *Z přímé dráhy* jen s nenulovým rozevřením – jinak panel vypíše větu 07B „Pojezd po čáře bez rozevření svazku nevymezuje pokrytý objem…“ a tlačítko vypne |
| Krok pojezdu [mm] | 5 | dosavadní pole *Krok výpočtu*, přejmenované |
| **Krok cíle [mm]** | šestina menšího rozměru průřezu (V svar 2,5) | nové, jen pro objem; hrana buňky mřížky; původně 4 mm – změněno podle rozboru 15 |
| Rozevření (poloviční úhel) [°] | 0 | beze změny |
| **Tolerance zachycení [mm]** | Automaticky | nové, ve skupině *Pokročilé*; automaticky = krok pojezdu × 0,71 (plocha) / × 0,6 (čára) jako v 07B. Tooltip: „vyhledávací pomůcka, ne šířka svazku“ |
| **Ověřit citlivost na krok** | zapnuto (rozhodnutí 2) | navíc hrubší běh se dvojnásobnými kroky a stejnou tolerancí (`check_volume_convergence`) |

- **Odhad před spuštěním:** nová `ModelSession.ndt_coverage_estimate(...)` spočítá bez
  geometrických průniků počet kandidátních buněk a poloh sondy (stejné vzorce jako
  ochrany 07B). Panel ukáže např. „Odhad: 500 buněk, 609 poloh sondy; s citlivostí
  navíc hrubší běh“. Překročení limitů 07B (20 000 buněk, 80 000 000 porovnání)
  vypne tlačítko s radou zvětšit krok – ještě před spuštěním.
- **Na pozadí:** dosavadní pomocný proces (`BackgroundRebuilder.submit_coverage`),
  volba citlivosti se mu předá. Během výpočtu panel ukazuje uplynulý čas, *Zastavit* ukončí
  proces. Výsledek zastaralého nebo zrušeného výpočtu se nezobrazí (dnešní
  `_coverage_context`).
- **Výsledek:** panel vypíše souhrn 07B beze změny textů – povinné `UT_DISCLAIMER`,
  `PERCENT_NOTE`, větu o aproximaci, mm³, procenta, kroky, toleranci a citlivost. Nahoře
  tučně tři procenta. Při rozdílu nad 1 p. b. oranžově „Výsledek je citlivý na krok –
  zjemni krok“; bez porovnání „Citlivost na krok neověřena“.

**Změřená doba** (cloudový počítač vývoje, V svar `tupy_svar_objem.json`, sonda 70°,
bez odrazů, pojezd po pravé horní ploše; jiný počítač bude jinak rychlý):

| Kroky pojezdu / cíle | Jemný běh | Celkem s citlivostí | Pokryto (jemný / hrubý) | Rozdíl |
|---|---|---|---|---|
| 5 / 2 mm, tolerance automaticky (3,54 mm) | 104,9 s | 139 s | 12,22 % / 5,59 % | 6,63 p. b. |
| 5 / 4 mm, tolerance automaticky (3,54 mm) | 35,9 s | 48 s | 9,02 % / 12,90 % | 3,88 p. b. |
| 5 / 4 mm, tolerance 8 mm | 35,3 s | 50 s | 9,02 % / 21,50 % | 12,48 p. b. |

„Celkem“ je doba celého příkazu `skodacad pokryti … --konvergence` včetně spuštění
a přepočtu dílu. Týž jemný běh 5/2 mm trval v 07B při místní zkoušce na jiném počítači
přibližně 42 s místo 104,9 s.

Čísla platí jen pro tuto jednu polohu a sondu. Plynou z nich dvě věci:

- **Výchozí nastavení musí být rychlý první pohled** (5/4 mm: necelá minuta i s citlivostí);
  jemnější výpočet si uživatel zvolí vědomě.
- **Tento V svar je na krok citlivý při všech změřených nastaveních** a větší tolerance to
  tu nespravila (na rozdíl od jiné dvojice kroků v 07B). 07C proto citlivost ukáže nahlas
  a barevný průřez pomůže najít, *kde* se jemný a hrubý výpočet liší. Hledání příčiny
  a případná úprava výpočtu 07B **nejsou součástí 07C** – jsou to samostatný další krok
  po dalším schválení.

## 5. Kresba výsledku: povrch cíle a průřez svarem

### Jak se obarví

07B záměrně neposílá z pomocného procesu žádnou geometrii, jen čísla každého kusu
(buňka, objem, stav). Kresbu proto spočítá `ModelSession.visible_ndt_coverage()` v okně
z toho, co už má:

1. Účinné těleso cíle znovu z `resolve_target` na **témž dílu**, pro který výsledek platí
   (desítky ms; uloží se do mezipaměti spolu s výsledkem).
2. Je-li zapnutý řez, cíl se rozřízne stejnou rovinou (`section.cut`). Rozříznuté těleso
   má mezi plochami i **plochu řezu** – průřez svarem se tím obarví sám, bez zvláštního
   výpočtu „víčka“.
3. Povrch tělesa se rozdělí na trojúhelníky (OCCT) a každý trojúhelník se rozřeže podél
   rovin **mřížky 07B** (stejný počátek, osy, krok cíle). Každý úlomek leží celý v jedné
   buňce a dostane barvu stavu jejího kusu. Uzly úlomků se nesdílejí, barvy se tedy
   nepřelévají (jako mapa Etapy 06).
4. Buňka s **více kusy** (např. hranol přes otvor): kus se pozná podle svého ohraničujícího
   kvádru. K tomu 07C přidá ke každému vzorku jen čísla mezí kusu (`piece_bounds`);
   výpočet, procenta, CSV ani algoritmus 07B se nemění. Když úlomek nejde jednoznačně
   přiřadit, nakreslí se **šedě – „nerozlišeno v kresbě“**, nikdy zeleně. Na čísla to
   nemá vliv.
5. Kus bez vnitřního bodu (stav *Nelze spolehlivě vyhodnotit*) se kreslí žlutě – barva
   se bere z buňky, ne z bodu, takže i takový kus je vidět.

Prohlížeč pak použije existující `show_coverage_map` (žádný nový druh kreslení pro mapu),
jen doplněný o šedé plochy řezu dílu – stejně, jako to už umí mapa tloušťky (`fill`).
Řez je dál **jen pohled**: nemění jmenovatel ani procenta (hlídá test).

**Ověřeno prototypem** (skript mimo repozitář, `build123d` + čistý Python, krok cíle 2 mm):

| Cíl | Povrch cíle | Součet obarvených úlomků | Úlomků | Čas | Plocha řezu Y = 0 | Součet úlomků v řezu |
|---|---|---|---|---|---|---|
| Tupý V (`tupy_svar_objem.json`) | 6 681,870 mm² | 6 681,870 mm² | 3 112 | 0,15 s | 146,1384 mm² | 146,1384 mm² (92 úlomků, 0,07 s) |
| Koutový (`koutovy_svar_objem.json`, s1) | 2 438,949 mm² | 2 438,949 mm² | 932 | 0,04 s | 24,5000 mm² | 24,5000 mm² (10 úlomků) |

Plocha řezu tupého V odpovídá vzorci: 14 613,843876 mm³ / 100 mm = 146,1384 mm².
Při kroku cíle 1 mm: 9 078 úlomků za 0,65 s. Kresba tedy nebude brzdou; drahý zůstává
samotný výpočet pokrytí.

### Co uvidíš

- **Bez řezu:** díl drátěně (jako mapa Etapy 06), povrch cíle barevně. Panel připomene:
  „Barevný je jen povrch cíle. Dovnitř se podívej tlačítkem *Průřez svarem*.“ Obarvený
  povrch tak nikdy není jediné zobrazení objemu (podmínka návrhu Etapy 07).
- **Průřez svarem:** zapne *Řez modelem* kolmo na osu cíle uprostřed jeho délky. Posuvník
  řezu pak jede podél svaru (rozsah = délka cíle). Plochy řezu dílu jsou šedé, průřez
  cíle barevný. Nový druh roviny řezu „kolmo na osu cíle“ v `ModelSession.section_settings`
  (jen pohled, neukládá se). Funguje i obyčejný řez X/Y/Z.
- Legenda zůstává: zelená *Geometricky pokryto*, červená *Geometricky nepokryto*, žlutá
  *Nelze spolehlivě vyhodnotit*, nově šedá *Nerozlišeno v kresbě* (jen kresba).
  Pod legendou věta 07B: „Stav vnitřního bodu zastupuje objem jeho kusu buňky; není
  důkazem zásahu každého místa.“

## 6. Co zůstává závazné

- Název vždy **Mapa geometrického pokrytí UT**; plné `UT_DISCLAIMER` a `PERCENT_NOTE`
  v panelu, CSV i souhrnu; žádná zakázaná označení (hlídá `tests/test_ndt_scope.py`,
  i v komentářích).
- Procento = geometrický podíl zadaného objemu, ne pravděpodobnost nalezení vady.
  Svar je **nominální zadaná oblast**, ne rozpoznaná hranice natavení.
- Okno modeluje jen přes `ModelSession`; každá úprava = jeden krok *Zpět*; výsledky
  pokrytí se neukládají; formát zůstává 16; výrobní díl se nemění.
- Změna dílu, cíle, sondy nebo přiložení mapu zruší; zastaralá studie se nepočítá.

## 7. Ověření před předáním

| Scénář | Podmínka převzetí |
|---|---|
| Dialog na ukázkách (tupý V, oba koutové) potvrzený beze změny | identický JSON cíle; zadaný objem 14 613,843876 / 2 450 mm³ ze vzorce |
| Hranol 10 × 20 × 30 mm v dialogu | zadaný objem 6 000 mm³; *Zkontrolovat* ukáže účinný objem z jádra |
| Svar mimo materiál, prázdný hranol, protínající se polygon | česká chyba, model beze změny, dialog zůstane otevřený |
| Vlastní (šikmý) směr ze souboru | dialog ho ukáže a zachová |
| *OK* v dialogu | jeden krok *Zpět*; mapa i ověření zaniknou; *Znovu* vrátí cíl |
| Pomůcka z rovné hrany | směr a délka hrany; jiná než rovná hrana = tlačítko vypnuté |
| Kresba celého pokrytého kvádrového cíle 10 × 20 × 30 mm (přímá sonda nad ním jako v testu 07B) | všechny úlomky zelené; součet ploch = povrch kvádru 2·(10·20 + 10·30 + 20·30) = 2 200 mm² |
| Kresba desky 200 × 100 × 20 mm v řezu z = 10 mm | součet úlomků v řezu = 20 000 mm²; zelená plocha v mezích odvozených z kroků a tolerance, při zjemnění se blíží 190 × 90 = 17 100 mm² (analytická mez 07B) |
| Nabídka *Otevřít ukázku* | podnabídka *NDT – cílové objemy* otevře obě ukázky; test ukázek je dál všechny postaví |
| Hranol přes otvor (více kusů v buňce) | správné přiřazení podle mezí kusu; nejednoznačné = šedé, nikdy zelené |
| Řez zapnutý / vypnutý / posunutý | procenta a mm³ výsledku beze změny, jen kresba |
| Panel: objem s přiloženou sondou | *Spočítat pokrytí* zapnuté; čára bez rozevření vypnutá s větou 07B; odhad; limity |
| Citlivost na pozadí | stejná čísla jako synchronně a jako CLI `--konvergence`; *Zastavit* nevrátí starý výsledek |
| Plochy a body Etapy 06 | referenční výsledky, mm², bodové počty a plošná kresba beze změny |
| Upozornění a zakázaná slova | `UT_DISCLAIMER` v panelu, `test_ndt_scope.py` prochází |
| Self-test okna | kreslení „target“, objemová mapa s nenulovou kresbou (dnešní kontrola „prázdná kresba“ se obrátí), snímek |
| Skutečné okno pod Xvfb | snímky: dialog, náhled cíle se sondou, mapa na povrchu a v průřezu svarem – ukázat autorovi (pravidlo 9) |
| Balíčky | sestavení a self-test staženého balíčku Windows i macOS |

Před každým commitem `ruff check src tests` a celé `pytest -q`; testy okna s dialogem
dialog nahradí (`no_dialogs`, `MainWindow._exec_dialog`) a běží s `timeout`.
Vývojové testy **nedokazují ruční funkčnost na autorově počítači** ani na MacBooku.

## 8. Malé kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **07C.1 – editor a náhled cíle** | dialog *Cílový objem…*, `check_ndt_volume_target`, pomůcka z hrany, `ndt_target_preview`, kreslení „target“, podnabídka *NDT – cílové objemy* | testy dialogu a Zpět/Znovu, self-test kreslení, snímek |
| **07C.2 – výpočet v panelu** | krok cíle, tolerance, citlivost, odhad, pomocný proces, souhrn | testy panelu a pozadí, shoda s CLI |
| **07C.3 – kresba a předvedení** | `piece_bounds`, obarvení povrchu a řezu, *Průřez svarem*, legenda, self-test, balíčky | analytické plochy kresby, snímky, Windows/macOS |

Každý krok má vlastní commit s testy. Do `main` se nic nesloučí bez pokynu autora.

## 9. Praktická zkouška pro autora (po 07C.3)

1. *Soubor → Otevřít ukázku → NDT – cílové objemy → tupy_svar_objem*, vybrat studii
   *UT objemu V svaru*: ve 3D modrý svar uvnitř plechu.
2. *Cílový objem…*: zkontrolovat průřez a 14 613,84 mm³; změnit tloušťku svaru na 20 mm
   a dát *Zkontrolovat v dílu* → česká chyba „Zadaný svar není celý v materiálu dílu –
   chybí 16586,8 mm³“ (ověřeno na jádru); *Storno*.
3. V *Sonda…* nastavit úhel paprsku 70° a odrazy 0 (jako měření v oddílu 4), kliknout
   na pravou horní plochu plechu, směr 180°, *Přiložit sondu sem*.
4. *Spočítat pokrytí* s výchozími kroky → po doběhnutí procenta, citlivost, barevný
   povrch svaru; *Průřez svarem* a posouvat řez podél svaru.
5. *Export CSV* a otevřít v Excelu (středník, desetinná čárka).
6. Změnit parametr tloušťky plechu `t`: mapa zmizí, studie je zastaralá a chce potvrzení.

Tím se zároveň dá udělat odložená ruční zkouška Etapy 06 (mapa ploch) – ale jen pokud
ji autor opravdu provede a potvrdí; návrh ji nepovažuje za hotovou.

## 10. Rozhodnutí autora

Prosím o schválení nebo úpravu těchto bodů (doporučení je vždy první):

1. **Směry v editoru jen ±X/±Y/±Z** (šikmé směry ze souboru se zachovají) –
   *doporučeno*, jednodušší a bez chyb z ručně psaných vektorů.
   Alternativa: libovolný vektor (tři čísla) – víc práce a víc příležitostí k chybě.
2. **Citlivost na krok ve výchozím stavu zapnutá** – *doporučeno*; výpočet trvá déle,
   ale panel nikdy neukáže číslo bez informace o jeho stabilitě.
3. **Výchozí kroky pojezdu 5 mm a cíle 4 mm** jako rychlý první pohled – *doporučeno*
   (u V svaru necelá minuta i s citlivostí); jemnější výpočet je volba uživatele
   (panel radí „zjemni krok“). *Změněno 17. 10. 2026 podle
   [rozboru citlivosti](15-rozbor-citlivosti-v-svaru.md): krok cíle je výchozí šestina
   menšího rozměru průřezu (V svar 2,5 mm, koutový 1 mm) – 4 mm byly o 3,2 p. b. vedle.*
4. **Tlačítko *Průřez svarem*** (řez kolmo na osu cíle) – *doporučeno*; je to pohled,
   na který je NDT technik zvyklý.

Schválením se **neschvaluje**: automatické rozpoznání svarů, obvodové/zakřivené svary,
odhad tepelně ovlivněné oblasti, změna výpočtu 07B nebo formátu, nové knihovny ani
sloučení do `main`.

**Autor 17. 10. 2026 napsal „schvaluji 07C“** – schváleny body 1–4 tak, jak jsou doporučené.

## 11. Provedení a upřesnění

| Krok | Co vzniklo | Ověření |
|---|---|---|
| 07C.1 | `gui/target_dialog.py`, `ModelSession.check_ndt_volume_target`, `ndt_target_outline`, `ndt_frame_from_edge`, `ndt_target_preview`, `viewer.show_target`, podnabídka *NDT – cílové objemy* | testy dialogu (identický JSON, chyby, Zpět), self-test „target“, snímky |
| 07C.2 | pole *Krok cíle*, *Tolerance zachycení*, *Ověřit citlivost na krok*, `ndt_coverage_estimate`, `compute_ndt_coverage(convergence=True)` i v pomocném procesu | shoda s přímým porovnáním i s pomocným procesem, testy panelu, okno spočítalo 9,02 % jako CLI |
| 07C.3 | `ndt/volume_drawing.py`, `VolumeSample.piece_bounds`, `set_section_target` (*Průřez svarem*), šedá legenda, kreslení „map_top“ | plochy kresby = povrch / průřez cíle, buňka se dvěma kusy u otvoru, self-test 600/400 mm², snímky |

Upřesnění proti návrhu (bez změny výpočtu 07B a formátu):

- **Náhled cíle i objemová mapa se kreslí navrch** (vrstva `Topmost`): cíl leží uvnitř
  neprůhledného dílu a jeho stěny splývají se stěnami dílu – v běžné vrstvě nebyl na snímku
  vidět. Plochy řezu dílu jsou pod mapou šedé (červená je „nepokryto“); panel *Řez* to
  píše („šedě pod mapou pokrytí“). Self-test kreslí druh „map_top“ zvlášť.
- *Průřez svarem* je nový druh řezu (`TargetSection`): poloha = vzdálenost od začátku cíle
  0 … délka, rovina míří k pozorovateli v izometrii. Jde zvolit i v panelu *Řez*
  (*Kolmo na osu cíle*). Posun a otočení řezu druh zachovají (`dataclasses.replace`).
- Skupina sondy a formulář pokrytí se nevešly do doku (panel se posouval do strany –
  starší stav); tlačítka sondy a krokování jsou nově po dvou řádcích, formulář zalamuje
  dlouhé popisky.
- Výsledek V svaru (`tupy_svar_objem.json`, sonda 70°, bez odrazů, kroky 5/4 mm) spočítaný
  v okně: pokryto **9,02 %**, nepokryto 90,98 %, citlivost **3,88 p. b.** (oranžově „zjemni
  krok“); 45–49 s na cloudovém počítači. V průřezu svarem je zelený jen pás u kořene.
