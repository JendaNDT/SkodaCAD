# NDT – návrh etapy 04 ke schválení: geometrický model UT paprsku

> Etapa 04 plánu `03-implementacni-plan.md` a závazného vymezení `04-zavazne-vymezeni-ut.md`.
> Zatím **jen návrh** – kód až po schválení. Jde o geometrickou dráhu středního paprsku svazku
> (přímá a úhlová sonda, odraz od stěny, lom podle Snellova zákona s výslovně zadanými
> předpoklady) – ne o fyzikální prozvučitelnost materiálu, detekovatelnost vad ani virtuální
> signály.

Stav: schváleno a provedeno 16. 10. 2026 (formát verze 15)

## 1. Co etapa přinese

Nový modul `src/skodacad/ndt/ut.py` bez okna: z přiložené virtuální sondy (`devices.Placement`
z etapy 03) vyšle do materiálu **střední paprsek svazku** a spočítá jeho **geometrickou dráhu**
dílem včetně případných odrazů na hranici geometrie.

| Část | Co počítá | Předpoklady |
|---|---|---|
| **1. Přímá sonda** | paprsek z výstupního bodu kolmo do materiálu ($\beta = 0^\circ$, proti normále plochy): délka v materiálu, bod a úhel dopadu na protější stěnu | střední paprsek = přímka |
| **2. Úhlová sonda – zadaný úhel lomu $\beta$** | paprsek odchýlený od vnitřní normály o úhel $\beta$ ($0^\circ < \beta < 90^\circ$) ve směru sondy: šikmá dráha $s$, vodorovný posun (**půlkrok** $p$), hloubka pod rovinou přiložení | $\beta$ zadá přímo uživatel (jako na štítku sondy, např. 45°, 60°, 70°) |
| **3. Úhlová sonda – lom podle Snellova zákona** | ze zadaného úhlu v předsádce $\alpha$ a rychlostí $c_1$ (předsádka) a $c_2$ (materiál) spočítá $\sin\beta = \frac{c_2}{c_1}\sin\alpha$ a kritický úhel $\alpha_{\text{krit}}$ | $c_1, c_2$ [m/s] a druh vlny (příčná / podélná) musí být **výslovně zadané**; nadkritický úhel ($\sin\beta \ge 1$) = jasná česká chyba (totální odraz) |
| **4. Odrazy na hranici geometrie** | v bodě dopadu na stěnu se paprsek zrcadlově odrazí ($\text{úhel odrazu} = \text{úhel dopadu}$ od normály plochy) a pokračuje dalším ramenem (**celý krok** = 1 odraz / 2 ramena) | čistě geometrický odraz bez změny módu vlny; dopad na hranu, roh nebo tečně = dráha se zastaví jako **nejistá** s českým důvodem |

**Co etapa 04 nedělá (podle `04-zavazne-vymezeni-ut.md`):**
- žádný útlum, rozptyl, struktura materiálu ani akustická vazba,
- žádná detekovatelnost vad ani syntetické signály,
- žádné „skryté tabulkové rychlosti“ bez vědomí uživatele – buď je zadaný přímo úhel $\beta$,
  nebo jsou výslovně zadané rychlosti $c_1, c_2$.

## 2. Ověření proti ručním výpočtům (`05-referencni-dily.md`)

