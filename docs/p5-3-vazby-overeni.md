# P5.3 — vazby v sestavě: implementace a ověření

**Stav: implementováno podle schváleného návrhu [P5.3](p5-3-navrh-vazeb.md)
(M1–M12, autor 30. 10. 2026: „schvaluji M1–M12“).** P5.3A je jádro (formát 30, řešič,
sezení, příkazová řádka, ukázka), P5.3B okno. Ruční zkouška vazeb a přijetí P5 (P5.5)
zůstávají na autorovi.

## Co přibylo

| Soubor | Co dělá |
|---|---|
| `document.py` | `VERSION = 30`; díly se dál ukládají v nejnižší potřebné verzi (24–28) |
| `assembly.py` | `Constraint`: `mate` (dotyk), `flush` (zarovnání), `distance` (vzdálenost, číslo nebo výraz), `coaxial` (souosost); odkazy `face` (`at`, `normal`, `type` `plane`/`cylinder`, bez poloměru), `plane` (`XY` +Z, `XZ` −Y jako u skic, `YZ` +X), `axis` (`X`, `Y`, `Z`); neznámý klíč, špatný druh odkazu, stejná komponenta, `value` mimo vzdálenost = česká chyba; bez vazeb verze 29, s vazbami 30; otisk podsestavy bez vazeb beze změny |
| `assembly_solve.py` (nový) | řešič tuhých těles nad numpy: skupiny propojených komponent (pevná komponenta skupiny nespojuje, skupina bez pevné drží první komponentu), Levenberg–Marquardt s krokem nejmenší normy (SVD) v měřítku mm, návrat volných pohybů, obrácení o 180° kolem X/Y/Z, volnost (posuny / otočení) z jádra Jacobiho matice, spor = zbytek nad 1·10⁻⁶ mm |
| `assembly_build.py` | po úrovních: komponenty ve vlastních souřadnicích → řešení vazeb → umístění kopií; stavy vazeb (splněna / ve sporu / odkaz nenalezen / počítá se / chyba), volnost komponent, nové polohy `solved`; podsestava se vazbami se splní při sestavení a dostane upozornění „otevři ji a ulož“ (soubor podsestavy se nemění) |
| `assembly_session.py` | `add_constraint`, `set_constraint`, `remove_constraint`; polohy z řešiče se zapíšou v téže změně (jeden krok Zpět); úprava, po které by byla ve sporu vazba, která předtím nebyla, se nepřijme; smazání komponenty smaže i její vazby; po změně dílu `notice` a „neuloženo“; `reference_at` (kliknutá plocha → odkaz v souřadnicích dílu), `gap` (dnešní vzdálenost), `constraint_kinds`, `constraint_faces` |
| `cli.py` | `skodacad sestava` vypíše volnost komponent, vazby se stavem a polohy, které se liší od souboru; spor = „NEÚPLNÁ“ a kód 1 |
| `examples/sestavy/krabicka_s_vazbami.json` | víčko určené vzdáleností `mezera` (0) a dvěma zarovnáními, čtyři nožičky dotykem se dnem (volné 2 posuny, 1 otočení) |
| `gui/assembly_window.py` | *Přidat vazbu…* (Ctrl+L) po kliku a Ctrl+kliku na dvě plochy – nabídne jen vhodné druhy, u vzdálenosti dnešní hodnotu; vazby ve stromu se stavem; panel *Vazba* (název, vzdálenost, *Použít vazbu*, *Smazat vazbu*, Delete); zvýraznění ploch vybrané vazby; volnost ve stromu i ve formuláři; hláška o přepočtu poloh |
| `gui/app.py` | self-test „✓ Vazby: 7 splněných, víčko plně určené, mezera 15 → z = 47 a Zpět“ |
| `README.md` | návod *Vazby*, oddíl formátu „Vazby v sestavě (`constraints`, verze 30)“ (čte ho i AI asistent), příkaz `skodacad sestava` |

## Ověření (matice B01–B20)

Testy: `tests/test_assembly_constraints.py` (B01–B19 a jádro okna), `tests/test_assembly_gui.py`
(B20 a chyby v okně).

