# ŠkodaCAD – pravidla projektu pro AI

## Uživatel a účel

- Osobní parametrický 3D CAD **jen pro autora**, nebude se distribuovat. Licence knihoven proto
  nejsou omezením (GPL knihovny jako řešič SolveSpace jsou v pořádku).
- Autor **neprogramuje**, projekt vzniká vibecodingem. Komunikuj česky, jednoduše a bez žargonu:
  co se změnilo, proč, a jak si to může ověřit (náhled, čísla, testy). Zásadní rozhodnutí
  (architektura, nové závislosti, změna formátu) nejdřív navrhni a nech schválit.
- **Každou odpověď zakonči jasně označeným nejvhodnějším dalším krokem** v tomto tvaru:
  `➡️ **Nejvhodnější další krok:** <jeden konkrétní krok> – <proč právě tento>`.
  Případné alternativy uveď až za ním, krátce.
- Použití: strojní díly, NDT, 3D tisk, krabičky na elektroniku – všechno.
- Vývoj probíhá v **Claude Code v cloudu (Linux)**. Cílová aplikace bude pro Windows, proto
  vše musí jít sestavit a otestovat i na Linuxu.

## Rozhodnutí (14. 10. 2026)

- **Python 3.11+ a build123d 0.13.0** nad Open CASCADE 8.0.1 (balík cadquery-ocp). Verze je
  zamčená v `pyproject.toml`. Používej API build123d 0.13 a každé volání ověř spuštěním –
  nevymýšlej třídy ani parametry (OCCT 7.x a 8.x se liší).
- **Model je čitelný JSON „recept“** (parametry + seznam prvků), ne Python skript (bezpečnost,
  editace z GUI i AI) a ne binární formát. Popis formátu je v README.md.
- **Okno: PySide6 6.11.2 + 3D prohlížeč Open CASCADE (V3d/AIS)**. Windows `.exe` staví
  PyInstaller v GitHub Actions (`.github/workflows/windows.yml`); z větve `main` se zveřejní
  jako vydání „nejnovejsi“ (odkaz ke stažení je v README). Repozitář je veřejný.
- Podklady jsou v `docs/` (tři výzkumy; `VYZKUM_3D_CAD.md` a `zprava-hluboky-vyzkum.md` jsou
  stejný text).

## Architektura (`src/skodacad/`)

| Soubor | Úloha |
|---|---|
| `document.py` | načtení/uložení JSON, kontrola struktury, `DocumentError` |
| `expressions.py` | bezpečné výrazy s parametry (vlastní AST, žádné `eval`) |
| `selectors.py` | sémantický výběr ploch a hran (ochrana proti topological naming problem) |
| `features.py` | prvky modelu; registrace dekorátorem `@feature("typ", "Český název")` |
| `rebuild.py` | přepočet seznamu prvků, stavy `ok` / `error` / `skipped` |
| `properties.py`, `materials.py` | objem, povrch, hmotnost, těžiště |
| `export.py` | STEP, STL, 3MF, GLB, SVG náhled |
| `cli.py` | příkazová řádka `skodacad build` |
| `session.py` | `ModelSession` – otevřený model: změna parametru, uložení, export (bez Qt) |
| `inspection.py` | český popis vybrané plochy/hrany |
| `gui/app.py` | spuštění okna, log `~/SkodaCAD/skodacad.log`, `--self-test`, `--screenshot` |
| `gui/main_window.py` | hlavní okno: parametry, strom prvků, vlastnosti, menu |
| `gui/viewer.py` | 3D prohlížeč OCCT (jediné místo GUI, které sahá na OCCT – jen kvůli kreslení) |
| `packaging/` | PyInstaller (`skodacad.spec`) pro sestavení `SkodaCAD.exe` |

## Pravidla

1. Plochy a hrany se **nikdy nevybírají indexem**, jen významem (`selectors.py`).
2. Každý nový prvek či změna geometrie má **test, který ověřuje fyziku**: objem podle vzorce,
   rozměry, `is_valid`. Nestačí „nespadlo to“.
3. Chyby pro uživatele jsou **česky a lidsky**: co se stalo a co zkusit. Výjimky jádra převádět
   na `FeatureError`; neočekávaná chyba nesmí shodit program.
4. Jednotky vždy **mm**, úhly ve **stupních**.
5. Změna formátu JSON = zvýšit `VERSION` v `document.py` a umět načíst staré soubory.
   Modely v `examples/` musí jít vždy postavit (hlídá to test).
6. Pracuj po **malých krocích**; po každém musí projít `ruff check src tests` a `pytest -q`,
   teprve pak commit.
