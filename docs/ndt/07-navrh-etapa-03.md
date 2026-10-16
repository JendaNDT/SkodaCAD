# NDT – návrh etapy 03 ke schválení: virtuální sonda na povrchu dílu

> Etapa 03 plánu `03-implementacni-plan.md`: polohování a obálky NDT zařízení. Zatím **jen
> návrh**. Geometrie přiložení – ne paprsek s lomem (etapa 04) ani pohyb myší (etapa 05).

Stav: návrh 16. 10. 2026 · navazuje na etapu 02 (`ndt/geometry.py`)

## 1. Co etapa přinese

Nový modul `src/skodacad/ndt/devices.py`: **virtuální sonda** (obecná, ne katalogová) a její
**přiložení na plochu dílu** s kontrolou, jestli tam fyzicky jde.

| Sonda | Tvar těla | Výstupní bod paprsku |
|---|---|---|
| **přímá** | válec Ø D × výška H (výchozí Ø 10 × 25) | uprostřed kontaktní plochy |
| **úhlová** | kvádr délka L × šířka W × výška H (výchozí 40 × 20 × 25) | `front` mm od čela (výchozí 12), paprsek míří dopředu |

**Přiložení** = bod na ploše + směr paprsku. Program postaví souřadný systém sondy: osa Z =
normála plochy ven, osa X = směr paprsku sklopený do tečné roviny, Y = Z × X. Sonda vždy
dosedá kontaktní plochou do tečné roviny v bodě přiložení.

**Kontroly přiložení** (všechno přes geometrické jádro etapy 02):

| Kontrola | Jak | Výsledek |
|---|---|---|
| **mezera pod sondou** | přesně – ~35 paprsků z kontaktní plochy kolmo k povrchu (ne vzorec) | největší mezera; nad mezí (výchozí **0,5 mm**) = *nedosedá* |
| **přesah** | bod kontaktní plochy, pod kterým v dosahu není povrch (okraj, otvor) | *přesahuje přes okraj / otvor* |
| **kolize těla** | společný objem těla sondy s dílem | *koliduje* + objem v mm³ |
| **vůle a manipulační rezerva** | nejmenší vzdálenost těla k překážkám **nad** rovinou přiložení | vůle v mm; pod rezervou (výchozí 0 mm) = *málo místa* |
| **posun po přímce** | řada přiložení s krokem podél zadaného směru | odkud kam sonda volně projede, kde začne kolize |

Stav přiložení: **přiloženo** / **koliduje** / **málo místa** / **nedosedá** / **přesahuje** /
**nejisté** (s českým důvodem). Mez 0,5 mm odpovídá EN ISO 17640 (mezera mezi povrchem a
spodkem sondy nejvýš 0,5 mm; pro vyšší se sonda musí přizpůsobit povrchu). Obě meze jdou
změnit – nejde o tvrzení o normové shodě.

## 2. Ověřeno prototypem na referenčních dílech

| Díl | Přiložení | Výsledek prototypu | Ručně |
|---|---|---|---|
| deska se žebrem | úhlová sonda, paprsek k žebru, výstupní bod x = 22 | vůle **5,00 mm** | čelo x = 10, žebro x = 5 ✓ |
| | x = 17 | vůle 0 (čelo se žebra dotkne), bez kolize | 17 − 12 = 5 ✓ |
| | x = 16 | kolize **500 mm³** | 1 × 20 × 25 ✓ |
| trubka 114,3 | přímá Ø 10 | mezera **0,22 mm** → přiloženo | 57,15 − √(57,15² − 5²) ✓ |
| | přímá Ø 20 | mezera **0,88 mm** → nedosedá | ≈ a²/4D = 0,87 ✓ |
| | úhlová, paprsek podél osy | mezera 0,88 mm (šířka 20 napříč) | ✓ |
| deska s otvorem Ø 20 | přímá Ø 10, 12 mm od osy | **přesahuje** nad otvor | 12 − 5 < 10 ✓ |
| | 16 mm od osy | přiloženo | ✓ |
| blok s kapsou | přímá Ø 20 na dně | přiloženo, vůle ke stěnám **5 mm** | (30 − 20)/2 ✓ |
| | přímá Ø 32 | kolize | 32 > 30 ✓ |
| obtížný přístup | úhlová podél žeber | přiloženo, vůle **5 mm** | (30 − 20)/2 ✓ |
| | úhlová napříč mezerou | kolize **5 000 mm³** | levé žebro celou tloušťkou 10 × 20 × 25 ✓ |

