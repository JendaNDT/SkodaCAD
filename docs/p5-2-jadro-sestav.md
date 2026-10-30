# P5.2A — jádro sestav (formát 29)

**Stav: implementováno podle schváleného návrhu [P5.1](p5-1-navrh-formatu-sestav.md)
(S1–S12, autor 30. 10. 2026: „schvaluji S1–S12“).** Jde o jádro bez okna: soubor sestavy,
sestavení, sezení se Zpět/Znovu a příkazová řádka. Okno (P5.2B) zbývá; ruční přijetí P5
zůstává na autorovi.

## Co přibylo

| Soubor | Co dělá |
|---|---|
| `document.py` | `VERSION = 29`; díl s `"kind": "assembly"` odmítne česky („je sestava, ne díl“), neznámý `kind` také; společný bezpečný zápis `write_json` |
| `assembly.py` | `Assembly`, `Component`: kontrola struktury (neznámý klíč = chyba, jedinečná `id`, jednotky mm, otisk 16 znaků), pravidla cest S4 (`check_path`), načtení a uložení |
| `assembly_build.py` | nalezení souborů s přesnou velikostí písmen, stavy komponent, otočení kolem pevných os X → Y → Z s přesnými násobky 90°, mezipaměť dílů podle souboru a SHA-256, podsestavy, cykly, meze, objem, hmotnost, obálka |
| `assembly_session.py` | `AssemblySession`: nová sestava (hned uložená), otevřít, uložit, *Uložit jako* (přepočítá cesty), vložit, smazat, přejmenovat, poloha, posun, otočení ±90°, pevná, *Najít soubor* s upozorněním, parametry, Zpět/Znovu |
| `cli.py` | `skodacad sestava <soubor>` – výpis komponent se stavy, objem, hmotnost, obálka; neúplná sestava = kód 1 |
| `examples/sestavy/` | ukázka *Krabička s víčkem*: `../krabicka.json`, víčko otočené o 180° kolem X (`dily/vicko.json`) a čtyři kopie nožičky (`dily/nozicka.json`) |
| `README.md` | oddíl „Sestavy“ v popisu formátu (čte ho i AI asistent), příkaz `skodacad sestava` |

Díly se dál ukládají v nejnižší potřebné verzi (24–28); soubor sestavy má verzi 29.
Starší aplikace ho odmítne hláškou „stáhni aktuální aplikaci“.

## Ověření (matice A01–A22)

Testy jsou v `tests/test_assembly.py`. „Okno“ = část, která patří do P5.2B.

| Č. | Test | Co ověřuje |
|---|---|---|
| A01 | `test_a01_…` | všechny díly z `examples/` se uloží ve verzi ≤ 28; díl ve verzi 29 se načte |
| A02 | `test_a02_…` | otevřít + uložit bez úprav = bajt po bajtu stejný soubor (po prvním doplnění otisků) |
| A03 | `test_a03_…` | sestava s verzí 28 i 30 a neznámý `kind` dílu se odmítnou |
| A04 | `test_a04_…` | sestava jako díl (i s verzí 1, jak by ji otevřela stará logika) a díl jako sestava = česká chyba; `skodacad build` na sestavě skončí kódem 2 |
| A05 | `test_a05_…` (12 případů) | chybějící/zdvojené id, neznámé klíče na všech úrovních, jednotky, otisk, `fixed`, trojice, hodnoty |
| A06 | `test_a06_…` (11 případů) | přesně zápisy z průzkumu P5: přijaty jen `dily/deska.json` a `../dily/deska.json` |
| A07 | `test_a07_…` | chybějící soubor = stav *chybí*, ostatní komponenty pokračují, uložení zachová záznam |
| A08 | `test_a08_…` | neplatný JSON, cizí soubor, novější verze, díl s chybou přepočtu |
| A09 | `test_a09_…` | cyklus přes podsložku (`a.json → b.json → a.json`) i sestava sama v sobě |
| A10 | `test_a10_…` | 9 úrovní → stop na 8. úrovni; 1 001 komponent; mez po rozbalení podsestav |
| A11 | `test_a11_…` | kvádr v rohu s (90, 0, 90) → obálka (0, 0, 0)–(10, 30, 20) podle ručního výpočtu; výraz v poloze; výchozí pořadí build123d dává jinou polohu |
| A12 | `test_a12_…` | otočení tlačítky: uložené úhly celá čísla `[90, 0, 90]`, obálka přesně 0 |
| A13 | `test_a13_…` | kopie sdílí tvar, poloha jedné nemění druhou, soubor dílu bajt po bajtu stejný |
| A14 | `test_a14_…` | změněný soubor dílu se použije (objem 12 000 → 24 000 mm³) s upozorněním, po uložení zmizí |
| A15 | `test_a15_…` | *Najít soubor* s jiným receptem upozorní, je jeden krok Zpět, nečitelný soubor se nepřijme |
| A16 | `test_a16_…` (2) | ukázka: objem = krabička + víčko (vzorec zaobleného obdélníku) + 4 × nožička (π r² h), hmotnost PETG, víčko z = 26…32; neúplná sestava = kód 1 a „NEÚPLNÁ“ |
| A17 | `test_a17_…` | podsestava posunutá a otočená o 90° kolem Z: obálka (95, 5, 0)–(105, 15, 3) |
| A18 | `test_a18_…` | složka projektu zkopírovaná jinam se otevře stejně (přenos mezi Windows a macOS ověří až CI P5.2B) |
| A19 | `test_a19_…` | jiná velikost písmen v cestě = najde se s upozorněním (na všech systémech stejně) |
| A20 | `test_a20_…` | vložit, posunout, přejmenovat, smazat = každá změna jeden krok; nezměněná úprava žádný; Znovu |
| A21 | `test_a21_…` | první komponenta pevná, tažení ji nepohne, číslem ve formuláři ano; nová sestava se hned uloží |
| A22 | `test_a22_…` | ukázka je v `examples/sestavy/`, je úplná a bez upozornění (nabídka, self-test a balíček – okno) |

Navíc: zpětný převod úhlů pro obecné úhly a ±90° kolem Y, vložení sestavy do sebe, podsestavy,
která obsahuje tuto sestavu (cyklus), nečitelného souboru a souboru na jiném disku Windows;
*Uložit jako* do podsložky přepočítá cestu na `../dily/kvadr.json`.

Jednorázové měření v cloudu: ukázka se sestaví za 0,6 s, podruhé ze mezipaměti za 5 ms.

## Zbývá (P5.2B a dál)

- Okno: *Nová sestava*, *Otevřít* pozná sestavu, strom komponent se stavy, formulář polohy
  s tlačítky ±90°, *Pevná*, *Najít soubor…*, *Otevřít díl*, kreslení kopií ve 3D.
- Přepočet dílů sestavy v pomocném procesu (S12), aby okno nestálo.
- Ukázková sestava v nabídce, v self-testu a v balíčku; přenos sestavy mezi Windows a macOS
  v CI (`p35-cross-os.yml`).
- P5.3 vazby, P5.4 kolize, kusovník a export – každé s vlastním návrhem.