| Referenční díl | Zadání | 1. rameno (půlkrok) | Po 1. odrazu (celý krok) |
|---|---|---|---|
| **1. Deska** ($t = 20\text{ mm}$) | přímá $\beta = 0^\circ$ shora | dráha **20,00 mm**, dopad kolmo ($0,0^\circ$) | – |
| | po změně $t = 30\text{ mm}$ | dráha **30,00 mm** | – |
| | úhlová $\beta = 45^\circ$ | půlkrok **20,00 mm**, dráha **28,28 mm**, hloubka 20,00 mm | celý krok **40,00 mm**, celková dráha **56,57 mm** |
| | úhlová $\beta = 60^\circ$ | půlkrok **34,64 mm**, dráha **40,00 mm** | celý krok **69,28 mm**, celková dráha **80,00 mm** |
| | úhlová $\beta = 70^\circ$ | půlkrok **54,95 mm**, dráha **58,48 mm** | celý krok **109,90 mm**, celková dráha **116,95 mm** |
| **2. Blok s kapsou** ($H = 40, h = 25$) | přímá zespodu pod kapsou / mimo kapsu | **15,00 mm** (dno kapsy) / **40,00 mm** (horní plocha) | – |
| **3. Deska se žebrem** ($t = 20$, žebro $s = 10$ v $x = 0$) | úhlová $45^\circ$ z $x = 20$ (vůle 3 mm) | dopad na dno v **$x = 0,00\text{ mm}$** (přímo pod osou žebra), dráha 28,28 mm | odraz do $( -20; 0; 20 )$ |
| | úhlová $45^\circ$ z $x = 22$ (rezerva 5 mm) | dopad na dno v **$x = 2,00\text{ mm}$** – k ose žebra chybí **2,00 mm** | – |
| | úhlová $60^\circ$ z $x = 34,64$ (vůle 17,64 mm) | dopad na dno v **$x = 0,00\text{ mm}$** i s rezervou 5 mm, dráha 40,00 mm | – |
| | přímá zespodu pod žebrem / vedle | **80,00 mm** / **20,00 mm** | – |
| **4. Deska s otvorem** ($\varnothing 20$) | přímá $\varnothing 10$, $16\text{ mm}$ od osy | přiloženo, dráha **20,00 mm** | – |
| **5. Trubka** ($D = 114,3, s = 6$) | přímá radiálně | dráha stěnou **6,00 mm** (dopad na vnitřní stěnu, $0,0^\circ$) | – |
| | obvodový paprsek $\beta = 60^\circ$ ($\le 63,5^\circ$) | zasáhne **vnitřní stěnu** ($r = 51,15\text{ mm}$) | – |
| | obvodový paprsek $\beta = 70^\circ$ ($> 63,5^\circ$) | **mine vnitřní stěnu**, projde tětivou na vnější stěnu (**39,09 mm**) | – |
| **6. Tupý svar V** ($t = 12, c = 20$, výstupní bod $x \ge 22$) | z $x = 22$: $45^\circ$ / $60^\circ$ | dopad na dno v $x = 10,00\text{ mm}$ / **$x = 1,22\text{ mm}$** (ke kořeni $x = 0$ chybí 1,22 mm) | – |
| | z $x = 32,97$: $70^\circ$ | dopad do kořene **$x = 0,00\text{ mm}$**, dráha **35,09 mm** | – |

## 3. Rozhraní (návrh)

```python
# 1) Lom podle Snellova zákona (jen s výslovně zadanými rychlostmi):
refraction = refract(alpha=36.44, c_wedge=2730, c_material=3250, wave="shear")
refraction.beta           # 45.0° (úhel lomu v materiálu)
refraction.critical_angle # 57.14° (kritický úhel v předsádce)

# 2) Dráha paprsku z přiložené sondy:
beam = trace_beam(geo, placed, beta=45.0, bounces=1, max_length=None)
beam.beta                 # úhel lomu v materiálu [°] (u přímé sondy 0°)
beam.legs                 # (BeamLeg(index, start, end, direction, length, incidence,
                          #          horizontal, depth, hit, reasons), ...)
beam.total_length         # součet délek jistých ramen v materiálu [mm]
beam.half_skip            # vodorovná vzdálenost 1. dopadu v rovině přiložení [mm] (půlkrok)
beam.full_skip            # vodorovná vzdálenost 2. dopadu [mm] (celý krok, je-li 1. odraz)
beam.certain, beam.reasons # jistota a české důvody nejistoty
beam.assumptions          # slovník předpokladů do protokolu (algoritmus, beta, c1, c2, odrazy)
```

- **Přiložení + paprsek:** `trace_beam` počítá geometrickou dráhu z výstupního bodu `placed.origin`
  a zároveň nese `placed` – uživatel tak vidí i to, kam by paprsek mířil z místa, kde sonda koliduje
  nebo má málo místa, ale výsledek přiložení (`koliduje` / `málo místa`) zůstane jasně vidět.
- **Start paprsku z povrchu:** výstupní bod `placed.origin` leží přímo na ploše přiložení, takže
  `geo.cast` najde 1. úsek v materiálu začínající v $0\text{ mm}$. Pokud by paprsek hned na začátku
  mířil ven z materiálu (např. na ostré hraně) nebo běžel po povrchu, vrátí `BeamPath` bez ramen
  jako **nejistý** s českým vysvětlením.