7. Nové závislosti jen se zdůvodněním a se zamčenou verzí.
8. GUI nesmí modelovat přes build123d/OCCT – jen přes `ModelSession`. Výjimkou je
   `gui/viewer.py`, který OCCT používá jen ke kreslení a výběru.
9. Okno se testuje dvakrát: `tests/test_gui.py` (offscreen, náhradní prohlížeč) a skutečně
   pod Xvfb snímkem okna. Změnu vzhledu ukaž uživateli snímkem.

## Příkazy

- Prostředí se v cloudové session připraví samo (`.claude/hooks/session-start.sh`).
  Ručně: `uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"`
- Testy: `pytest -q`  ·  Kontrola kódu: `ruff check src tests`
- Postavit model: `skodacad build examples/priruba.json --set D=200` → soubory v `out/`
- Výsledek ukaž uživateli jako náhled `out/<model>.svg` spolu s objemem a hmotností.
- Snímek okna v cloudu:
  `xvfb-run -a -s "-screen 0 1280x800x24" skodacad-gui --screenshot out/okno.png`
- Kontrola okna i 3D: `xvfb-run -a skodacad-gui --self-test out/self-test.txt`
- Sestavení aplikace lokálně: `uv pip install -e ".[build]"` a
  `pyinstaller packaging/skodacad.spec --noconfirm`; pak self-test `dist/SkodaCAD/SkodaCAD`.
- Stav sestavení pro Windows sleduj v GitHub Actions (workflow „Windows aplikace“).

## Známé pasti (OCCT prohlížeč)

- Po změně velikosti nativního okna se musí volat `V3d_View.MustBeResized()`, jinak výběr
  myší míří vedle (`OccViewer._sync_size` porovnává skutečnou velikost okna).
- Obrysy ploch (`SetFaceBoundaryAspect`) nastavovat až po `SetColor`, jinak je přebarví.
- Ve Windows se HWND předává OCCT jako PyCapsule (`viewer._as_capsule`).
- Souřadnice myši z Qt násobit `devicePixelRatioF()` (škálování obrazovky 125–150 %).
- build123d importuje IPython – v PyInstalleru ho nevynechávat.
- `QAction.triggered` posílá navíc `checked` (False) – do `lambda k=key: …` by se dostalo
  místo `k`. Akce zakládej jen přes `MainWindow._action` (volá slot bez argumentů) a každou
  novou akci pokryj testem, který ji opravdu stiskne (`tests/test_gui.py`).

## Známé pasti (sestavení pro Windows)

- `actions/upload-artifact` bez `include-hidden-files: true` vynechá složky s tečkou
  (`sklearn/.libs` s `vcomp140.dll`) → aplikace u uživatele spadla při startu. Proto úloha
  `kontrola-stazeni` testuje přesně stažený balíček, ne složku na sestavovacím počítači.
- Sestavovací počítač GitHubu má Visual C++ Redistributable, uživatel ne. Hlídá to
  `packaging/check_dlls.py` (v balíčku nesmí chybět msvcp140/vcruntime140/vcomp140…).
- Windows konzole na GitHubu není UTF-8 → `PYTHONUTF8=1` v workflow.
- Než pošleš uživateli odkaz ke stažení, musí projít obě úlohy workflow.

## Jak přidat nový prvek

1. Funkce v `features.py` s dekorátorem `@feature("typ", "Český název")`.
2. Číselné hodnoty čti přes `ctx.num` / `ctx.positive` (umí výrazy), chyby hlas `FeatureError`.
3. Test v `tests/test_features.py` s očekávaným objemem podle vzorce.
4. Doplň tabulku prvků v README.md.

## Plán

- [x] **Fáze 0** – jádro bez GUI: JSON model, parametry a výrazy, skica, vysunutí, rotace,
  zaoblení, sražení, skořepina, exporty, testy.
- [ ] **Fáze 1** – skicář s vazbami (řešič SolveSpace, balík `python-solvespace`), díry se
  závity podle strojnických tabulek, pole a zrcadlení.
- [x] **Fáze 2a** – okno (PySide6 + OCCT prohlížeč): parametry s přepočtem, strom prvků,
  vlastnosti, výběr ploch/hran, export; Windows `.exe` přes GitHub Actions.
- [ ] **Fáze 2b** – úprava prvků ve stromu, převod kliknutí na sémantický výběr hran
  (např. „zaobli tuhle hranu“), přepočet na pozadí, nový model od nuly.
- [ ] **Fáze 3** – sweep/loft, řezy modelem, měření, normalizované díly, NDT (mapa tloušťky stěny).
- [ ] **Fáze 4** – AI asistent upravující JSON model, omezené přímé úpravy ploch.
