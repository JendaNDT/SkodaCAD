# P6.7 – řízený obdélníkový přechod

Implementace z 31. 10. 2026 navazuje na [ověřený průzkum P6.6](p6-6-vodici-krivky-overeni-a-navrh.md).
Používá stávající build123d 0.13.0 / OCCT 8.0.1, bez nové závislosti.

## Rozsah a ovládání

Dvě skici v rovinách XY s osami +X/+Y/+Z, druhá ve větší výšce. Každá má jeden
platný obdélník bez díry a bez zaoblení, se stranami rovnoběžnými s X/Y. Středy
mohou být posunuté. Koncové rohy se určují geometricky, nikoli pořadím hran jádra:
A (+X,+Y), B (−X,+Y), C (−X,−Y), D (+X,−Y).

Každé vodítko je kubická Bézierova křivka. Koncové body jsou rohy profilů,
dvě rukojeti jsou v H/3 a 2H/3, jejich X/Y se zadává jako odchylka od přímé
spojnice rohů. Všechna vodítka tedy sdílejí z = Ht. Při stejných odchylkách
obou rukojetí je skutečné vychýlení uprostřed 3/4 zadané odchylky.

Formulář má pevné řádky A–D, čtyři hodnoty na řádek a podporuje výrazy parametrů.
Kliknutí na označení řádku je pouze pohled: zvýrazní přesnou křivku a ukáže
čárkovaný řídicí polygon s dvěma rukojeťmi. A0/A1 apod. označují začátek/konec.
Výběr neoznačí dokument jako změněný. Úprava hodnoty jde přes `ModelSession`,
funguje Zpět/Znovu, uložení a otevření. Zastaralá nebo chybná vodítka se nezobrazují.
Přepočet používá stávající pomocný proces; viewer dostává jen čísla pro kreslení.

Výsledkem je plné těleso s operací new/add/cut, použitelné i jako zdroj pole.
Mezilehlé řezy jsou konvexní čtyřúhelníky, při nesouměrných vodítkách obecně
nejsou obdélníkové. Kruhy, šikmé profily, zaoblení, díry a duté stěny jsou odmítnuté.

## Formát 34

```json
{"id":"prechod","type":"guided_loft","sketches":["dole","nahore"],
 "operation":"new","guides":[
   {"corner":{"x":1,"y":1},"controls":[[0,0],[0,0]]},
   {"corner":{"x":-1,"y":1},"controls":[[0,0],[0,0]]},
   {"corner":{"x":-1,"y":-1},"controls":[[0,0],[0,0]]},
   {"corner":{"x":1,"y":-1},"controls":[[0,0],[0,0]]}
 ]}
```

Čtyři rohy musí být různé, znaménka celočíselná ±1; pořadí záznamů není identita.
Každá rukojeť je dvojice konečných čísel nebo výrazů. Starší deklarovaná verze
s tímto prvkem se odmítne; běžné staré modely dál zapisují svou potřebnou verzi
24–33. Formát sestav se nemění. Klíče wall, wall_mode a ruled nejsou dovolené.

## Geometrie a odmítnutí nejasných případů

Čtyři plochy vzniknou přímo z dvojic kubických vodítek jako Bézierovy plochy
stupně 1 × 3. V každé výšce spojují sousední vodítka přímé úsečky. Čela se
znovu vytvoří z čísel; sešívání nikdy nepoužívá přijaté sdílené plochy skic.

Před vytvořením tělesa se z rozdílů sousedních vodítek sestaví čtyři polynomy
orientovaných vektorových součinů stupně šest. Kladnost všech čtyř v celém [0,1]
zaručuje striktně konvexní nezborcený čtyřúhelník. Rozdíly se normalizují největší
absolutní složkou S; koeficienty se přijmou pouze nad rezervou
max(10⁻¹⁰, (10⁻⁶ mm / S)²). Smíšené meze se půlí de Casteljauovým algoritmem,
nejvýše do hloubky 18 a 4096 uzlů na součin. Záporná nebo neprůkazná mez znamená
odmítnutí. Vzorkování nenahrazuje tuto kontrolu: test zahrnuje zúžení mezi
pevně rozmístěnými kontrolními řezy.

Základem je vlastnost konvexního obalu Bernsteinovy báze
([MIT, Bézier curves](https://web.mit.edu/hyperbook/Patrikalakis-Maekawa-Cho/node9.html)).
Použití této vlastnosti na orientované součiny je náš postup. Výpočet používá
IEEE double s rezervou, nikoli formálně zaokrouhlovanou intervalovou aritmetiku.
Velmi úzké či numericky špatně podmíněné případy se mohou konzervativně odmítnout.
Profily a výška musí přesáhnout 10⁻⁵ mm; příliš velké souřadnice se odmítnou,
pokud 16 ULP dosáhne geometrické tolerance 10⁻⁶ mm. Výpočet probíhá relativně
ke středu dolního čela, aby velký posun neznehodnotil integrál plochy.

Po sešití se vyžaduje jeden platný solid dle P1. Jeho objem se porovná s nezávislým
integrálem průřezů z Bernsteinových koeficientů (mez max(2×10⁻⁵ mm³, V×10⁻⁸)).
Na finálních plochách se ověří 20 bodů vodítek a 36 bodů vnitřku pláště s mezí
10⁻⁶ mm. Tyto vzorky kontrolují výsledek jádra, nejsou důkazem konvexity.
Při selhání není náhradní geometrie; poslední úspěšný stav přepočtu zůstane zachovaný.

## Reference a ověření

Příklad `examples/rizeny_prechod.json`: čela 40 × 30 → 24 × 18 mm, H = 60 mm.
Souměrné skutečné vyboulení Bx = 7 a By = 5 mm se zadává rukojeťmi ±4Bx/3,
±4By/3. Poloviční šířky v řezu jsou

a(t) = 20 − 8t + 4Bx·t(1−t), b(t) = 15 − 6t + 4By·t(1−t).

V = 4H ∫₀¹ a(t)b(t) dt = **77 760 mm³**, bez vyboulení **47 040 mm³**.
Testy používají nezávislý integrál v mocninné bázi, přesné řezy a body konečného
pláště. Dále pokrývají posuny, asymetrii, pořadí záznamů, konvexitu, křížení,
vlastnictví vstupů, new/add/cut, pole, následnou díru, worker, historii, staré verze
a STEP zpět do jádra. Offscreen GUI ověřuje formulář i zotavení z chybného tvaru;
self-test zabalené aplikace provede úpravu rukojeti, Zpět/Znovu, zápis v34,
opětovné otevření, STEP a kreslení vodítek. Konkrétní výsledky běhů jsou v PR.
