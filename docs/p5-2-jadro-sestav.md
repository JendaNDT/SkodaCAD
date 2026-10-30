# P5.2 — polohy v sestavě: jádro formátu 29 a okno

**Stav: implementováno podle schváleného návrhu [P5.1](p5-1-navrh-formatu-sestav.md)
(S1–S12, autor 30. 10. 2026: „schvaluji S1–S12“).** P5.2A je jádro (soubor sestavy,
sestavení, sezení se Zpět/Znovu, příkazová řádka), P5.2B okno sestavy. Ruční zkouška
a přijetí P5 zůstávají na autorovi.

## Co přibylo

| Soubor | Co dělá |
|---|---|
| `document.py` | `VERSION = 29`; díl s `"kind": "assembly"` odmítne česky („je sestava, ne díl“), neznámý `kind` také; společný bezpečný zápis `write_json` |
| `assembly.py` | `Assembly`, `Component`: kontrola struktury (neznámý klíč = chyba, jedinečná `id`, jednotky mm, otisk 16 znaků), pravidla cest S4 (`check_path`), načtení a uložení |
| `assembly_build.py` | nalezení souborů s přesnou velikostí písmen, stavy komponent, otočení kolem pevných os X → Y → Z s přesnými násobky 90°, mezipaměť dílů podle souboru a SHA-256, podsestavy, cykly, meze, objem, hmotnost, obálka |
| `assembly_session.py` | `AssemblySession`: nová sestava (hned uložená), otevřít, uložit, *Uložit jako* (přepočítá cesty), vložit, smazat, přejmenovat, poloha, posun, otočení ±90°, pevná, *Najít soubor* s upozorněním, parametry, Zpět/Znovu |
| `cli.py` | `skodacad sestava <soubor>` – výpis komponent se stavy, objem, hmotnost, obálka; neúplná sestava = kód 1 |
| `examples/sestavy/` | ukázka *Krabička s víčkem*: `../krabicka.json`, víčko otočené o 180° kolem X (`dily/vicko.json`) a čtyři kopie nožičky (`dily/nozicka.json`) |
| `README.md` | návod „Sestavy“, oddíl „Sestavy“ v popisu formátu (čte ho i AI asistent), příkaz `skodacad sestava` |
| `gui/assembly_window.py` (P5.2B) | okno sestavy: strom komponent se stavy, formulář polohy (čísla i výrazy, tlačítka ±90°, *Pevná*), *Vložit díl*, *Smazat*, *Najít soubor…* (s otázkou u jiného receptu), *Otevřít díl* v hlavním okně, Zpět/Znovu, klik ve 3D vybere kopii, díly na pozadí v pomocném procesu |
| `gui/main_window.py` | *Otevřít…* pozná sestavu podle `kind` a otevře okno sestavy; *Nová sestava…*; *Otevřít ukázku → Sestavy* (šablona – *Uložit* se zeptá kam) |
| `gui/app.py`, `packaging/skodacad.spec` | self-test otevře ukázkovou sestavu se skutečným 3D; balíček přibalí `examples/sestavy/` |
| `tests/p35_cross_os.py`, `p35-cross-os.yml` | na jednom systému vznikne sestava v podsložce s odkazy `../…`, na druhém se otevře úplná se stejnými otisky, objemem a obálkami |

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
| A18 | `test_a18_…`, `p35_cross_os.py` | složka projektu zkopírovaná jinam se otevře stejně; v CI vytvořená na macOS / Windows a otevřená na druhém systému (místně ověřena kopie složky: 64 387,064 mm³) |
| A19 | `test_a19_…` | jiná velikost písmen v cestě = najde se s upozorněním (na všech systémech stejně) |
| A20 | `test_a20_…` | vložit, posunout, přejmenovat, smazat = každá změna jeden krok; nezměněná úprava žádný; Znovu |
| A21 | `test_a21_…` | první komponenta pevná, tažení ji nepohne, číslem ve formuláři ano; nová sestava se hned uloží |
| A22 | `test_a22_…`, okno, self-test | ukázka je v `examples/sestavy/`, úplná a bez upozornění; nabídka *Sestavy*, self-test „✓ Sestava: 31309 mm³“ a balíček |

Okno (`tests/test_assembly_gui.py`, náhradní prohlížeč): strom a souhrn po otevření z hlavního
okna, formulář = jeden krok Zpět i se jménem, chybný výraz, ±90° a *Pevná*, chybějící díl
a *Najít soubor* s otázkou, vložení a smazání, klik ve 3D, *Otevřít díl*, nová sestava
a všechny akce souboru, ukázka jako šablona (díly zkopírované do `dily/`, soubor ukázky beze změny), dotaz při zavření,
výpočet dílů v pomocném procesu (stav „počítá se“, pak úplná sestava). Skutečné okno pod Xvfb:
self-test `VÝSLEDEK: OK` včetně „✓ Sestava“ a snímek okna sestavy.

Navíc: zpětný převod úhlů pro obecné úhly a ±90° kolem Y, vložení sestavy do sebe, podsestavy,
která obsahuje tuto sestavu (cyklus), nečitelného souboru a souboru na jiném disku Windows;
*Uložit jako* do podsložky přepočítá cestu na `../dily/kvadr.json`.

Jednorázové měření v cloudu: ukázka se sestaví za 0,6 s, podruhé ze mezipaměti za 5 ms.

## Omezení a zbývá

- Ruční zkouška autora na Windows i Macu (založit sestavu, vložit díly, otočit, uložit,
  přesunout složku, smazat díl a najít ho znovu).
- *Uložit* ukázky zkopíruje její díly do `dily/` vedle sestavy (CI na Windows ukázalo, že
  ukázky na disku D: a uživatelská složka na C: relativní cestu nedovolí). Obecné *Zabalit
  sestavu* (i s podsestavami) je pozdější krok.
- Tažení komponent myší zatím není (poloha jen číslem a ±90°); okno nemá barvy po
  komponentách.
- P5.3 vazby (nejdřív návrh řešiče a zápisu), P5.4 kolize, kusovník a export.
