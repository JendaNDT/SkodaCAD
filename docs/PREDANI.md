# ŠkodaCAD – předávací dokument pro dalšího AI agenta

> Sepsáno 16. 10. 2026 při přechodu z **Claude Code (cloud, Linux)** na **Google Antigravity**
> (lokálně na autorově počítači). Pravidla projektu jsou v [`AGENTS.md`](../AGENTS.md) – přečti ho
> celý; tady je **stav, prostředí, pracovní cyklus a další krok**.

## 1. O projektu a autorovi

- **ŠkodaCAD** je osobní parametrický 3D CAD (strojní díly, NDT, 3D tisk, krabičky). Díl je
  čitelný JSON „recept“ (parametry + prvky), jádro build123d / Open CASCADE z něj postaví přesné
  těleso; okno PySide6 s 3D prohlížečem OCCT; aplikace pro **Windows i macOS** (Apple Silicon).
- Autor **neprogramuje** – vyvíjí vibecodingem, komunikace **česky**, jednoduše; každou
  odpověď zakonči řádkem `➡️ **Nejvhodnější další krok:** …`. Rád si věci ověřuje: dávej čísla,
  zdroje a odkazy. Zásadní rozhodnutí navrhni a nech schválit (volby, jedna „(doporučeno)“).
- Repozitář: <https://github.com/JendaNDT/SkodaCAD> (veřejný).

## 2. Stav k 16. 10. 2026

| Oblast | Stav |
|---|---|
| Jádro, skicář s vazbami (slvs), díry, závity, pole/zrcadlení, tažení/přechod, normalizované díly | hotovo (fáze 0–3) |
| Okno: parametry, strom, formuláře, výběr ve 3D, Zpět/Znovu, přepočet na pozadí | hotovo (fáze 2) |
| Měření, mapa tloušťky stěny, řez modelem | hotovo (fáze 3) |
| AI asistent v aplikaci (Claude API) | hotovo, **autor ho vyzkouší až na konci vývoje** |
| NDT etapy 00–03: referenční díly, studie v modelu, geometrické jádro, virtuální sonda | hotovo |
| Sladění UT se závazným vymezením (`docs/ndt/04-zavazne-vymezeni-ut.md`) | hotovo |
| macOS (Apple Silicon) – první verze | hotovo, **ověřeno autorem na MacBooku Air M4 i ve Windows** |
| Formát modelu | `VERSION = 14` (`src/skodacad/document.py`), načte i verze 1–13 |
| Testy | `pytest -q` → **658 passed** (Linux, Windows i macOS v GitHub Actions) |

**Ke stažení** (sestavuje GitHub z větve `main`):

- Windows: <https://github.com/JendaNDT/SkodaCAD/releases/latest/download/SkodaCAD-windows.zip>
- macOS: <https://github.com/JendaNDT/SkodaCAD/releases/download/nejnovejsi-mac/SkodaCAD-macos.zip>

**Otevřené body** (podrobněji v kap. 7):

1. NDT **etapa 04** – geometrický model UT svazku (další na řadě, nejdřív návrh ke schválení).
2. Ruční výsledky referenčních dílů (`docs/ndt/05-referencni-dily.md`) **čekají na ověření
   kolegou NDT technikem** – tabulka „Záznam ověření“ je prázdná.
3. Fáze 4: omezené přímé úpravy ploch (zatím jen v plánu).
4. Ve `docs/ndt/` jsou dva soubory s číslem 04 a dva s 05 – záměrně se nepřečíslovávají
   (odkazy); další návrh má číslo **09**.

## 3. Kde co najdeš

| Soubor / složka | Obsah |
|---|---|
| `AGENTS.md` | pravidla, rozhodnutí s daty, architektura, **známé pasti** (čti před každou změnou v dané oblasti), plán |
| `GEMINI.md`, `CLAUDE.md` | jen odkaz na `AGENTS.md` (+ krátké shrnutí v `GEMINI.md`) |
| `README.md` | návod pro autora (stažení, ovládání, funkce) + **„Formát modelu“** – podle něj píše JSON i AI asistent v aplikaci (`assistant.py` ho čte jako systémový pokyn), proto ho drž přesný |
| `docs/ndt/` | NDT: plán (`03-…`), **závazné vymezení UT (`04-zavazne-…`)**, požadavek macOS (`05-podpora-…`), návrhy etap a referenční díly; přehled v `docs/ndt/README.md` |
| `examples/`, `examples/ndt/` | ukázkové a referenční modely – musí jít vždy postavit (hlídá test) |
| `src/skodacad/` | kód (tabulka modulů v `AGENTS.md`, kap. Architektura) |
| `tests/` | testy ověřují fyziku (objemy podle vzorců, ruční výpočty NDT) |
| `packaging/` | PyInstaller (`skodacad.spec`), spouštěč, kontrola DLL pro Windows |
| `.github/workflows/` | `windows.yml` a `macos.yml` – testy, sestavení, self-test staženého balíčku, vydání |
| `.claude/` | jen pro Claude Code v cloudu (příprava prostředí) – v Antigravity se nepoužívá |

