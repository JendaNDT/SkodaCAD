# P7.68–P7.71 – karta prvku, karta Řez a pohledy skicáře (rámy 2a, 3c, 2d)

*Navazuje na responzivní okno [P7.64–P7.67](p7-64-responzivita.md) (PR #135, `6da18ad`,
ověřeně vydané). Pokyn autora „ok, pokračuj“ (8. 11. 2026). Jedna dávka podle rozhodnutí
„Větší dávky“; každá změna vzhledu ověřená i na responzivitu (pravidlo z 8. 11. 2026).*

## Co se změnilo

- **P7.68 Pilulka u díry (rám 2a).** Vybraná díra ve stromu ukáže v pilulce „Vybráno:
  Upínání · 4 díry M6“, jako návrh. Čeština počtu: 1 díra, 2–4 díry, 5 a víc děr. Ostatní
  prvky ukazují krátký údaj ze stromu jako dosud („R2“, „×6“…). Řádek stromu zůstává
  „Upínání · M6 ×4“.
- **P7.69 Sekce v kartě prvku (rám 2a).**
  - Polohy děr jsou ve sbalitelné sekci „▾ Středy děr“ s počtem vpravo („4“), pod ní
    číslovaná tabulka.
  - Nevyplněné volby (vlastní průměr, hloubka, posun roviny…) jsou na konci karty ve sbalené
    sekci „▸ Další volby“ s počtem. Rozbalená je ukáže jen pro čtení. Dřív tam byla věta
    „Nevyplněné volby: 8. Ukáže je Upravit prvek (Ctrl+E).“
  - Bublina sekce vyjmenuje, které volby to jsou. Název prvku do sekce nepatří, je
    v titulku karty.
  - Karta díry se teď při 1440 × 900 vejde bez posuvníku (samotest už nehlásí „!“).
- **P7.70 Karta Řez (rám 3c).**
  - Nabídka roviny ukazuje „Kolmo na Y“ (celý název je v bublině položky).
  - Popisek posuvníku je „Poloha“; osa je v bublině pole („Poloha Y [mm]“).
  - Pod plochou řezu je krátká věta „Řez je jen pohled. Model se nemění a do souboru se
    neukládá.“ Kde řez je a v jaké barvě, říká pilulka a bublina věty.
- **P7.71 Pohledy skicáře (rám 2d).** Ve skicáři je vpravo dole přepínač „Kolmo na skicu |
  Celá skica“ místo pohledů 3D:
  - *Celá skica* dá celý obrys do volného místa mezi kartami (stejně jako *Celý obrys*).
  - *Kolmo na skicu* posune počátek skici doprostřed volného místa a měřítko nechá.
  - Po Hotovo nebo Zrušit se vrátí pohledy 3D.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_model_card.py` (upravený 1) | pilulka „Vybráno: Upínání · 4 díry M6“; sekce „Středy děr“ s počtem 4 rozbalená, klik ji sbalí; „Další volby“ sbalené, tlačítko zůstává aktivní i v kartě jen pro čtení, klik ukáže „Vlastní průměr“ jen pro čtení, název nikdy |
| `tests/test_tool_cards.py` (upravený 1), `tests/test_gui.py` (upravený 1) | karta Řez: „Kolmo na Y“, „Poloha“ a bublina „Poloha Y [mm]“, krátká věta, poloha a barva řezu v bublině |
| `tests/test_sketch_mode.py` (+1) | přepínač skicáře vidět místo pohledů 3D, „Celá skica“ přizpůsobí měřítko, „Kolmo na skicu“ dá počátek doprostřed volného místa, karta se nepřekrývá s ostatními, po Zrušit zpět pohledy 3D |
| testy okna (21 souborů, Linux) | viz PR |
| self-test (Linux Xvfb, skutečné 3D) | „Levá karta“: skutečný klik rozbalí a sbalí „Další volby“ (7), pilulka „4 díry M6“; „Skicář v okně“: skutečný klik na „Celá skica“; celý self-test OK |
| skript responzivity (5 velikostí × 7 rámů) | viz PR |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[2a model](p7-68-srovnani/2a-model-svetly-srovnani.png),
[3c řez](p7-68-srovnani/3c-rez-srovnani.png),
[2d skicář](p7-68-srovnani/2d-skicar-srovnani.png).

## Meze a zbývající rozdíly

- Karta prvku dál ukazuje hodnoty jen pro čtení s tlačítkem *Upravit prvek* (P7.6). Návrh
  kreslí rovnou úpravu se Zrušit / Potvrdit.
- Texty voleb zůstávají ze schématu: „válcové zahloubení pro imbus (ISO 4762)“,
  „Rovina: horní plocha dílu“, „Středy děr“. Návrh má „Válcové zahloubení“, „Na ploše:
  Horní plocha“, „Polohy děr“. Změna schématu by změnila i formulář úprav a příkazovou
  řádku, je to samostatné rozhodnutí.
- Karta Řez má dál řádek „Řez ☑ zapnutý (klávesa R)“ (meze P7.54).
- Skicář: návrh nabízí ve výběru víc vazeb najednou (Tečně, Na bod/čáře, Stejně velké,
  Souměrně, sbalené Ostatní). Aplikace ukazuje jen vazby, které řešič pro výběr přijme.
