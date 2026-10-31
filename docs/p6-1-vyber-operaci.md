# P6.1 — výběr pokročilých operací a první průzkum

Datum: **30. 10. 2026**. Výchozí `main`: `c8e4746`, po
[PR #69](https://github.com/JendaNDT/SkodaCAD/pull/69).
Pracovní návrh v rámci pokynu pokračovat samostatně podle roadmapy z 28. 10. 2026.
Produkční funkce ani nový formát modelu zatím nevznikají.

## Návaznost na P5

Na doporučení dokončit ruční přejímku P5 ve Windows a Excelu autor odpověděl
**„to přeskočíme“**. Tyto zkoušky zůstávají neprovedené a neblokují přechod na P6.
Pokyn není výsledkem ruční zkoušky. Platí dosavadní meze kontrol sestav a NDT.

Technické ověření P5 je doložené v [protokolu Macu](p5-5-overeni-macos-2026-10-30.md).
PR #69 prošlo 1 942 testy na každém systému a self-testy stažených balíčků:
[Windows](https://github.com/JendaNDT/SkodaCAD/actions/runs/41130225910),
[macOS](https://github.com/JendaNDT/SkodaCAD/actions/runs/41130225970).
Také [přenos STEP mezi systémy](https://github.com/JendaNDT/SkodaCAD/actions/runs/41130225950)
prošel. Toto jsou automatické kontroly, nikoli vynechaná ruční přejímka.

## Co už existuje a doporučené pořadí

`features.py` již umí konstantní zaoblení, skořepinu, tažení a přechod mezi skicami.
P6 je má rozšířit. Autor zatím pro tuto etapu nedodal vlastní referenční díl;
pracovní pořadí vychází z existujících ukázek, nikoli z nově potvrzeného požadavku.

| Pořadí | Rozšíření | Vztah k dnešním dílům | Rozhodnutí pro první krok |
|---|---|---|---|
| 1 | Proměnné zaoblení | `krabicka.json` a `kryt.json` již používají konstantní poloměr; rozšíření umožní různě velké přechody na koncích hrany | Prověřit jednu přímou vypouklou hranu mezi dvěma rovinami, dva koncové poloměry |
| 2 | Spolehlivější skořepiny a kontrola skutečné tloušťky | `krabicka.json`, dutý loft `vysypka.json`; známý náhradní postup loftu měří stěnu v rovinách skic, nikoli kolmo k plášti | Samostatný výzkum měření a přesného odsazení; žádné tiché přepínání postupu |
| 3 | Loft s vodicími křivkami | `vysypka.json`; větší kontrola obrysu mezi profily | Samostatný návrh odkazů na křivky a průsečíky s profily, až po první operaci |
| později | Další křivky a plošné modelování | Bez konkrétního referenčního dílu | Nyní nerozšiřovat rozsah |

Nejde o příslib, že všechny kandidáty současné jádro spolehlivě zvládne.

## P6.2 — skutečně provedený omezený pokus

Spustitelný [průzkum](p6-1-pruzkum-zaobleni.py):

```sh
.venv/bin/python docs/p6-1-pruzkum-zaobleni.py
```

Prostředí: Apple M4, Python 3.12.14, build123d 0.13.0, OCP 8.0.1.1.
JSON s naměřenými hodnotami vzniká v `out/p6-1-pruzkum-zaobleni.json`.

Použit je již instalovaný `BRepFilletAPI_MakeFillet`. Podle
[dokumentace OCCT 8.0.1](https://occt3d.com/dev/doc/refman/html/class_b_rep_fillet_a_p_i___make_fillet.html)
podporuje lineární změnu mezi dvěma koncovými poloměry. Pokus ověřuje skutečné
volání dostupné v OCP. Dokumentace
[`ThruSections`](https://occt3d.com/dev/doc/refman/html/class_b_rep_offset_a_p_i___thru_sections.html)
popisuje přechod přes profily; samotné použití tohoto API nedokládá podporu vodicích
křivek a ta v tomto průzkumu zkoušena nebyla.

Hrana se hledá významem (`parallel: Z`, `near: [20, 15, 0]`), nikoli pořadím v tělese.
Na kvádru 40 × 30 × 20 mm se upravuje jeden vypouklý svislý roh.
Poloměry se vztahují k nižšímu/vyššímu Z a před voláním jádra se případně prohodí
podle prvního vrcholu skutečné kontury OCCT.

| Případ | Očekávání | Naměřeno / výsledek |
|---|---|---|
| K1, R3 → R3 | Objem `40·30·20 − (1 − π/4)·3²·20` | **23 961,371669412 mm³**, shoda do 10⁻⁶ mm³ |
| K2, R2 → R6 | Platné těleso; na koncích ústup bodů dotyku od původního rohu 2 a 6 mm; objem mezi konstantním R2 a R6 | **23 924,189749031 mm³**, splněno |
| K3, R6 → R2 | Stejný objem díky symetrii, prohozené koncové ústupy | **23 924,189749031 mm³**, splněno |
| K4, totožný kvádr s obrácenou topologickou orientací po rotaci | R2 zůstane dole a R6 nahoře; stejný objem | **23 924,189749031 mm³**, splněno; jádru se předají opačně seřazené hodnoty |
| D1, navíc vzdálený průchozí otvor Ø6 | Objem K2 minus `π·3²·20`; stejná místa dotyku na upraveném rohu | **23 358,703071601 mm³**, splněno |
| F1, R80 → R80 | Poloměr se na kvádr nevejde | Jádro hlásí `IsDone = False`; žádný výsledek přijat |

U každého hotového výsledku prošla společná kontrola P1 (`inspect_volume`,
`check_modification`): uzavřený platný objem, jedno těleso a zachovaný počet těles.
Dále se kontroluje nezměněná obálka do 2·10⁻⁶ mm, koncové ústupy do 10⁻⁶ mm,
úbytek objemu a nezměněný objem vstupu. Ruff pro průzkum prošel.

**Meze důkazu:** analytický objem je doložen pro konstantní R3. U proměnného
zaoblení jde o kontroly mezí objemu, koncové geometrie, symetrie a vzdáleného otvoru;
nejde o úplné ověření zákona poloměru uvnitř hrany ani tečnosti celé nové plochy.
Nelze automaticky integrovat čtvrtkruhové vodorovné řezy jako u konstantního
zaoblení. Zakřivené hrany, tečné řetězce, dutiny a skutečný autorský díl zkoušeny nebyly.

## Konkrétní návazný krok

Pro první produkční rozšíření doporučuji samostatné **Proměnné zaoblení** s tímto
omezeným rozsahem:

1. Jedna přímá vypouklá hrana mezi dvěma rovinnými plochami; tečný řetězec,
   uzavřená hrana, více vybraných hran a konkávní případ se předem odmítnou.
2. Dva kladné konečné poloměry v mm, včetně parametrických výrazů. Shodné hodnoty
   jsou přípustné a musí dát stejnou geometrii jako běžné konstantní zaoblení.
3. Před uložením navrhnout stabilní vyjádření směru, pojistku významového odkazu
   a nový typ prvku. Čísla se nesmějí obrátit jen kvůli jinému pořadí vrcholů OCCT.
   Okno má ukázat směr a umožnit jeho obrácení.
4. Doplnit ověření průběhu uvnitř hrany a tečnosti, sousedních detailů, změn
   parametrů a nejednoznačného výběru. Hotové pokusy K1–F1 jsou výchozí evidence,
   nikoli kompletní matice produkčních regresí.
5. Až potom služba → zápis a čtení modelu → session a Zpět/Znovu → formulář a výběr
   ve 3D → ukázka → skutečné místní okno a balíčky obou systémů.

Nový typ bude vyžadovat návrh změny formátu (navazující verze 32); v tomto kroku
zůstává `document.VERSION = 31`. Nepřidává se závislost ani náhradní aproximace.
P6.3 implementace ani P6.4 přijetí tímto nejsou dokončené.

**Navázání 31. 10. 2026:** po pokynu autora „ok pokračuj“ bylo doplněno měření
uvnitř hrany. Původní dvouhodnotové volání OCCT má v tomto případě nelineární
průběh. [Návrh a implementace P6.2/P6.3](p6-2-promenne-zaobleni.md) používá přesný
přímkový loft řezacího profilu pro výslovně omezený pravoúhlý roh, s kontrolou
průběhu, tečnosti a objemu a se zápisem verze 32. Historické výsledky výše zůstávají
evidencí původního pokusu, nikoli objemem nové funkce.