## 4. Příprava prostředí na autorově počítači

Potřeba: **git**, **uv** (správce Pythonu a balíčků) a přístup na GitHub (push). Python se
instaluje přes uv – **musí být 3.13**: řešič `slvs==3.2` nemá balíček pro Python 3.14.

**macOS (Terminál):**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh        # jednou: uv
git clone https://github.com/JendaNDT/SkodaCAD.git && cd SkodaCAD   # nebo git pull
uv venv --python 3.13 .venv
uv pip install -e ".[dev,gui,build]"
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # jednou: uv
git clone https://github.com/JendaNDT/SkodaCAD.git; cd SkodaCAD
uv venv --python 3.13 .venv
uv pip install -e ".[dev,gui,build]"
.venv\Scripts\activate
```

(Když PowerShell aktivaci odmítne kvůli zásadám spouštění skriptů, jednou
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

**Kontrola, že prostředí počítá stejně jako dosud** (všechno musí sedět):

```bash
ruff check src tests                      # All checks passed!
pytest -q                                 # 658 passed (~2–5 min)
skodacad build examples/priruba.json      # „Objem: 311 093 mm³“, exporty v out/
skodacad-gui --self-test out/self-test.txt   # (out/ vytvořil build) na konci „VÝSLEDEK: OK“
skodacad-gui                              # okno s ukázkou příruby
```

Poznámky: testy okna si samy nastaví `QT_QPA_PLATFORM=offscreen` (žádné okno nevyskočí).
Spuštění ze zdrojů na Macu (ne zabalená `.app`) zatím nikdo nezkoušel – kdyby 3D nešlo, viz
pasti macOS v `AGENTS.md` a řádek „Okno a 3D prohlížeč“ v `out/self-test.txt`.

## 5. Pracovní cyklus (jak se tu pracuje)

1. **Návrh** nové etapy v `docs/ndt/NN-navrh-….md`: co přesně, proč, rozhraní (funkce/třídy),
   **ručně spočítané kontrolní příklady**, co v etapě nebude, otázky k rozhodnutí. Autor
   schválí (třeba „Ano, pusť se do toho“) – teprve pak kód.
2. **Malé kroky** ve větvi (`git switch -c ndt-etapa-04`): jádro + testy → session/CLI → okno →
   dokumentace. Po každém kroku `ruff check src tests` + `pytest -q`, pak commit (česky).
3. **Okno**: změnu vzhledu ověř skutečným snímkem (`skodacad-gui --screenshot out/okno.png`)
   a ukaž ho autorovi.
4. **Push větve** → GitHub Actions spustí „Windows aplikace“ a „macOS aplikace“ (jen když se
   změnil kód, testy, ukázky, `packaging/`, `pyproject.toml` nebo workflow – samotná
   dokumentace sestavení nespouští). Obě úlohy obou workflow musí být zelené
   (`sestaveni` i `kontrola-stazeni` – ta testuje přesně stažený balíček).
5. **„Sluč to“** od autora → pull request do `main`, sloučit metodou *merge*. Na `main` se pak
   sestavení spustí znovu a zveřejní vydání `nejnovejsi` (Windows) a `nejnovejsi-mac`.
6. **Po sloučení** zkontroluj oba běhy na `main` a obě vydání (ukazují na nový commit, mají ZIP)
   a teprve pak pošli autorovi odkazy a co si vyzkoušet.
7. Stará pracovní větev z Claude Code (`ccr-299f2dcb-9w8xc9`) se dál nepoužívá – nové větve
   vždy z aktuálního `main`.

## 6. Nedělat

- Neměnit zamčené verze knihoven ani nepřidávat závislost bez návrhu a schválení.
- Nevybírat plochy/hrany indexem; nemodelovat v GUI mimo `ModelSession`.
- Neměnit formát JSON bez zvýšení `VERSION` a načtení starých souborů.
- Nevydávat výsledky NDT za prozvučitelnost nebo detekci vad; neměnit `UT_DISCLAIMER`
  (test ho porovnává s dokumentem); žádné virtuální A/B-scany (mimo schválený rozsah).
- Nepřepisovat AI asistenta v aplikaci na jiného poskytovatele – `anthropic==1.15.0` a modely
  `claude-opus-5-5` / `claude-sonnet-5-5` jsou schválené rozhodnutí (ID modelů jsou správně).
- Testy nesmí volat síť (AI asistent v testech přes `assistant.offline_client`).
- Nedávat autorovi odkaz ke stažení dřív, než projdou obě úlohy obou workflow.
- Nesahat na vydání `nejnovejsi-mac` tak, aby se stalo „latest“ – rozbil by se odkaz pro Windows
  (`releases/latest`); proto `--prerelease --latest=false` v `macos.yml`.

## 7. Další krok: NDT etapa 04 – výchozí bod pro návrh

**Zadání** (`docs/ndt/03-implementacni-plan.md`, etapa 04): přímá sonda jako první – osa
paprsku, materiál, tloušťka, délka dráhy, vstup/výstup a odraz na hranici geometrie; pak úhlová
sonda – lom podle Snellova zákona s definovanými rychlostmi a módem vlny, kritické úhly
a neplatná nastavení. Výstup: paprsek a jeho geometrická dráha v řezu a ve 3D. Hotovo, když
úhly, délky a průsečíky souhlasí s ručními výpočty na jednoduchých tělesech.

**Závazné omezení** (`docs/ndt/04-zavazne-vymezeni-ut.md`, má přednost): jen **geometrický**
model svazku; lom a odraz jen s **výslovně zadanými předpoklady** (rychlosti, mód vlny), které
algoritmus skutečně počítá a testuje. Žádný útlum, amplituda, signál ani tvrzení o detekci.
Nejistá místa = „Nelze spolehlivě vyhodnotit“ s českým důvodem. Povinné upozornění UT
v okně i výstupech.

**Na čem stavět (hotové a otestované):**

- `ndt/geometry.py` – `PartGeometry(part).cast(origin, direction, max_length)` → `RayResult`
  (`hits` s `point`, `normal` ven z materiálu, `incidence` ve stupních, `entering`; `segments`
  v materiálu; `reasons` u nejistých případů: po povrchu, přes hranu, tečně).
  `surface_at(point)` → normála a zakřivení; `visible`, `collision`.
- `ndt/devices.py` – `place(geo, probe, point, beam/angle)` → `Placement`: `origin` = **výstupní
  bod na povrchu**, `x_dir` = směr paprsku v tečné rovině, `z_dir` = normála ven. Paprsek
  v materiálu pod úhlem β od normály: `d = sin β · x_dir − cos β · z_dir`.
- Odraz na stěně s normálou `n`: `d' = d − 2 (d·n) n`; další úsek = nový `cast` z bodu odrazu.
- Sonda je uložená ve studii (`device`, formát v14); přiložení je jen pohled
  (`ModelSession.ndt_placement_request`). Okno kreslí sondu `viewer.show_probe` – čára dráhy
  půjde stejnou cestou (nový druh kreslení přidat i do self-testu, viz pasti měření).
