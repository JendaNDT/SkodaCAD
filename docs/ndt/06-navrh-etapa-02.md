# NDT – návrh etapy 02 ke schválení: společné geometrické jádro

> Etapa 02 plánu `03-implementacni-plan.md`. Zatím **jen návrh** – kód až po schválení.
> Jde o geometrii (kudy vede přímka, kde je materiál), ne o fyziku UT ani detekovatelnost.

Stav: návrh 16. 10. 2026 · navazuje na etapy 00–01 (větev `ccr-299f2dcb-9w8xc9`)

## 1. Co etapa přinese

Jeden modul `src/skodacad/ndt/geometry.py` bez okna, který budou používat všechny čtyři
metody (UT paprsek, RT projekce, PT a MT přístup). Šest druhů dotazů na **přesné těleso**
Open CASCADE:

| Dotaz | Otázka | Typické použití později |
|---|---|---|
| **průchod paprsku** | kde přímka vstupuje do materiálu a kde z něj vystupuje, kolik mm vede materiálem | UT dráha, RT prozařovaná tloušťka |
| **bod plochy** | směr ven z materiálu (normála), poloměry zakřivení, hlavní směry, druh plochy | přiložení sondy, tečná rovina, nedosednutí na válci |
| **bod uvnitř / vně** | je bod v materiálu, mimo něj, nebo na povrchu? | cílový objem svaru, vzorkování pokrytí |
| **viditelnost** | vidí bod plochy daným směrem ven, nebo mu něco stojí v cestě (a co, jak daleko)? | PT prohlídka, RT zdroj, přístup nástroje |
| **kolize tělesa** | překrývá se těleso (sonda, jho, detektor) s dílem? Kolik mm³? Jaká je vůle k překážkám? | sonda vedle žebra, jho mezi výztuhami |
| **odkaz → plocha** | plocha z kontrolované oblasti studie (významem, ne indexem) | všechny metody |

## 2. Co jsem ověřil na referenčních dílech (OCCT 8.0.1)

| Zkouška | Výsledek |
|---|---|
| Paprsek přes desku s otvorem (z = 10, podél X) | průsečíky 20 / 110 / 130 / 220 mm → dva úseky po **90 mm** ✓ |
| Paprsek trubkou svisle osou | 42,85 / 48,85 / 151,15 / 157,15 → dva úseky po **6 mm** ✓ |
| Kolize kvádru 40 × 20 × 25 se žebrem (zasunutý o 3 mm) | průnik **1 500 mm³** = 3 × 20 × 25 ✓; položený na plochu 0 mm³ ✓ |
| Zakřivení vnější plochy trubky | poloměr **57,15 mm** po obvodu, rovná podél osy ✓ |
| Rychlost | paprsek i s rozdělením na úseky **0,04–0,08 ms** (≈ 10 000 paprsků/s); kolize 3–6 ms |
| ⚠ Paprsek ležící **přesně v horní ploše** desky | jádro hlásí „vstup“ a „výstup“ → naivně 200 mm v materiálu, ve skutečnosti **nic** |
| ⚠ Paprsek přesně **přes hranu** desky | stejný průsečík dvakrát (dvě plochy u hrany) |

Poslední dva řádky jsou přesně ty „tiché falešné odpovědi“, před kterými plán varuje. Proto se
úseky v materiálu neurčují párováním vstup/výstup, ale **každý úsek mezi průsečíky se ověří
bodem uprostřed** (uvnitř / vně / na povrchu). Co leží na povrchu nebo prochází hranou, je
**nejisté** a nikdy se nezapočítá jako materiál.

## 3. Výsledky s jednotkami a kódem nejistoty

Každý výsledek nese:

- **hodnoty v mm a stupních** (délka v materiálu, vzdálenost, úhel dopadu 0–90° od normály),
- **jistotu**: `ok` (jednoznačné), nebo `uncertain` + seznam **českých důvodů**:

| Důvod | Kdy |
|---|---|
| paprsek běží po povrchu | úsek mezi průsečíky leží na ploše (deska „naplocho“) |
| paprsek prochází hranou nebo rohem | průsečík leží na hraně plochy (blíž než 0,001 mm) |
| paprsek se plochy jen dotýká | dopad skoro tečně (úhel od normály nad 89,4°) |
| jádro nerozhodlo | výjimka nebo neznámý stav bodu |

- **verzi algoritmu** (`ALGORITHM = "ndt-geometrie 1"`) a **tolerance** jako pojmenované
  konstanty – do pozdějšího protokolu.

Tolerance jsou **numerické** (shoda průsečíků 1e-6 mm, hrana 0,001 mm, tečnost 89,4°), ne
fyzikální. Pravidla metod (např. „koncové echo do 60°“ u tloušťkoměru, šířka svazku) patří do
etap 04+ a nastaví si je každá metoda sama. Stávající tloušťkoměr (`measure.RayCaster`) se
**nemění**.

