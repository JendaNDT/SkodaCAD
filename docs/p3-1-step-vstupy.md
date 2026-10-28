# P3.1 — referenční STEP vstupy

Připravená [sada šesti souborů](../tests/fixtures/step/) slouží jako základ pro
návrh a pozdější ověření importu STEP. Všechny vzorky jsou **syntetické**, vytvořené
pro tento projekt ze zadaných jednoduchých rozměrů. Nejsou to exporty od zákazníků
ani z nezávislých CAD systémů; jejich průchod sám o sobě nedokazuje obecnou
kompatibilitu STEP. Tento krok nepřidává uživatelský import ani nemění formát modelu.

## Původ a očekávání

Vzorky byly vytvořeny na macOS pomocí `build123d 0.13.0` a `cadquery-ocp-novtk
8.0.1.1.0`. Předpis je ve [skriptu](../tests/fixtures/step/vytvorit_vzorky.py).
Souřadnice jsou vztažené k počátku; rozměry v tabulce jsou očekávané fyzické
rozměry v mm, objemy v mm³, spočítané z předpisu těles, ne odečtené ze souboru.

| Soubor | Co představuje a jak vznikl | Očekávané vlastnosti |
|---|---|---|
| [01-jedno-teleso.step](../tests/fixtures/step/01-jedno-teleso.step) | Kvádr 40 × 30 × 20 mm; export build123d, mm. | 1 kořen, 1 těleso, 6 ploch; hranice (0, 0, 0) až (40, 30, 20); objem 24 000. |
| [02-dve-telesa.step](../tests/fixtures/step/02-dve-telesa.step) | Dva oddělené kvádry 10 × 20 × 30 a 5 × 10 × 15 mm; každý samostatně převeden STEP zapisovačem, mm. | 2 kořeny, 2 tělesa, 12 ploch; hranice (0, 0, 0) až (35, 20, 30); součet objemů 6 750; bez struktury sestavy. |
| [03-sestava.step](../tests/fixtures/step/03-sestava.step) | Tytéž dva kvádry jako pojmenované součásti „Deska“ a „Kostka“ v sestavě, mm. | 1 kořen sestavy, 2 součásti, 2 tělesa, 12 ploch; stejné celkové hranice a objem jako 02; dvě vazby `NEXT_ASSEMBLY_USAGE_OCCURRENCE`. |
| [04-palce.step](../tests/fixtures/step/04-palce.step) | Kvádr se skutečnou jednotkou STEP INCH; fyzicky 2 × 1 × 0,5 palce. | 1 kořen, 1 těleso, 6 ploch; hranice (0, 0, 0) až (50,8, 25,4, 12,7); objem 16 387,064. |
| [05-otevrena-plocha.step](../tests/fixtures/step/05-otevrena-plocha.step) | Jediná rovinná obdélníková plocha 40 × 20 mm, mm. | 1 kořen, 0 těles, 1 plocha; hranice (−20, −10, 0) až (20, 10, 0); objem 0. Geometricky platná plocha, ale netvoří uzavřené těleso. |
| [06-poskozeny.step](../tests/fixtures/step/06-poskozeny.step) | První polovina bajtů vzorku 01; zbytek včetně konce STEP úmyslně chybí. | Čtení souboru skončí chybou syntaxe; žádné spolehlivé rozměry ani počet těles se neočekávají. |

U vícetělesového vzorku je první kvádr od (0, 0, 0) do (10, 20, 30),
druhý od (30, 0, 0) do (35, 10, 15). Vzorky 02 a 03 mají shodnou geometrii,
ale záměrně odlišnou strukturu STEP. U plochy se nulový objem nesmí zaměnit za
platné uzavřené těleso. Přijetí či odmítnutí jednotlivých kategorií budoucím
importem rozhodne až jeho návrh; zde je pouze popsané vstupní chování.

## Identita a ověření

SHA-256 dodaných souborů:

```text
c326fffbe82273617c8e009f9992f04080e615b6863f686a9bea9e7216cce812  01-jedno-teleso.step
11a3cc83a880c00dc2ba5bea1a8a1173dfdc1f7cd4ea4eeaa21adadc7497e943  02-dve-telesa.step
1f1993250b6a555730367ff7089e9e2b6350dc7b5927a5d132decfd9034784ba  03-sestava.step
1bbd9ecfdbbe43e829ac0a7a5a2d9f3985c14bec2898b99a2192e592da4448fe  04-palce.step
23f564aa265d7ebd65ae278eed335557c9f6394f2fe7f8610ec47606c67541fd  05-otevrena-plocha.step
dfe370bd414a9418d4f20746e02eb5dc0e3e3efacf2304ef1368e5218ad2a2a6  06-poskozeny.step
```

[Testy](../tests/test_p31_step_fixtures.py) ověřují otisky, počet kořenů,
těles a ploch, platnost geometrie, hranice s tolerancí 0,000001 mm, objemy
s absolutní tolerancí 0,00001 mm³, strukturu sestavy, zápis jednotky INCH a
odmítnutí zkráceného souboru čtečkou OCCT. Čtení pro ověření používá stejné
geometrické jádro jako tvorba vzorků; analytické rozměry jsou nezávislou
kontrolou, nikoli náhradou zkoušky s jiným CAD systémem. Kontrola platnosti
otevřené plochy znamená pouze platnost její geometrie, nikoli uzavřenost tělesa.

Skript lze spustit z kořene repozitáře příkazem
`.venv/bin/python tests/fixtures/step/vytvorit_vzorky.py`; **přepíše vzorky**.
Časové údaje či verze knihoven mohou změnit bajty a otisky, i když se geometrie
nezmění. Při úmyslné změně je třeba znovu ověřit očekávané rozměry i strukturu
a upravit otisky v testu i zde; samotné přegenerování není důkaz shody.

## Omezení a pokračování

Sada obsahuje základní geometrii v milimetrech a palcích, jednoduchou plochou
sestavu a jeden způsob poškození. Nepokrývá skutečné soubory z jiných CADů,
vnořené nebo opakované součásti, komplikované křivky, větší soubory, jiné typy
poškození ani rozdílné STEP profily. Před přijetím P3 je vhodné sadu doplnit
o soubory z reálného pracovního postupu se známým původem a rozměry.
Ověření na druhém OS a kompletní zkouška importu/exportu patří do P3.5.

Další etapa P3.2 navrhne přenositelné uložení zdroje, identitu, odkazy,
velikost a obnovu chybějícího souboru; změna formátu vyžaduje zvláštní
schválení autora před implementací.
