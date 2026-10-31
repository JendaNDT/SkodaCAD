# P6.2 — skořepiny: tři reference, měření a rozsah další opravy

Datum **31. 10. 2026**, produkční základ **b245175** (PR #71). Po pokynu autora
„ok, udělej to“ k prověření tří referenčních dílů. Výstupem je spustitelný průzkum,
recepty dílů, měření a konkrétní návrh další implementace. Produkční kód,
závislosti a formát aplikace se v tomto kroku nemění.

## Výsledek

Na třech referencích současná skořepina vytvořila platná tělesa a její objemy
souhlasí s nezávislými analytickými vzorci. V pravidelných částech stěn odpovídá
měření zadané tloušťce. U rohů je nutné rozlišovat zesílení a nejisté měření;
nelze vyžadovat, aby každý normálový paprsek kdekoliv prošel právě zadanou vzdálenost.

Konkrétní nález pro navazující opravu je **dutý loft výsypky**: zadané 3 mm jsou
v rovinách skic, naměřená délka materiálem kolmo k plášti je ve vzorcích
**2,608803–2,769231 mm**. Přímý 3D offset zde vrátil platné, ale nezměněné plné
těleso; aplikace jej odmítla objemovou kontrolou a použila současný náhradní
postup. Tento postup i jeho omezení již popisuje ukázka, formulář jej ale
neodlišuje samostatnou volbou od skutečné normálové stěny.

## Reprodukce a metoda

```sh
.venv/bin/python docs/p6-3-pruzkum-skorepin.py --output out/p6-3-skorepiny
.venv/bin/ruff check src tests docs/p6-3-pruzkum-skorepin.py
```

Místní prostředí: Apple M4, Python **3.12.14**, build123d **0.13.0**, OCP **8.0.1.1**.
Každý ze šesti případů běží odděleným procesem s limitem 120 s. Výsledek obsahuje
verze, commit, SHA-256 skriptu, všechny body a normály, hodnoty i nejisté vzorky.
Recepty `.json`, přesné `.step` a izometrické `.svg` se generují do uvedené složky.
Žádný soubor autora se nepřepisuje. Workflow **P6 průzkum skořepin** opakuje stejné
kontroly na Windows a macOS a uchovává kompletní výstupy; výsledky běhu jsou v PR.

Pro každou ponechanou vnější plochu se použije parametrická síť **5 × 5** bodů,
vynechají se body mimo oříznutou plochu a do 0,0001 mm od hrany. U každého bodu
se ověří, že malý krok dovnitř leží v materiálu a krok ven mimo něj.
Otevírané čelní plochy nejsou součástí měření stěn. Síť není rovnoměrná podle
plochy a nedokazuje globální minimum ani hodnoty mezi vzorky.

Skript zaznamenává **dva různé údaje**:

- `normal_material_length_mm`: první výstup paprsku z materiálu v záporné normále,
  bez úhlového filtru; čistě geometrická délka materiálem.
- `thickness_mm`, `oblique`: současné měřidlo `measure.RayCaster`, které odmítá
  protější stěnu odkloněnou o více než 60°. U šikmého odrazu vrací nejistý výsledek.

Tato zkouška není validací UT ani důkazem prozvučitelnosti nebo detekovatelnosti vad.
Geometrická kontrola CADu nemá měnit stávající význam NDT měřidla.

## Tři referenční díly — místní výsledky

| Recept | Rozměry / zadaná stěna | Objem [mm³] | Vzorky měřidla | Délka materiálem kolmo [mm] |
|---|---|---:|---|---|
| `kvadr.json` | 80 × 50 × 30, otevřený vršek, 3 mm | 32 088,000000 | 125 hodnot = 3 mm | 3,000000–3,000000 |
| `sikme_steny.json` | dole 80 × 50, nahoře 40 × 30, výška 40, 3 mm | 33 193,128199 | 111 hodnot = 3 mm; 4 nejisté u dna | 3,000000–14,662921 |
| `zaobleny_kryt.json` | 80 × 50 × 30, rohy R6, spodní lem R3, 2 mm | 21 145,933511 | 425 hodnot = 2 mm | 2,000000–2,000000 |

Maximální odchylka známých hodnot od jmenovité stěny byla pod **2,3 · 10⁻¹³ mm**;
pracovní mez porovnání je **0,00002 mm**, nikoli výrobní tolerance. Objemy se liší
od analytických hodnot o méně než **4 · 10⁻¹¹ mm³**. Každý výsledek prošel kontrolou
P1, má jedno uzavřené platné těleso a menší objem než výchozí plný díl.

U šikmého dílu leží čtyři vzorky dna pod plným klínem v místě styku se šikmým bokem.
Paprsek nenarazí na vnitřní dno ve vzdálenosti 3 mm; prochází zesíleným rohem až
k šikmému boku. Současné měřidlo jej správně odmítá úhlovým filtrem. Hodnota
14,662921 mm proto není tenká stěna ani selhání odsazení. Samotný název
`BSPLINE` není důkazem, že offset plochy selže: boky tohoto rovinného loftu jsou
v jádře reprezentované jako BSpline a výsledek je správný.

### Nezávislé vzorce objemu

Kvádr: `V = 80·50·30 − 74·44·27`.

Šikmý díl má vnější poloviny šířek `a(z) = 40 − z/2`, `b(z) = 25 − z/4`.
Vnitřní rovnoběžné boky mají poloviny šířek
`aᵢ(z) = a(z) − t·√1,25`, `bᵢ(z) = b(z) − t·√1,0625` a dno v `z = t`.
Objem je `∫₀⁴⁰ 4ab dz − ∫ₜ⁴⁰ 4aᵢbᵢ dz`. To ověřuje odsazení kolmo ke skutečným
rovinám, nikoli jen zmenšení horní a dolní skici o stejné číslo.

Zaoblený kryt: pro zaoblený obdélník `L × W`, rohy `R`, výšku `H` a spodní lem `f`
je `A = L·W − (4−π)R²`, `P = 2(L+W) − 2(4−π)R` a
`F(L,W,H,R,f) = A·H − P·f²(1−π/4) + π·f³(5/3−π/2)`.
Vzorec vznikne integrací obsahu `A − Pq + πq²`, kde
`q(z) = f − √(f² − (z−f)²)` pro `0 ≤ z ≤ f`.
Skořepina t2 má objem `F(80,50,30,6,3) − F(76,46,28,4,1)`.

## Tři kontroly mezí

| Případ | Zjištění | Interpretace |
|---|---|---|
| Stejný kryt, stěna 4 mm přes spodní R3 | Platný solid; měřidlo 265 hodnot 4–4,414214 mm, 160 nejistých; geometricky 4–7,283658 mm | Zánik vnitřního zaoblení vede k zesílení. Ve středu oblouku analyticky `3 + √2 = 4,414214 mm`. Není důvod automaticky označit každý větší údaj za chybu. |
| Kvádr, stěna 26 mm | Česká chyba, vrácená geometrie je původní plné těleso 120 000 mm³ | Současná kontrola P1 odmítá neúčinnou skořepinu a zachovává stav k opravě. |
| Stávající výsypka, stěna 3 mm | 125 hodnot 2,608803–2,769231 mm, bez nejistých; objem 908 807,481709 mm³ | Přímý offset má stejný objem jako plný díl 23 169 043,764569 mm³; použitý vnitřní loft ze zmenšených skic nevytváří 3 mm kolmo. |

Obecný přesný offset složitých ploch se v tomto kroku nepodařilo prokázat. Nezkouší
se znovu dříve zaznamenané postupy s růstem paměti ani změna knihoven. Zjištění
neopravňuje měnit starým modelům jejich geometrii bez výslovné změny režimu.

## Konkrétní návrh navazující implementace

1. **Pojmenovat význam stěny loftu.** V okně rozlišit „Kolmo ke stěně“ a „V rovinách
   skic“. Nově vytvořený normálový režim nesmí po selhání tiše přejít na druhý postup.
   Nezměněný výsledek jádra se nadále odmítá; neproveditelný normálový loft končí
   českou chybou a odkazem na výslovnou volbu druhého režimu.
2. **Zachovat staré recepty.** Chybějící volba v dosavadních modelech zachová dnešní
   chování, včetně této výsypky. Nové uložené pole vyžaduje samostatný návrh formátu
   (navazující verze 33) před produkční změnou; tento průzkum formát nemění.
3. **Měření pro CAD.** Připravit samostatný přehled geometrické délky materiálem
   kolmo k povrchu, s počtem vzorků, místy, zesíleními a nevyhodnotitelnými body.
   Přehled není potvrzení globální konstantní tloušťky. Úhlový filtr měření NDT
   ponechat a jeho nejisté výsledky nezaměňovat za naměřenou tenkou stěnu.
4. **Přijímání výsledku.** Platnost, uzavřenost, počet těles a úbytek objemu z P1
   zůstávají povinné. Navíc sledovat skutečně otevřená čela a původ vnějších stěn.
   Vzorkované měření doplňuje tyto kontroly; samo není univerzálním důkazem
   správnosti offsetu. Zesílení u styku stěn se reportuje, ne plošně odmítá.
5. **Regrese před předáním.** Převést tyto tři reference, dvě mezní skořepiny a starou
   výsypku do produkčních regresí; přidat konstantní kužel a válec, změnu parametru,
   volbu režimu, Zpět/Znovu, uložení/otevření staré i nové verze a předání workerem.
   Následuje skutečné okno na Macu a oba úplné workflow s balíčky.

První praktická oprava má tedy řešit **výslovný režim stěny dutého loftu a jeho
čitelné vyhodnocení**. Přepis funkčního výpočtu tří běžných skořepin nemá z tohoto
průzkumu oporu. Obecná podpora libovolného offsetu a autorská přejímka zůstávají otevřené.

## Primární podklady

- [OCCT 8.0.1: MakeThickSolid](https://occt3d.com/dev/doc/refman/html/class_b_rep_offset_a_p_i___make_thick_solid.html):
  duté těleso s odstraněnými čely a odsazenými stěnami.
- [OCCT 8.0.1: MakeOffsetShape](https://occt3d.com/dev/doc/refman/html/class_b_rep_offset_a_p_i___make_offset_shape.html):
  omezení průniků, kontinuity a samoprůniků; parametr `Intersection` není obecná
  záruka opravy. V instalovaném build123d 0.13.0 jej `offset_3d` nastavuje na `True`.
- Instalovaný kód `features._hollow_loft`, `features.build_shell`,
  `measure.RayCaster` a `geometry_validation.check_modification`; samotná deklarace
  API není důkazem správnosti konkrétního výsledku.
