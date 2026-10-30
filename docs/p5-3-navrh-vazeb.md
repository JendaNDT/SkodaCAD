# P5.3 — návrh vazeb v sestavě

**Stav: návrh předaný autorovi ke schválení, bez implementace.** `src/` se nemění, formát
zůstává ve verzi 29. Vychází z `main` / `91f8a70` (sloučené
[PR #63](https://github.com/JendaNDT/SkodaCAD/pull/63), P5.2 polohy; autor k vydání napsal
„Ok, funguje to“) a z bodu P5.3 [roadmapy](roadmapa-vyvoje.md#p5--sestavy): po odsouhlasení
řešiče souosost, dotyk a vzdálenost, stavy nedourčeno/přeurčeno, spolehlivé odmítnutí sporu.
Navazuje na [formát sestav P5.1](p5-1-navrh-formatu-sestav.md) (S12: poloha se ukládá vždy).

## 1. Co to autorovi přinese

- Místo čísel stačí říct, **jak díly k sobě patří**: „víčko leží na okraji krabičky“,
  „šroub je v díře“, „mezi deskou a krabičkou je mezera 2 mm“. Aplikace polohu dopočítá.
- Když se díl změní (vyšší krabička, posunutá díra), polohy se **samy přepočítají**.
- U každého dílu je vidět, jestli je **plně určený**, nebo kolik pohybů mu zbývá
  („volná: 2 posuny, 1 otočení“). Vazby, které si odporují, aplikace **odmítne** a řekne
  česky, které to jsou – nikdy je tiše nesplní napůl.

## 2. Rozhodnutí ke schválení M1–M12

| Rozhodnutí | Doporučená varianta | Důsledek / alternativa |
|---|---|---|
| **M1 Čtyři druhy vazeb** | **Dotyk** (dvě rovinné plochy na sobě, normály proti sobě), **zarovnání** (dvě rovinné plochy v jedné rovině, normály stejným směrem), **vzdálenost** (dotyk s mezerou, hodnota v mm, číslo nebo výraz s parametry sestavy) a **souosost** (osy dvou válcových ploch – díra, čep – nebo osa dílu splývají). | Pokryje krabičky (víčko, deska na sloupcích) i strojní díly (šroub v díře, hřídel v ložisku). Úhel, tečnost, vazby na hrany a body jsou pozdější krok. |
| **M2 Na co vazba odkazuje** | Na **plochu komponenty významem** v souřadnicích jejího dílu: `{"component": "vicko", "face": {"at": […], "normal": […], "type": "plane"}}` – stejný zápis a hledání jako u uložených měření a skic (P1.3), nikdy pořadím. Navíc **základní roviny a osy dílu**: `{"component": "noha", "plane": "XY"}`, `{"component": "sroub_1", "axis": "Z"}`. | Plocha se najde i po změně rozměru dílu. Základní roviny pomohou u dílů bez vhodné plochy (souměrné umístění). U podsestavy se hledá na celé podsestavě v jejích souřadnicích. |
| **M3 Vlastní řešič tuhých těles** | Malý řešič nad knihovnou **numpy** (v aplikaci už je – potřebuje ji build123d). Každá volná komponenta má 6 neznámých (posun + otočení), vazba = rovnice mezi plochami. Metoda Levenberg–Marquardt; každá **skupina propojených komponent se počítá zvlášť**. | Řešič skicáře `slvs` tuhá tělesa ve veřejném rozhraní nemá (průzkum V7) a při chybném volání shodí celý program. Žádná nová závislost. Skupiny: 40 víček 0,13 s místo 3,7 s (V6). |
| **M4 Nejmenší posun** | Řešič hledá polohu **co nejblíž té dnešní**. Co vazby neurčují, zůstane, jak bylo (posun do strany, otočení kolem osy šroubu); jen když se díl musí srovnat, může se volné otočení nepatrně změnit (průzkum: 0,34°). | Díly „neskáčou“. Kdo chce přesnou polohu, přidá další vazbu. |
| **M5 Obrácený díl** | Když vazby nejdou splnit, řešič zkusí každý vázaný díl předem **obrátit o 180°** kolem X, Y a Z a vezme první řešení, které vazby splní. Teprve potom hlásí spor. | Obrácenou nožičku (V4b) spraví sám; bez toho uvízne (normály míří stejným směrem). Pro dotyk místo zarovnání se ale nerozhoduje sám – druh vazby určuje autor. |
| **M6 Stupně volnosti** | Z řešení se pozná, kolik pohybů komponentě zbývá (0 = **plně určená**), a rozliší se posuny a otočení. Vazby navíc, které si neodporují (víčko: dotyk + dvě zarovnání = 9 rovnic na 6 neznámých), jsou v pořádku. | Nedourčená komponenta není chyba – zůstane v poslední poloze a okno řekne „volná: 2 posuny, 1 otočení“. |
| **M7 Spor** | Spor = rovnice nejdou splnit (zbytek nad 1·10⁻⁶ mm). **Nová nebo změněná vazba, která vytvoří spor, se nepřijme** – česká chyba s názvem vazby, sestava zůstane, jak byla. Když spor vznikne změnou souboru dílu, polohy **zůstanou uložené**, vazby ve sporu jsou červeně a sestava je neúplná (bez exportu, stejně jako chybějící díl). | Nikdy se nevydává napůl splněná vazba za výsledek. Spor V3 (vzdálenost 0 a 5 mm) průzkum zachytil přesně (zbytek 5/√2). |
| **M8 Pevné a výrazové polohy** | Pevná komponenta se nehýbe nikdy. Skupina vázaných komponent bez pevné drží první komponentu skupiny v pořadí sestavy. Komponentu, jejíž poloha je zadaná **výrazem**, řešič neposouvá – vazba na ni s jinou polohou je chyba „poloha je zadaná výrazem, nahraď ji číslem“. | Výrazy (P5.2) zůstanou platné; řešič je tiše nepřepíše. |
| **M9 Uložení polohy** | Výsledek řešiče se **zapíše do `placement`** (čísla zaokrouhlená na 1·10⁻⁹ mm a °), přidání vazby i nová poloha = **jeden krok Zpět**. Ruční posun nebo ±90° u vázané komponenty se přijme a vazby ji hned srovnají – změní se jen volné pohyby. | Soubor jde otevřít i bez řešiče a starší čtení poloh zůstává (S12). Uživatel vidí v čísle, kam díl vazby daly. |
| **M10 Formát 30** | Sestava dostane nepovinný seznam `constraints` (`id`, `type`: `mate` / `flush` / `distance` / `coaxial`, `a`, `b`, `value` jen u vzdálenosti, nepovinný `name`). Sestava **bez vazeb se dál ukládá ve verzi 29**, s vazbami ve **30**. Neznámý klíč = chyba. Smazání komponenty smaže i její vazby (S6). | Starší aplikace sestavu s vazbami odmítne hláškou „stáhni aktuální aplikaci“, místo aby vazby tiše zahodila. |
| **M11 Kdy se počítá** | Po každé úpravě sestavy a po načtení dílů (otevření, F5, návrat z hlavního okna). Když se polohy po změně dílu změní, sestava je „neuložená“ (hvězdička) a okno napíše „polohy se po změně dílu přepočítaly“. | Změna dílu se promítne hned; uložit ji je na autorovi. |
| **M12 Okno (P5.3B)** | *Přidat vazbu*: klik na plochu první komponenty, Ctrl+klik na plochu druhé → nabídnou se jen vhodné druhy (dvě roviny: dotyk / zarovnání / vzdálenost; dva válce nebo osa: souosost). Vazby ve stromu pod komponentami se stavem, úprava hodnoty vzdálenosti, smazání. U komponenty stav „plně určená“ / „volná: …“ / „ve sporu“. | Stejné ovládání jako výběr ploch u dílu. Tažení myší s vazbami a pohyb mechanismů jsou mimo rozsah. |

Ukázka zápisu (body ploch jsou z ukázky *Krabička s víčkem*):

```json
"constraints": [
  {"id": "v1", "type": "mate", "name": "Víčko leží na okraji",
   "a": {"component": "krabicka", "face": {"at": [0, 24, 30], "normal": [0, 0, 1], "type": "plane"}},
   "b": {"component": "vicko", "face": {"at": [0, 24, 2], "normal": [0, 0, 1], "type": "plane"}}},
  {"id": "v2", "type": "flush",
   "a": {"component": "krabicka", "face": {"at": [40, 0, 15], "normal": [1, 0, 0], "type": "plane"}},
   "b": {"component": "vicko", "face": {"at": [40, 0, 1], "normal": [1, 0, 0], "type": "plane"}}},
  {"id": "v3", "type": "distance", "value": "mezera",
   "a": {"component": "krabicka", "face": {"at": [0, 0, 0], "normal": [0, 0, -1], "type": "plane"}},
   "b": {"component": "nozicka_1", "plane": "XY"}},
  {"id": "v4", "type": "coaxial",
   "a": {"component": "deska", "face": {"at": [35, 20, 1.5], "normal": [1, 0, 0], "type": "cylinder"}},
   "b": {"component": "sroub_1", "axis": "Z"}}
]
```

## 3. Co potvrzuje současný kód

- `selectors.find_face` hledá plochu podle bodu, normály a druhu (P1.3) a už ho používají
  měření, skici i přímé úpravy – vazby ho převezmou beze změny.
- `assembly_build.rotation_matrix` / `angles_of` převádějí otočení na úhly kolem pevných os
  s přesnými násobky 90° a zaokrouhlením – výsledek řešiče se tak zapíše čitelně.
- `AssemblySession._change` je jediné místo úprav (Zpět/Znovu); řešení se do něj vejde jako
  součást téže změny. `AssemblyResult` už má stav komponenty – přibude stav vazeb.
- numpy je v aplikaci jako závislost build123d (a už ho používá `ndt/plan.py`); scipy je
  tam také, ale řešič ho nepotřebuje.

## 4. Průzkum

Jednorázový průzkum, **ne test projektu**: [`p5-3-pruzkum-vazeb.py`](p5-3-pruzkum-vazeb.py),
cloud Linux, build123d 0.13.0, numpy 2.5.4. Skutečné díly ukázky: krabička, víčko, nožička.

| Č. | Případ | Výsledek | Závěr |
|---|---|---|---|
| V1 | Dotyk víčka s okrajem krabičky | zbytek 3·10⁻¹⁴, volné 3 (posuny X, Y, otočení Z), víčko z = 32 | M1, M6 |
| V2 | + zarovnání boční stěny X a Y, start natočený o 8° a 12° a posunutý | volné 0, nadbytečné rovnice 6 (bez sporu), poloha přesně [0, 0, 32], [180, 0, 0] jako ručně v ukázce, 3 ms | M4, M6 |
| V3 | Vzdálenost 0 a 5 mm mezi týmiž rovinami | zbytek 3,536 = 5/√2 → **spor** | M7 |
| V4 | Nožička: dotyk se dnem, start mírně nakloněný | volné 3, x a y zůstaly −30 / −15, z = −3; volné otočení se změnilo o 0,34° | M4 (přiznaná drobnost) |
| V4b | Nožička vložená obráceně | samotný řešič uvízne (zbytek 2); s obrácením o 180° kolem X splněno | M5 |
| V5 | Souosost osy nožičky s osou Z krabičky | volné 2 (posun podél osy, otočení kolem ní) | M1, M6 |
| V6 | 40 víček, každé dotyk + 2 zarovnání (240 neznámých) | najednou 3,7 s, **po skupinách 0,13 s**, stejný výsledek | M3 skupiny |
| V7 | Veřejné rozhraní `slvs` | body, čáry, kružnice, roviny – žádná transformace tuhého tělesa | M3 ne slvs |

Časy jsou jednorázové měření v cloudu, ne slib.

## 5. Budoucí matice B01–B20

**Specifikace testů pro implementaci, ne přidané testy.**

| Č. | Případ | Očekávání |
|---|---|---|
| B01 | Sestavy verze 29 a ukázky | načtou se beze změny; sestava bez vazeb se uloží ve verzi 29 |
| B02 | Sestava s vazbami: uložit, otevřít | verze 30, totožné vazby i polohy |
| B03 | Verze 30 se starou aplikací / neznámý klíč ve vazbě / neznámý druh | odmítnuto česky |
| B04 | Vazba na neexistující komponentu nebo plochu, která zmizela | stav vazby „odkaz nenalezen“, poloha beze změny, sestava neúplná |
| B05 | Dotyk víčka (V1) | z = 32 podle rozměrů, volné 3 |
| B06 | Dotyk + 2 zarovnání (V2) z natočeného startu | přesně [0, 0, 32], [180, 0, 0], plně určeno |
| B07 | Vzdálenost výrazem s parametrem | poloha podle parametru, změna parametru posune díl |
| B08 | Souosost válcových ploch (šroub v díře) a osy dílu | osy splývají, volné 2 |
| B09 | Spor (V3) při přidání vazby | vazba se nepřijme, česká chyba s názvem, sestava beze změny, žádný krok Zpět |
| B10 | Spor po změně souboru dílu | polohy uložené, vazby ve sporu, sestava neúplná |
| B11 | Obrácený díl (V4b) | vyřeší se obrácením o 180° |
| B12 | Pevná komponenta | řešič ji nikdy neposune |
| B13 | Komponenta s výrazem v poloze | vazba odmítnuta s radou nahradit výraz číslem |
| B14 | Skupina bez pevné komponenty | první komponenta skupiny zůstane, ostatní se dopočítají |
| B15 | Ruční posun / ±90° vázané komponenty | volné pohyby se změní, vázané se vrátí; jeden krok Zpět |
| B16 | Změna rozměru dílu (vyšší krabička) | víčko se posune s okrajem; sestava „neuložená“ s hláškou |
| B17 | Smazání komponenty | smažou se i její vazby, jeden krok Zpět |
| B18 | 40 nezávislých skupin (V6) | po skupinách, řádově desetiny sekundy |
| B19 | Podsestava jako komponenta vazby | plocha se najde na podsestavě v jejích souřadnicích |
| B20 | Okno: přidat dotyk dvěma kliky, upravit vzdálenost, smazat; stav „volná: …“ | každá akce jeden krok Zpět, akce stisknuté v testu okna |

## 6. Co P5.3 záměrně neřeší

Úhel, tečnost, vazby na hrany, body a skici, tažení vázaných dílů myší, pohyb mechanismů
a animace, vazby uvnitř podsestavy z nadřazené sestavy, kolize a vůle (P5.4), kusovník
a export (P5.4).

## 7. Navazující kroky a rozsah schválení

1. **P5.3A jádro** – řešič, formát 30, stavy, `AssemblySession`, příkazová řádka (výpis
   vazeb a volnosti), ukázka s vazbami, testy B01–B19.
2. **P5.3B okno** – přidání vazby kliknutím, seznam vazeb, stav volnosti, test B20, snímek okna.
3. **P5.4 kontroly** – kolize, vůle, kusovník, export, vymezení NDT.

Schválení M1–M12 opravňuje implementovat P5.3A a P5.3B podle tohoto zápisu. Ruční přijetí
P5 zůstává na autorovi.
