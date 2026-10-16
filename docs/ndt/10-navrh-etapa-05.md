# NDT – návrh etapy 05: ruční pohyb sondy v okně (milník M1)

> Etapa 05 plánu `03-implementacni-plan.md` a závazného vymezení `04-zavazne-vymezeni-ut.md`.
> Uzavírá **milník M1 (první fungující UT)**: plynulý ruční pohyb virtuální sondy po povrchu
> dílu se živým přepočtem přístupnosti (kolize, vůle, mezera, přesah) a geometrické dráhy
> paprsku ve 3D i v řezu modelem.

Stav: návrh 16. 10. 2026 · **schváleno a provedeno 16. 10. 2026**

## 1. Co etapa přinese

Etapy 03 a 04 naučily program přiložit sondu do jednoho kliknutého bodu a spočítat z něj
geometrickou dráhu UT paprsku. Etapa 05 z toho udělá **interaktivní prohlížení („jezdím sondou
po dílu“)** dvěma způsoby, které se vzájemně doplňují:

| Způsob pohybu | Jak se ovládá | K čemu je nejlepší |
|---|---|---|
| **1. Tažení sondy myší po povrchu ve 3D** | přepínač **Jezdit sondou myší** v panelu NDT (nebo podržení `Alt` + tažení levým tlačítkem) | rychlé ruční přejíždění po ploše dílu (deska, trubka, okolí žebra či svaru) a okamžité sledování, kam míří paprsek a kde sonda narazí |
| **2. Přesný posuv podél směru paprsku (přímá dráha)** | tlačítka **◀ / ▶** (krok v mm) a **posuvník přímé dráhy** v panelu NDT (nad `devices.scan_line`) | přesné najetí k překážce nebo ke kořeni svaru po milimetrech, zjištění volného úseku (např. *volně 0–48 mm*) a plynulé projíždění dráhy posuvníkem |

Při každém posunu nebo pootočení sondy se živě obnoví:
1. **3D tělo sondy v barvě stavu** (zelená = přiloženo, oranžová = málo místa / nedosedá / přesahuje, červená = koliduje),
2. **lomená čára osy UT paprsku v dílu** (přímé rameno i odrazy od stěn, vidět skrz díl i v zapnutém *Řezu modelem*),
3. **český souhrn v panelu NDT** (souřadnice výstupního bodu, mezera, vůle k překážkám, délky ramen, půlkrok, celý krok a případný důvod nejistoty či nemožného přiložení).

**Co etapa 05 nemění a nedělá:**
- **nemění formát souboru JSON** (zůstává verze 15) ani samotné těleso dílu – poloha sondy a posuv po dráze jsou pohled (jako řez modelem); ukládání drah a mapa pokrytí přijdou v etapě 06,
- **neposuzuje fyzikální prozvučitelnost materiálu ani detekovatelnost vad** (`docs/ndt/04-zavazne-vymezeni-ut.md`); v panelu je trvale viditelné `UT_DISCLAIMER`.

## 2. Ovládání v okně (scénář „klikni, nastav, pozoruj“)

### A) Tažení myší ve 3D (*Jezdit sondou myší*)

- V části *Přístupnost UT sondy* přibude zapínací tlačítko **Jezdit sondou myší** (a zkratka: podržení klávesy **`Alt`** při tažení levým tlačítkem myší funguje i bez přepínání režimu).
- Když je režim *Jezdit sondou myší* zapnutý:
  - **levé tlačítko (klik nebo tažení po dílu)** plynule posouvá sondu po ploše pod kurzorem,
  - **`Alt` + kolečko myši** (nebo políčko *Směr paprsku [°]*) pootáčí sondu na místě po 15°,
  - **otáčení a posun kamery** zůstávají dostupné přes prostřední/pravé tlačítko, `Shift` + levé tažení (posun i na trackpadu Macu) a kolečko myši (zoom).
- Když kurzor při tažení sjede mimo díl nebo na plochu vzniklou jen *Řezem modelem*, poslední platné přiložení zůstane na místě a ve stavovém řádku se česky ukáže důvod.

### B) Posuv po přímce a posuvník (*Posuv směrem paprsku*)

- Pod přiloženou sondou v panelu NDT přibude řádek pro řízený posuv podél směru paprsku (nebo proti němu):
  - tlačítka **◀ Krok zpět** a **Krok vpřed ▶** (posunou přiloženou sondu po aktuální ploše o zvolený krok, výchozí **1 mm**, bez nutnosti trefovat se myší),
  - tlačítko **Zkontrolovat přímou dráhu** (spustí `scan_line` z aktuální polohy ve směru paprsku na zadanou délku, např. 50 mm po 1 mm, vypíše volné úseky *„volně 0–48 mm, první potíž po 49 mm: Málo místa…“* a zpřístupní **posuvník dráhy**, kterým lze sondu po spočítaných bodech plynule posouvat tam a zpět).

### C) Spolupráce s Řezem modelem (`R`)

- Zapneš *Řez modelem* (např. podélně kolmo na Y na tupém svaru nebo desce se žebrem) a táhneš sondu myší nebo posuvníkem po horní ploše: v rozříznutém dílu přímo vidíš, kdy 1. rameno (půlkrok) nebo 2. rameno po odrazu (celý krok) zasáhne kořen svaru a kdy už čelo sondy narazí do převýšení svaru nebo do žebra.

