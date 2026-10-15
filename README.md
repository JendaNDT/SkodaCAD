# ŠkodaCAD

Osobní parametrický 3D CAD postavený na jádře **Open CASCADE** (přes knihovnu
[build123d](https://github.com/gumyr/build123d)). Vyvíjený vibecodingem v Claude Code.

**Stav:** jádro + první okno pro Windows. Díl se popíše v čitelném souboru JSON
(parametry + seznam prvků), jádro z něj postaví přesné těleso, spočítá objem a hmotnost
a uloží exporty pro jiné CAD programy i 3D tisk. Okno ukáže díl ve 3D a dovolí měnit
parametry.

## Aplikace pro Windows

1. Stáhni **[SkodaCAD-windows.zip](https://github.com/JendaNDT/SkodaCAD/releases/latest/download/SkodaCAD-windows.zip)**
   (stránka [Releases](https://github.com/JendaNDT/SkodaCAD/releases), vydání „nejnovejsi“).
2. Rozbal ho (pravé tlačítko → *Extrahovat vše*).
3. Ve složce `SkodaCAD` spusť **`SkodaCAD.exe`**.
4. Windows může napsat *„Systém Windows ochránil váš počítač“* – aplikace není digitálně
   podepsaná. Klikni na *Další informace* → *Přesto spustit*.

Aplikace sestavuje GitHub automaticky po každé změně ve větvi `main`
(postup [.github/workflows/windows.yml](.github/workflows/windows.yml)).

### Ovládání

| Akce | Jak |
|---|---|
| Otáčení | levé tlačítko + táhnout |
| Posun | prostřední nebo pravé tlačítko + táhnout |
| Zoom | kolečko (ke kurzoru) |
| Výběr plochy / hrany | klik – popis (typ, obsah, průměr…) se ukáže dole ve stavovém řádku |
| Více hran / ploch | `Ctrl`+klik (nebo `Shift`+klik) přidá nebo ubere |
| Co s výběrem | pravé tlačítko (bez tažení): Zaoblit, Srazit, Skica na ploše, Skořepina… |
| Zrušit výběr | `Esc` |
| Celý díl | dvojklik nebo `F` |
| Pohledy | `0` izometrie, `1` zepředu, `3` zprava, `7` shora (s `Ctrl` opačná strana) |
| Změna parametru | přepiš hodnotu vlevo a stiskni Enter (číslo, `12,5` i výraz `D/2 + 5`) |
| Přepočítat | `F5` |

Neplatná hodnota parametru se zbarví červeně a model zůstane beze změny. Když některý
prvek nejde spočítat, ve stromu prvků se ukáže ✕ a česky proč.

### Vlastní díl od nuly

1. **Soubor → Nový**, vlevo nahoře vyplň název a materiál.
2. **Přidat prvek → Skica**: na rovině XY vznikne obdélník 40 × 30. Vpravo v panelu
   *Úprava prvku* změň rozměry, přidej další tvary (*Přidat tvar*) – otvor je tvar
   s režimem *odečíst*.
3. **Přidat prvek → Vysunutí**: ze skici vznikne těleso, vpravo nastav vzdálenost.
4. Díra nebo výstupek: další **Skica** se sama položí na horní plochu dílu (kružnice Ø10),
   pak **Vysunutí** s operací *odebrat materiál* a případně *Řez skrz celý díl*.
5. **Zaoblení / Sražení kliknutím**: klikni ve 3D na hranu (další s `Ctrl`), pravé tlačítko →
   *Zaoblit vybrané hrany*. Program si hranu nezapamatuje číslem, ale významem („hrana mezi
   přední a pravou plochou“, „kružnice R3 na horní ploše“) – výběr tak platí i po změně
   rozměrů. Hrany vybraného zaoblení svítí ve 3D růžově; další přidáš přes pravé tlačítko →
   *Přidat vybrané hrany do…*. Hrany jde vybrat i ručně ve formuláři (na ploše, rovnoběžné…).
6. **Skica na ploše kliknutím**: klikni na rovinnou plochu (i dno kapsy nebo schod), pravé
   tlačítko → *Skica na vybrané ploše* – kružnice Ø10 vznikne v místě kliknutí.
7. **Skicář (obrys z čar s vazbami)**: *Přidat prvek → Skica – nakreslit obrys…* (nebo u tvaru
   „Obrys z čar“ tlačítko *Upravit ve skicáři…*). Viz [Skicář](#skicář) níže.
8. **+ Parametr** vytvoří pojmenovaný rozměr; jeho název pak můžeš napsat do kteréhokoli
   pole (např. `sirka` nebo `sirka/2 - 5`).

### Skicář

1. Nástroj **Úsečka** (`L`): klikej body obrysu. Klik na existující bod čáry napojí, klik do
   počátku (zelený kroužek) obrys k počátku připne. Skoro vodorovná/svislá čára dostane vazbu
   sama. Konec řetězu: `Esc` nebo pravé tlačítko. **Oblouk** (`A`): začátek, konec a bod,
   kudy má vést.
2. Nástroj **Výběr** (`S`): klikni na čáru nebo bod (`Ctrl` = přidat další) a přidej vazbu
   tlačítkem vlevo – *Vodorovně, Svisle, Rovnoběžně, Kolmo, Tečně, Stejně velké, Na bodě/čáře,
   Uprostřed, Pevný bod*.
3. **Kóta…** (`D`): úsečka = délka, oblouk = poloměr, dva body nebo bod a čára = vzdálenost,
   dvě úsečky = úhel. Hodnota může být číslo i výraz s parametrem (`sirka`, `D/2`) – obrys se
   pak mění s parametrem.
4. Dole vpravo je vidět, kolik rozměrů **zbývá určit** (modrý obrys jde ještě táhnout myší),
   nebo **✓ plně určeno** (černý obrys). Vazby, které si odporují, jsou **červeně** – smaž je
   (*Smazat vazbu*) nebo dej *Zpět* (`Ctrl+Z`).
5. **Pomocná čára** (`G`) se účastní vazeb, ale není součástí obrysu (např. osa souměrnosti).
6. **Hotovo** uloží obrys do modelu (jako jeden krok pro Zpět v hlavním okně). Obrys pak vysuň
   nebo orotuj; s režimem *odečíst* je z něj otvor.

Ukázka: *Soubor → Otevřít ukázku → paka* – změň `L` nebo `R` a obrys páky se přepočítá.

Prvek vybraný ve stromu jde smazat (*Smazat*, klávesa Delete) nebo posunout (▲ ▼). Nový prvek
se vloží za vybraný. **Zpět / Znovu**: `Ctrl+Z` / `Ctrl+Y`.

Do složky **`SkodaCAD`** ve tvém uživatelském profilu (`C:\Users\<jméno>\SkodaCAD`) se
zapisuje soubor `skodacad.log` – při potížích ho pošli, je v něm popis chyby.

## Příkazová řádka

```bash
skodacad build examples/priruba.json            # postaví přírubu, exporty do out/
skodacad build examples/priruba.json --set n=8  # totéž s 8 dírami místo 4
skodacad build examples/krabicka.json --format 3mf,svg
```

Výstup:

```
Strom prvků:
  ✓ Skica „Obrys příruby“
  ✓ Vysunutí „Deska“
  ...
Vlastnosti dílu:
  Objem:     311 093 mm³ (311.09 cm³)
  Hmotnost:  2.442 kg (ocel, 7.85 g/cm³)
  Rozměry:   165.00 × 165.00 × 18.00 mm
Uloženo: out/priruba.step, out/priruba.stl, out/priruba.3mf, out/priruba.svg
```

| Formát | K čemu |
|---|---|
| `step` | přesná geometrie pro jiné CAD programy (Inventor, Solid Edge, Fusion …) |
| `stl`, `3mf` | 3D tisk (3MF je modernější a nese jednotky) |
| `glb` | prohlížeče, Blender |
| `svg` | izometrický náhled se skrytými hranami |

## Formát modelu

```json
{
  "format": "skodacad",
  "version": 3,
  "name": "Plochá příruba",
  "material": "ocel",
  "parameters": {"D": 165, "t": 18, "k": "D - 40"},
  "features": [ ... ]
}
```

Každá číselná hodnota může být číslo nebo **výraz** s parametry, např. `"D/2 - 5"`.
Výrazy umí `+ - * / **`, závorky, `sqrt`, `sin`, `cos`, `tan` (ve stupních), `min`, `max`, `pi`.
Rozměry jsou v milimetrech, úhly ve stupních.

### Prvky (`features`)

Každý prvek má jedinečné `id`, `type` a volitelně český `name` pro výpis stromu.

| `type` | Co dělá | Hodnoty |
|---|---|---|
| `sketch` | 2D skica | `plane`, `offset`, `elements` (seznam tvarů) |
| `extrude` | vysunutí skici | `sketch`, `distance`, `operation`, `direction`, `through_all` |
| `revolve` | rotace skici kolem osy | `sketch`, `axis` (`X`/`Y`/`Z`), `angle` (výchozí 360) |
| `fillet` | zaoblení hran | `edges`, `radius` |
| `chamfer` | sražení hran | `edges`, `distance` |
| `shell` | skořepina (vydlabání) | `thickness`, `open_faces` (např. `["top"]`) |

* **`plane`** – základní rovina `XY`, `XZ`, `YZ`, nebo plocha dílu `top`, `bottom`, `front`,
  `back`, `left`, `right`. Souřadnice skici na ploše dílu jsou globální (na `top` platí X a Y dílu).
* **`operation`** – `new` (první těleso), `add` (přidat materiál), `cut` (odebrat).
* **`direction`** – `normal` (ven z roviny), `reverse` (opačně), `both` (symetricky, `distance` je
  celková tloušťka). Řez (`cut`) jde ve výchozím stavu do materiálu.
* **`through_all": true`** – řez skrz celý díl.

### Tvary ve skice (`elements`)

| `shape` | Hodnoty |
|---|---|
| `rectangle` | `width`, `height`, `corner_radius` |
| `circle` | `diameter` |
| `circle_pattern` | `count`, `pitch_diameter`, `diameter`, `start_angle` – díry na roztečné kružnici |
| `regular_polygon` | `sides`, `diameter` (opsaný) – např. šestihran |
| `slot` | `length` (rozteč středů), `width` – drážka |
| `polygon` | `points` – seznam bodů `[[x, y], …]` |
| `profile` | obrys z úseček a oblouků s vazbami – kreslí se ve skicáři, viz níže |

Všechny tvary mají navíc `center` (`[x, y]`), `angle` a `mode` (`add` = přidat, `subtract` = odečíst,
tak vzniká např. otvor v kruhu).

### Obrys s vazbami (`profile`)

```json
{"shape": "profile",
 "points": {"A": [0, 0], "B": [40, 0], "C": [40, 20], "M": [40, 10], "D": [0, 20]},
 "segments": {"s1": {"type": "line", "start": "A", "end": "B"},
              "s2": {"type": "arc", "start": "B", "end": "C", "center": "M"},
              "s3": {"type": "line", "start": "C", "end": "D"},
              "s4": {"type": "line", "start": "D", "end": "A"}},
 "constraints": [{"type": "coincident", "point": "A", "on": "origin"},
                 {"type": "horizontal", "segment": "s1"},
                 {"type": "length", "segment": "s1", "value": "sirka"},
                 {"type": "radius", "segment": "s2", "value": 10},
                 {"type": "tangent", "segments": ["s1", "s2"]}]}
```

* `points` jsou přibližné polohy – přesné spočítá řešič vazeb (SolveSpace) při každém přepočtu.
* Oblouk vede **proti směru hodinových ručiček** od `start` do `end`; `"construction": true`
  = pomocná čára. Bod `origin` je počátek skici.
* Vazby: `fix` (point), `coincident` (point + on: bod/čára/origin), `horizontal`/`vertical`
  (segment, nebo points), `parallel`, `perpendicular`, `tangent`, `equal` (segments),
  `midpoint` (point + segment); kóty s `value` (číslo nebo výraz): `length` (segment),
  `distance` (points, nebo point + segment), `radius` (segment), `angle` (segments, °).

### Výběr hran (`edges`)

Hrany se vybírají **významem, ne číslem** – výběr tak platí i po změně rozměrů.

```json
"edges": "all"
"edges": {"face": "top"}                                  // hrany horní plochy
"edges": {"face": "top", "type": "circle", "radius": "D/2"} // jen vnější kružnice nahoře
"edges": {"parallel": "Z"}                                // svislé hrany
"edges": {"between": ["front", "right"]}                  // hrana mezi přední a pravou plochou
"edges": {"face": "top", "radius": 3, "near": [20, 0, 10]} // z děr R3 nahoře ta nejbližší k bodu
"edges": [{"face": "top"}, {"parallel": "Z"}]             // seznam = všechny dohromady
```

Výběr kliknutím ve 3D vytváří tyto popisy sám: zkusí nejjednodušší, který vybere přesně
kliknuté hrany. `near` (nejbližší k bodu) použije jen tam, kde nic jiného nestačí – třeba jedna
ze čtyř stejných děr. Soubory verze 1 (bez `between`, `near` a seznamu) se načtou dál.

### Materiály

`ocel`, `nerez`, `litina`, `hlinik`, `mosaz`, `med`, `titan`, `pla`, `petg`, `abs`
(diakritika a velká písmena nevadí).

## Pro vývoj

Pravidla projektu, architektura a plán jsou v [CLAUDE.md](CLAUDE.md). Podkladové výzkumy
jsou ve složce [docs/](docs/).

```bash
pip install -e ".[dev,gui]"   # jádro, okno a nástroje pro vývoj
pytest -q                     # testy (ověřují geometrii výpočtem objemu)
ruff check src tests          # kontrola kódu
skodacad-gui                  # spustí okno (bez argumentu otevře ukázku příruby)
skodacad-gui --self-test zprava.txt   # kontrola aplikace bez obsluhy
```