- **Odraz:** na konci ramene v bodě `exit` s venkovní normálou $\vec{n}$ je odražený směr
  $\vec{d}' = \vec{d} - 2(\vec{d}\cdot\vec{n})\vec{n}$. Další `geo.cast` startuje z bodu dopadu
  (posunutého o $10^{-5}\text{ mm}$ ve směru $\vec{d}'$, aby nezačal na téže ploše). Pokud byl
  dopad nejistý (`THROUGH_EDGE`, `GRAZING`, `ALONG_SURFACE`), další odraz se už nepočítá.

## 4. Příkazová řádka a okno

### Příkazová řádka (`skodacad sonda`)

Rozšíření stávajícího příkazu `skodacad sonda` o volby paprsku:
- `--uhel BETA` – úhel lomu v materiálu ve stupních (u úhlové sondy např. `--uhel 45`; u přímé
  sondy je vždy $0^\circ$),
- `--snell ALFA,C1,C2` – místo `--uhel` spočítá úhel lomu ze Snellova zákona (úhel v předsádce
  v °, rychlost v předsádce v m/s, rychlost v materiálu v m/s, např. `--snell 36.44,2730,3250`),
- `--odrazy N` – počet odrazů od stěn (výchozí `1` u úhlové = 2 ramena / celý krok, `0` u přímé),
- `--dosah MM` – maximální celková délka dráhy v materiálu [mm].

Ukázka výstupu:
```
skodacad sonda examples/ndt/zebro.json --bod 20,0,20 --smer -1,0,0 --uhel 45
Úhlová sonda 40 × 20 × 25 mm, výstupní bod 12 mm od čela (mezera nejvýš 0.50 mm, rezerva 0.00 mm)
Přiložení v [20; 0; 20], paprsek [-1; 0; 0]:
  Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 3.00 mm.
Dráha paprsku (úhel lomu 45.0°, nejvýš 1 odraz, algoritmus ndt-ut-paprsek 1):
  rameno 1: [20; 0; 20] → [0; 0; 0], délka 28.28 mm, vodorovně 20.00 mm, hloubka 20.00 mm (dopad 45.0°)
  rameno 2: [0; 0; 0] → [-20; 0; 20], délka 28.28 mm, vodorovně 40.00 mm, hloubka 0.00 mm (dopad 45.0°)
  celkem v materiálu: 56.57 mm, půlkrok 20.00 mm, celý krok 40.00 mm, jistota: ok
  (ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí …)
```

### Okno (panel NDT + 3D pohled a řez)

1. **Nastavení sondy (`Probe` / dialog *Sonda…*):**
   - U úhlové sondy přibude **úhel lomu v materiálu $\beta$ [°]** (výchozí **45°**, rozsah 1–85°)
     a **počet odrazů** (výchozí **1** = 2 ramena, rozsah 0–5).
   - V dialogu *Sonda…* navíc volitelná pomůcka *Spočítat ze Snellova zákona* ($\alpha$, $c_1$, $c_2$
     → vyplní $\beta$ a ukáže kritický úhel).
2. **3D prohlížeč a řez modelem:**
   - Při přiložené sondě se ve 3D vykreslí **osa paprsku** (výrazná lomená čára po ramenech
     s kuličkami v bodech dopadu/odrazu).
   - Při zapnutém **Řezu modelem** (`R`) zůstane sonda i dráha paprsku vidět přímo v rozříznutém
     dílu.
3. **Panel NDT (*Přístupnost UT sondy*):**
   - Pod stavem přiložení vypíše souhrn dráhy (délka 1. ramene, půlkrok, celý krok, souřadnice
     dopadu a případné důvody nejistoty).

## 5. K rozhodnutí

1. **Uložit úhel lomu `angle` ($\beta$, výchozí 45°) a počet odrazů `bounces` (výchozí 1 u úhlové,
   0 u přímé) do `device` ve studii?**
   - *Návrh:* **ano**, jako nepovinné položky `device` (`beam_angle`: 45, `bounces`: 1) – stávající
     soubory verze 14 se načtou beze změny (chybějící položky dostanou výchozí hodnoty), takže ani
     není nutné zvyšovat číslo verze JSON (nebo zvýšit na verzi 15, pokud chceš mít jistotu, že
     starší verze programu nový soubor neodmítne).
2. **Zobrazení paprsku v okně už v etapě 04, nebo až v etapě 05 spolu s tažením myší?**
   - *Návrh:* nakreslit osu paprsku u přiložené sondy **už v etapě 04** (plní to výstup etapy 04
     „Paprsek a jeho geometrická dráha v řezu a ve 3D“), a v etapě 05 pak přidat plynulé tažení
     sondy myší po povrchu.
3. **Výchozí počet odrazů u úhlové sondy:** **1 odraz** (2 ramena = přímý paprsek + 1 odraz od
   zadní stěny, tedy půlkrok i celý krok), a u přímé sondy **0 odrazů** (1 průchod ke koncovému
   echu)?

## 6. Postup (malé kroky, po každém `ruff` + `pytest`)

| Krok | Soubor | Obsah |
|---|---|---|
| 1 | `ndt/ut.py` + `tests/test_ndt_ut.py` | přímý a úhlový paprsek, Snellův zákon (`refract`), odrazy (`trace_beam`), testy všech referenčních dílů z tabulky v kap. 2 a hraničních případů |
| 2 | `ndt/devices.py`, `cli.py` + testy | volitelné `beam_angle` a `bounces` u sondy, volby `--uhel`, `--snell`, `--odrazy`, `--dosah` v `skodacad sonda` |
| 3 | `session.py`, `gui/viewer.py`, `gui/ndt_panel.py`, `gui/app.py` + testy | kreslení dráhy paprsku ve 3D (i v řezu), nastavení v dialogu *Sonda…*, výpis v panelu NDT, kontrola v self-testu |
| 4 | `README.md`, `CLAUDE.md`, `docs/ndt/` | dokumentace, známé pasti, aktualizace stavu plánu |
