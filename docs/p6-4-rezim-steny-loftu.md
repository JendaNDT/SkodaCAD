# P6.3 — výslovný význam stěny dutého loftu

31. 10. 2026, základ `814893a` (PR #72). Autor potvrdil implementaci volby
„Kolmo ke stěně“ / „V rovinách skic“. Navazuje na
[průzkum a jeho meze](p6-3-skorepiny-overeni-a-navrh.md).

## Zápis a kompatibilita

Prvek `loft` má nepovinné pole `wall_mode`:

- `normal`: `wall` je velikost vnitřního 3D offsetu. Nepřechází na 2D postup.
- `sections`: každý profil se zmenší 2D offsetem o `wall`; vnitřní loft se odečte.
  Kolmo ke šikmému plášti může být stěna tenčí.
- Chybějící klíč zachovává původní algoritmus, jeho pořadí i objemovou pojistku.
  `null`, prázdný řetězec a jiné hodnoty nejsou platný explicitní režim.

Pole vyžaduje **formát 33**, i když právě není zadaná stěna. Starší číslo verze
s tímto polem se odmítá, aby jiná aplikace režim tiše neignorovala. Čtení podporuje
verze 1–33. Díly bez nového pole zachovávají verze 24–32 podle dosavadních pravidel;
sestavy nadále 29–31. Geometrie starých receptů ani jejich pole se při načtení nemění.
Žádná nová závislost a žádná změna měřidla NDT.

## Výpočet a ovládání

Nový loft ze session/schématu nese `wall_mode: "normal"`. Formulář má dvě výslovné
volby. U starého receptu bez pole je navíc označen původní automatický postup;
úprava jiného pole zachová chybějící klíč. Volba nového režimu je běžná změna
session se Zpět/Znovu, zápisem a přepočtem v pomocném procesu.

Normálový režim používá pouze 3D offset s oběma otevřenými konci. Nezměněný,
neplatný nebo objemově poškozený výsledek se odmítá českou chybou, která poradí
výslovnou druhou volbu. Kontroly P1 vyžadují uzavřený kladný objem, úbytek materiálu
a zachování počtu těles. Tyto nutné podmínky nejsou univerzálním důkazem konstantní
tloušťky složitého povrchu; známé meze OCCT a zesílení rohů platí dál.

Navíc `loft_wall.check_normal_wall` ověří ve vzorcích zachovaný vnější povrch,
průchod oběma otvory, délku materiálem kolmo a odstup vnitřních ploch od vnějších.
Vnější plochy mají síť 3 × 3, vnitřní navíc zahrnují krajní parametry; pracovní
mez je `max(0,00002 mm, wall·10⁻⁶)`. Tím se zachytí i formálně platný obrácený
offset kužele při příliš velké stěně. Větší délka v zesíleném rohu není chyba.
Neověřitelná plocha vede k odmítnutí; vzorky stále nejsou důkazem globálního minima.

Režim v rovinách skic nepoužívá 3D offset. Vyžaduje právě jeden menší vnitřní profil
bez děr pro každý vnější profil, platné vnitřní těleso a objem odebraného materiálu
odpovídající celému vnitřnímu loftu. Rozpad profilu, neúčinný offset, vyčnívající
vnitřní loft nebo zánik tělesa končí chybou. Starý automatický postup se těchto
nových pravidel netýká, aby se nezměnily existující díly.

Regrese ověří analytické objemy a normálová měření válce, kužele, rovinných šikmých
boků a zaobleného průřezu; starou výsypku a oba výslovné režimy; chyby a zachování
historie; nové výchozí hodnoty, formulář bez nechtěné konverze, verze, uložení,
worker a self-test balíčku. Výsledky úplných sad a místního okna budou v PR.

Samostatný obecný přehled vzorkované tloušťky a globální dokazování offsetu nejsou
součástí této volby. Nejde o implementaci obecné opravy BSpline offsetů.

## Místní ověření

Na MacBooku Air M4 prošly cílené geometrické, formátové, session, worker a GUI
kontroly, Ruff a celý self-test sestavené aplikace (`VÝSLEDEK: OK`) včetně nového
formuláře a v33. Podpis místní `.app` prošel `codesign --verify --deep --strict`.
Skutečným oknem prošlo přepnutí normálového režimu na roviny skic, Zpět/Znovu,
uložení a nové otevření téhož souboru přes dialog. Okno pak ukázalo uloženou volbu
„V rovinách skic“ a objem 32 233 mm³. Použit byl vlastní testovací profil a kopie
ukázky; přejímka autorského dílu tím není nahrazená. Evidence je místně v
`out/p6-wall-mode/`, úplné počty a kontroly obou systémů se předávají v PR.
