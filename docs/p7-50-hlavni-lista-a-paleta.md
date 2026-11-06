# P7.50 – hlavní lišta a plovoucí paleta příkazů (vydání A, krok 3)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R2–R4 schválil
autor 6. 11. 2026.*

## Co se změnilo

- **Hlavní lišta 52 px** (`gui/main_bar.py`) nahradila pás přes celou šířku okna:
  - vlevo název dílu (13/700) a podtitulek „soubor · materiál · upraveno“
    (u ukázky „nový model“);
  - uprostřed segmentový přepínač činností 3D model | Skica | Výkres | Sestava | NDT |
    Zobrazení (aktivní položka `--ctl`, podklad `--sep`);
  - vpravo Zpět/Znovu s ikonami Duo a pole „Najít příkaz…“ 220 × 26 se zkratkou
    (Ctrl+Shift+P, na Macu ⌘⇧P), které otevře dosavadní hledání příkazů.
- **Plovoucí paleta příkazů** je karta nahoře uprostřed volného místa mezi levou
  a pravou kartou. Tlačítka mají šířku 56 px, ikonu 24 px nad popiskem 11 px a skupiny
  oddělují svislé čáry. Popisky skupin zmizely; zůstaly jako popis tlačítek pro čtečky
  a v hledání příkazů. Když se stránka nevejde, objeví se posuvník a paleta je o něj
  vyšší, takže popisky nezakryje.
- **Činnost „Soubor“ zmizela** z přepínače. Nový, Otevřít, Import STEP, Uložit,
  Uložit jako a Export jsou v nabídce Soubor a mají dosavadní zkratky (R4).
- **Oblíbené příkazy** jsou na konci palety za oddělovačem, jen jako připnutá tlačítka
  (R4). Sbalení palety (dvojklik na činnost, Ctrl/⌘+F1) skryje příkazy činnosti, ale
  připnuté oblíbené zůstanou vidět. Kliknutí na činnost paletu zase rozbalí.
- **Mac:** sjednocený titulek a lišta (`setUnifiedTitleAndToolBarOnMac`), takže semafor
  okna je v hlavní liště (R3). Lišta má vlevo místo pro semafor.
  **Windows a Linux:** systémový titulek a pod ním řádek nabídek (R2).
- „Celý díl“ obchází i paletu nahoře. Díl se vejde pod ni a mezi boční karty.
- Bez změny zůstalo: rozhraní pásu (`add_page`, `select_page`, `page`, `collapsed`,
  `command_groups`), uložené rozložení `okno.json`, hledání příkazů, přehled zkratek F1
  a oblíbené. Model, výpočty ani formát souborů se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_gui.py::test_main_bar_and_floating_palette_follow_design` | výška 52 px, název a podtitulek včetně „upraveno“ po změně parametru, šest činností bez „Soubor“, paleta nahoře mezi kartami, pole hledání otevře dialog hledání, dvojklik sbalí a klik rozbalí |
| `tests/test_gui.py::test_ribbon_overflow_keeps_commands_available` | v úzkém okně se paleta posouvá a posuvník nezakryje popisky |
| `tests/test_floating.py::test_command_palette_is_centered_between_side_cards_and_reported_as_top_inset` | paleta je uprostřed volného místa, nepřesáhne mezi karty a hlásí horní okraj pro „Celý díl“ |
| `tests/test_viewer_surface.py` | „Celý díl“ s horním okrajem |
| self-test „Hlavní lišta a paleta“ (Linux Xvfb) | při 1440/1024/960 se lišta vejde, skutečný klik na činnost Zobrazení přepne paletu, ta nepřekrývá karty a skutečný klik na tlačítko palety spustí *Celý díl* právě jednou; na Macu se ověří semafor v liště |
| self-test hledání příkazů a oblíbených | připnutý příkaz zůstane vidět i při sbalené paletě |

Snímky: [světlý](p7-48-snimky/okno-lista-svetly.png), [tmavý](p7-48-snimky/okno-lista-tmavy.png),
[činnost NDT](p7-48-snimky/okno-lista-ndt.png).

## Meze

- Karta NDT je zatím původní dlouhý panel s posuvníky. Přestaví ji NDT průvodce (P7.55).
- Stavový řádek s nápovědou k myši zůstává do P7.53 (pilulka a přepínač pohledů).
- Semafor v liště a vzhled na Windows ověří až self-test balíčků na GitHubu.
