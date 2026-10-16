# ŠkodaCAD – pravidla pro Gemini (Google Antigravity)

Úplná pravidla projektu jsou v **`AGENTS.md`** (společný soubor pro všechny AI nástroje) a stav
projektu, nastavení prostředí a další krok v **`docs/PREDANI.md`**. Před první změnou si přečti
oba soubory celé – tento soubor je jen shrnutí pro případ, že se `AGENTS.md` nenačte sám.

@AGENTS.md

## Nejdůležitější (podrobně v `AGENTS.md`)

- Autor **neprogramuje**: komunikuj **česky**, jednoduše, bez žargonu; každou odpověď zakonči
  řádkem `➡️ **Nejvhodnější další krok:** <krok> – <proč>`, alternativy až za ním.
- **Zásadní rozhodnutí** (architektura, nová závislost, změna formátu JSON, nová etapa NDT)
  nejdřív navrhni a nech autora schválit. Do `main` jen přes pull request na jeho „Sluč to“
  a se zelenými workflow „Windows aplikace“ i „macOS aplikace“.
- **Zamčené verze** (`pyproject.toml`): Python 3.13, build123d 0.13.0 / Open CASCADE 8.0.1,
  PySide6 6.11.2, slvs 3.2, anthropic 1.15.0, PyInstaller 6.22.3. Každé volání knihovny ověř
  spuštěním – nevymýšlej třídy ani parametry.
- **Malé kroky**: po každém `ruff check src tests` a `pytest -q` (vše zelené), pak commit.
- Plochy a hrany **nikdy indexem**, jen významem (`selectors.py`); jednotky mm a stupně; chyby
  česky; GUI modeluje jen přes `ModelSession`.
- **NDT/UT**: jen přístupnost sondy a geometrické pokrytí (`docs/ndt/04-zavazne-vymezeni-ut.md`),
  povinné upozornění `ndt.UT_DISCLAIMER` beze změny; výsledky NDT se nevymýšlejí.
- AI asistent **uvnitř aplikace** používá Claude API (`anthropic`, modely `claude-opus-5-5` /
  `claude-sonnet-5-5`) – je to schválené rozhodnutí, neměň ho na jiného poskytovatele.
