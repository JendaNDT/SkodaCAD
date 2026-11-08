# P7.63 – pilulka NDT podle rámu 2c

*Třetí krok dávky v draftu PR #134, po [P7.61](p7-61-karta-nahledu-a-pilulka-rezu.md)
a [P7.62](p7-62-karta-mereni.md). Pokyn autora „ok, pokračuj“ (8. 11. 2026).*

## Co se změnilo

- **Pilulka u přiložené UT sondy** ukazuje „● Přiloženo | Paprsek s 1 odrazem · horní
  plocha“, jako v rámu 2c. Dřív tam byl dlouhý popis kliknuté plochy („Plocha – rovinná,
  obsah 20 000 mm², normála … · pravým tlačítkem …“).
  - Počet odrazů bere ze sondy studie: „bez odrazu“, „s 1 odrazem“, „s 2 odrazy“.
  - Plochu pojmenuje podle směru: horní, spodní, přední, zadní, pravá, levá. Jinak napíše
    „šikmá nebo zakřivená plocha“.
  - Když sonda nedosedá, pilulka ukáže první důvod (třeba mezeru pod sondou).
- **Priorita zpráv:** popis kliknuté plochy má u přiložené sondy nižší váhu. Celý popis je
  v bublině pilulky a dál ve stavovém řádku (testy, čtečky). Skutečná hlášení okna
  (např. „Uloženo“) mají přednost. Po posunu sondy se věta obnoví.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_ndt_wizard.py` (upravený 1) | skutečné kliknutí na desku a *Přiložit sondu sem*: pilulka „Paprsek s 1 odrazem · horní plocha“, stavový řádek dál s popisem plochy; hlášení „Uloženo“ má přednost, po jeho smazání se věta vrátí |
| testy okna, karet, pilulky, náhledů, skicáře, NDT průvodce a návrhu (Linux) | 38 + 216 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „NDT průvodce“ (Linux Xvfb, skutečné 3D) | přiložení („Paprsek s 1 odrazem · horní plocha“), celý self-test OK |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[2c NDT průvodce](p7-63-srovnani/2c-ndt-pruvodce-srovnani.png).

## Meze

- Návrh píše „horní plocha desky“. Aplikace název dílu nepřidává: „deska“ je název
  souboru, ne druh plochy.
- Pilulka u spočítaného pokrytí (rám 3d) zůstává beze změny.