| Č. | Test | Výsledek |
|---|---|---|
| B01 | `test_b01_…` | ukázka bez vazeb se ukládá ve verzi 29 bez klíče `constraints`, otisk beze změny; ukázka s vazbami ve verzi 30 |
| B02 | `test_b02_…` | uložit a otevřít: verze 30, vazby i polohy totožné se souborem ukázky, sestava neuložená není |
| B03 | `test_b03_…` (18 případů) | verze 31, vazby ve verzi 29, neznámé klíče na všech úrovních, druh `angle`, plocha `cone`, poloměr, nulový směr, rovina `AB`, osa u dotyku, roviny u souososti, stejná komponenta, chybějící / přebytečná hodnota, zdvojené id, dva odkazy najednou – vše česká chyba |
| B04 | `test_b04_…` | vazba na neexistující komponentu a na plochu, která na dílu není: „odkaz nenalezen“, poloha beze změny, sestava neúplná, přidat takovou vazbu nejde |
| B05 | `test_b05_…` | dotyk víčka: z = 32 (okraj 30 + deska 2), víčko 26…32, volné 2 posuny a 1 otočení, zbytek pod 1·10⁻⁹ |
| B06 | `test_b06_…` | dotyk + 2 zarovnání z natočeného startu (8° a 12°): přesně [0, 0, 32], [180, 0, 0], plně určené |
| B07 | `test_b07_…` | vzdálenost `mezera` = 15 → víčko z = 47; Zpět → 32; výraz `2 * mezera + 1` u nožičky |
| B08 | `test_b08_…` | souosost díry Ø 10 a čepu: osa čepu x = 20, y = 0 (obálka 15…25, −5…5), volné 1 posun a 1 otočení; osa Z dílu s osou Z dílu |
| B09 | `test_b09_…` | vzdálenost 5 mm proti dotyku: nepřijato „Vazby si odporují (…): zbytek 3,54 mm“ (= 5/√2), sestava beze změny, žádný krok Zpět |
| B10 | `test_b10_…` | sloupek o 2 mm vyšší: obě vazby „ve sporu“, deska zůstala v z = 10, sestava neúplná a ne neuložená; jiná úprava jde dál |
| B11 | `test_b11_…` | obrácená nožička se obrátí: otočení [0, 0, 0], horní plocha z = 0 |
| B12 | `test_b12_…` | dvě pevné komponenty: spor „obě komponenty jsou pevné…“, krabička se nehne; pevné víčko, volná krabička: posune se krabička o 8 mm |
| B13 | `test_b13_…` | víčko s polohou `H + 3`: nepřijato s radou „nahraď výraz číslem“; s `H + 2` přijato bez posunu |
| B14 | `test_b14_…` | skupina bez pevné: první komponenta (krabička) drží polohu, víčko se dopočítá |
| B15 | `test_b15_…` | ruční posun (5, 0, 10) víčka s dotykem: x zůstane, z se vrátí; ±90° kolem Z projde; plně určené víčko se vrátí celé bez kroku Zpět |
| B16 | `test_b16_…` | krabička vysoká 40: víčko z = 42, sestava neuložená, hláška „po změně dílu přepočítaly: „Víčko““ |
| B17 | `test_b17_…` | smazání víčka smaže vazby v1–v3 (jeden krok Zpět), smazání a změna vazby |
| B18 | `test_b18_…` | 40 víček (120 vazeb), všechna přesně [0, 0, 32]; v cloudu 2,8 s celý test (hlavně hledání ploch), mez testu 20 s |
| B19 | `test_b19_…` | nožička na dně krabičky uvnitř podsestavy posunuté o 10 mm: z = 7; vazba uvnitř podsestavy se splní (víčko 36…42), soubor podsestavy beze změny |
| B20 | `test_b20_…` (okno) | strom: „✓ plně určená“, „✓ volná: 2 posuny, 1 otočení“, „Vazby (7)“; smazat vazbu (Delete), klik na dno a Ctrl+klik na nožičku → nabídka dotyk / zarovnání / vzdálenost, výchozí vzdálenost 0, zadáno 2 → nožička z = −5; vzdálenost 1,5 a název ve formuláři → z = −4,5; každá akce jeden krok Zpět, tři kroky zpět vrátí ukázku |

Navíc: chyby v okně (bez výběru, dvě plochy jedné komponenty, rovina + válec, spor) jsou české
dialogy; změněný díl v okně posune víčko, souhrn napíše „po změně dílu přepočítaly“ a titulek
hvězdičku; vazby čekají na díly počítané v pomocném procesu („počítá se“, přidat nejde) a po
dopočtu se splní; odkaz z kliknuté plochy je v souřadnicích dílu ([10, 24, 30] ve sestavě →
[10, −24, 2] u otočeného víčka); `skodacad sestava` s vazbami, se sporem a s polohou, která se
liší od souboru.

Skutečné okno pod Xvfb: self-test `VÝSLEDEK: OK` včetně „✓ Sestava“ a „✓ Vazby“; snímek okna
s vybranou vazbou (plochy zvýrazněné, stav komponent ve stromu).

Jednorázové měření v cloudu: ukázka s vazbami se sestaví za 0,7 s, podruhé z mezipaměti
za 44 ms.

## Sloučení

Sloučeno v [PR #65](https://github.com/JendaNDT/SkodaCAD/pull/65) jako `822e3e8`. Před
sloučením: v cloudu úplná sada **1 907 testů** (22:41 min) a `ruff check src tests`; na
GitHubu workflow „Windows aplikace“ a „macOS aplikace“ (testy, sestavení, self-test,
kontrola staženého balíčku) a „P3 STEP přenos mezi systémy“ (sestava s vazbou vytvořená na
jednom systému a otevřená na druhém) – vše úspěšně. Ruční zkouška vazeb autorem zatím neproběhla.

## Co se při implementaci ukázalo (a je opravené)

- Řešič z průzkumu dorovnával vzdálenost natočením dílu a krok tlumil podle velikosti sloupců
  matice (Marquardt). U volné krabičky pod pevným víčkem pak ujela do strany o 43 mm (a se
  šumem bez SVD o 536 mm). Oprava: rovnice směrů násobené ramenem, krok nejmenší normy v mm
  s jednotným útlumem a na konci návrat volných pohybů → přesně [0, 0, 8].
- Natočení nožičky 4° / 3° narovná vazba s nejmenším otočením; úhel kolem Z se přitom změní
  o 0,1° (průzkum 0,34°). Je to geometricky nejmenší pohyb, ne chyba (M4 to připouští).

## Omezení a zbývá

- Okno nemá editor parametrů sestavy – výraz ve vzdálenosti jde změnit přímo v poli vazby.
- Vazby jen mezi komponentami nejvyšší úrovně; vazby uvnitř podsestavy se mění v jejím souboru.
- Úhel, tečnost, hrany a body, tažení vázaných dílů myší a pohyb mechanismů jsou mimo P5.3.
- Ruční zkouška na Windows a Macu a přijetí P5 (P5.5) jsou na autorovi; P5.4 kolize, kusovník
  a export následují.
