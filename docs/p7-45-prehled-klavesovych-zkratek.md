# P7.45 – přehled klávesových zkratek

Na pokyn autora z 5. 11. 2026 („ok, udělej přehled klávesových zkratek“), navazuje
na hledání příkazů [P7.37](p7-37-hledani-prikazu.md) a filtry
[P7.40–P7.44](p7-43-text-hledani-a-filtr-mereni.md).

## Co uživatel uvidí

- **Nápověda → Klávesové zkratky…** nebo klávesa **F1** otevře přehled.
  Hlavní okno (díl) i okno sestavy mají vlastní přehled; sestava dostala novou
  nabídku *Nápověda*.
- Řádky jsou ve skupinách podle nabídek (*Soubor*, *Úpravy*, *Model*, *Zobrazení* …)
  a na konci dvě skupiny ovládání, které není příkazem:
  - **Myš ve 3D** – otáčení, posun (i Shift+levé na trackpadu), kolečko, dvojklik,
    výběr kliknutím a Ctrl/⌘+klikem; v dílu pravý klik a NDT sonda s Alt
    (na Macu ⌥), Esc ruší rozpracované tažení rukojeti.
  - **Ve stromu a filtrech** – Enter/↓ a Esc ve filtrech; v dílu Esc v náhledu
    nového prvku a Ctrl/⌘+Enter v panelu AI; v sestavě Ctrl/⌘+A a Esc ve stromu.
- Nahoře je filtr se stejným ovládáním jako ostatní filtry (bez diakritiky,
  „Filtr: 2 z 43 zkratek“, Enter skočí na první nalezený, Esc filtr zruší).
- Přehled je jen pro čtení: nic nespouští a model, výběr ani historii nemění.
  Příkaz se spouští dál přes *Najít příkaz* (Ctrl+Shift+P).
- Na Macu se zkratky ukazují systémovým zápisem (⌘, ⇧, ⌥).

## Jak to funguje

- `gui/shortcut_overview.py`: `collect_shortcuts` čte zkratky přímo ze
  skutečných `QAction` okna (stejný průchod nabídkami a pásem karet jako
  hledání příkazů, `collect_commands`). Přehled proto **nezastará** – změněná
  nebo odebraná zkratka se v něm projeví sama (hlídá test).
- Ovládání myší a místní klávesy jsou pevné řádky ověřené proti kódu
  (`viewer.py` – tažení, kolečko, Alt, dvojklik, Esc; `tree_filter.py`;
  stromu sestavy). Sestava nemá místní nabídku ve 3D ani NDT sondu, proto
  tyto řádky neukazuje.
- `conflicts` vypíše zkratku, kterou by měly dva příkazy téhož okna (Qt by pak
  nespustil žádný). Dnes žádná taková není v dílu ani v sestavě.

## Ověření

- `tests/test_shortcut_overview.py` (9 testů): skutečná akce F1 v dílu i sestavě
  otevře přehled se zkratkami z nabídek i ovládáním myší, filtr „ulozit“ najde
  právě *Uložit* a *Uložit jako*, Esc vrátí všechny řádky, model a historie se
  nezmění; žádná zkratka se neopakuje a každá akce se zkratkou v okně je
  v přehledu (kromě dvou místních, které jsou mezi pevnými řádky); změna
  zkratky se v přehledu projeví; zápis ⌘/⌥ na Macu; Enter ve filtru.
- Self-test balíčku (Windows i macOS) má krok „✓ Přehled zkratek (díl)“
  a „✓ Přehled zkratek (sestava)“: skutečná klávesa F1, počty řádků, filtr,
  Esc, kontrola kolizí a beze změny modelu.
- Snímek dialogu pod Xvfb byl prohlédnut (české tlačítko *Zavřít*, čitelné
  sloupce).
