# P7.48 – vzhled a ikony Duo (vydání A, krok 1)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md). Rozhodnutí R1–R7 autor
schválil 6. 11. 2026 („schvaluji R1–R7“).*

## Co se změnilo

- **Barvy z návrhu.** Nový modul `gui/ui_theme.py` obsahuje všech 23 barev z tabulky
  „Design Tokens“ návrhu, zvlášť pro světlý a tmavý vzhled. Paleta aplikace se z nich
  nastaví při startu a při každé změně *Zobrazení → Vzhled*. Pokud je zvoleno
  „Podle systému“, nastaví se i při změně vzhledu systému. Panely mají barvu
  neprůhledné karty (`--float` nad horní barvou 3D, rozhodnutí R1). Pole jsou `--ctl`,
  odkazy a ikony `--accent` a vybraná položka `--btn`.
- **Ikony Duo.** 41 ikon z návrhu je vložených v `gui/duo_icons.py`, takže balíček
  nepotřebuje další soubory. Kreslí je `QSvgRenderer`: obrys v barvě odkazu palety,
  vybrané plochy toutéž barvou s průhledností 0,24 (světlý) nebo 0,30 (tmavý). Mají je
  příkazy modelu, Nový/Otevřít/Uložit/Zpět/Znovu, hledání, NDT metody UT/PT/MT/RT,
  studie, audit, návrh úpravy, měření, řez, mapa tloušťky a pohledy Izo/Zepředu/Shora/
  Celý díl. Příkazy, pro které sada Duo ikonu nemá (např. AI asistent, Přepočítat),
  dál kreslí původní glyf.
- **Pozadí 3D.** Přechod je přesně podle návrhu: světlý #f2f5fa → #b8c4d6, tmavý
  #3b4049 → #16181c a popisky os jsou v tmavém vzhledu bílé. Při měření se ukázalo,
  že OCCT dřívější zápis barev (`Quantity_TOC_RGB`) bral jako lineární a na obrazovce
  je zesvětlil. Spodek světlého přechodu tak byl #dde4ec místo #b8c4d6. Nově se
  barvy předávají jako sRGB. Kreslení dílu, výběr ani ostatní barvy ve 3D se nemění.
- **Písmo.** Na Windows Segoe UI Variable Text (nebo Segoe UI), na Macu zůstává systémové
  SF Pro. Velikost písma se zatím nemění, upraví ji krok P7.50 spolu s lištou.

Model, výpočty, NDT ani formát souborů se nemění. Vzhled je jen preference okna.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_ui_theme.py` (12 testů) | barvy přesně podle tabulky v `p7-48-navrh-okna/README.md` (test tabulku přímo čte), čitelnost textu ≥ 4,5 : 1 na kartách i polích, `--fg3` ≥ 3 : 1, paleta, přepnutí vzhledu, 41 ikon shodných se soubory návrhu, tmavá varianta, vykreslení všech ikon v obou barvách, původní glyfy |
| `tests/test_gui.py::test_appearance_switch_recolors_duo_icons_and_3d_background` | skutečné akce *Vzhled → Tmavý / Světlý*: paleta, ikony, pozadí 3D; model ani historie beze změny |
| testy okna, hledání, oblíbených, zkratek, filtrů, sestavy a pozadí | viz PR |
| self-test „Vzhled a ikony“ (Linux Xvfb) | 41 ikon v obou vzhledech, paleta, snímek 3D tmavý/světlý |
| měření snímků 1440 × 900 | pozadí 3D nahoře/dole #f2f5fa/#b8c4d6 a #3b4049/#16181c, přesně jako návrh |

Snímky: [světlý](p7-48-snimky/okno-svetly.png), [tmavý](p7-48-snimky/okno-tmavy.png).
Rozložení okna (pás, docky) je zatím původní, mění se v P7.49 a P7.50.

## Meze

- Na macOS se nativní styl ovládacích prvků řídí paletou jen částečně (tlačítka a pole
  kreslí systém). Přesné barvy karet a polí doladí P7.49–P7.52 vlastním stylem karet.
- Okno sestavy sdílí paletu, ikony Duo i pozadí 3D (R6); jeho rozložení se v tomto
  plánu nemění.
