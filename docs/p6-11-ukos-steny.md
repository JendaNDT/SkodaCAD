# P6.11 – Úkos stěn: průzkum jádra a návrh rozsahu

*Datum 9. 11. 2026. Autor na otázku „Kterým směrem má P6 pokračovat?“ vybral **Úkos stěn**
(všechny tři položky tabulky [P6.1](p6-1-vyber-operaci.md) jsou hotové a vydané).
Dokument zaznamenává průzkum a rozhodnutí před implementací a na konci provedení (P6.12);
výsledky kontrol jsou v PR.*

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
  u přímých úprav (významem, ne indexem), `type` je `plane` nebo `cylinder` (kužel první verze
  nezná); `origin` je pojistka původu plochy (P1.3, P2.2). Dvě shodné plochy v seznamu se
  odmítnou. Válec musí mít osu rovnoběžnou se směrem tažení.
- **D3** `pull`: směr tažení `+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z` v osách dílu.
- **D4** `angle`: úhel ve stupních, nenulový, `|angle| ≤ 30°` (výraz s parametry). Znaménko
  podle zjištění výše. Úhel je **absolutní**: výsledný sklon plochy vůči směru tažení je právě
  zadaný, i když už byla nakloněná (zjištěno měřením, viz Provedení). Příliš strmý úhel jádro
  odmítne a my to řekneme česky.
- **D5** `neutral`: neutrální rovina kolmá na směr tažení. Buď **číslo** (souřadnice v mm
  podél osy tažení, výraz), nebo odkaz na **rovinnou plochu** dílu (stejné pojistky; její
  normála musí být rovnoběžná s osou tažení).
- **D6** Vstup i výsledek prochází společnou kontrolou P1 (`_modification_input`,
  `_accept_modification`): platné jedno těleso, žádné prázdné objemy, nezměněný počet těles.
- **D7** Po výpočtu se **ověří sklon každé zadané plochy**: vnější normála výsledné plochy
  má složku ve směru tažení rovnou `sin(angle)` (tolerance 10⁻⁶). Neprošlé = chyba, ne tiché
  přijetí. Ověření přes výsledek, nikoli podle „jádro neohlásilo chybu“. Výsledná plocha se
  najde přes `ModifiedShape` + `is_same` v hotovém tělese.
- **D8** Chyby česky a s radou: plocha jiného druhu, plocha kolmá na směr tažení, tečný
  řetěz s plochou, kterou nejde zkosit („zaoblení dna udělej až po úkosu“), příliš velký
  úhel, neutrální rovina nekolmá na tažení, plocha už na dílu není.
- **D9** Nejde opakovat polem ani zrcadlením (mění celý díl jako zaoblení). Okno
  (výběr ploch ve 3D, formulář, náhled, značky) je samostatný krok po jádru a zápisu.

Nepřidává se závislost ani náhradní aproximace. Meze: tečný řetěz se zkosí vcelku, výběrové
plochy typu B-spline nejdou, kužel se dál zkosí jen kolem své osy podle pravidel jádra.

## Provedení (P6.12)

- `draft.py` (služba), prvek `draft` ve `features.py`, formát **35** jen s tímto prvkem
  (`document.py`, kontrola struktury při načtení), schéma s polem směru, úhlu a neutrální
  roviny, ukázka [`examples/ukos_krabicka.json`](../examples/ukos_krabicka.json), README.
- **Měření při implementaci:** kontrola sklonu výsledku zachytila, že jádro nastavuje úhel
  **absolutně** (plocha nakloněná o −4° a znovu zkosená o +2° skončí na +2°, ne na −2°). Původní
  očekávání „přičíst úhel“ bylo špatně; opraveno podle měření, nikoli povolením tolerance.
- **Výběr ve 3D:** nabídka *Úkos vybraných stěn* (jen roviny a válce, bez hran) vytvoří prvek
  s odkazy a původem ploch; neutrální rovina se nastaví na začátek vybraných stěn proti směru
  tažení (u dna při tažení nahoru). Náhled i potvrzení jedním krokem jsou stejné jako u ostatních
  prvků z výběru. Úpravy: *Přidat vybrané stěny do…* přidá další stěny, zvýraznění ukáže plochy
  prvku.
- Neutrální rovina zadaná **odkazem na plochu** funguje v souboru a v AI; formulář ji ukáže jen
  jako „rovinná plocha dílu“ a při úpravě zachová.
- Testy: `tests/test_draft.py` (objem podle vzorců, změřený sklon, kapsa, tečný řetěz, válec,
  neutrální plocha, odmítnutí, pojistky, formát 35, session), `tests/test_gui.py` (příkaz z výběru,
  náhled, potvrzení, Zpět) a nativní self-test „Úkos stěn“.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_draft.py` (30) | objem podle vzorce (čtyři stěny, opačný směr, neutrální rovina uprostřed / plochou, dvě stěny, válec → kužel, kapsa, tečný řetěz se zaoblenými rohy), změřený sklon ploch, odmítnutí (úhel, vodorovná plocha, duplicita, původ, neutrální plocha, příliš strmý úhel, zaoblení dna, válec s osou mimo tažení, koule), absolutní úhel, formát 35, ukázka, session (výběr, přidání stěn, zvýraznění) |
| `tests/test_gui.py` (+2) | příkaz *Úkos vybraných stěn* ze skutečného výběru: náhled bez změny modelu, potvrzení = jeden krok, Zpět; příkaz jen pro roviny a válce bez hran |
| úplná sada `pytest -q` (Linux) | 3 153 úspěšných; 6 testů předpokládalo „nejnovější verze formátu je 34“ – upraveny na 35 a znovu úspěšné (210 v dotčených souborech); `ruff check src tests` bez nálezů |
| nativní self-test (Linux Xvfb, skutečné 3D) | „Úkos stěn“: ukázka, objem 28 556,588413 mm³ podle vzorce, změna úhlu, Zpět, zvýraznění čtyř stěn, uložení v35; celý self-test OK |

Snímky okna (Linux Xvfb, 1440 × 900):
[hotový úkos – karta prvku](p6-12-snimky/ukos-hotovy-karta-prvku.png),
[nový úkos z vybraných stěn – náhled](p6-12-snimky/ukos-nahled-z-vyberu.png),
[zvýraznění stěn prvku](p6-12-snimky/ukos-zvyrazneni-ploch.png).

## Meze

- Kužel jako zadaná plocha, válec s osou mimo směr tažení, jiné druhy ploch a směr tažení mimo
  osy dílu nejsou podporované.
- Úkos zkosí vždy celý tečný řetěz navazujících ploch; plocha s navazujícím vodorovným
  zaoblením (třeba dno kapsy) nejde, úkos patří před zaoblení.
- Neutrální rovina se ani při změně dílu sama nepřesouvá (číslo nebo výraz s parametry; odkaz
  na plochu sleduje její polohu).
- Prvek nelze opakovat polem ani zrcadlením. Nejde o výrobní výkresový úkos podle normy.