## 4. Rozhraní (návrh)

```python
geo = PartGeometry(part)                     # jádro načte díl jednou, dotazy pak rychle
ray = geo.cast(origin, direction, max_length=None)
ray.segments        # [Segment(start, end, length, entry: Hit, exit: Hit, certain)]
ray.hits            # [Hit(distance, point, normal, face, incidence, entering, reasons)]
ray.material_length # součet jistých úseků (mm); ray.certain, ray.reasons
geo.classify(point)                          # "inside" / "outside" / "surface"
geo.surface_at(point)                        # SurfacePoint(point, normal, kind, radii, directions)
geo.visible(point, direction, max_length=None)  # Visibility(visible, blocker: Hit|None, reasons)
geo.collision(solid, ignore_faces=())        # Collision(volume, colliding, clearance, reasons)
geo.faces_of(target)                         # plochy kontrolované oblasti studie (významem)
```

- Normála vždy **ven z materiálu** (i u vnitřní stěny trubky nebo díry).
- Kolize: **dotyk není kolize** (sonda položená na plochu má průnik 0); kolize = průnik
  s objemem nad 0,001 mm³. Vůle = nejmenší vzdálenost k plochám dílu kromě `ignore_faces`
  (plocha, na které sonda stojí).
- Všechno bez okna a bez Qt. Volá se z `ModelSession` až v etapách 03/05 (výpočet nad
  hotovým dílem, drahé dávky později v pomocném procesu).
- **Zjednodušená síť pro rychlý náhled se teď nedělá**: přesné těleso zvládne ~10 000
  paprsků za sekundu. Síť přidám, až ji změřená potřeba vyžádá (mapa pokrytí v etapě 06),
  a vždy jen pro náhled – rozhodnutí zůstanou na přesném tělese.

## 5. Ukázka bez okna

Nový příkaz pro kontrolu čísel (jako `skodacad build`):

```
skodacad paprsek examples/ndt/trubka.json --z 0,0,100 --smer 0,0,-1
Paprsek z [0; 0; 100] směrem [0; 0; -1] (algoritmus ndt-geometrie 1):
  úsek 1: 42.85 → 48.85 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  úsek 2: 151.15 → 157.15 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  celkem v materiálu: 12.00 mm, jistota: ok
```

## 6. Testy (analytická tělesa, ruční výpočty)

- **Deska** 20 mm: kolmý paprsek 20 mm; šikmý 45° 28,28 mm; úhel dopadu 45,0°;
  po změně t = 30 → 30 mm.
- **Otvor**: paprsek osou otvoru – žádný materiál; podél X přes otvor 2 × 90 mm;
  paprsek 12 mm od osy 20 mm.
- **Trubka**: radiálně 2 × 6 mm; tětiva ve vzdálenosti 54 mm od osy (mine vnitřní stěnu)
  2·√(57,15² − 54²) = 37,42 mm; úhel dopadu asin(54 / 57,15) = 70,9°; normála vnitřní stěny
  míří do otvoru; poloměry zakřivení 57,15 / ∞.
- **Dutina**: kvádr s kulovou dutinou R10 uprostřed – svislý paprsek 2 úseky, celkem 40 − 20 mm.
- **Svar**: paprsek osou svaru shora 15 mm (12 + 2 + 1).
- **Nejisté případy**: paprsek ležící v horní ploše desky → žádný materiál, `uncertain`
  „běží po povrchu“; paprsek přes hranu → `uncertain` „hranou“; tečna k trubce →
  `uncertain` „jen dotýká“. **Žádný z nich se nesmí započítat jako materiál.**
- **Bod uvnitř/vně/na povrchu** na desce, v otvoru, v dutině.
- **Viditelnost** (deska se žebrem): bod x = 30 na desce směrem (−1, 0, 1) → zakryto žebrem ve
  vzdálenosti 35,36 mm; směrem (−1, 0, 3) → vidí (paprsek přejde nad žebrem).
- **Kolize** (deska se žebrem): kvádr 40 × 20 × 25 na desce, střed x = 22 → průnik 1 500 mm³;
  x = 30 → bez kolize, vůle k žebru **5,00 mm**; 0,5 mm nad plochou → vůle 0,5 mm.
- **Rychlost**: 1 000 paprsků trubkou pod 1 s (hlídá, aby se nic nezpomalilo).

## 7. Soubory a kroky

| Krok | Soubor | Obsah |
|---|---|---|
| 1 | `ndt/geometry.py` + `tests/test_ndt_geometry.py` | paprsek, úseky, nejistota, bod uvnitř/vně |
| 2 | totéž | bod plochy (normála, zakřivení), viditelnost, kolize, plochy studie |
| 3 | `cli.py` + test | `skodacad paprsek` |
| 4 | README, CLAUDE.md, `docs/ndt/README.md` | popis, pasti (paprsek v ploše, hrana), plán |

Formát souboru se **nemění**, nové knihovny **žádné**, okno beze změny.
