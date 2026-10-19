# Závazné vymezení rozsahu PT modulu ŠkodaCAD

**Rozhodnutí autora: 19. 10. 2026** – schválením návrhu etapy 11 včetně doporučení 1–9
([19-navrh-etapa-11.md](19-navrh-etapa-11.md)). Dokument má stejnou platnost jako
[závazné vymezení UT](04-zavazne-vymezeni-ut.md) a přednost před staršími návrhy
(`01-…`, `02-…`, `03-…`) všude, kde by požadovaly fyzikální výpočet kapilární zkoušky. Jde
o změnu zadání pro Claude Code, nikoli o schválený NDT postup.

## Co PT modul SMÍ vyhodnocovat

Jen **geometrickou přístupnost povrchu** pro jednotlivé kroky kapilární zkoušky (podle
EN ISO 3452-1: příprava a předčištění, nanesení penetrantu, odstranění přebytku, nanesení
vývojky, prohlídka, závěrečné čištění):

1. **Nástřik:** vede na místo volná přímka zvenku pod zadaným úhlem od kolmice?
2. **Otření nástrojem:** vejde se na místo zadaný nástroj (kulička špičky a dřík)?
3. **Prohlídka:** je místo vidět pod zadaným úhlem k povrchu a vejde se oko do zadané
   vzdálenosti?
4. **Upozornění:** šířka mezery proti protější stěně a otevřenost místa (podíl volných
   směrů).

**Doporučené názvy v GUI a protokolech:** „Přístupnost povrchu pro PT“,
„Mapa geometrické přístupnosti PT“. Nepoužívat označení, která slibují víc než geometrii
(například „mapa citlivosti“).

## Co PT modul NESMÍ tvrdit, že vyhodnocuje

- **Fyziku zkoušky:** smáčivost, vzlínání ani odstranitelnost penetrantu, dobu penetrace
  a vyvolání, kvalitu vrstvy vývojky, vliv materiálu, drsnosti, teploty a znečištění.
- **Podmínky prohlídky:** osvětlení a UV-A (ISO 3059) se nepočítají, program na ně jen
  upozorní.
- **Detekovatelnost vad:** citlivost zkoušky, velikost nebo druh zjistitelné vady, způsobilost
  kontroly podle normy.

„Přístupné“ **není** důkaz, že by se na místě vada našla. Upozornění na úzkou štěrbinu
(„hrozí falešná indikace“) je jen geometrické varování, ne výpočet vzlínání.

## Výsledky a jejich význam

- **Přístupné:** všechny zvolené kroky geometricky jdou se zadanými nástroji a mezemi.
- **Omezené:** některý krok jde jen s omezením (jen jemný nástroj, jen šikmo) nebo platí
  upozornění (úzká mezera, hluboké místo).
- **Nepřístupné:** některý zvolený krok geometricky nejde se žádným zadaným nástrojem ani
  v žádném zkoušeném směru. Nejde o důkaz, že jiný postup není možný.
- **Nelze spolehlivě vyhodnotit:** rozhodující paprsek je nejistý (přes hranu, tečně), vstupy
  jsou neúplné nebo jádro nerozhodlo. Nevyplňovat fiktivním výsledkem.

Uvádět použité nástroje, úhly, vzdálenost, postup čištění, počet směrů, krok sítě, verzi
algoritmu a které hodnoty jsou zvolené pro výpočet (ne z normy). Procento přístupné plochy
je jen geometrický podíl plochy, ne pravděpodobnost nalezení vady.

## Povinné upozornění v GUI i v každém exportovaném protokolu

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti povrchu pro jednotlivé kroky kapilární zkoušky (nanesení, čištění a odstranění přebytku, vývojka, prohlídka) na základě zjednodušených modelů nástrojů a výhledu. Nevyhodnocuje smáčivost, vzlínání ani odstranitelnost penetrantu, citlivost zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.

## Požadavky na implementaci

1. Výpočet geometrie je oddělený od okna (`ndt/pt.py`), opakovatelný (pevná sada směrů,
   žádná náhoda) a testovaný na ručně spočítaných dílech.
2. O tom, že se nástroj vejde, rozhoduje přesná kontrola průniku s tělesem; paprsky jsou jen
   rychlé síto. Nejisté se nikdy nepočítá jako přístupné.
3. Upozornění výše je doslova v konstantě `skodacad.ndt.PT_DISCLAIMER`; `tests/test_ndt_scope.py`
   ho porovnává s tímto dokumentem.
4. PT nikdy nemění geometrii dílu a AI není zdrojem čísel ani výsledků PT.
