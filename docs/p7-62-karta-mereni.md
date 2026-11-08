# P7.62 – karta Měření podle rámu 3b

*Druhý krok dávky v draftu PR #134, po [P7.61](p7-61-karta-nahledu-a-pilulka-rezu.md).
Pokyn autora „ok, pokračuj“ (8. 11. 2026). Dávka se vydá najednou, podle rozhodnutí
„Větší dávky“ z téhož dne.*

## Co se změnilo

- **Co je vybráno.** Pod nadpisem karty Měření je „Vybráno: 2 díry · Závity M8 ×2“
  místo „Vybráno: 2 plochy“, jako v rámu 3b:
  - Stěna díry se pozná podle toho, že její normála míří k ose válce (`inspection.is_hole`).
    Čep ani vnější plášť trubky dírou nejsou.
  - Ke kterému prvku stěny patří, hledá `ModelSession.selection_owner` stejně jako
    pojistka původu u přímých úprav (P2): od kterého prvku plocha nepřetržitě existuje.
  - Když plochy patří k různým prvkům nebo to nejde určit, název prvku se vynechá.
  - „2 díry“ se ukáže i ve stavovém hlášení okna.
- **Řádek „Osy: rovnoběžné“.** Pod hodnotami měření dvou rovnoběžných os je řádek
  „Osy: rovnoběžné“. Podobně „Plochy: rovnoběžné“ a „Hrany: rovnoběžné“. Je to jen
  informace: nejde vybrat ani uložit, protože nemá číslo.
- **Desetinná čárka.** Hodnoty v kartě Měření, v pilulce, v popisku čáry ve 3D
  a v kartě Řez (plocha řezu, rozsah posuvníku) se ukazují s čárkou („40,00 mm“).
  - Data se nemění: položky seznamu, uložená měření v souboru, CSV, příkazová řádka
    i ostatní panely dál používají tečku.
- Model, formát souborů (34) ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_tool_cards.py` (upravené 3) | skutečný výběr dvou děr M8: „Vybráno: 2 díry · Závity M8 ×2“, poslední řádek „Osy: rovnoběžné“ nejde vybrat, pilulka „Rozteč os 40,00 mm“, popisek čáry „40,00 mm“; řez „-40,00 až 40,00 mm“; `decimal_comma` nechá tečku za větou |
| `tests/test_inspection.py` (+1) | stěna díry v desce je díra, plášť válce ani rovina ne |
| `tests/test_gui.py` (upravené 4) | popisek tloušťky stěny a rozteče ve 3D a plocha řezu s čárkou; řádek nejkratší vzdálenosti se hledá podle názvu (poslední je „Osy: rovnoběžné“) |
| úplná sada `pytest -q` (Linux, mění se `session.py`) | 3114 úspěšných, 2 přeskočené, 1 chyba v testu, který bral poslední řádek jako nejkratší vzdálenost; po opravě testu 5/5 dotčených testů úspěšných; `ruff check src tests` bez nálezů |
| self-test „Karty nástrojů“ (Linux Xvfb, skutečné 3D) | „Vybráno: 2 díry · Závity M8 ×2“, řádek „Osy: rovnoběžné“ nejde vybrat, pilulka „Rozteč os 40,00 mm“, plocha řezu „1 493,91 mm²“; celý self-test OK |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[3b měření](p7-62-srovnani/3b-mereni-srovnani.png), [3c řez](p7-62-srovnani/3c-rez-srovnani.png).

## Meze

- Návrh píše „Závity M8“, aplikace „Závity M8 ×2“ (stejný krátký údaj jako strom).
- Desetinná čárka je jen v kartách Měření a Řez, v pilulce a v popisku ve 3D. Karta
  Díl, NDT a dialogy ukazují tečku jako dosud.
- Díra se pozná jen u válcové stěny. Kuželové zahloubení a plocha závitu z plošek se
  počítají jako plochy.
