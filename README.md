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
5. **Zaoblení / Sražení**: hrany se vybírají popisem („na horní ploše“, „rovnoběžné s osou Z“,
   „poloměr 9“) – výběr tak platí i po změně rozměrů.
6. **+ Parametr** vytvoří pojmenovaný rozměr; jeho název pak můžeš napsat do kteréhokoli
   pole (např. `sirka` nebo `sirka/2 - 5`).

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
  "version": 1,
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

Všechny tvary mají navíc `center` (`[x, y]`), `angle` a `mode` (`add` = přidat, `subtract` = odečíst,
tak vzniká např. otvor v kruhu).

### Výběr hran (`edges`)

Hrany se vybírají **významem, ne číslem** – výběr tak platí i po změně rozměrů.

```json
"edges": "all"
"edges": {"face": "top"}                                  // hrany horní plochy
"edges": {"face": "top", "type": "circle", "radius": "D/2"} // jen vnější kružnice nahoře
"edges": {"parallel": "Z"}                                // svislé hrany
```

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
