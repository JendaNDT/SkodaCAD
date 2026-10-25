# P2.2 — návrh zápisu přímé úpravy do modelu

**Stav: schváleno autorem 25. 10. 2026, bez implementace.** Autor odpověděl
**„schvaluji H1–H8“** na výzvu, která uváděla i sloučení návrhového
[PR #43](https://github.com/JendaNDT/SkodaCAD/pull/43) a zahájení P2.3. `src/` se tímto
PR nemění, formát zůstává ve verzi 22 až do implementace. Vychází z `main` / `3cd612dc281ca45d76747f4976a5769f532c3329`
(po sloučení [PR #42](https://github.com/JendaNDT/SkodaCAD/pull/42)). Navazuje na
schválený [rozsah P2.1](p2-1-navrh-rozsahu-primeho-modelovani.md) (G1–G8, Q01–Q24)
a na [bezpečné reference P1.3](p1-3-navrh-bezpecnych-referenci.md), oddíl 6, který
ukládaný původ ploch výslovně odkázal na samostatný návrh.

## 1. Co to autorovi přinese

- Každá přímá úprava je v souboru modelu **čitelný řádek** jako ostatní prvky: která
  plocha, o kolik nebo na jaký průměr. Jde ji upravit v okně, v textu i přes AI.
- Úprava si navíc pamatuje, **z kterého prvku plocha pochází**. Když se po změně dřívějšího
  rozměru nebo smazání prvku najde jiná plocha, aplikace úpravu **zastaví s českou
  chybou** místo toho, aby tiše posunula špatnou plochu.
- Staré soubory se otevřou beze změny.

## 2. Rozhodnutí ke schválení H1–H8

| Rozhodnutí | Doporučená varianta | Důsledek / alternativa |
|---|---|---|
| **H1 Dva nové typy prvku** | `move_face` (*Posunutí plochy*: `face`, `origin`, `distance`) a `face_diameter` (*Průměr plochy*: `face`, `origin`, `diameter`). Volitelně `name` jako u všech prvků. | Každý typ má jen svá pole a vlastní kontroly, ve stromu i v README je hned jasné, co dělá (stejně jako oddělené zaoblení a sražení). Alternativa: jeden typ s přepínačem druhu – méně typů, ale pole, která platí jen někdy. |
| **H2 Odkaz na plochu** | Pole `face` = dnešní zápis plochy z P1.3: `{"at": [x, y, z], "normal": [nx, ny, nz], "type": …}`. `type` je povinný: `plane` u posunutí, `cylinder` u průměru. **Pevný poloměr se neukládá.** | Úprava díry pak přežije změnu průměru díry dřív ve stromu (průzkum F3). S pevným poloměrem jako u uložených měření by každá taková změna vyžádala nový výběr (F4). Bezpečnost místo poloměru drží H3. |
| **H3 Pojistka původu** | Pole `origin` = id prvku, od kterého plocha v místě odkazu na díle **nepřetržitě existuje** (hledá se odzadu přes stavy dílu po jednotlivých prvcích). Uloží se při výběru plochy; při každém přepočtu se spočítá znovu pro nalezenou plochu a **musí souhlasit**, jinak česká chyba „plocha teď pochází z prvku X, úprava byla zadaná na plochu z prvku Y – vyber plochu znovu“. Recept se sám nikdy neopravuje. | Zachytí záměny, které dnešní odkaz pustí (Z1–Z4, i pouhou změnou parametru); běžné změny rozměrů projdou (F1–F6). Nepozná záměnu mezi kusy **téhož** prvku, např. dvěma kopiemi jednoho pole (M1) – to zůstává zbytkem R04. Platí jen pro nové typy; měření, skici a NDT se nemění. |
| **H4 Chybějící nebo cizí původ** | `origin` je **povinný**. Chybí-li (ručně psaný soubor) nebo neexistuje-li takový prvek před úpravou, prvek skončí chybou s radou vybrat plochu znovu (*Převzít výběr* z P2.4 ho doplní). | Bezpečnější než původ dopočítat a přijmout. Alternativa: chybějící původ tolerovat jako dnešní odkaz – snazší ruční psaní, ale bez pojistky. |
| **H5 Hodnoty** | `distance` v mm, výraz s parametry, konečné a ≠ 0; + ven z materiálu, − dovnitř. `diameter` v mm, výraz, konečný a > 0; shoda s dnešním průměrem = chyba „úprava nic nemění“ (G3). | Výrazy dovolí navázat úpravu na parametr (např. `"distance": "-t/2"`). |
| **H6 Formát 23** | `VERSION = 23`; verze 1–22 se načtou beze změny obsahu. Uložení zapíše verzi 23 jako u všech dřívějších zvýšení; starší aplikace takový soubor odmítne stávající hláškou „stáhni aktuální aplikaci“. | Jednoduché a stejné jako dosud. Alternativa: psát 22, dokud model nové prvky nepoužívá – lepší pro starší sestavení, ale nová logika ukládání a víc testů. |
| **H7 Vazby na ostatní prvky** | Nové typy patří do `VOLUME_FEATURES` (závěrečná kontrola tělesa), **ne** do `REPEATABLE_FEATURES`: pole a zrcadlení vybraných prvků je odmítne stávající chybou (jako zaoblení); zrcadlení celého dílu zrcadlí výsledek včetně úprav. Do `SELECTION_FEATURES` patří až s oknem (P2.4). NDT studie zastarají otiskem receptu bez změny kódu NDT. | Stejné chování, jaké už mají zaoblení, sražení a skořepina. |
| **H8 README pro AI a R12** | Popis obou typů přidat do oddílu README „Formát modelu“, který čte AI asistent, a přitom opravit **R12** (oddíl dosud uvádí zápis v21) na verzi 23. Ověřit, že pokyn AI obsahuje nové typy. | R12 je podle auditu P0 riziko pro AI; oprava při změně téhož oddílu nic nestojí navíc. Bez H8 by AI nové prvky neznala. |

Ukázka zápisu (hodnoty z průzkumu):

```json
{"id": "tensi_deska", "type": "move_face", "name": "Tenčí deska",
 "face": {"at": [10, 15, 20], "normal": [0, 0, 1], "type": "plane"},
 "origin": "deska", "distance": -3}

{"id": "dira_8", "type": "face_diameter", "name": "Kopie díry na Ø8",
 "face": {"at": [18, 12, 10], "normal": [-1, 0, 0], "type": "cylinder"},
 "origin": "pole", "diameter": 8}
```

## 3. Co potvrzuje současný kód

- `Document.from_dict` kontroluje u prvků jen jedinečné `id` a textový `type`; neznámý typ
  odmítne až přepočet. `to_dict` zapisuje vždy aktuální `VERSION`.
- `selectors.find_face` odmítá neznámé klíče v odkazu – proto je `origin` pole prvku, ne
  součást `face`, a `face` zůstává stejný zápis, jaký mají měření a skici.
- `rebuild` už drží díl před každým prvkem (`BuildResult.parts_before`). Pojistka H3
  potřebuje tytéž stavy při výpočtu prvku – implementace P2.3 je musí prvku zpřístupnit
  jen ke čtení, bez další kopie geometrie.
- Pole a zrcadlení opakují jen prvky se záznamem operací (`_source_operations`);
  úprava počítaná jako zaoblení záznam nemá, takže ji odmítnou. Text té chyby P2.3 rozšíří
  o přímé úpravy.
- Shoda nosné plochy (`picking._same_surface`) už existuje pro přenos ploch z řezu;
  průzkum ji použil beze změny.

## 4. Průzkum pojistky původu

Jednorázový průzkum, **ne implementované regrese**: [`p2-2-pruzkum-puvodu.py`](p2-2-pruzkum-puvodu.py),
cloud Linux, Python 3.13.17, build123d 0.13.0, OCCT 8.0.1. Model: deska 60 × 40 × H,
čep Ø12 výšky 10 nahoře, průchozí díra Ø d, pole 2 kusů po 12 mm a sražení svislých
hran. Odkaz se vyhodnotí dnešním `find_face`, původ podle H3.

| Případ | Plocha nalezená odkazem | Původ | Závěr |
|---|---|---|---|
| O1 horní plocha čepu | rovina z = 30 | `cep` | uložit původ |
| O2 horní plocha desky | rovina z = 20 | `deska` | uložit původ |
| O3 kopie díry z pole | válec R3 | `pole` | uložit původ |
| Z1 čep smazán → horní plocha čepu | rovina z = 20 (deska) | `deska` | **zachyceno** – bez pojistky by se posunula deska |
| Z2 pole smazáno → kopie díry (s R) | válec R3 (původní díra) | `dira` | **zachyceno** |
| Z3 pole smazáno → kopie díry (bez R) | válec R3 (původní díra) | `dira` | **zachyceno** |
| Z4 jen parametr H = 35 → horní plocha čepu | rovina z = 35 (deska) | `deska` | **zachyceno** – čep vyjel výš, nejbližší je deska |
| F1 H = 25 → horní plocha desky | rovina z = 25 | `deska` | projde |
| F2 H = 25 → horní plocha čepu | rovina z = 35 | `cep` | projde |
| F3 d = 8 → kopie díry (bez R) | válec R4 | `pole` | projde |
| F4 d = 8 → kopie díry (s pevným R3) | – | – | chyba už dnes, odtud H2 |
| F5 sražení smazáno → horní plocha desky | rovina z = 20 | `deska` | projde |
| F6 rozteč pole 14 → kopie díry (bez R) | válec R3 | `pole` | projde |
| M1 pole 3 → 2 kusy → třetí díra | válec R3 (druhá kopie) | `pole` | **nezachyceno** – stejný původ |

Výpočet původu trval v průzkumu 4–14 ms. Na pěti ukázkách z `examples/` (1–13 prvků,
8–52 rovinných a válcových ploch) měla každá plocha hotového dílu dohledatelný původ
a nejpomalejší výpočet trval 17 ms (`kryt.json`). Jde o jednorázové měření, ne časový slib.

## 5. Budoucí matice W01–W16

**Specifikace testů pro P2.3, ne přidané testy.** Doplňuje Q01–Q24 z P2.1 o zápis,
načtení a pojistku. U každé chyby ověřit českou zprávu, stav `error`, přeskočení
následných prvků a nezměněný recept.

| Č. | Případ | Očekávání |
|---|---|---|
| W01 | Soubory všech verzí 1–22 a všechny ukázky | načtou se a přepočítají se stejně jako dnes |
| W02 | Uložit model bez nových prvků a znovu otevřít | stejný obsah, verze 23 |
| W03 | Uložit a otevřít model s oběma typy | totožné prvky, stejný díl (objem, rozměry) |
| W04 | Soubor verze 24 | odmítnout stávající hláškou o novější verzi |
| W05 | `move_face` bez `face`, s `type` ≠ `plane`, s neznámým klíčem v `face` | chyba prvku s českou radou |
| W06 | `face_diameter` s `type` ≠ `cylinder` | chyba prvku |
| W07 | `distance` 0, nekonečné, neplatný výraz; `diameter` ≤ 0 nebo beze změny | chyba prvku, hodnota v textu chyby |
| W08 | Chybějící `origin` (H4) | chyba prvku s radou vybrat plochu znovu |
| W09 | `origin` s id, které není před úpravou | chyba prvku |
| W10 | Z1–Z4 z průzkumu | chyba „plocha teď pochází z prvku …“ |
| W11 | F1–F3, F5, F6 z průzkumu | úprava proběhne, objem podle vzorce |
| W12 | M1 | úprava proběhne na jiné kopii – test dokládá přiznanou mez, ne správnost |
| W13 | Dvě úpravy téže plochy za sebou | druhá má původ v první úpravě; obě projdou |
| W14 | Pole nebo zrcadlení vybírající přímou úpravu | odmítnout stávající chybou rozšířenou o přímé úpravy |
| W15 | NDT studie a uložené měření po přidání úpravy | studie zastará; měření se přepočítá |
| W16 | Pokyn AI asistenta | obsahuje oba typy a verzi 23 (oprava R12) |

## 6. Navazující kroky a rozsah schválení

1. **P2.3 Výpočet** – oba typy v jádře podle G1–G8 a H1–H8, formát 23, README; testy
   Q01–Q22 a W01–W16. Malé kroky s Ruff a celým pytest, PR ke kontrole.
2. **P2.4 Ovládání** – klik na plochu → hodnota → náhled → Použít / Zrušit, *Převzít výběr*,
   nástroj AI.
3. **P2.5 Přijetí** – Q01–Q24 a W01–W16 na obou systémech, stažené balíčky, ruční zkouška.

Schválení H1–H8 opravňuje připravit implementaci P2.3 podle tohoto zápisu. Samotné
schválení **nic neslučuje do main**; návrhový PR se slučuje jen s výslovným souhlasem
autora. Zbytek R04 (M1), R03 a NDT-17 zůstávají otevřené.