## 3. Rychlost a oddělení výpočtů od GUI

1. **Zrychlení opakovaného přiložení na téže ploše (`ndt/geometry.py`, `ndt/devices.py`):**
   - Nejdražší část `place()` (~20 ms) je ořez dílu poloprostorem nad tečnou rovinou v `_clearance_above`.
   - Na rovinné ploše (deska, pásnice, okolí svaru) je tečná rovina pro všechny body plochy **stejná**. Uložením oříznutého tvaru nad rovinou do mezipaměti `PartGeometry` (podle roviny s přesností $10^{-4}\text{ mm}$) klesne čas jednoho přiložení při tažení po rovinné ploše z ~25 ms na **~4–6 ms** (150+ přiložení za sekundu).
2. **Plynulé tažení v prohlížeči (`gui/viewer.py`):**
   - Při tažení myší prohlížeč čte plochu a 3D bod pod kurzorem z OCCT (`MoveTo` + `PickedPoint`) a hlásí nový bod jen tehdy, když se posunul aspoň o **0,5 mm** – okno se tak nezahltí zbytečnými překresleními na místě.
3. **Veškerá logika v `ModelSession` (`session.py`):**
   - Okno ani prohlížeč nic nepočítají – volají metody `ModelSession`:
     ```python
     session.move_ndt_probe(shapes, point)        # posun přiložené sondy na nový bod pod myší
     session.shift_ndt_probe(step_mm)             # posun o krok [mm] ve směru paprsku (+vpřed, −vzad)
     session.scan_ndt_line(length_mm, step_mm=1)  # přímá dráha (LineScan) z aktuálního přiložení
     session.select_ndt_scan_index(index)         # výběr bodu z přímé dráhy posuvníkem
     ```

## 4. Ověření na referenčních dílech (`05-referencni-dily.md`)

| Referenční díl | Scénář v okně / `ModelSession` | Očekávaný výsledek |
|---|---|---|
| **3. Deska se žebrem** (`zebro.json`) | přiložit v $x = 60$, směr $180^\circ$ (k žebru), táhnout / krokovat k žebru | v $x = 22$ vůle 5 mm (paprsek dopadne v $x = 2$); v $x = 20$ dopad přesně pod osu žebra $x = 0$ (vůle 3 mm); v $x = 17$ dotyk čela se žebrem (vůle 0 mm); v $x = 16$ **kolize 500 mm³** |
| **6. Tupý svar V** (`tupy_svar.json`) | přiložit v $x = 35$, $\beta = 70^\circ$, posouvat k ose svaru | v $x = 32{,}97$ paprsek zasáhne kořen $(0; 0; 0)$; při $x < 22$ čelo sondy narazí do převýšení svaru (**kolize**) |
| **5. Trubka** (`trubka.json`) | táhnout přímou sondu $\varnothing 10$ po vnějším plášti | v každém bodě pláště tečná rovina sleduje válec, mezera **0,22 mm** (přiloženo), paprsek kolmo stěnou **6,00 mm** |
| **2. Blok s kapsou** (`kapsa.json`) | táhnout přímou sondu zespodu ($z = 0$) přes obrys kapsy | mimo kapsu dráha paprsku **40,00 mm**, pod kapsou skokově **15,00 mm** (dno kapsy) |

## 5. K rozhodnutí

1. **Jak zapínat tažení sondy myší ve 3D?**
   - *Návrh:* obojí – zapínací tlačítko **Jezdit sondou myší** v panelu NDT (pro delší zkoumání bez držení klávesy) **a zároveň** podržení **`Alt` + levé tlačítko myší** kdykoli při vybrané UT studii (rychlé přemístění sondy bez přepínání režimu).
2. **Mít v panelu NDT i krokování (◀ / ▶ po mm) a posuvník přímé dráhy (`scan_line`)?**
   - *Návrh:* **ano** – myší člověk rychle najde oblast a tlačítky ◀ / ▶ nebo posuvníkem přímé dráhy pak s milimetrovou přesností najede na mez kolize nebo přesně do kořene svaru.
3. **Formát modelu beze změny (verze 15)?**
   - *Návrh:* **ano** – ruční ježdění sondou je živý pohled (stejně jako řez modelem); ukládání vyhodnoceného pokrytí a drah přijde v dalších etapách.

## 6. Postup implementace (malé kroky, po každém `ruff` + `pytest`)

| Krok | Soubor | Obsah |
|---|---|---|
| 1 | `ndt/geometry.py`, `ndt/devices.py`, `session.py` + `tests/test_ndt_session.py` | mezipaměť poloprostoru nad rovinou pro rychlý posuv, metody `move_ndt_probe`, `shift_ndt_probe`, `scan_ndt_line`, `select_ndt_scan_index` v `ModelSession` |
| 2 | `gui/viewer.py`, `gui/ndt_panel.py`, `gui/main_window.py`, `gui/app.py` + `tests/test_gui.py` | režim *Jezdit sondou myší* + `Alt`+tažení ve 3D prohlížeči, tlačítka ◀ / ▶ a posuvník přímé dráhy v panelu NDT, doplnění self-testu |
| 3 | `README.md`, `CLAUDE.md`, `docs/ndt/` | návod k ovládání pohybu sondy, známé pasti, uzavření milníku M1 v plánu |
