# P1.2A — průběh a ověření

Autor 20. 10. 2026 schválil [rozsah A1–A7](p1-2a-navrh-spolecne-kontroly-geometrie.md)
slovy „ok, schvaluji“. Dokumentační PR #32 je sloučený jako `15b8bf4`.
Implementace má vlastní větev; ke sloučení implementačního PR je nutný další souhlas autora.

## Průběh

- A.1: společný validátor a kontroly `new/add/cut` jsou v commitu `2bd1c86`.
  Ruff prošel; celý pytest: **1 165 testů / 408,34 s**, bez přeskočení.
  Regrese dokládají analytické objemy, polohu materiálu, oddělené složky a hranice účinku.
- A.2: místní kandidáti zaoblení/sražení/skořepiny a závěrečná pojistka jsou zapojené.
  Cílená sada **176 testů / 10,86 s** prošla; úplná kontrola před druhým commitem probíhá.
  Pozdní chyba skutečného pole děr vrátí původní geometrii; tato regrese nedokládá
  úplnou obnovu všech slovníků kontextu (ta zůstává v P1.2B).
- A.3: společné zprávy, rozhraní, přenos, kompletní kompatibilita a cílové sestavení zatím čekají.
- Cílené testy se provádějí během jednotlivých kroků. Celý pytest a Ruff jsou povinné před commitem;
  konečné výsledky a časy budou uvedené po skutečném dokončení kontrol.
- Ruční přijetí nového balíčku autorem zatím neproběhlo.

## Výchozí měření

Před změnou produkčního kódu vznikla baseline `tests/benchmark_p0.py`:
main `15b8bf48f12b6d59ac6ea554def414f8d4ae4979`, jehož produkční zdroje jsou shodné
s main `6e38d06` uvedeným v návrhu. Python 3.12.14 / macOS arm64,
zahřátí + 3 opakování každého scénáře; časy nejsou prahy pro CI.

Samostatně byly zachycené objemy, celé obálky a počty solidů všech 26 rekurzivních
JSON ukázek na nezměněném jádře. Jde o podklad kompatibility; nezastupuje
analytické ověření fyziky nových regresí.

## Omezení zjištěné při implementaci

build123d 0.13.0 čte `Compound.volume` přes přímé solidy/shelly. Uměle vnořený
compound může mít dva solidy o celkovém objemu 24 250 mm³, ale vlastnost `volume`
vrátí jen 250 mm³. Validátor proto kontroluje shodu vykázaného objemu se součtem
všech skutečných objemových složek a takový rozpor odmítá. Kontejnery prochází,
žádnou složku nevybírá ani potichu nepřeskupuje. Běžné platné vícesolidové tvary
a uzavřené dutiny zůstávají podporované. Obecná oprava tohoto rozhraní knihovny
není součástí P1.2A.

R01 (export/NDT při chybě), R03 (ukládání), R04 (reference), R05 (úplná obnova
kontextu), R12 (popis formátu používaný AI) a NDT-17 zůstávají otevřené.
Formát modelu je stále 22.
