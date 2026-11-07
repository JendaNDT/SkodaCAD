# P8.5 – rozbor pauz Qt po novém hlavním okně (P7.48–P7.53)

Autor po vydání `ad7fb19` (PR #128, sloučeno s výjimkou P8.5) napsal „ok, zjisti to“.
Tento záznam je **diagnostika**, ne nové měření rozpočtu: limity, zmrazený měřicí
program P8.5 (`tests/budget_p8.py`, `tests/soak_p8*.py`) ani jeho výsledky se nemění.

## Výchozí stav

Rozpočet `ci-windows`, mez `qt.max_gap_s` (nejdelší interval obsluhy Qt) = 3 s:

| Běh | Commit | `qt.max_gap_s` | Celý běh | Výsledek |
|---|---|---:|---:|---|
| PR #128 | `091d55b` | 1,966 s | 1 112 s | prošlo |
| PR #128 | `c5a6b13` | 3,172 s | 1 434 s | **neprošlo** |
| `main` | `ad7fb19` | 3,336 s | 1 393 s | **neprošlo** |

Ostatních 22 mezí prošlo ve všech bězích. Neúspěchy zůstávají zapsané jako neúspěchy.

## Postup

[`p8-5-rozbor-pauz.py`](p8-5-rozbor-pauz.py) spouští stejnou zátěž (`soak_p8.child`,
1 zahřívací + 4 měřené cykly) se skutečným Qt časovačem 50 ms a navíc s hlídacím
vláknem: při pauze nad 0,3 s každých 100 ms zapíše zásobník hlavního vlákna
(jen rámce `skodacad` a `soak_p8`). Každá pauza nese krok cyklu, po kterém vznikla.
Měřeno v cloudu (Linux, Xvfb, Mesa llvmpipe), postupně na téže zátěži:
`33eedcf` (před novým oknem), `ad7fb19` (nové okno) a s opravami níže.
Cloudový počítač kolísá; srovnávají se proto počty a zdroje pauz, ne jednotlivé ms.

## Zjištění

**1. Nejdelší pauza (přes 3 s) je kontrola v měřicím programu, ne aplikace.**
Vzniká v kroku `assembly-preview-close` na `soak_p8_gui.py:132`
`inspect_assembly(window.session.result, 800)` → `benchmark_p8.inspect_assembly`,
která v hlavní smyčce okna ověřuje `is_valid` všech 800 kopií sestavy. Stejně
dlouhá je i před novým oknem (cloud: `33eedcf` 3,45 s, `ad7fb19` 3,37 s). Délka
závisí na rychlosti počítače – proto stejný kód na GitHubu jednou projde (1,97 s)
a jindy ne (3,17–3,34 s). Na hlídací vlákno při ní dosáhne málo vzorků (OCCT drží
GIL), takže zásobník ukazuje vnější rámec měřiče.

**2. Nové okno přidalo kratší pauzy v obnově stromu prvků (opraveno).**

* Každá obnova stromu nastavovala všem řádkům novou `QIcon`. QIcon nejde porovnat,
  takže každé nastavení hlásilo změnu řádku. Nově se klíč ikony (`druh|barva`) drží
  v `model_card.ICON_ROLE` a ikona se nastaví jen při skutečné změně (`4c1578f`).
* Sloupec těles má `ResizeToContents`. Změna jeho textu (při přepočtu u všech řádků)
  přeměřila celý strom, s vlastní kresbou řádku z P7.51 (Python) řádky × řádky:
  obnova stromu se 122 řádky **200–270 ms**. Během obnovy je sloupec teď
  `Interactive` a šířka se spočítá jednou na konci: **asi 20 ms** (`9bd4f91`).

Obnova stromu bez změny modelu (122 řádků): před novým oknem 2–4 ms, s novým oknem
22–39 ms, po první opravě 12–17 ms.

| Zátěž 1 + 4 cykly (cloud) | `33eedcf` před | `ad7fb19` nové okno | s opravami |
|---|---:|---:|---:|
| Pauzy ≥ 0,3 s mimo krok sestavy | 29 | 72 | 37 |
| Jejich součet | 14,4 s | 46,6 s | 19,1 s |
| Nejdelší z nich | 0,68 s | 0,95 s | 0,71 s |
| Vzorků zásobníku v `_refresh_tree` | 0 | 87 | 4 |

**3. Zbytek je překreslení 3D přes celé okno.** Po opravách jsou nejčastější
zásobníky `viewer.show_part`, `show_guides` a `highlight` → `_request_redraw`.
3D teď podle návrhu 1a zabírá celou šířku okna pod kartami, takže softwarové
OpenGL (cloud, GitHub bez grafické karty) kreslí víc bodů: překreslení asi
12 → 22 ms na volání. Je to cena vzhledu podle návrhu, ne chyba.

Ikony Duo nejsou příčinou: 41 ikon se poprvé nakreslí za 0,18 s a dál se berou
z paměti (obnova 59 tlačítek 0,001 s).

## Regresní testy

`tests/test_model_card.py`:
`test_tree_refresh_without_change_reports_no_row_change` (bez opravy 1 selže)
a `test_tree_refresh_measures_rows_once_not_once_per_changed_row`
(bez opravy 2: 58 měření na 6 řádků místo nejvýš 24).

## Co zůstává otevřené

Mez `qt.max_gap_s` počítá i vlastní kontrolu geometrie měřicího programu v hlavní
smyčce okna. Změna měřicího postupu (např. tuto kontrolu z intervalů Qt vyjmout)
by byla nová změna pravidel P8.5 a čeká na rozhodnutí autora; nic z toho zde není
provedeno ani předpokládáno. Výsledky hostovaných běhů s opravami jsou v PR.
