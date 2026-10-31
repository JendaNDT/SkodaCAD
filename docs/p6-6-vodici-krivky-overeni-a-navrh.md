# P6 – vodicí křivky přechodu: ověření a návrh

Datum: **31. 10. 2026**, výchozí `main` **445bd66**, po [PR #74](https://github.com/JendaNDT/SkodaCAD/pull/74).
Autor odsouhlasil „Prověřit přechody s vodicími křivkami“. Výstupem této etapy je
spustitelný průzkum, fyzikální reference, meze a návrh první funkce.
Aplikace, její geometrii ani formát 33 tento krok nemění.

## Závěr

Vodítka lze použít bez nové knihovny. Pro první produkční krok doporučuji **plný
přechod mezi dvěma obdélníkovými čely, se čtyřmi kubickými rohovými vodítky**.
U přímých stran profilů lze použít přímo Bézierovy plochy se společnými řídicími
body. Výsledek má nezávislý analytický objem a kontrolu průřezů po celé výšce.
Pět takových sítí prošlo také obecným Gordonovým algoritmem, včetně ohnutí,
čtyř profilů v nerovnoměrných výškách a obráceného směru křivek.

Obecné Gordonovy plochy jsou vhodný další kandidát pro zakřivené profily.
Samotné splnění vodítek, P1 a koncových profilů však nedokazuje požadovaný tvar
mezi nimi ani tečnou návaznost sousedních ploch. Příklady níže tuto mezeru měří.
Zvyšovat toleranci sešití kvůli tomu nebylo potřeba ani vyzkoušeno jako oprava.

## Co je skutečně dostupné

Místní prostředí: Python 3.12.14, build123d **0.13.0**, OCP **8.0.1.1**
(`cadquery-ocp-novtk` 8.0.1.1.0), již používané `ocp_gordon` **0.3.1**.
`loft()` nemá argument pro vodítka; OCCT `ThruSections` skládá postupné profily.
Použitá vydání knihoven byla ověřena importem, zdrojovým kódem a spuštěním,
nejen podle proměnlivé dokumentace „latest“.

- [OCCT 8.0.1 – ThruSections](https://occt3d.com/dev/doc/refman/html/class_b_rep_offset_a_p_i___thru_sections.html): rozhraní sekcí, bez samostatné sítě vodítek.
- [build123d – přímé API](https://build123d.readthedocs.io/en/latest/direct_api_reference.html#build123d.Face.make_gordon_surface): `Face.make_gordon_surface(profiles, guides, tolerance)` a `Face.make_bezier_surface(points)`.
- [Oficiální příklad křídla](https://build123d.readthedocs.io/en/latest/tutorial_spitfire_wing_gordon.html): síť profilů a vodítek, uzavření čelem a solidem.
- [Zdroj a meze ocp_gordon](https://github.com/gongfan99/ocp_gordon), [poznámka autora o mezerách](https://github.com/gongfan99/ocp_gordon/wiki/Gordon-Surface-Misalignment): aproximace při přeparametrizování může rozpojit sousední plochy; jde o důvod skutečně měřit hranice.

Samostatný průzkum v CI připíná již existující tranzitivní `ocp_gordon==0.3.1`.
Produkční závislosti se nemění. JSON evidence obsahuje skutečné verze NumPy,
SciPy, Pythonu, systému a SHA-256 průzkumného skriptu.

## Reprodukce a kontroly

```sh
.venv/bin/python docs/p6-6-pruzkum-voditek.py --output out/p6-guided-loft-study
.venv/bin/pytest -q tests/test_guided_loft_study.py
.venv/bin/ruff check src tests docs/p6-6-pruzkum-voditek.py
```

Každý případ běží v samostatném procesu s limitem 60 sekund. Výstup zahrnuje
`inputs.json`, `result.json`, úplné vzorky hranic a u kruhů radiální měření.
Platné kandidáty mají STEP, SVG a síť jen pro obrázek. Soubory vstupů mají vlastní
výzkumné označení `skodacad-guided-loft-study`; nejsou receptem aplikace.
Hlavní `results.json` má `complete: false` až do dokončení všech případů, aby
předchozí úspěšný běh nezakryl nové selhání.

Kontroly:

- P1: celý platný kladný uzavřený objem, právě jeden solid. Samotná P1 nestačí na křížení.
- Gordonova pracovní mez 0,000001 mm; kontrolní mez vzorků **0,00001 mm**.
- Čtyři boční plochy se sešijí s původními čely přes `Shell`, poté `Solid`.
  Výsledná nejvyšší tolerance hran se zapisuje; u referencí zůstala kolem 10⁻⁷ mm.
- Pro každou vstupní křivku na příslušné ploše 41 parametrických bodů včetně konců:
  původní body se uloží **před** voláním jádra. Zapisuje se také změna bodů vstupů.
- Obdélníkové případy mají vedle Gordonova tělesa přímou Bézierovu referenci,
  analytický objem a 80 vnitřních kontrolních bodů pláště.
- Kruhy: 180 radiálních paprsků v devíti výškách mezi profily, plocha prostředního
  řezu, objem a 12 vzorků úhlu normál podél společných vodítek. Paprsek je přesná
  geometrická služba, nejde o NDT tloušťku ani filtr koncového echa.
- Tři samostatné pytest reference ověřují objem jiným výpočtem a nutnost hledat
  kolaps průřezu i mezi dvěma platnými čely.

Vzorky nejsou globální důkaz odchylky ani tečnosti. Výšky vodítek v tomto pokusu
jsou `z(t)=60t`; obecná prostorová vodítka, více průsečíků s jedním profilem,
tečnost na okolní díl ani odolnost offsetu z těchto výsledků neplynou.

## Devět případů a místní výsledky

Všechny rozměry v mm, objemy v mm³. Tolerance jsou číselné, nikoli výrobní přejímka.

| Případ | Očekávání | Místní výsledek |
|---|---|---|
| Rovný obdélníkový přechod | 40×30 → 24×18, výška 60; objem komolého jehlanu | **47 040**, shoda s běžným loftem i Bézierovou referencí |
| Vyboulený | Čtyři vodítka zvětší prostředek; koncová čela zůstanou | **77 760**, shoda s integrálem; běžný loft má 47 040 |
| Ohnutý | Posun středů po výšce při stejných velikostech průřezů nemění objem | **77 760**, vodítka i vnitřní body splněny |
| Více profilů | Profily při t=0 / 0,17 / 0,63 / 1 leží na téže referenci | **77 760**, největší vzorkovaná odchylka hranice přibližně 1,26·10⁻¹¹ mm |
| Obrácené křivky | Opačná geometrická orientace vodítek a pořadí vstupů zachovají tvar | **77 760**, stejné fyzikální kontroly |
| Dva kruhové profily | Ukázat, zda síť vynutí také kruhový průřez uprostřed | P1 platná, objem **97 370,056333**; prostřední diagonální poloměr **23,535534** místo 25, zlom až **15,635947°** |
| Tři kruhové profily | Přidaná střední kružnice r=25 zlepší určení pláště | **103 044,238950** proti referenci **103 044,239038**; max. vzorkovaná radiální odchylka **2,19·10⁻⁸ mm**, úhel do 0,000001° |
| Mezírka vodítka | Jeden konec vodítka je 1 mm od čela | Síť odmítnuta jádrem; návrhová kontrola ji zachytí před konstrukcí |
| Křížení | Platná čela, rohová vodítka se uvnitř protnou | **P1 překvapivě přijme** solid o objemu 14 992; nezávislá kontrola konvexity jej odmítne |

Poslední případ je hlavní důvod nepřidat pouze volání Gordonova algoritmu do
stávajícího loftu. P1 se v této etapě nemění; nová operace bude potřebovat vlastní
kontrolu vložené sítě. `reference_accepted` v evidenci značí splnění dané reference,
nikoli dostupnou funkci aplikace nebo univerzální certifikaci geometrie.

### Nezávislé rovnice

Vyboulený obdélník má polorozměry
`a(t)=20+20t−28t²`, `b(t)=15+14t−20t²`, `z(t)=60t`.
Objem je `4·60·∫₀¹ a(t)b(t)dt = 77 760`. Posun středu jej nemění.
Pro obecné čtyři kubické rohy se integruje obsah čtyřúhelníku podle shoelace
vzorce. Orientované součiny sousedních stran jsou polynomy; jejich minimum se
hledá i ve stacionárních bodech celého intervalu, ne jen v několika řezech.
Mez tohoto součinu je samostatně 0,00001 mm². Kořeny se zde počítají numericky;
nejde o certifikovanou intervalovou aritmetiku. Produkční pojistka bude potřebovat
konzervativní mez a při nerozhodném výsledku síť odmítnout.

Kruhová reference je rotační těleso s `r(t)=20+20t(1−t)`:
`V=60π∫₀¹r(t)²dt=32 800π`. Dva koncové kruhy a čtyři rohová vodítka tuto další
podmínku neobsahují. Gordonův výsledek s nimi tedy není automaticky chybou
algoritmu; neodpovídá však dodatečnému očekávání kruhových meziřezů a hladkého
pláště. Třetí profil v této konkrétní pravidelné síti dal referenční tvar ve vzorcích.

## Návrh první produkční funkce

Samostatný typ **Řízený přechod**, pracovní název `guided_loft`. První rozsah:

1. Dvě uzavřené obdélníkové skici bez zaoblení a děr, na rovnoběžných
   rovinách se souhlasnými lokálními osami. První ověření provést pro XY a kladnou výšku.
2. Čtyři kubická rohová vodítka. Konce se odvodí z geometrických rohů obou profilů;
   nezadávají se číslem vrcholu/hranové položky. Každý roh určí znaménka lokálního
   X/Y vůči středu obdélníku. Změna rozměru skici tak zachová význam rohu.
3. Na každém vodítku dvě řídicí rukojeti, v jedné a dvou třetinách výšky. Zadat lze
   jejich posun X/Y od přímého spojení rohů, včetně parametrických výrazů. Jejich
   Z se pro první verzi měnit nedá; průchod každou mezilehlou rovinou je jednoznačný.
4. Plný solid, operace nový/přidat/odebrat. První verze neobsahuje dutou stěnu,
   obecné obloukové profily ani tečnost na sousední díl. Právě ty potřebují další
   ověření; dnešní režimy a měření stěny obyčejného loftu zůstanou samostatné.

Pracovní náčrt zápisu, **dosud nepodporovaný aplikací**:

```json
{
  "type": "guided_loft",
  "id": "rizeny_prechod",
  "sketches": ["dole", "nahore"],
  "guides": [
    {"corner": {"x": 1, "y": 1}, "controls": [[7, 5], [7, 5]]},
    {"corner": {"x": -1, "y": 1}, "controls": [[-7, 5], [-7, 5]]},
    {"corner": {"x": -1, "y": -1}, "controls": [[-7, -5], [-7, -5]]},
    {"corner": {"x": 1, "y": -1}, "controls": [[7, -5], [7, -5]]}
  ],
  "operation": "new"
}
```

Příklad ukazuje posuny řídicích bodů, nikoli přímo vyboulení průřezu v jeho
polovině. Například stejné posuny 7/5 u obou rukojetí dají v polovině příspěvek
3/4 těchto hodnot. Čísla 4/3 násobku vyboulení použitá v průzkumu jsou uvedena
přímo v `inputs.json`; nesmějí se zaměnit s poloměrem nebo kótou skutečného řezu.

Pro první omezený tvar použít čtyři `Face.make_bezier_surface` ze sousedních
vodítek a společná čela. Prostorové čtyři rohy mají po celé výšce konvexní
nekolabující průřez, ověřený polynomy, a stejný jednoznačný parametr výšky.
To umožňuje kontrolovat křížení nad rámec P1. Gordon zůstává porovnávací metodou
pro tento rozsah a výzkumnou metodou pro pozdější obecnou síť.

Vytvoření nového typu bude vyžadovat návrh a zápis formátu **34**, nikoli změnu
významu starého `loft`. Před přijetím: kontrola profilů, jedinečnosti čtyř rohů,
konečnosti výrazů, konvexity v intervalu, shody čel a vodítek, P1 a odmítnutí
neplatné sítě českou chybou. Při odmítnutí zachovat předchozí díl a přeskočit
navazující historii. Žádné tiché nahrazení běžným loftem.

Okno bude zobrazovat barevně označená čtyři vodítka, jejich směr a dva řídicí body.
První editor může mít čtyři řádky s X/Y posuny obou rukojetí; výběr řádku zvýrazní
příslušnou křivku a body ve 3D. Rozlišit skutečný plášť od řídicího polygonu.
Veškerý výpočet přes ModelSession a proces na pozadí, každá úprava jeden krok
Zpět/Znovu. Samostatné volné prostorové křivky jako prvky stromu lze přidat později;
první verze je pro tuto úzce vymezenou funkci nepotřebuje.

## Stav ověření a další práce

Místně: devět pokusů s výše uvedenými výsledky, analytické reference a cílené
regrese stávajících loftů. Zdroj aplikace se nemění, proto se místní úplná sada
neopakuje (CLAUDE pravidlo 6). Podmínkou sloučení jsou úplné Windows/macOS kontroly
včetně stažených balíčků a nový průzkum na obou systémech. Jejich konkrétní výsledky
budou v implementačním PR; místní evidence je `out/p6-guided-loft-study/`.

Následuje první omezená implementace podle návrhu, s fyzikálními testy průřezů,
parametrů, zneplatnění výběrů, chyb, historie, workeru a skutečného okna. Uživatelovo
vlastní referenční těleso pro P6.4 zatím není dodané; přejímka na něm zůstává otevřená.
