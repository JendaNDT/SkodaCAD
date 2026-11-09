# P7.75–P7.77 – značky u vazeb skici, stručná karta Výběr a náhled prvku (rámy 2d, 3a)

*Navazuje na [P7.72–P7.74](p7-72-texty-karty-diry.md) (PR #137, `1c8163c`, ověřeně vydané).
Pokyn autora „ok, pokračuj v práci“ (9. 11. 2026). Jedna dávka podle rozhodnutí „Větší
dávky“; každá změna vzhledu ověřená i na responzivitu (pravidlo z 8. 11. 2026).*

## Co se změnilo

- **P7.75 Značky u vazeb skici (rám 2d).** Každý řádek vazby v levé kartě skicáře začíná
  malou značkou druhu vazby (například „∥“ rovnoběžně, „⊥“ kolmo, „─“ vodorovně, „│“
  svisle, „=“ stejně velké, „Ø“ průměr, „R“ poloměr, „∠“ úhel). Barva je šedá, u vazby se
  sporem červená. Popisek se tím nezměnil, jen je předsazený o značku. Každý druh vazby,
  který skicář zná, má svou značku (hlídá to test).
- **P7.76 Karta Výběr bez opakovaného stavu (rám 2d).** Věta „Zbývá určit: 2 rozměry“ je
  v pilulce dole, karta Výběr ji už neopakuje. V kartě zůstávají jen varování (například
  řešič hlásí spor nebo nezavřený obrys). Bez varování je řádek skrytý a karta je kratší.
- **P7.77 Náhled prvku (rám 3a).**
  - Šedý řádek „Druh prvku (id)“ pod nadpisem karty ho jen opakoval. V náhledu je skrytý,
    druh a id jsou v bublině nadpisu (i při prohlížení téhož prvku).
  - Sražení má pole „Vzdálenost [mm]“ místo „Velikost [mm]“, jako v návrhu.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění. Změna schématu sražení
  je jen popisek pole: klíč `distance` i uložená data zůstávají stejné.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_sketch_mode.py` (+1) | `KIND_GLYPHS` pokrývá všechny druhy v `CONSTRAINT_LABELS`; značka se skutečně vykreslí (delegát do obrázku); karta Výběr bez varování skrytá, s varováním viditelná |
| `tests/test_inspector_card.py` (+1) | v náhledu je řádek druhu skrytý a má bublinu, nadpis nese „(id)“ v bublině, popisek chamferu je „Vzdálenost [mm]“ |
| testy okna, karet, náhledů, skicáře, sestavy a schématu (22 souborů, Linux) | 543 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test (Linux Xvfb, skutečné 3D) | „Skicář v okně“: karta Výběr bez opakovaného stavu, „Zbývá určit: 2 rozměry“ v pilulce; celý self-test OK |
| skript responzivity (5 velikostí × 7 rámů) | 35 snímků, žádný nový nález; zůstává jen známých 7 posuvníků obsahu karty NDT (meze P7.64–P7.67) |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[2d skicář](p7-75-srovnani/2d-skicar-srovnani.png),
[3a náhled prvku](p7-75-srovnani/3a-nahled-prvku-srovnani.png).

## Meze a zbývající rozdíly

- Karta prvku dál ukazuje hodnoty jen pro čtení s tlačítkem *Upravit prvek* (P7.6).
- Pole *Název* zůstává v náhledu nového prvku (návrh ho nemá); hrany se popisují jako
  „Úsečky na horní ploše…“ místo „Obvod horní plochy“.
- Skicář nabízí jen vazby, které řešič pro daný výběr přijme; počet vazeb najednou nahoře
  se řídí výběrem (rozdíl proti návrhu je dán ukázkovým výběrem, ne chybějící funkcí).
- Karta NDT v nízkém okně posouvá obsah kroku (doslovné upozornění UT, R7).
