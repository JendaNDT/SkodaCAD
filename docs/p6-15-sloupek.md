# P6.15 – Sloupek: návrh a provedení

*Datum 10. 11. 2026, navazuje na [žebro](p6-13-zebro.md) v téže dávce (PR #141, formát 36).
Pokyn autora „další rozšíření P6“. Zbylí kandidáti z P6.1 (proměnné zaoblení pro víc hran,
přechod s kruhy) jsou výzkumně riskantní – dřívější průzkum ukázal, že kruhové profily jádro
nezaručí. Sloupek je užitečný pro krabičky a desky plošných spojů a využívá už ověřený postup
„až k tělesu“ ze žebra.*

## Jak sloupek funguje (D1–D6)

- **D1 Prvek `boss`**, formát **36** (společný se žebrem; ani jedno zatím nebylo vydáno).
- **D2 Zadání:** `plane` + `offset` (rovina, odkud sloupek vede), `positions` (středy),
  `diameter`, volitelně `hole_diameter` a `hole_depth`, `direction` (`reverse` = proti normále
  roviny, `normal` = po normále). Hodnoty mohou být výrazy.
- **D3 Až k tělesu:** z válce se odečte těleso a ponechají se jen kusy začínající na středu
  startovní kružnice; kus za tělesem zmizí.
- **D4 Otvor jen do sloupku:** vrtá se do ponechaného kusu, těleso pod ním zůstane celé
  (zkouška: bod uprostřed otvoru ve dně je v materiálu, v otvoru sloupku je vzduch). Stěna
  kolem otvoru aspoň 0,2 mm.
- **D5 Žádné tiché přečnívání:** sloupek, který dosáhne konce válce (pod ním není materiál),
  začíná v materiálu nebo se tělesa nedotýká, se odmítne česky.
- **D6 Společná kontrola P1** přes `ctx.apply`; patří do `VOLUME_FEATURES` i
  `REPEATABLE_FEATURES` (pole). Nabídka *Přidat prvek → Sloupek* s náhledem, ukázka
  [`sloupky_krabicka.json`](../examples/sloupky_krabicka.json).

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_boss.py` (22) | objem podle vzorce (plný válec, s otvorem, slepý otvor, tři sloupky), otvor nepoškodí dno, sloupek zčásti ve stěně, odmítnutí (špatný směr, přes okraj, start v materiálu, rozměry, struktura), parametry, pole, popis ve stromu, formát 36, ukázka |
| `tests/test_gui.py` (+1) | nabídka *Sloupek*: náhled s objemem podle vzorce, potvrzení = jeden krok, Zpět |
| ukázka | čtyři sloupky Ø6 s otvorem Ø2,5, objem přesně podle vzorce, jedno těleso |

Snímky okna (Linux Xvfb, 1440 × 900):
[hotové sloupky](p6-15-snimky/sloupek-hotove-karta-prvku.png),
[nový sloupek – náhled](p6-15-snimky/sloupek-nove-nahled.png).

## Meze

- Sloupek je válec (bez kužele, žeber a zaoblení paty); otvor je hladký (bez závitu).
- Kopie z pole mimo materiál vznikne jako samostatné těleso – jako u ostatních prvků pole.
- Neověřeno na vlastním dílu autora.
