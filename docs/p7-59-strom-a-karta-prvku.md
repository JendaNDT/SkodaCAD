# P7.59 – krátké řádky stromu a zkrácená karta prvku (rámy 2a, 2b)

*Navazuje na [srovnání P7.58](p7-58-ulozeni-a-srovnani.md). Tam vyšly jako největší
rozdíly proti návrhu dlouhé popisy ve stromu a celý formulář prvku v pravé kartě.
Pokračování na pokyn autora „ok, tak pokračuj v práci“ (8. 11. 2026).*

## Co se změnilo

- **Strom prvků podle rámu 2a.** Řádek ukazuje jen jméno prvku („Upínání“) a vpravo
  krátký údaj šedě:
  - díra a normalizovaný díl: velikost a počet („M6 ×4“);
  - pole: „×3“ nebo „3 × 2“;
  - zaoblení: „R2“ (proměnné „R2→R6“);
  - sražení, skořepina a posunutí plochy: „1 mm“;
  - průměr plochy: „Ø12“.
  
  Prvek bez údaje (skica, vysunutí) má vpravo jen stav ✓. Prvek bez jména se jmenuje
  druhem a id („Zaoblení fillet1“).
- **Celý popis zůstává.** Bublina řádku dál ukazuje celý popis i „Počet těles: 1 → 1“.
  Filtr stromu (Ctrl+F) hledá v celém popisu jako dřív. Text položky se nemění, mění se
  jen kresba (`features.tree_name` / `tree_summary`, role `NAME_ROLE` / `SUMMARY_ROLE`).
- **Zkrácená pravá karta při prohlížení prvku:**
  - jen vyplněné hodnoty, bez pole Název (je v titulku karty);
  - polohy děr písmem se stejně širokými znaky, každý bod na řádku, s počtem v popisku
    („Středy děr [x; y] · 4“);
  - nápověda k druhu prvku je v bublině titulku;
  - dole věta „Nevyplněné volby: N. Ukáže je Upravit prvek (Ctrl+E).“
- **Úpravy beze změny.** *Upravit prvek* (Ctrl+E, dvojklik) otevře celý formulář
  v náhledu jako dosud.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_model_card.py` (+1, upravený 1) | kresba řádku „Upínání“ + „M6 ×4  ✓“, skica jen „✓“, bublina s počtem těles; souhrny všech druhů včetně výrazu s parametrem (R2) |
| testy okna, karet, náhledů, skicáře, filtru, sestavy, hledání, NDT průvodce, vodítek, přechodů a zaoblení (Linux) | 208 + 278 + 204 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „Levá karta“ (Linux Xvfb, skutečné 3D) | kresba řádku „Upínání · M6 ×4 ✓“, skutečný klik myší na řádek vybere díru, karta má „Středy děr [x; y] · 4“, skryté pole Název, větu o nevyplněných volbách, obsah 302 px se vejde; celý self-test OK |

Srovnání s návrhem (Linux Xvfb, 1440 × 900, [skript P7.58](p7-58-srovnani-ramu.py)):
[2a světlý](p7-59-srovnani/2a-model-svetly-srovnani.png),
[2b tmavý](p7-59-srovnani/2b-model-tmavy-srovnani.png).

## Meze

- Rozbalovací pole v kartě jen pro čtení jsou šedá (neaktivní), návrh je kreslí běžnou
  barvou. Text druhu díry se v 304 px ořízne („válcové zahloubení p…“).
- Polohy jsou jeden sloupec „x; y“ na řádku, návrh má číslovanou tabulku se dvěma
  sloupci. Sekce „Vlastní průměr“ se nevykresluje sbalená, nevyplněné volby jsou jen
  spočítané v závěrečné větě.
- Patička Zrušit / Potvrdit z rámu 2a patří k náhledu úpravy (*Upravit prvek*), ne
  k prohlížení. To zůstává bez patičky.
- Šířku a zalomení se skutečným písmem Windows a macOS ověří až self-test na GitHubu.
