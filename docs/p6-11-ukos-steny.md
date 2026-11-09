# P6.11 – Úkos stěn: průzkum jádra a návrh rozsahu

*Datum 9. 11. 2026. Autor na otázku „Kterým směrem má P6 pokračovat?“ vybral **Úkos stěn**
(všechny tři položky tabulky [P6.1](p6-1-vyber-operaci.md) jsou hotové a vydané).
Tento dokument zaznamenává průzkum a rozhodnutí před implementací; výsledky kontrol
implementace jsou v PR.*

## K čemu je úkos

Svislé stěny dílu se nakloní o malý úhel (typicky 1–5°) kolem **neutrální roviny**: v ní se
rozměr nemění, nad a pod ní se stěna odklání. Díl se pak dá vytáhnout z formy (odlitek,
vstřikování) a krabičky a kryty se líp tisknou a sundávají z podložky. V aplikaci žádný
prvek nic podobného nedělá a nejde to obejít zaoblením ani posunem plochy.

## Průzkum jádra

Spustitelný [`p6-11-pruzkum-ukosu.py`](p6-11-pruzkum-ukosu.py) (Python 3.12, build123d 0.13.0,
OCP 8.0.1, výsledky do `out/p6-11-pruzkum-ukosu.json`) volá `BRepOffsetAPI_DraftAngle`.
Každý případ má **nezávislý analytický objem** (číselná integrace průřezu po výšce):

| Případ | Výsledek | Shoda s analytickým objemem |
|---|---|---|
| K1 kvádr 40×30×20, 5°, neutrální dno, tažení +Z | horní plocha se zmenší, dno beze změny | do 10⁻⁶ mm³ |
| K1 totéž s tažením −Z | horní hrana 43,5 mm (stěna se rozšíří) | do 10⁻⁶ mm³ |
| K2 neutrální rovina uprostřed (z = 10) | rozměr v rovině řezu se nemění | do 10⁻⁵ mm³ |
| K3 záporný úhel (−5°) | totéž co opačný směr tažení | do 10⁻⁶ mm³ |
| K4 jen dvě protilehlé stěny | zkosí se jen rozměr v X | přesně |
| K5 válec Ø20×30, 3° | komolý kužel | do 10⁻⁶ mm³ |
| K6 kvádr se zaoblenými svislými hranami R4 | **jedna zadaná stěna zkosí celý tečný řetěz** (8 ploch) | do 10⁻⁶ mm³ |
| K7 kapsa 30×20×10 v bloku, neutrální = horní plocha | kapsa se zužuje ke dnu | přesně |
| K8 stupňovitý díl, úkos jen horního hranolu | stupeň zůstává | přesně |
| G1 vodorovný směr tažení (+X) | funguje i mimo osu Z | do 10⁻⁵ mm³ |
| F1 úhel 80° | jádro hlásí `IsDone = False` | – |
| F2 vodorovná plocha vůči tažení +Z | jádro hlásí `AddDone = False` | – |
| F3 neutrální rovina daleko mimo díl | platí, jen se rozměry mění víc | do 10⁻⁵ mm³ |
| K9 kapsa se **zaobleným dnem** | stěna se zkosit nedá (`AddDone = False`) – řetěz zahrnuje zaoblení dna | – |
| K10 stěna s průchozím otvorem Ø6 | platné těleso | – |

Zjištění důležitá pro návrh:

- **Znaménko.** Kladný úhel nakloní vnější normálu plochy **směrem ke směru tažení**.
  U vnější stěny to znamená, že se zúží směrem k tažení, u kapsy se kapsa rozšíří směrem
  k tažení. Opačné chování dá záporný úhel (nebo opačný směr tažení). Okno to ukáže v náhledu.
- **Tečný řetěz.** Jádro šíří úkos po tečně navazujících rovinných, válcových a kuželových
  plochách. Zadaná stěna tedy zkosí i zaoblené svislé rohy. Nedá se zakázat, ale dá se
  **ověřit**: kontrolu sklonu provádíme na všech zadaných plochách výsledku.
- **Zaoblení dna** stěny kapsy brání: vodorovné zaoblení patří do tečného řetězce a nejde
  zkosit. Postup je stejný jako ve strojírenských CADech: **úkos před zaoblením** dna.
- **Plochy jiného druhu** než rovina, válec a kužel jádro odmítá (nic se neudělá).
- Jádro **nevrací** seznam změněných ploch přes `Modified` (je prázdný); funguje
  `ModifiedShape` a nalezení výsledné plochy přes `is_same` v tělese. Orientace normály
  se čte až z plochy výsledného tělesa (`ModifiedShape` samo má orientaci obrácenou).

## Rozhodnutí D1–D9 (rozsah první verze)

- **D1** Nový prvek `draft` („Úkos stěn“), formát **35** jen s tímto prvkem. Díly bez něj
  zůstávají ve verzích 24–34; starší aplikace se na novém prvku nezmýlí, protože o něm neví.
- **D2** `faces`: neprázdný seznam odkazů na plochy `{at, normal, type, origin}` stejné jako
  u přímých úprav (významem, ne indexem), `type` je `plane`, `cylinder` nebo `cone`; `origin`
  je pojistka původu plochy (P1.3, P2.2). Dvě shodné plochy v seznamu se odmítnou.
- **D3** `pull`: směr tažení `+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z` v osách dílu.
- **D4** `angle`: úhel ve stupních, nenulový, `|angle| ≤ 30°` (výraz s parametry). Znaménko
  podle zjištění výše. Příliš strmý úhel jádro odmítne a my to řekneme česky.
- **D5** `neutral`: neutrální rovina kolmá na směr tažení. Buď **číslo** (souřadnice v mm
  podél osy tažení, výraz), nebo odkaz na **rovinnou plochu** dílu (stejné pojistky; její
  normála musí být rovnoběžná s osou tažení).
- **D6** Vstup i výsledek prochází společnou kontrolou P1 (`_modification_input`,
  `_accept_modification`): platné jedno těleso, žádné prázdné objemy, nezměněný počet těles.
- **D7** Po výpočtu se **ověří sklon každé zadané plochy**: vnější normála výsledné plochy
  má složku ve směru tažení rovnou `sin(angle)` (tolerance 10⁻⁶). Neprošlé = chyba, ne tiché
  přijetí. Ověření přes výsledek, nikoli podle „jádro neohlásilo chybu“.
- **D8** Chyby česky a s radou: plocha jiného druhu, plocha kolmá na směr tažení, tečný
  řetěz s plochou, kterou nejde zkosit („zaoblení dna udělej až po úkosu“), příliš velký
  úhel, neutrální rovina nekolmá na tažení, plocha už na dílu není.
- **D9** Nejde opakovat polem ani zrcadlením (mění celý díl jako zaoblení). Okno
  (výběr ploch ve 3D, formulář, náhled, značky) je samostatný krok po jádru a zápisu.

Nepřidává se závislost ani náhradní aproximace. Meze: tečný řetěz se zkosí vcelku, výběrové
plochy typu B-spline nejdou, kužel se dál zkosí jen kolem své osy podle pravidel jádra.
