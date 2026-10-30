# P5.1 — návrh datového formátu sestav

**Stav: schváleno autorem 30. 10. 2026** slovy **„schvaluji S1–S12“** (návrhové
[PR #62](https://github.com/JendaNDT/SkodaCAD/pull/62)). Schválení opravňuje zahájit P5.2
podle tohoto zápisu. `src/` se tímto krokem
nemění, formát modelu zůstává ve verzi 28 až do implementace P5.2. Vychází z `main` / `1ac9b12` (po sloučení
[PR #61](https://github.com/JendaNDT/SkodaCAD/pull/61)) a z bodu P5.1 schválené
[roadmapy](roadmapa-vyvoje.md#p5--sestavy): oddělit díl, instanci a sestavu; identity,
relativní cesty, cyklické odkazy, chybějící komponenty a verze. Formát se podle roadmapy
nejdřív schvaluje.

## 1. Co to autorovi přinese

- Ze stávajících dílů (krabička, víčko, šrouby, deska elektroniky…) složíš **sestavu**:
  každý díl dostane polohu a natočení. Stejný díl jde vložit vícekrát (čtyři stejné šrouby).
- Sestava je **vlastní soubor**, který na soubory dílů jen **odkazuje**. Když díl
  upravíš, sestava ho při příštím otevření ukáže už upravený. Sestava soubory dílů
  **nikdy nepřepisuje**.
- Když soubor dílu chybí nebo je poškozený, sestava se přesto otevře. Řekne česky, co
  chybí, a záznam dílu nesmaže. Oprava jde přes *Najít soubor…*.
- Stávající soubory dílů zůstanou beze změny. Otevřou je i starší verze aplikace.

## 2. Tři pojmy a ukázka souboru

| Pojem | Co to je | Kde je uložené |
|---|---|---|
| **Díl** | dnešní model: parametry, prvky, materiál, NDT studie, výkres | vlastní soubor dílu, beze změny |
| **Komponenta** | jedno vložení dílu do sestavy: id, název, odkaz na soubor, poloha, příznak *pevná* | řádek v sestavě |
| **Sestava** | název, popis, parametry sestavy a seznam komponent | vlastní soubor sestavy |

Komponenta může odkazovat i na jinou sestavu (**podsestava**, např. deska elektroniky
s konektory). Ukázka uspořádání a souboru (otisky jsou **ilustrativní**):

```
projekt/
  krabicka_sestava.json        ← sestava
  dily/spodek.json, vicko.json, sroub_m3x8.json
  elektronika/deska.json       ← podsestava
```

```json
{
  "format": "skodacad",
  "kind": "assembly",
  "version": 29,
  "name": "Krabička s elektronikou",
  "description": "",
  "units": "mm",
  "parameters": {"H": 30},
  "components": [
    {"id": "spodek", "name": "Spodek",
     "source": {"path": "dily/spodek.json", "fingerprint": "1f0c9a7e5b2d4c38"},
     "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
     "fixed": true},
    {"id": "vicko", "name": "Víčko",
     "source": {"path": "dily/vicko.json", "fingerprint": "8a41d0c2e9f3b765"},
     "placement": {"position": [0, 0, "H + 2"], "rotation": [180, 0, 0]}},
    {"id": "sroub_1", "source": {"path": "dily/sroub_m3x8.json"},
     "placement": {"position": [-34, -19, "H + 2"], "rotation": [0, 0, 0]}},
    {"id": "sroub_2", "source": {"path": "dily/sroub_m3x8.json"},
     "placement": {"position": [34, 19, "H + 2"], "rotation": [0, 0, 0]}},
    {"id": "elektronika", "name": "Deska s plošným spojem",
     "source": {"path": "elektronika/deska.json"},
     "placement": {"position": [0, 0, 4], "rotation": [0, 0, 90]}}
  ]
}
```

## 3. Rozhodnutí ke schválení S1–S12

| Rozhodnutí | Doporučená varianta | Důsledek / alternativa |
|---|---|---|
| **S1 Samostatný soubor, odkazy na díly** | Sestava je vlastní soubor JSON. Komponenty na soubory dílů **odkazují**, díly do sestavy nekopírují. | Úprava dílu se projeví ve všech sestavách, které ho používají; jeden díl může být ve více sestavách. Nevýhoda: při přenosu je třeba kopírovat celou složku. Alternativy: díly vložené do souboru sestavy jako kopie (jeden soubor, ale úprava dílu se do sestavy nedostane) nebo více těles v jednom souboru dílu (nejde znovu použít). Případné *Zabalit sestavu* (zkopírovat sestavu se všemi díly do jedné složky nebo ZIP) je pozdější samostatný krok. |
| **S2 Obsah sestavy** | `name`, `description`, `units` (jen `"mm"`), `parameters` (jako u dílu, pro polohy) a `components`. Komponenta: `id`, nepovinný `name`, `source`, `placement`, nepovinný `fixed`. **Neznámý klíč v sestavě, komponentě, zdroji nebo poloze = česká chyba.** Komponenta nemá vlastní parametry ani materiál. | Překlep v ručně psaném souboru nebo v návrhu AI se nepřehlédne. Jiný rozměr = jiný soubor dílu (např. `sroub_m3x8.json`, `sroub_m3x12.json`). Parametry na komponentu (jeden soubor šroubu, různé délky) jsou možné později s vlastním návrhem – změní kusovník i identitu ploch. |
| **S3 Rozlišení souboru a verze 29** | Sestava má `"kind": "assembly"` a **verzi 29**. Díl `kind` nemá a dál se ukládá v nejnižší potřebné verzi (24–28), takže ho otevře i starší aplikace. Díl otevřený jako sestava a sestava otevřená jako díl (okno, `skodacad build`, AI) = česká chyba „tento soubor je sestava / díl“. Neznámý `kind` = chyba. | Starší aplikace sestavu odmítne stávající hláškou „stáhni aktuální aplikaci“. **Vlastní číslování sestav od 1 by bylo nebezpečné:** dnešní načítání neznámé klíče přeskočí, sestavu by otevřelo jako **prázdný díl** a uložením by ji přepsalo (ověřeno v oddílu 5). Stejná přípona `.json` a stejný dialog *Otevřít*. |
| **S4 Cesta ke zdroji** | `source.path` = cesta **vůči složce souboru sestavy**, oddělovač vždy `/`, `..` jen na začátku (`../dily/deska.json`). Odmítnout: absolutní cestu, písmeno disku, `\`, prázdné části, `.` a `..` uprostřed. Soubor se musí najít **s přesnou velikostí písmen**; najde-li se jen s jinou, upozornit „na systému, který rozlišuje velká a malá písmena, by se nenašel“. Díl na jiném disku Windows nejde vložit – rada zkopírovat ho do složky projektu. | Složka projektu jde přenést mezi Windows a Macem i na jiné místo disku. Každý soubor má právě jeden zápis cesty, takže stejný díl se pozná. Nová sestava se proto hned při založení uloží (bez umístění nejde spočítat cestu). |
| **S5 Otisk zdroje (jen informace)** | Nepovinné `source.fingerprint` = otisk receptu dílu (`study.part_fingerprint`: parametry, prvky, materiál – bez názvů, měření, NDT a výkresu), zapsaný při uložení sestavy. Liší-li se při otevření, sestava napíše „díl se od posledního uložení sestavy změnil – zkontroluj polohy“. **Nikdy neblokuje** – sestava vždy použije aktuální díl. | Autor se dozví, proč díry už nelícují. Upozornění zmizí po uložení sestavy; otevření sestavu nemění. U podsestavy otisk jejího receptu. Úprava výkresu nebo NDT studie v dílu upozornění nevyvolá. |
| **S6 Identita komponenty** | Každá komponenta má textové `id` jedinečné v sestavě (vzor jako u prvků: `sroub_1`, `sroub_2`). Vše, co na komponentu odkazuje (budoucí vazby, kusovník, výběr ve 3D), používá `id`, **nikdy pořadí**. V podsestavě se komponenta určí cestou id (`["elektronika", "konektor_1"]`). Smazání komponenty smaže i vazby na ni (jeden krok Zpět). | Přeřazení komponent nic nerozbije. Plochy dílu se ve vazbách P5.3 budou vybírat **významem** jako dnes (pravidlo 1), v souřadnicích dílu. |
| **S7 Poloha** | `placement.position` = posun [x, y, z] v mm, `placement.rotation` = úhly [rx, ry, rz] ve stupních: **otočení kolem pevných os sestavy nejdřív X, pak Y, pak Z**. Čísla nebo výrazy s parametry sestavy. Násobky 90° se počítají přesně a úhly z tlačítek „otočit o 90°“ se ukládají zaokrouhlené (90, ne 89,99999999999999). Jen posun a otočení – **žádné měřítko ani zrcadlení**. Výchozí poloha = počátek bez otočení. | Čitelné pro autora, okno i AI. Pořadí os je třeba mít výslovně: výchozí pořadí build123d je jiné a dává jinou polohu (oddíl 5, P1). Zrcadlený díl = vlastní soubor s prvkem *Zrcadlení*. Alternativa: zapsat směr os X a Z dílu (přesné, bez pořadí), ale obecný úhel a úhel z parametru jsou pak nečitelné. |
| **S8 Pevná komponenta** | `"fixed": true` – první vložená komponenta je pevná. Pevnou nehne tažení myší ani budoucí řešič vazeb; poloha jde změnit jen výslovně číslem ve formuláři. `false` se do souboru nepíše. | Sestava má pevný základ. V P5.2 (bez vazeb) jde hlavně o ochranu proti nechtěnému posunu. |
| **S9 Chybějící a vadná komponenta** | Stavy komponenty: **ok**, **chybí** (soubor nenalezen), **nečitelná** (není JSON, není ŠkodaCAD, novější verze, neplatná struktura), **chyba dílu** (přepočet nedopadl `ok`, pravidlo P1.4 E1), **cyklus**. Sestava se otevře vždy; vadná komponenta zůstane v seznamu s českým důvodem a ve 3D se nekreslí. Její záznam se **nesmaže ani nezmění**, uložení ho zachová. *Najít soubor…* změní jen `path` (jeden krok Zpět); jiný otisk ohlásí před přijetím. Nikdy se nevybere jiný soubor automaticky. | Rozpracovaná sestava se neztratí. Hmotnost a kusovník se v okně ukážou s nápisem „neúplné – chybí N komponent“; **export geometrie, kusovníku a kontrola kolizí jen pro úplnou sestavu** (stejně jako P1.4 E2 u dílu). |
| **S10 Podsestavy, cykly, meze** | Podsestavy dovolené. Cyklus se pozná podle skutečného souboru (i přes `..` a odkazy systému) a ohlásí cestou „krabicka_sestava.json → elektronika.json → krabicka_sestava.json“. Meze: nejvýš **8 úrovní** a **1 000 komponent** celkem (po rozbalení podsestav) – zvoleno, ne změřeno. | Žádné nekonečné načítání. Podsestava je v nadřazené sestavě jeden tuhý celek; její vnitřek se upravuje v jejím souboru. |
| **S11 Hranice sestavy** | Sestava **nikdy nezapisuje do souborů dílů** a má vlastní Zpět/Znovu. *Otevřít díl* přepne okno na soubor dílu (s dotazem na uložení), po návratu se sestava přepočítá. NDT studie, výkres, měření a mapa tloušťky patří dílu; sestava je ve formátu 29 nemá. Výsledky NDT dílu se **nikdy nevydávají za výsledek sestavy** (sousední díl může sondě zavazet). | Změna komponenty nemůže změnit zdrojový díl ani jinou komponentu (roadmapa P5.2). NDT v sestavě a výkres sestavy jsou pozdější samostatné návrhy (P5.4 vymezí). Úprava dílu přímo v sestavě není v rozsahu. |
| **S12 Přepočet a budoucí vazby** | Každý zdrojový soubor se postaví **jednou**, kopie dílu sdílí tvar a liší se jen polohou. Přepočet běží v pomocném procesu jako u dílu. Průniky mezi kopiemi (kolize v P5.4) jen nedestruktivně (`geometry._common`). Až přibudou vazby (P5.3, vlastní návrh a vlastní verze formátu), **poloha se dál ukládá vždy** jako poslední vypočtený výsledek. | Čtyři šrouby nestojí čtyřikrát tolik času. Sdílené hrany už jednou zpomalovaly NDT (PR #59) – oddíl 5, P4. Sestava s vazbami půjde otevřít i tehdy, když řešič selže. |

## 4. Co potvrzuje současný kód

- `Document.from_dict` kontroluje `format` a `version`, ostatní neznámé klíče přeskočí.
  Soubor `{"format": "skodacad", "version": 1, "kind": "assembly", "components": […]}`
  dnes otevře jako **prázdný díl** a `to_dict` z něj udělá díl verze 24 bez komponent –
  odtud S3 (verze 29, ne vlastní číslování).
- `Document.to_dict` už dnes zapisuje nejnižší potřebnou verzi (24–28 podle výkresu), takže
  díly verzi 29 nedostanou. `Document.save` zapisuje přes dočasný soubor a výměnu; soubor
  sestavy použije stejný postup.
- `study.part_fingerprint` (otisk receptu bez názvů) existuje a používají ho NDT studie;
  S5 ho jen převezme. `Document.with_parameters` existuje (pro pozdější parametry
  komponenty).
- Dialog *Otevřít* filtruje `*.json`; sestava se pozná podle `kind`, ne přípony.
- Ukázky: `test_examples_and_cli`, nabídka ukázek, self-test a `skodacad.spec` procházejí
  `examples/*.json` (a `ndt/`), dva testy `rglob` celou složku. Ukázková sestava proto
  patří do vlastní podsložky `examples/sestavy/` a P5.2 musí tyto průchody upravit.
- `ModelSession` drží jeden díl; sestava dostane vlastní session se Zpět/Znovu (pravidlo 8
  a 10 platí i pro ni).
- `geometry._common` (nedestruktivní průnik) existuje od PR #59. Řešič `slvs 3.2` umí
  i prostorové vazby – je kandidát pro P5.3, rozhodne se tam.

## 5. Průzkum

Jednorázový průzkum, **ne test projektu**: [`p5-1-pruzkum-sestav.py`](p5-1-pruzkum-sestav.py),
cloud Linux, build123d 0.13.0, OCCT 8.0.1.

| Č. | Případ | Výsledek | Závěr |
|---|---|---|---|
| P1 | Kvádr 30 × 20 × 10 v rohu u počátku, úhly (90, 0, 90) kolem pevných os X→Y→Z | obálka (0, 0, 0)–(10, 30, 20) podle ručního výpočtu | S7 platí |
| P1 | Totéž s výchozím pořadím build123d | obálka (−20, −10, 0)–(0, 0, 30) | **jiná poloha** – pořadí musí být výslovné (`Extrinsic.XYZ`) |
| P2 | Otočení o 90° kolem X | max y = 4,4·10⁻¹⁵ místo 0; s přesnou maticí přesně 0 | násobky 90° počítat přesně |
| P2 | 90° kolem X, pak 90° kolem Z, převod zpět na úhly | 89,999999999999986 / −0 / 89,999999999999986 | úhly z tlačítek zaokrouhlit |
| P3 | `krabicka.json`: sestavení dílu, 100 posunutých kopií | díl 212–342 ms, 100 kopií 80–108 ms; všechny kopie sdílí tvar, zdroj beze změny, objem 21 045,40 mm³, 26,73 g | stavět jednou, kopie jen posunout (S12) |
| P4 | Průnik dvou kopií kvádru 20 mm posunutých o 15 mm | oba způsoby 2 000 mm³ (vzorec 5 · 20 · 20); výchozí `&` přidal do hran **zdroje** záznamy 36 → 44, `_common` 36 → 36 | kolize kopií jen nedestruktivně |
| P5 | Pravidla cest S4 na 11 zápisech | přijato jen `dily/deska.json` a `../dily/deska.json`; díl na jiném disku Windows nemá relativní cestu | S4 platí |
| P6 | `a.json → b.json → ./sub/../a.json` | „cyklus: a.json → b.json → a.json“ | cyklus podle skutečného souboru (S10) |

Časy jsou jednorázové měření v cloudu, ne slib.

## 6. Budoucí matice A01–A22

**Specifikace testů pro P5.2, ne přidané testy.** U každé chyby ověřit českou zprávu
a nezměněné soubory.

| Č. | Případ | Očekávání |
|---|---|---|
| A01 | Soubory dílů verzí 1–28 a všechny ukázky | načtou se a uloží beze změny; díl nikdy nedostane verzi 29 |
| A02 | Sestavu otevřít a uložit bez úprav | totožný obsah souboru |
| A03 | `kind: "assembly"` s verzí pod 29, neznámý `kind` | chyba |
| A04 | Sestava otevřená jako díl (okno, `skodacad build`, AI), díl jako sestava | česká chyba „je to sestava / díl“ |
| A05 | Chybějící nebo zdvojené `id`, neznámý klíč, `units` jiné než mm | chyba s názvem místa |
| A06 | Všech 11 zápisů cesty z průzkumu P5 | přijato / odmítnuto stejně |
| A07 | Soubor dílu chybí | stav *chybí*, ostatní komponenty ok, uložení zachová záznam beze změny |
| A08 | Není JSON, není ŠkodaCAD, novější verze, díl s chybou přepočtu | stav *nečitelná* / *chyba dílu* s důvodem |
| A09 | Cyklus A → B → A a A → A | stav *cyklus* s cestou, načítání skončí |
| A10 | 9 úrovní podsestav, 1 001 komponent | chyba s mezí |
| A11 | Kvádr z P1 s (90, 0, 90), posun a výraz s parametrem | obálka podle výpočtu, posun podle parametru |
| A12 | Násobky 90°, dvě otočení tlačítkem | obálka přesně 0, uložené úhly celé |
| A13 | Dvě kopie téhož dílu, změna polohy jedné | druhá beze změny, soubor dílu bajt po bajtu stejný, kopie sdílí tvar |
| A14 | Změna souboru dílu mezi otevřeními | sestava ukáže nový díl a upozornění; po uložení upozornění zmizí |
| A15 | *Najít soubor…* s jiným otiskem | upozornění před přijetím, jeden krok Zpět |
| A16 | Objem a hmotnost sestavy | součet komponent podle vzorce; neúplná = „neúplné“, export odmítnut |
| A17 | Podsestava s posunem i otočením | obálka komponent podle složení obou poloh |
| A18 | Přenos složky projektu Windows ↔ macOS | otevře se stejně (rozšířit workflow `p35-cross-os.yml`) |
| A19 | Soubor nalezený jen s jinou velikostí písmen | upozornění |
| A20 | Vložení, smazání, posun, přejmenování; nezměněný formulář | každá změna jeden krok Zpět, beze změny žádný |
| A21 | Pevná komponenta | první vložená pevná; tažení ji nepohne |
| A22 | Ukázková sestava v `examples/sestavy/` | jde postavit, test ukázek, nabídka, self-test a balíček ji znají |

## 7. Co P5.1 záměrně neřeší

Vazby a jejich řešič (P5.3), kolize, vůle, kusovník a export sestavy (P5.4), NDT v sestavě,
výkres sestavy, úprava dílu přímo v sestavě, parametry komponent, pole komponent,
*Zabalit sestavu*, import sestav ze STEP (P3 je dál odmítá) a AI nástroje pro sestavy.
Každé z toho dostane vlastní návrh, až na ně dojde.

## 8. Navazující kroky a rozsah schválení

1. **P5.2 Polohy** – jádro formátu 29 (načtení, kontrola, uložení, stavy komponent, cesty,
   cykly, poloha), session sestavy se Zpět/Znovu, přepočet v pomocném procesu, okno
   (nová sestava, vložit díl, strom komponent, formulář polohy s tlačítky ±90°, pevná,
   *Najít soubor…*, *Otevřít díl*), ukázka a testy A01–A22. Postup po malých krocích
   s Ruff a celým pytest.
2. **P5.3 Vazby** – nejdřív návrh řešiče a zápisu vazeb.
3. **P5.4 Kontroly** – kolize, vůle, kusovník, export, vymezení NDT.
4. **P5.5 Přijetí** – ruční zkouška autora na obou systémech.

Schválení S1–S12 opravňuje zahájit P5.2 podle tohoto zápisu. Ruční přijetí P5 a odborná
validace NDT zůstávají na autorovi.
