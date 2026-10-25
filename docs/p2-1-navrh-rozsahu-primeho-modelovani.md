# P2.1 — návrh rozsahu přímého modelování

**Stav: schváleno autorem 25. 10. 2026, bez implementace.** Autor v rozhovoru
odpověděl **„schvaluji G1–G8“** na výzvu, která uváděla i sloučení návrhového
[PR #42](https://github.com/JendaNDT/SkodaCAD/pull/42) a přípravu P2.2. Schválení se týká
G1–G8 a matice Q01–Q24; P2.2–P2.5 ani nový formát tím schválené nejsou.
Modelový formát zůstává ve verzi 22, `src/` se nemění. Vychází z `main` / `fe2a087757796946d9664ddd4a3aa0c2e1874037`
(po sloučení [PR #41](https://github.com/JendaNDT/SkodaCAD/pull/41)); autor 25. 10. 2026
[přijal P1](p1-5-overeni.md#sloučení-a-přijetí-p1-autorem). Navazuje na
[roadmapu P2](roadmapa-vyvoje.md#p2--přímé-modelování-čeká-na-schválení-implementace),
[smlouvu geometrických operací P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md)
a [bezpečné reference P1.3](p1-3-navrh-bezpecnych-referenci.md).

## 1. Co to autorovi přinese

- Klikneš na **rovinnou plochu** a posuneš ji o zadaný počet mm (deska tenčí, dno kapsy
  mělčí, bok širší) – bez hledání, který prvek ve stromu ji vytvořil.
- Klikneš na **válcovou plochu** (díra nebo čep) a zadáš **nový průměr**. Osa zůstane.
- Úprava se přidá jako **nový krok na konec stromu**: jde vrátit (Zpět), smazat
  i později změnit číslo. Funguje i na díle bez historie, tedy i po budoucím
  importu STEP (P3).
- Co jádro neumí spolehlivě, aplikace **odmítne česky a díl nechá beze změny**.

## 2. Rozhodnutí ke schválení G1–G8

| Rozhodnutí | Doporučená varianta | Důsledek / alternativa |
|---|---|---|
| **G1 Princip** | Přímá úprava je **samostatný prvek na konci stromu**, který mění hotový díl. Původní prvky zůstanou beze změny. Konkrétní zápis navrhne P2.2. | Funguje i bez historie (STEP), jeden krok Zpět, platí kontroly P1. Alternativa „změnit parametr původního prvku“ (táhnout plochu = změnit hloubku vysunutí) jde jen tam, kde je vazba jasná; lze ji přidat později jako zkratku. Úpravy bez historie (díl jako „mrtvé“ těleso) nedoporučuji. |
| **G2 První podporované úpravy** | (a) **posun jedné rovinné plochy** kolmo k ní, i šikmé; (b) **změna průměru jedné válcové plochy** – otvor i čep. Jedna plocha = jeden prvek. | Více ploch najednou jádro zvládne (případ K5), ale ztíží ovládání i chybové hlášky; doporučuji až po ověření první verze. Čep je stejný výpočet jako díra (D6), proto je v rozsahu. |
| **G3 Zadávané hodnoty** | Rovina: **posun v mm**, + ven z materiálu (přidá), − dovnitř (ubere). Válec: **nový průměr v mm**. Obojí smí být výraz s parametry. Posun 0 nebo stejný průměr = chyba „úprava nic nemění“. | Průměr je u díry srozumitelnější než „posun o 0,5 mm“. Alternativa: i u válce zadávat posun stěny. |
| **G4 Chování sousedů** | Sousední plochy si drží svůj tvar a jen se prodlouží nebo zkrátí. Čep na posunuté ploše **zůstane na místě a zkrátí se** (S1), kuželové sražení vedle posunuté plochy se zvětší (P3). Když by soused zanikl, plocha splynula s jinou nebo vnikla do jiné části tělesa, úprava se **odmítne**. | Stejné chování mají běžné CAD funkce „posunout plochu“. Přenášet prvky s plochou (čep jede nahoru s ní) by byla jiná, složitější operace mimo první verzi. |
| **G5 Kontroly výsledku** | Celá smlouva P1 (platná uzavřená tělesa, stejný počet těles) a navíc: plocha **patří k dílu**; **stejný počet ploch** jako před úpravou; **žádná plocha s nulovou výměrou** (≤ 10⁻⁶ mm²); upravená plocha je **na požadovaném místě** (rovina posunutá o zadanou hodnotu, válec s novým poloměrem na stejné ose, obojí do 10⁻⁶ mm); změna objemu větší než εV z P1.1. Nic se neopravuje ani nezkouší s větší tolerancí. | Bez těchto doplňků by prošly tři chybné případy z průzkumu: cizí plocha tiše ignorovaná (X1), zaniklé sražení ponechané jako plocha s nulovou výměrou (D9) a díra, u které se rozbila tečnost zaoblení (D10). |
| **G6 Nepodporováno v první verzi** | Předem odmítnout: **plochu s tečně navazujícím sousedem** (zaoblení, úhel normál pod 1°), kužel, kouli, toroid, obecné plochy z tažení/přechodu, plochy **vymodelovaného závitu**. Díra protnutá jinou dírou (D7) se odmítne až podle výsledku jádra. | Seznam se může zúžit jen novým schválením. Plocha rozdělená na víc kusů ve stejné rovině: posune se jen kliknutý kus. |
| **G7 Historie a navazující věci** | Odkaz na plochu **významem podle P1.3** (bod, směr, druh, u válce poloměr); nejednoznačnost = česká chyba, nic se nehádá. **Pole a zrcadlení přímé úpravy neopakují** (jako zaoblení) – u pole děr se změní jen kliknutá díra. NDT studie po úpravě **zastarají** stávajícím otiskem receptu; uložená měření se přepočítají. U díry z prvku *Díra* okno upozorní, že označení závitu a tabulková hodnota se nemění. | Zbytkové riziko R04 platí i zde: po změně dřívějšího parametru se může jediný kandidát najít na jiné ploše se stejným směrem. Pojistku (kontrolní údaje plochy) navrhne P2.2. |
| **G8 Rozsah schválení** | Schválit G1–G7 a matici Q01–Q24. **P2.2 formát, P2.3 výpočet, P2.4 okno a AI, P2.5 přijetí** se předkládají zvlášť. | Žádná nová závislost: potřebná funkce `BRepOffset_MakeOffset` je v instalovaném jádru OCCT 8.0.1. Nový typ prvku bude znamenat formát 23 – rozhodne P2.2. |

Více těles ve smyslu D1 z P1.1: úprava změní jen těleso, kterému plocha patří, ostatní
zůstanou beze změny a počet těles se nesmí změnit.

## 3. Co potvrzuje současný kód

- Zaoblení, sražení a skořepina mění hotový díl stejnou cestou
  (`_modification_input` → výpočet → `_accept_modification` → `check_modification`).
  Přímá úprava do tohoto vzoru zapadá; nový typ musí patřit do `VOLUME_FEATURES`.
- Plochy se hledají významem v `selectors.find_face` (`at`, `normal`, `type`, `radius`);
  rovnocenné kandidáty odmítá od P1.3. Výběr kliknutím popisuje `picking.face_reference`.
- Výběr z 3D umí dnes `SELECTION_FEATURES = ("fillet", "chamfer", "sketch", "shell", "hole")`
  v `session.py`; nový prvek tam patří také (P2.4).
- Pole a zrcadlení opakují jen `REPEATABLE_FEATURES` – zaoblení ani skořepina v nich
  nejsou, přímá úprava také ne.
- Otisk NDT studie se počítá z receptu (`study.part_fingerprint`), takže jakýkoli nový
  prvek studii označí jako zastaralou bez další změny kódu NDT.
- `document.VERSION = 22`; nový typ prvku vyžaduje zvýšení verze a načtení starých souborů.

## 4. Průzkum jádra

Jednorázový průzkum, **ne implementované regrese**: [`p2-1-pruzkum-jadra.py`](p2-1-pruzkum-jadra.py),
cloud Linux, Python 3.13.17, build123d 0.13.0, cadquery-ocp 8.0.1.1.0. Použitá funkce:
[`BRepOffset_MakeOffset`](https://dev.opencascade.org/doc/refman/html/class_b_rep_offset___make_offset.html)
s nulovým posunem celku a `SetOffsetOnFace` pro vybranou plochu, spojení sousedů
průsečíkem (`GeomAbs_Intersection`). Očekávání jsou ručně spočítaná ze vzorců.

| Případ | Očekávání [mm³] | Výsledek jádra | Závěr |
|---|---|---|---|
| K1 kvádr 40×30×20, horní plocha +5 | 30 000 | 30 000, rozměr 40×30×25 | shoda |
| K2 kvádr, horní plocha −5 | 18 000 | 18 000 | shoda |
| K3 / K4 kvádr, horní −20 / −25 | odmítnout | jádro odmítlo | správně |
| K5 kvádr, horní +5 a pravá +2 najednou | 31 500 | 31 500, 42×30×25 | shoda |
| D1 / D2 průchozí díra Ø10 → Ø8 / Ø12 | 22 994,6904 / 21 738,0533 | totéž | shoda |
| D3 díra Ø10 → Ø32 (prorazí stěnu) | odmítnout | jádro odmítlo | správně |
| D4 slepá díra Ø10 hl. 8 → Ø12 | 23 095,2213 | totéž | shoda |
| D5 díra u kraje Ø10 → Ø14 | odmítnout | jádro odmítlo | správně |
| D6 čep Ø10 → Ø12 | 25 130,9734 | totéž | shoda |
| S1 plocha s čepem +5 | 30 392,6991 (čep zkrácen o 5) | totéž | shoda |
| D7 křížené díry, svislá Ø10 → Ø8 | odmítnout | jádro odmítlo | správně |
| D8 díra se sražením 1 mm, Ø10 → Ø11 | 22 094,8859 | totéž | shoda |
| D9 díra se sražením, Ø10 → Ø12 | odmítnout (sražení zanikne) | **platný tvar se sražením o výměře 0** | zachytí jen G5 |
| D10 díra se zaoblením R1, Ø10 → Ø11 | odmítnout (tečnost) | **platný tvar, objem 21 544,9614** | zachytí jen G6 |
| R1 lichoběžník, horní +5 | 20 625 | totéž | shoda, šikmé boky se prodloužily |
| R2 lichoběžník, šikmý bok +3 | 20 012,4612 | totéž | shoda |
| R3 svislé hrany R3, horní +5 | 29 806,8583 | totéž | shoda |
| R4 horní hrany R3, horní +5 | odmítnout | jádro odmítlo | správně, G6 by odmítl předem |
| R5 / R6 / R7 schod, nižší plocha +3 / +10 / +15 | 19 800 / odmítnout / odmítnout | 19 800 / odmítlo / odmítlo | správně |
| R8 / R9 dno kapsy +2 / −3 | 23 400 / 22 400 | totéž | shoda |
| R10 / R11 U tvar, vnitřní stěna +10 / +22 | 25 500 / odmítnout | 25 500 / odmítlo | správně |
| P1 `priruba.json`, jedna díra Ø18 → Ø20 | 310 018,1226 | totéž, ostatní tři díry beze změny | shoda |
| P2 příruba, spodní plocha −3 | 259 055,9920 | totéž | shoda |
| P3 příruba, horní plocha +3 | 356 282,0015 (sražení se zvětší) | totéž | shoda |
| P4 příruba, horní plocha −3 | odmítnout (sražení by zaniklo) | jádro odmítlo | správně |
| X1 plocha z jiného tělesa | odmítnout | **hotovo bez chyby, díl beze změny** | tichý nezdar – zachytí G5 |

Všechny úspěšné případy se shodují se vzorcem do 10⁻¹⁰ mm³ a trvaly 6–31 ms.
Navíc s kvádrem po posunu horní plochy o +5 dalo navazující zaoblení horních hran R2
platné těleso výšky 25 mm a navazující díra Ø6 objem přesně podle vzorce
(navazující prvky s upraveným dílem pracují; objem zaoblení se vzorcem neověřoval). Shoda objemu sama nedokazuje správný tvar; matice níže proto
vyžaduje i rozměry a polohu upravené plochy.

**Zjištěné pasti pro implementaci:** vstupem musí být jednotlivé těleso (`TopoDS_Solid`)
– se složeninou jádro vrátí jen skořápku; `Part(TopoDS_Solid)` hlásí objem 0, výsledek
se musí obalit složeninou; plocha, která k tělesu nepatří, se tiše ignoruje (X1);
nulový posun hlásí jádro jako chybu `NullOffset`, aplikace ho má odmítnout dřív.

## 5. Budoucí matice přijetí Q01–Q24

**Specifikace testů pro implementaci P2.3–P2.5, ne přidané testy.** U každého odmítnutí
ověřit českou zprávu, nezměněný díl, kontext a přeskočení následných prvků (jako P1).

| Č. | Případ | Očekávání |
|---|---|---|
| Q01 | Kvádr, horní plocha +5 / −5 | 40×30×25 / 40×30×15; objem podle vzorce; plocha v z = 15 / 5 |
| Q02 | Kvádr, horní −20 a −25 | odmítnout, díl beze změny |
| Q03 | Průchozí díra Ø10 → Ø8 a Ø12 | objem podle vzorce, válec na stejné ose s novým poloměrem |
| Q04 | Slepá díra Ø10 hl. 8 → Ø12 | hloubka 8 zachovaná, objem podle vzorce |
| Q05 | Čep Ø10 → Ø12 | objem a průměr podle vzorce, výška čepu beze změny |
| Q06 | Díra, která by prorazila stěnu (D3, D5) | odmítnout |
| Q07 | Šikmá plocha lichoběžníku +3 | objem = původní + 3 × výměra plochy; sousedé zůstávají v původních rovinách |
| Q08 | Plocha se svislými zaobleními (R3) | objem podle poměru výšek, poloměry zaoblení beze změny |
| Q09 | Plocha nebo díra s tečným sousedem (R4, D10) | odmítnout předem s důvodem „navazuje zaoblení“ |
| Q10 | Díra se sražením Ø11 / Ø12 | Ø11 objem podle vzorce; Ø12 odmítnout (zánik sražení) |
| Q11 | Schod +3 / +10 / +15 | +3 objem podle vzorce; ostatní odmítnout |
| Q12 | Dno kapsy +2 / −3 | hloubka 3 / 8 mm, objem podle vzorce |
| Q13 | U tvar +10 / +22 | +10 mezera 5 mm; +22 odmítnout |
| Q14 | Plocha s čepem +5 | čep zůstane na místě, zkrácený o 5 mm |
| Q15 | Příruba: jedna díra Ø18 → Ø20 | jen kliknutá díra Ø20, tři zbylé Ø18, objem podle vzorce |
| Q16 | Příruba: spodní −3 a horní +3 / −3 | tloušťka 15 a 21 mm podle vzorce; horní −3 odmítnout |
| Q17 | Posun 0, stejný průměr, nekonečná nebo neplatná hodnota | odmítnout předem, „úprava nic nemění“ / chyba hodnoty |
| Q18 | Plocha, která k dílu nepatří (X1) | odmítnout |
| Q19 | Kužel, koule, plocha tažení/přechodu, vymodelovaný závit | odmítnout předem s českým důvodem |
| Q20 | Dva oddělené solidy, úprava jednoho | druhé těleso beze změny, počet 2 → 2 |
| Q21 | Prvek za úpravou (zaoblení, díra) | počítá s upraveným dílem, objem podle vzorce |
| Q22 | Změna parametru před úpravou | plocha se najde znovu, nebo nejednoznačnost = česká chyba; nic se nehádá |
| Q23 | Zpět, Znovu, uložit a otevřít | stejný výsledek; staré soubory se otevřou beze změny |
| Q24 | NDT studie a uložené měření | studie zastará; měření na posunuté ploše ukáže novou hodnotu |

Q22–Q24 závisí na zápisu z P2.2 a ověří se v P2.5 i na Windows a Macu.

## 6. Navazující kroky

1. **P2.2 Zápis** – podoba nového prvku v receptu, odkaz na plochu a kontrolní údaje proti
   R04, formát 23 a načtení starších verzí. Samostatné schválení.
2. **P2.3 Výpočet** – prvek v jádře podle G1–G7 s náhledem na kopii, testy Q01–Q22.
3. **P2.4 Ovládání** – klik na plochu → hodnota → náhled → Použít / Zrušit; stejné pravidlo
   pro nástroj AI.
4. **P2.5 Přijetí** – Q01–Q24, oba systémy, stažené balíčky, ruční zkouška autora.

Schválení tohoto návrhu **nespouští implementaci ani nový formát** a návrhový PR se
neslučuje do main bez výslovného souhlasu autora. Odborná NDT-17 a otevřená rizika R03,
R04/P16 a R12 se tímto návrhem neřeší.
