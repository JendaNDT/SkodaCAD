# P6.16 – Proměnné zaoblení víc hran a přechod s kruhy: průzkum a uzavření P6

*Datum 10. 11. 2026. Pokyn autora: dodělat P6 kompletně (zbývající kandidáti z
[P6.1](p6-1-vyber-operaci.md)). Spustitelný průzkum:
[`p6-16-pruzkum-zaobleni-vice-hran.py`](p6-16-pruzkum-zaobleni-vice-hran.py) (build123d 0.13.0,
OCP 8.0.1). Každý případ má nezávislý analytický objem.*

## 1. Proměnné zaoblení víc hran

Dnešní operace umí **jednu** přímou pravoúhlou hranu. Zkoušeno: opakování téže operace na
víc hranách bloku 60 × 40 × 20 (svislé hrany, R2 → R6, délka 20, odebraný objem jedné hrany
podle vzorce 74,395303 mm³).

| Případ | Výsledek |
|---|---|
| Čtyři nezávislé svislé hrany po sobě | odebráno 297,581214 mm³, **chyba 3·10⁻⁷ mm³** proti vzorci, platné těleso, 10 ploch (6 + 4) |
| Střídavě R2 → R6 a R6 → R2 | stejný objem, chyba 3·10⁻⁷ mm³ |
| Jedna vodorovná hrana (délka 60) | přijata, objem podle vzorce |
| Zaoblení se dotýkají (deska 12 mm, R6 + R6) | **odmítnuto** (změna ploch) |
| Zaoblení se překrývají (deska 11 mm) | **odmítnuto** (zásah do jiného detailu) |
| Vodorovná a pak svislá hrana u téhož vrcholu | **odmítnuto** (konec hrany není uzavřen kolmou plochou) |
| Konstantní zaoblení R1 na obvodu horní i spodní plochy po čtyřech svislých | platné těleso (OCCT zvládne řetěz přímek a oblouků) |
| **Skořepina 2 mm po zaoblení** | **neplatné těleso** (plochy zaoblení OCCT neodsadí); prvek *Skořepina* to odmítne |
| Zaoblení na hotové skořepině | R2 → R6 přijato (vzorec přesně), R2 → R7 a R8 **odmítnuto** (řezací těleso zasáhne dutinu) |
| Čas čtyř hran | 0,16 s |

**Zjištění.** Jádro zvládne víc *nezávislých* hran přesně a atomicky. Hrany, které se stýkají
v rohu, neumí: OCCT nemá přesný průběh proměnného poloměru (viz [P6.2](p6-2-promenne-zaobleni.md)
– čtvrtina hrany vychází 2,79 místo 3 mm) a vlastní konstrukce rohové záplaty by byla
aproximace, kterou projekt záměrně nedělá.

**Rozhodnutí D1: nový prvek pro víc hran se nedělá.** Nezávislé hrany lze dnes zaoblit
jedním prvkem na hranu a poloměry svázat parametry (`R1`, `R2` jsou výrazy), takže změna jedné
hodnoty přepočte všechny hrany; výsledek je přesně stejný. Víc hran v jednom prvku by přineslo
jen pohodlí výběru a stálo by změnu formátu (37), výběru ve 3D, formuláře a značek konců.
Když se ukáže, že je pohodlí potřeba, jde o samostatné rozšíření bez změny geometrie.

**Rozhodnutí D2: stýkající se hrany (rohy) zůstávají trvalou mezí.** Odmítají se s českým
vysvětlením (stávající kontrola konců hrany).

**Praktická pravidla pro tvůj postup (krabičky):**
1. **Skořepinu dělej před proměnným zaoblením**, ne po něm (po zaoblení je neplatná).
2. Zaoblení na hotové skořepině musí zůstat v rohu: poloměr R vyčnívá do stěny o R·(√2 − 1)
   po úhlopříčce, takže pro stěnu 2 mm vychází nejvýš R ≈ 6,8 (R6 projde, R7 ne).
3. Konstantní zaoblení horního obvodu po proměnných svislých zaobleních funguje.

## 2. Přechod s kruhy

[Průzkum vodicích křivek P6.6](p6-6-vodici-krivky-overeni-a-navrh.md) ukázal: dva kruhové
profily s vodítky **nedají kruhový průřez uprostřed** (poloměr 23,54 místo 25 mm, zlom až
15,6°), kdežto s třetím, prostředním kruhem plocha sedí na analytický objem (odchylka 2·10⁻⁸ mm).

Ověřeno v aplikaci: **stávající prvek *Přechod* se třemi kruhovými skicami** (Ø40 – Ø50 – Ø40
po 30 mm) dává objem **103 044,2393 mm³** proti analytické reference 103 044,2390 mm³
(rozdíl 3·10⁻⁴ mm³, platné těleso). Kruhový přechod s řízeným tvarem tedy už existuje
a řídí se **prostřední skicou**.

**Rozhodnutí D3: řízený přechod s kruhy se nedělá.** Vodítka u dvou kruhů kruhový průřez
nezaručí, a bez této záruky by operace neodpovídala pravidlu „žádná tichá aproximace“.
Postup pro uživatele: použít *Přechod* s víc skicami.

## 3. Uzavření P6

Hotové a vydané: proměnné zaoblení jedné hrany (v32), výslovné režimy stěny loftu (v33),
CAD přehled stěny, řízený obdélníkový přechod s rukojetmi (v34), úkos stěn (v35), žebro a
sloupek (v36). Zbylé kandidáty zapisuji jako **meze s důvodem**, ne jako nedodělky:
rohy se stýkajícími hranami a řízený kruhový přechod nemají v současném jádře přesné řešení.

Otevřené zůstává to, co nejde bez tebe: P6.4 přejímka na tvém dílu (přeskočena na tvůj
pokyn), a uvedené operace nejsou ověřené na tvém skutečném dílu.

## Ověření

| Kontrola | Výsledek |
|---|---|
| průzkum ([skript](p6-16-pruzkum-zaobleni-vice-hran.py)) | všechny případy výše, objemy podle vzorců |
| `tests/test_p6_limits.py` | čtyři hrany přesně, skořepina po zaoblení odmítnuta, zaoblení na skořepině R6 ano / R7 ne, tři kruhy proti analytické referenci |