Jedno přiložení trvá ~25 ms (paprsky otisku + průnik + vzdálenost) – na tažení myší
v etapě 05 to stačí.

Zjištění z prototypu: vůle se musí měřit jen k překážkám **nad** rovinou přiložení – jinak
by sonda na trubce měla „vůli 6 mm“ k vnitřní stěně a sonda vedle otvoru k jeho stěně.

## 3. Rozhraní (návrh)

```python
probe = Probe.angle(length=40, width=20, height=25, front=12)  # nebo Probe.straight(10, 25)
limits = Limits(max_gap=0.5, reserve=0.0)
placed = place(geo, probe, point, beam_direction, limits)
placed.state          # "ok" / "collision" / "tight" / "lift_off" / "overhang" / "uncertain"
placed.messages       # české vysvětlení
placed.gap, placed.overhang, placed.volume, placed.clearance
placed.frame          # počátek, osy X/Y/Z sondy; placed.exit_point, placed.beam (pro etapu 04)
placed.body           # těleso sondy (pro kreslení)
scan = scan_line(geo, probe, start, beam_direction, move_direction, length, step, limits)
scan.free_ranges      # [(od, do)] mm – kde sonda volně jede
```

## 4. Testy (hodnoty z tabulky v kap. 2)

- Deska se žebrem: x = 22 → vůle 5,00; x = 17 → bez kolize; x = 16 → kolize 500 mm³;
  s rezervou 5 mm: x = 22 přiloženo, x = 20 *málo místa*. **Posun po přímce** od x = 80
  k žebru s krokem 0,5 mm → volně do x = 17 (bez rezervy) / 22 (rezerva 5) – stejné meze jako
  v `05-referencni-dily.md`.
- Trubka: přímá Ø 10 mezera 0,219 mm; Ø 20 0,882 mm → nedosedá; úhlová paprsek po obvodu →
  mezera 7,33 mm (zadní konec 28 mm od přímky dotyku); paprsek podél osy 0,88 mm.
- Otvor, kapsa, obtížný přístup, koutový svar (úhlová sonda k stojině: výstupní bod ≥ 24 mm
  od osy přiloženo, 23 mm koliduje se svarem).
- Vydutá plocha (stěna otvoru): rovná sonda do díry nedosedne → koliduje.
- Chybné zadání (záporné rozměry, výstupní bod mimo tělo, nulový směr) = česká chyba.

## 5. K rozhodnutí

1. **Okno už v etapě 03?** Návrh: v panelu NDT tlačítko *Přiložit sondu sem* – klikneš na
   plochu, sonda se ve 3D nakreslí zeleně (přiloženo), oranžově (málo místa / nedosedá),
   červeně (kolize), s textem výsledku. Tažení myší a paprsek zůstanou na etapu 05.
2. **Uložit sondu do studie?** Návrh: studie dostane `device` (druh, rozměry, výstupní bod,
   meze mezery a rezervy) – **formát verze 14**, starší soubory se načtou beze změny. Polohy
   sondy se zatím neukládají (přijdou s drahami v etapě 06).
3. **Výchozí manipulační rezerva**: 0 mm (jen fyzická kolize), nebo např. 5 mm (místo pro
   prsty a kabel)?

## 6. Co v etapě 03 nebude

Lom paprsku podle Snellova zákona a odrazy (etapa 04), tažení sondy myší (05), katalog
skutečných sond a předsádek, tvarované předsádky pro trubky (08), naklopení sondy vůči
ploše a omezení sklonu plochy (např. „jen shora“) – přidám, až bude potřeba.

Zdroj meze 0,5 mm: ISO 17640:2018 (a 2005), kap. o zakřivených plochách – mezera mezi
zkoušeným povrchem a spodkem sondy nesmí být větší než 0,5 mm.