- `skodacad sonda …` (CLI) – vzor pro případný příkaz s dráhou svazku.

**Ruční kontrolní hodnoty, které už existují** (`docs/ndt/05-referencni-dily.md`, deska t = 20 mm,
úhel β v oceli): 45° → půlkrok 20,00 mm, dráha k dolní ploše 28,28 mm; 60° → 34,64 / 40,00 mm;
70° → 54,95 / 58,48 mm (půlkrok = t·tg β, dráha = t / cos β). Lom: sin α / c₁ = sin β / c₂;
kritický úhel pro mód s rychlostí c₂: α = arcsin(c₁ / c₂).

**Otázky, které má návrh položit autorovi** (návrh = `docs/ndt/09-navrh-etapa-04.md`):

1. Zadává se úhel přímo v oceli (β, jak se sondy obvykle značí), nebo úhel klínu a rychlosti
   (α, c klínu, c v materiálu, mód vlny) – nebo obojí? Rychlosti musí zadat/potvrdit autor nebo
   kolega NDT technik, AI je nevymýšlí.
2. Ukládat parametry svazku do studie (rozšíření `device` → **formát v15**), nebo zatím jen pohled?
3. Kolik odrazů (půlkroků) sledovat a do jaké délky dráhy?
4. Jak dráhu ukázat: čára ve 3D (barva podle jistoty), v řezu modelem, výpis v CLI?
5. Pořadí: přímá sonda (kolmo) → úhlová s β → lom z klínu (podle plánu).

## 8. Historie rozhodnutí a podklady

Všechna rozhodnutí s daty jsou v `AGENTS.md`, kap. „Rozhodnutí“. Podkladové výzkumy volby
technologie jsou v `docs/` (`VYZKUM_3D_CAD.md` = `zprava-hluboky-vyzkum.md`). Historie změn je
v gitu – každý commit popisuje co a proč (česky); sloučené etapy jsou pull requesty #1–#14.
