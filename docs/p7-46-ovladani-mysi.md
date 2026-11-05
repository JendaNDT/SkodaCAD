# P7.46 – Ovládání myší v Nápovědě

Na pokyn autora z 5. 11. 2026 („ok, uprav text Ovládání v Nápovědě“), navazuje
na [P7.45 – přehled klávesových zkratek](p7-45-prehled-klavesovych-zkratek.md).

## Co se změnilo

- Dřív *Nápověda → Ovládání* ukázalo malé okno se zprávou: pět řádků ovládání
  myší, napsaných zvlášť. Část ovládání v něm chyběla (NDT sonda s Alt, Esc ve 3D)
  a text se mohl rozejít s přehledem F1.
- Teď je to **Nápověda → Ovládání myší…** a otevře **tentýž přehled jako F1**,
  rovnou s vybranou skupinou *Myš ve 3D*. Text ovládání je tak jen na jednom
  místě (`shortcut_overview.py`), ověřený proti kódu prohlížeče.
- Totéž má okno sestavy (dosud ovládání v Nápovědě nemělo).
- Stavový řádek dílu na konci připomíná „F1: všechny zkratky“, sestava
  „F1: zkratky a ovládání myší“.
- Jen pohled: model, výběr ani historie se nemění. Formát beze změny.

## Ověření

- `tests/test_shortcut_overview.py`: Ovládání myší v dílu i sestavě je v Nápovědě
  a otevře přehled s vybraným prvním řádkem skupiny *Myš ve 3D*; F1 dál začíná
  nahoře bez výběru; stavový řádek odkazuje na F1.
- `tests/test_gui.py::test_every_action_runs_without_error`: stisk všech akcí
  otevře přehled zkratek dvakrát (F1 a Ovládání myší) místo staré zprávy.
- Self-test balíčku (díl i sestava): krok „✓ Přehled zkratek“ navíc stiskne
  *Ovládání myší…* a ověří, že přehled začíná na skupině *Myš ve 3D*.
- Snímek dialogu pod Xvfb prohlédnut.
