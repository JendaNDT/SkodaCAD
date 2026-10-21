# P1.2A — konkrétní návrh společné kontroly geometrie

**Stav: A1–A7 schváleno autorem 20. 10. 2026; implementace probíhá.**
Podklad: `main / 6e38d0681ac495c08189cd6f129cafe7166a2c7a`, po sloučení
[PR #31](https://github.com/JendaNDT/SkodaCAD/pull/31).
Závazná pravidla jsou ve [schválené smlouvě P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md);
tento návrh je nemění. Rozpracovává její první implementační krok.

## 1. Schválený rozsah

Cíl: geometrický výsledek se přijme až po společné kontrole. Neplatný či prázdný
výsledek se nesmí stát přijatým dílem. Platný díl může mít více objemových těles;
uživatel uvidí jejich skutečný počet a jeho změnu.

| Bod | Schválený konkrétní rozsah |
|---|---|
| **A1 Společná kontrola** | Malý interní modul `geometry_validation.py`: kontrola objemových tvarů, čísel, uzavřenosti, počtu složek a objemových podmínek P1.1. Bez nové závislosti, veřejného rozhraní nebo ukládaných polí. |
| **A2 Zapojení do geometrie** | Kandidát před zápisem v `BuildContext.apply` i v zaoblení, sražení a skořepině; závěrečná pojistka všech 3D prvků v `_run_feature`. Pravidla zahrnou i nástroje děr, závitů, pole, zrcadlení, loftu a normalizovaných dílů. |
| **A3 Čísla a změny chování** | Konečné hodnoty používané geometrií hlídat v `BuildContext.num`; zachovat tolerance P1.1. Odmítnout přidání bez účinku, neobjemové/vadné složky a skořepinu bez otevřené plochy. Žádná automatická oprava nebo zvětšování tolerancí. |
| **A4 Stejné zprávy všude** | Využít existující `FeatureStatus.message` pro úspěšný 3D prvek: počet před → po. Zobrazit jej viditelně v okně, CLI a souhrnu AI; konečný počet uvádět i pro 1 těleso. Bez změny JSON nebo protokolu workeru. |
| **A5 Regrese a kompatibilita** | Splnit matici níže: analytické objemy i poloha, všechny složky, chyby, poslední platný díl, přenos, Zpět/Znovu a všech 26 současných ukázek. Formát 22 a načítání verzí 1–22 zůstanou zachované. |
| **A6 Malé kroky** | Jedna implementační větev/PR se třemi postupnými kroky A.1–A.3. Po každém Ruff a celý pytest před commitem. Schválení A1–A7 dovolí tyto kroky bez opakovaného schvalování téhož rozsahu. |
| **A7 Přijetí a hranice** | Windows i macOS: testy, baseline, sestavení a self-test staženého balíčku; cílená ruční zkouška. Úplná obnova kontextu P1.2B, reference P1.3, export/NDT P1.4, P2 a nový formát zůstávají mimo. Sloučení implementačního PR vyžaduje souhlas autora. |

Autor po předložení návrhu potvrdil A1–A7 slovy „ok, schvaluji“.
Dokumentační [PR #32](https://github.com/JendaNDT/SkodaCAD/pull/32) je sloučený
(`15b8bf4`). Tím je povolena implementace A.1–A.3 v jednom samostatném PR.
[Průběh a skutečná evidence](p1-2a-overeni.md) rozlišují hotové kontroly od dosud
neprovedeného přijetí. Sloučení implementačního PR dál vyžaduje souhlas autora.

## 2. Ověřený výchozí stav a místa změn

| Současné místo | Co dělá dnes | Navržený zásah |
|---|---|---|
| `features.BuildContext.apply` | `new/add` kontrolují objem nástroje; `cut` také úbytek a úplné odebrání. `add` bez účinku projde. | Vstup A, nástroj B a kandidát R projdou společnou kontrolou; při zamítnutí se tato podoperace nezapíše ani nezaznamená. |
| `build_fillet/chamfer/shell` | Výsledek jádra se zapisuje přímo do `ctx.part`; prázdné `open_faces` jsou povolené. | Nejprve místní kandidát, pak kontrola a teprve zápis. Skořepina vyžaduje skutečně nalezené otevřené plochy. |
| `rebuild._run_feature` | Kontroluje jen `is_valid`, a to jen při změně identity objektu; při chybě vrací `part_before`. | Závěrečná kontrola úspěšného 3D prvku nezávisle na identitě objektu; zachovat existující chybový tok a přeskočení zbytku. |
| `rebuild.FeatureStatus` | Má již pole `message`, ale u úspěchu je prázdné. | Naplnit zprávu počtem před/po celém úspěšném 3D prvku. Nové pole ani stav nejsou potřeba. |
| `gui.MainWindow._refresh_tree` | Zprávu dává do tooltipu, do textu stromu ji nepřidává. | Krátký viditelný údaj o počtu u 3D prvku; plné znění v tooltipu. |
| `cli._build`, `assistant.build_report` | Zprávu prvku vypisují pouze při chybě. | U úspěšných 3D prvků vypisovat také informaci o počtu. |
| Vlastnosti dílu | `PartProperties.solids` už existuje; GUI/CLI zvlášť upozorňují jen při N≠1; AI konečný počet uvádí. | GUI/CLI vždy uvedou konečný počet. AI zachová souhrn a přidá změny u prvků. |
| `worker.encode_result/decode_result` | Přenášejí existující seznam stavů včetně zpráv a geometrii přes BinTools. | Zachovat strukturu přenosu; doplnit test zprávy přes skutečný proces. |

Průzkum na stávajícím build123d 0.13.0 / OCCT 8.0.1 potvrdil:
`Part()` má `is_valid=True`, ale objem 0 a žádný solid. Složený tvar může obsahovat
jeden validní solid a samostatnou volnou plochu. Počet solidů tedy sám nestačí.
`TopoDS_Iterator` dovoluje projít vnořené kontejnery; uzavřenost shellů lze číst
přes `BRep_Tool.IsClosed_s(shell.wrapped)`. Nezavádět neexistující obecnou vlastnost
`Shape.is_closed`. Prázdný tvar ošetřit před přístupem k `wrapped`.

Jde o ověření dostupného rozhraní, nikoli hotový validátor nebo novou regresní sadu.

## 3. Návrh společné kontroly

### 3.1 Malý interní modul

Nový `src/skodacad/geometry_validation.py` bude záviset pouze na již instalovaném
build123d/OCCT a standardní knihovně. Nebude importovat Qt, session, dokument ani NDT.

Navržené odpovědnosti: přečíst ověřené vlastnosti tvaru, ověřit pravidlo operace
a sestavit společnou informaci o počtu těles. Výsledek inspekce může být malá
neměnná interní struktura s počtem solidů, objemem, objemy složek a obálkou.
Nejde o modelový formát: neukládá se, nepřenáší workerem a nerozšiřuje `BuildResult`.

Modul při neúspěchu vrátí přesnou českou příčinu interní výjimkou; `features.py`
ji převede na `FeatureError` s názvem operace a radou. Tím nevznikne cyklický import.
Bez obecného systému registrací, nových režimů nebo plošného přepracování tříd.

### 3.2 Objemový tvar

Kontrola nástroje i kandidáta musí:

1. Rozlišit chybějící tvar a prázdný tvar; pro 3D vyžadovat alespoň jeden solid.
2. Projít vnořené `Compound/CompSolid` a jejich skutečný obsah. Samostatný shell,
   plocha, drát, hrana, bod nebo prázdná složka mimo objemová tělesa jsou chyba.
   Nestačí jen vybrat `.solids()` a zbytek zahodit. Solid s dutinou nebo průchozí
   dírou je povolen; vnitřní shell není volná plocha.
3. Ověřit `is_valid` celku i každého solidu a uzavřenost všech jeho hraničních
   shellů. Otevřený shell není platný materiál ani při kladně vypočteném objemu.
4. Ověřit konečnost používaných čísel, souřadnic vrcholů, obálky a objemů.
   Tato kontrola spolu s platností topologie není novým slibem metrologické přesnosti.
5. Pro každý solid požadovat `Vi > 10⁻⁹ × max(1 mm³, abs(Vi))`.
   Pro výsledek požadovat také rozlišitelný celkový objem podle P1.1.
   Vadná/drobná složka se nevynechává; odmítne se celý kandidát.

Nástroj B může obsahovat několik oddělených řezaček nebo přídavků. Jeho počet
nemusí odpovídat počtu solidů výsledného dílu. Meze účinku se nesmějí zvětšit kvůli
zbytečně dlouhé řezačce díry: její objem do `εV(A,R)` nepatří.

### 3.3 Čísla, tolerance a podmínky operací

`BuildContext.num` po vyhodnocení každé geometricky používané hodnoty ověří
`math.isfinite`. Dnes číselný vstup do `expressions.evaluate` odchází před kontrolou
konečnosti; návrh tuto cestu uzavře na hranici geometrie. Celý obecný vyhodnocovač
výrazů ani číselná pravidla NDT se tím nepřepracovávají. Kladné rozměry dál hlídá
`positive`; souřadnice/posuny/úhly mohou být záporné, ale vždy konečné.

Platí schválená `εL=10⁻⁶ mm` pro analytická porovnání rozměrů a
`εV=10⁻⁹ × max(1 mm³, abs(VA), abs(VR))` pro objem/účinek.
Při prvním tělese je VA=0. Na hranici `účinek ≤ εV` nastane chyba.
Žádné změny tolerancí skic, sémantických výběrů ani NDT.

| Cesta | Povinné podmínky před přijetím |
|---|---|
| `new` | A chybí; B/R splňují objemovou smlouvu. Druhé `new` se dál odmítá. |
| `add` bez A | Stejné jako první `new`; dnešní způsob založení dílu zůstává. |
| `add` s A | Platné A, B i R; `VR−VA > εV`, `VR ≤ VA+VB+εV`; žádná složka se nezahodí. Počet může růst, klesat i zůstat stejný. |
| `cut` | Platné A, B i R; `VA−VR > εV`, `VR > εV`. Řez mimo/tečný a úplné odebrání celého dílu jsou chyby. Odstranění jednoho z více solidů je povoleno, zůstane-li platný rozlišitelný díl. |
| Zaoblení/sražení | Kladná konečná hodnota, nalezené hrany; platný kandidát, stejný počet solidů jako před úpravou. Objem smí růst u vnitřního rohu. |
| Skořepina | Kladná konečná tloušťka; neprázdné nalezené otevřené plochy; platný kandidát, stejný počet solidů, `0 < VR < VA−εV`. |

Skutečný význam `A∪B / A∖B` a požadovanou polohu materiálu musí doložit také
prostorové reference v testech. Samotné objemové nerovnosti nejsou důkazem správnosti
jádra. Tento rozsah nepřidává druhou sadu kontrolních booleovských operací při každém
přijetí ani netvrdí obecnou detekci všech chyb OCCT; odpovídá vymezení P1.1.

## 4. Zapojení bez částečného přijetí kandidáta

`BuildContext.apply` přečte dosavadní A a nástroj B, ověří je, vypočte místní R,
ověří R a podmínky operace a teprve potom nastaví `ctx.part` a přidá záznam této
podoperace do `recording`. Při odmítnutí se tato podoperace nesmí objevit jako přijatá.
Chyby jádra dostanou český popis operace; dosavadní konkrétní rady `empty_cut` zůstanou.

Zaoblení, sražení a skořepina stejně vytvoří místního kandidáta; přijatý díl se
nepřepíše dříve, než kandidát projde kontrolou. Chybu validátoru nebalit do
nepravdivé zprávy „poloměr je příliš velký“, jestli skutečná příčina je vadná složka.

Závěrečná pojistka v `_run_feature` pokryje typy:
`extrude, revolve, sweep, loft, standard, hole, pattern, mirror, fillet, chamfer, shell`.
Kontroluje i případ vrácení stejného objektu a nečekané `part=None` po úspěšném
3D prvku. Povinnost doplnit tento seznam při budoucím novém typu bude popsaná
a testovaná proti současnému registru. Skica není 3D prvek: platný dokument
tvořený skicami může mít `part=None` a nedostane falešnou chybu objemu.

Kontrola výsledku neopakuje modelování v GUI. Pravidla platí i při přepočtu
v pomocném procesu a v přímém volání jádra. Existující postupy tvorby tvarů
(závit, uzavřená trasa tažení, fallback dutého loftu) se nepřepisují;
jejich zvolený výsledný nástroj musí projít společnou kontrolou.

**Hranice vůči P1.2B:** P1.2A zajistí nepřijetí vadného kandidáta a zachování
posledního platného tělesa při chybě prvku dnešním mechanismem `part_before`.
Nezavádí úplný snímek/obnovu `sketches, operations, recording` ani hluboké kopírování
celého kontextu. Složený prvek může před chybou poslední podoperace vykonat předchozí
podoperace; celková transakce je P1.2B. R05 proto nelze uzavřít v P1.2A.
Regrese P1.2A ověří zachování geometrie i hodnotově; pouhá shoda objektu nestačí.

## 5. Výstup pro uživatele a přenos

Jedna společná zpráva vznikne až po úspěchu celého 3D prvku, z `parts_before`
a konečného přijatého tvaru. Nehlásit všechny dílčí kroky pole/závitu a neoznačit
neúspěšný pokus za úspěšnou změnu počtu.

Příklady navržených textů:

- První těleso: „Počet těles: 0 → 1.“
- Oddělený přídavek nebo rozdělující řez: „Počet těles: 1 → 2. Výsledek obsahuje
  2 samostatná objemová tělesa.“
- Odebrání jednoho ze dvou: „Počet těles: 2 → 1.“
- Pole tří trubek: „Počet těles: 1 → 3. Výsledek obsahuje 3 samostatná objemová tělesa.“
- Úprava bez změny počtu: „Počet těles: 1 → 1.“

U první vícesolidové operace bude obdobně 0 → N. Počet pochází z topologie jádra;
netvrdí fyzické spojení v mezerách pod numerickým rozlišením.

| Rozhraní | Přijetí zprávy |
|---|---|
| GUI | Krátké „tělesa: před → po“ přímo u úspěšného 3D prvku ve stromu, plná zpráva v tooltipu. Ve vlastnostech vždy „Počet těles: N“. Úspěch zůstává zeleným úspěchem, bez chybového dialogu. |
| CLI `build` | Zpráva také u úspěšného 3D řádku; konečný počet ve vlastnostech. Existující návratové kódy a exportní pravidla se nemění. |
| AI `build_report` | Tatáž zpráva u úspěšných 3D prvků; zachovaný souhrn geometrie, počtu těles a chyb. Testovat offline bez API klíče či síťového volání. |
| Worker | Zprávy přežijí `encode_result → pickle → decode_result` i skutečný `spawn`; žádné nové klíče/příkazy protokolu. |
| Chyba/přeskočení | Stavy zůstávají `ok/error/skipped`. Chyba má příčinu a radu; přeskočený prvek nemá vymyšlený počet výsledku. Nezmění se tím zacházení s chybným modelem v exportu/NDT. |

Navržené chyby například: „Přidání nepřidalo rozlišitelný materiál – změň polohu
nebo rozměry přídavku.“; „Skořepina potřebuje alespoň jednu otevřenou plochu –
vyber plochu, kterou chceš odstranit.“; „Výsledek obsahuje neuzavřenou objemovou
složku – uprav poslední prvek nebo použij Zpět.“
Text se může jazykově doladit, ale musí sdělit skutečnou příčinu a možnost nápravy.

## 6. Konkrétní regresní sada po schválení

**Matice přijetí.** Skutečný stav sad a výsledky jsou v [evidenci P1.2A](p1-2a-overeni.md).
ID G/N/A/C/F/H/S/L/M/T odkazují na přesná zadání a vzorce v P1.1.
U odmítnutí kontrolovat chybu, přeskočený následný prvek a původní díl
(objem, obálku, počet i referenční materiál v místě); u samostatného `apply`
také nezapsání odmítnuté podoperace. Úplný kontext složeného prvku testuje až P1.2B.

| Sada | Zadání a očekávaný výsledek | Navržené umístění |
|---|---|---|
| V1 / G01–G04 | Prázdný `Part`, otevřený shell s kladným objemem, vadná/malá složka, solid + volná plocha/hrana, vnořené kontejnery. Chyba bez tichého odstranění; platný víceobjemový nástroj a dutina projdou. | nový `tests/test_geometry_validation.py` |
| V2 / čísla | NaN/±Inf jako přímé číslo, parametr a použitý výraz; odmítnutí před geometrickou operací. Nulové/záporné rozměry zůstanou chyby, záporné konečné posuny zůstanou platné. | nový soubor + `test_rebuild_errors.py` |
| V3 / N01–N03 | První `new` i `add`: 24 000 mm³; druhé `new` chyba; dvě kružnice Ø10 vysunuté 10 dávají 500π mm³ a 2 solidy. | `test_features.py`, `test_rebuild_errors.py` |
| V4 / A01–A05 | Překryv 36 000 mm³, plošný dotyk 24 250/N=1, oddělený i hranový/bodový dotyk 24 250/N=2; vnitřní/totožný přídavek nově chyba. Kontrolovat i polohu a zachovaný materiál A. | nový soubor + `test_features.py` |
| V5 / C01–C05 | Kapsa 23 750; řez mimo/tečný a celý díl chyba; rozdělení 21 600/N=2; dvě řezačky v desce 16 000−80π/N=1. Kontrolovat obě skutečné díry a materiál mimo ně. | nový soubor + `test_features.py` |
| V6 / F01–F03, H01–H03 | Zachovat analytické vnější rohy; vnitřní L po R2 má 3 000+(4−π)×10, po s=2 má 3 020 mm³. Stejný počet; R50/s50, chybějící hrany, nula a záporné rozměry jsou chyby. | `test_features.py`, `test_rebuild_errors.py` |
| V7 / S01–S02 | Otevřený vršek 50×30×20/t2: 8 472 mm³, původní obálka a tloušťka. Vynechané/prázdné otevřené plochy i neproveditelná stěna chyba. | `test_features.py`, `test_rebuild_errors.py` |
| V8 / L01–L04 a cesty | Loft 28 000 a 7 000π mm³, vadné profily odmítnout; zachovat obě existující interpretace tloušťky dutého loftu. Pro každý současný 3D typ doložit cestu společnou kontrolou, včetně rotace, tažení, normalizovaného dílu a závitu. | `test_sweep_loft.py`, existující testy příslušných prvků |
| V9 / M01, hranice M02 | Pole tažení nadále 3 validní solidy a trojnásobný objem; pole/zrcadlení děr zachovají polohy. Při selhání pozdní podoperace zůstane poslední díl před celým prvkem; netvrdit tím obnovu skic/operací. | `test_pattern.py`, `test_sweep_loft.py`, `test_rebuild_errors.py` |
| V10 / T01–T03 | Mezery 10⁻⁵/N=2 a 10⁻⁸/N∈{1,2}, rozměry a objemy podle P1.1. Rozhodovací hranice účinku 0, 0,5 εV, εV, 2 εV a měřítka 0,1/1/10. Viz odlišení numerické a geometrické zkoušky níže. | nový soubor |
| V11 / výstupy | Shodné počty/zprávy 0→1, 0→2, 1→2, 2→1, 1→3 a 1→1 v jádře/CLI/AI/GUI; informace není chyba. Poslední platný náhled při chybě se nehlásí jako úspěch chybného prvku. | `test_examples_and_cli.py`, `test_assistant.py`, `test_gui.py` |
| V12 / přenos a historie | Přenos přes BinTools/pickle a skutečný worker; shodná geometrie, zprávy a stavy. Novou chybu přidání/skořepiny lze vzít Zpět, Znovu a opravit bez změny původního souboru. | `test_background.py`, `test_session.py`, `test_session_editing.py` |
| V13 / soubory | Rekurzivně přepočítat všech 26 JSON ukázek, porovnat výchozí objemy, obálky a počet; uložit/otevřít kopii bez změny zdroje. Doplnit načtení jednoduchého historického receptu pro verze 1–22, zachovat testy novějších sekcí. Žádná nová uložená pole, `VERSION=22`. | `test_p0_regressions.py`, `test_document.py` |
| V14 / závěrečná pojistka | Řízeně vložený prázdný/smíšený výstup 3D prvku i nezměněná identita nesmějí obejít kontrolu. Samostatné skici bez tělesa zůstanou platné. | `test_rebuild_errors.py`, nový soubor |

V10 rozdělí přesnou numerickou hranici a chování skutečného jádra:
hranici porovnání testovat na nezávisle zvolených číslech bez OCCT; v geometrických
případech porovnat skutečný změřený účinek se skutečnou `εV(A,R)`.
Neslibovat vytvoření každé nominální mikromezery nebo přesně hraničního objemu
pod rozlišením jádra. Rovnost, zaokrouhlení i hodnoty těsně po obou stranách
hranice musí mít samostatnou numerickou regresi; neskrývat je širší tolerancí.

Skutečné tvary používat všude, kde je lze stabilně vytvořit. Náhradu výstupu jádra
použít pouze pro řízenou simulaci vadného kandidáta nebo selhání, nikoli místo
analytických testů. Nepřepisovat očekávání starého testu jen proto, aby nová
kontrola prošla. Nové zpřísnění v A05/S02 výslovně zdokumentovat.

X01–X03 (nová operace průniku) zůstávají specifikací pro budoucí práci.
Úplná M02 transakce všech slovníků je kritérium P1.2B, nikoli hotový výstup P1.2A.

## 7. Pořadí implementace a kontrolní body

| Krok | Změny | Podmínka commitu |
|---|---|---|
| **A.1 Jádro** | Interní validátor, konečnost v `BuildContext.num`, kandidát a pravidla `new/add/cut`; V1–V5, V10, příslušná kompatibilita. | Ruff a celý pytest; analytické a chybové případy projdou. Přijatá geometrie při zamítnutí zůstává hodnotově stejná. |
| **A.2 Ostatní 3D prvky** | Místní kandidáti fillet/chamfer/shell, neprázdné otevřené plochy, závěrečná pojistka všech 3D typů; V6–V9, V14. | Ruff a celý pytest; existující loft/sweep/závit/pole zůstávají správné. R05 se neprohlašuje za uzavřené. |
| **A.3 Zprávy a přijetí** | Společné zprávy v `FeatureStatus`, GUI/CLI/AI, přenos a historie; V11–V13, dokumentace změn, výkonové porovnání a ruční postup. | Ruff a celý pytest; poté oba kompletní workflow a ruční zkouška balíčku. |

Kroky tvoří jeden schvalovaný rozsah P1.2A; průběžný commit není hotová etapa
a nepředává se jako nové vydání. Pokud vyjde najevo potřeba změnit smlouvu,
závislosti, formát nebo zapojit P1.2B/P1.4, připraví se konkrétní změna rozsahu
k samostatnému rozhodnutí. Kontroly se nevypnou kvůli průchodu testů.

## 8. Ověření výkonu, sestavení a ruční přijetí

Před implementací uložit baseline nezměněného main uvedeného nahoře a po dokončení
stejným `tests/benchmark_p0.py` kandidáta: zahřátí + 3 opakování, stejné prostředí,
verze knihoven a hardware. Porovnat mediány přepočtů příruby/krabičky/rámu/svaru,
přenos výsledku a 1 000 NDT paprsků; zaznamenat změny zdrojů a podpisy geometrie.
Zveřejnit poměry časů a omezení měření; paměť je jen maximum celého procesu.
Nepřidávat časové prahy do CI. NDT algoritmus se kvůli benchmarku nemění.

Opakované kontroly stejné geometrie mohou přidat náklady. Naměřené zpomalení
popsat a zdůvodnit před přijetím; neskrývat ho vynecháním kontrol.
Nevytvářet novou trvalou cache podle identity měnitelného tvaru. Případné místní
opětovné použití již přečtených vlastností nesmí přežít změnu tvaru nebo přepočet.

V implementačním PR musí být zelené obě úlohy stávajících workflow
„Windows aplikace“ i „macOS aplikace“ na aktuální hlavě: Ruff, úplný pytest,
baseline, sestavení, kontrola staženého balíčku a self-test s výsledkem OK.
Původní dokumentační PR #32 sestavení podle filtrů cest nespustil;
jeho místní testy nebyly ověřením následné implementace.

Změnu vzhledu ukázat snímkem skutečného okna, vedle offscreen testů Qt.
Na macOS použít běžící nativní okno; při ověření v Linuxu postup Xvfb dle CLAUDE.
Konkrétní balíček ručně přijmout alespoň na autorově Macu M4 s uvedením commitu,
systému a výsledků. Případný ruční průchod na Windows zaznamenat samostatně;
průchod na Macu jej nenahrazuje. Automatizované kontroly obou systémů jsou povinné:


1. Otevřít přírubu; u prvků i ve vlastnostech ověřit počet 1. Upravit rozměr,
   Zpět/Znovu a uložit/otevřít kopii: správný objem a zprávy.
2. Vysunout dvě oddělené kružnice Ø10 o 10 mm: 2 tělesa, 500π mm³,
   výslovně 0→2. Ve 3D jsou vidět obě části.
3. Na kvádru 20×30×40 přidat oddělený kvádr 5×5×10: 24 250 mm³,
   zpráva 1→2. Odebrat celý malý kvádr: 24 000 mm³, 2→1.
4. Přidat těleso zcela uvnitř stávajícího: česká chyba bez účinku, původní
   geometrie zachovaná; Zpět a oprava polohy fungují.
5. Skořepina 50×30×20/t2 s vrškem: 8 472 mm³. Prázdné otevřené plochy odmítnuty,
   žádný zmenšený plný díl jako úspěch. Výběr vršku a Zpět obnoví platný stav.
6. Existující pole tří trubek zůstane úspěšné s 3 tělesy; chybný R50/s50 zachová
   poslední platný díl a přeskočí další prvky.
7. Stejnou kopii otevřít přes CLI a offline souhrn AI: shodné počty i chyby.
   Ověřit také skutečný přepočet na pozadí v okně.

NDT-17 se tímto ručním CAD průchodem nedokončuje. Zejména nejde o ověření
odborných NDT výsledků nad více solidy.

## 9. Kritéria dokončení a co zůstává otevřené

P1.2A bude dokončeno teprve po implementaci A1–A7, splnění V1–V14,
zveřejnění místních výsledků i Windows/macOS evidence a cíleném ručním přijetí.
Počet testů má přirozeně vzrůst oproti výchozím 1 099; důkazem jsou konkrétní
případy a výsledky, ne samotný počet.

Přijetí vyžaduje: žádný tichý průchod dohodnutých vadných kandidátů; zachované
všechny platné složky; shodné zprávy ve třech rozhraních; žádná změna formátu,
zdrojových ukázek či NDT vymezení; žádné nezdůvodněné odstranění testu nebo přepsání starého očekávání.
R02 lze po ověření aktualizovat jako vyřešené pravidlo a viditelnost počtu těles;
P1.2A nedokazuje obecnou správnost všech geometrických či NDT výpočtů.

Zůstávají otevřené R05/úplné transakce (P1.2B), R04/reference (P1.3),
R01/export částečného dílu a NDT při chybě (P1.4), R03/atomické ukládání,
R12/oddíl README předávaný AI a odborná NDT-17. P1.2A nesmí prohlásit chybný
model za hotový jen proto, že zachovaný náhled prošel kontrolou objemu.
Dnešní exportní chování se v tomto kroku nemění; o jeho nápravě se rozhodne v P1.4.

**Mimo schvalovaný rozsah:** nový průnik v modelu, formát 23, import STEP, přímé
modelování P2, sestavy P5, nové automatické opravování geometrie, změny závislostí,
přepracování NDT tolerancí a NDT-16.

## 10. Zdroje pro kontrolu návrhu

[Schválená P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md),
[roadmapa P1](roadmapa-vyvoje.md#p1--bezpečná-geometrie),
[audit P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení),
[pravidla projektu](../CLAUDE.md#pravidla).

Konkrétní implementační místa na uvedeném main:
[prvky a BuildContext](../src/skodacad/features.py),
[přepočet a FeatureStatus](../src/skodacad/rebuild.py),
[GUI](../src/skodacad/gui/main_window.py),
[CLI](../src/skodacad/cli.py),
[souhrn AI](../src/skodacad/assistant.py),
[přenos workeru](../src/skodacad/worker.py),
[vlastnosti](../src/skodacad/properties.py),
[číselné výrazy](../src/skodacad/expressions.py),
[regrese obnovy](../tests/test_rebuild_errors.py),
[regrese P0](../tests/test_p0_regressions.py),
[baseline P0](../tests/benchmark_p0.py).

Tyto odkazy jsou podklady návrhu, nikoli tvrzení, že plánované změny už existují.
