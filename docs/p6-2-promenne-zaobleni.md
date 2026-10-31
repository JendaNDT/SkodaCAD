# P6.2/P6.3 — lineární proměnné zaoblení

Datum: **31. 10. 2026**, výchozí `main` **3332c1f** (PR #70).
Navazuje na [výběr operací P6](p6-1-vyber-operaci.md) a pokyn autora „ok pokračuj“.

## Výsledek podrobnějšího průzkumu

Původní pokus správně ověřil konce R2/R6, nikoli průběh uvnitř hrany. Podrobnější
měření ve stejném OCP 8.0.1.1 ukázalo, že volání `Add(R1, R2, edge)` na kvádru
nedává přesně lineární průběh: ve čtvrtině hrany vychází **2,785714286 mm** místo
**3 mm**, ve třech čtvrtinách **5,214285714 mm** místo **5 mm**. Polovina i konce sedí.
Jde o naměřenou vlastnost tohoto případu, ne důkaz správnosti obecného zaoblení.

[API OCCT](https://occt3d.com/dev/doc/refman/html/class_b_rep_fillet_a_p_i___make_fillet.html)
popisuje lineární změnu. Zápis dvou koncových hodnot v
[implementaci OCCT 8.0.1](https://github.com/Open-Cascade-SAS/OCCT/blob/V8_0_1/src/ModelingAlgorithms/TKFillet/BRepFilletAPI/BRepFilletAPI_MakeFillet.cxx)
ale sám o sobě neověřuje geometrii mezi konci. Produkční funkce proto používá
jedinou explicitní konstrukci uvedenou níže; neslibuje obecnou náhradu za fillet OCCT.

## Přesná konstrukce a podporovaný rozsah

Podporuje **jednu přímou vnější vypouklou hranu**, dva pravoúhlé rovinné boky
a na obou koncích rovinnou plochu kolmou k hraně. Směr může být libovolný v prostoru.
Poloměry jsou kladné konečné hodnoty nebo výrazy; shodné hodnoty jsou přípustné.

Na každém konci vznikne uzavřený profil „čtverec minus čtvrtkruh“ se třemi hranami.
Přímkový loft mezi podobnými profily je řezací těleso. Kruhové řezy kolmé k původní
hraně mají poloměr **R(t) = R1 + t·(R2 − R1)**, kde `t` je podíl délky hrany.
Kruhové oblouky navazují na oba boky tečně. Nejde o triangulaci ani o náhradní
aproximaci po selhání jiné metody. Jádro stále pracuje s obvyklými numerickými tolerancemi.

Odebraný objem má nezávislý analytický vzorec:

`V = (1 − π/4) · délka / 3 · (R1² + R1·R2 + R2²)`.

Po výpočtu musí projít celá kontrola P1, zůstat počet těles, vzniknout právě jedna
nová plocha a úbytek objemu odpovídat vzorci do `max(εV z P1, 10⁻⁶·V)`.
Částečně vyčnívající řezací těleso nebo průnik s dutinou tuto kontrolu nesplní.
Nepřípustně velký či numericky nerozlišitelný řez se odmítá před konstrukcí.
Ostatní solidy dílu se přebírají beze změny.

Vstup předem odmítá křivku, vnitřní kout, úhel boků jiný než 90°, šikmé zakončení,
tečný řetězec a složitý koncový vrchol. Po výpočtu se odmítá i zánik plochy,
zásah do jiného detailu nebo neúplný/neplatný výsledek. Chyba nechává původní
geometrii v historii k opravě; navazující prvky se přeskočí a platí běžné blokování exportu.

## Ukládání: verze 32

Samostatný typ `variable_fillet` nemění význam stávajícího `fillet`.

| Pole | Význam |
|---|---|
| `edges` | stávající významový výběr, musí najít právě jednu hranu |
| `radius_start`, `radius_end` | R1 a R2 v mm; číslo nebo výraz s parametry |
| `direction` | uložený jednotkový vektor směru hrany, tři konečná čísla |
| `reverse` | nepovinný JSON boolean, výchozí `false`; prohodí začátek a konec |
| `origin` | id prvku, od kterého na nosné přímce v aktuálním místě výběru nepřetržitě existuje jedna hrana |
| `normals` | dvojice uložených jednotkových vnějších normál boků, bez významu jejich pořadí |

Směr se při prvním výběru určí tak, aby jeho největší složka byla kladná, a uloží
se. Přepočet řadí konce geometricky podle tohoto vektoru, nikoli pořadím vrcholů
v OCCT. Skutečná změna směru hrany, změna původu nebo boků vyžaduje nový výběr.
Samotná změna délky či R1/R2 směr nepřepíše. Pojistky se automaticky neopravují.

Díly s tímto typem se ukládají ve verzi **32**, včetně dílů s výkresem. Staré díly
zůstávají ve verzi 24–28, sestavy ve verzi 29–31. Čtení podporuje verze 1–32;
nový typ pod starším číslem verze se odmítá. Starší aplikace verzi 32 odmítne.
Žádná nová závislost. Pole a zrcadlení tento dokončovací prvek neopakují.

Pojistka omezuje záměny, ale neřeší historickou identitu libovolných geometricky
stejných kopií vytvořených stejným prvkem. Platí dosavadní meze významových odkazů P1.

## Ovládání a ověření

Výběr jedné hrany ve 3D → **Proměnné zaoblení vybrané hrany** → formulář R1/R2
a **Obrátit směr R1 → R2**. Zelené značky R1/R2 označují konce původní hrany.
Jde o pohled; jejich zobrazení ani výběr ve stromu nemění recept. Původ a směr
vyplňuje session při výběru, nevznikají neúplným vložením z obecné nabídky prvků.
Změny procházejí běžnou historií session včetně Zpět/Znovu a pomocného procesu.

Ukázka: [`promenne_zaobleni.json`](../examples/promenne_zaobleni.json), kvádr
40 × 30 × 20 mm, R2 → R6. Objem **23 925,604696567 mm³**; analyticky
23 925,604696644 mm³ (odchylka pod 10⁻⁶ mm³).

Regrese [`test_variable_fillet.py`](../tests/test_variable_fillet.py) kontrolují
objem podle vzorce, 30 bodů v řezech po celé délce a tečnost v pěti místech každého
styku s bokem; konstantní i oba proměnné směry, prostorové natočení, druhý solid,
vzdálený a kolidující otvor, neplatné hodnoty a pojistky, křivku, vnitřní kout,
šikmý konec, změnu délky, historii, uložení a čtení starých verzí.
GUI regrese navíc provádí výběr → formulář → obrácení → Zpět a ověřuje značky.
Self-test balíčku obsahuje ukázku, obrácení, Zpět/Znovu, zápis v32 a snímek 3D.

### Místní ověření na MacBooku Air M4

31. 10. 2026 prošlo **1 966 testů za 541,39 s** a kontrola Ruff. Po následných
opravách pouze v okně prošlo dalších **142 cílených GUI testů za 95,17 s**.
Finální balíček PyInstaller prošel celým self-testem (`VÝSLEDEK: OK`) s místním
akcelerovaným kreslením a kontrolou podpisu `codesign --verify --deep --strict`.
Evidence je místně v ignorované složce `out/p6-2026-10-31/`.

Při průchodu skutečným oknem přes macOS přístupnost se potvrdily dvě závady:
nativní dialog nepovolil platný JSON a úplné mazání stromu při přepočtu vedlo
k pádu `libqcocoa` se zastaralými odkazy na buňky. Díl nyní sdílí se sestavou
Qt souborové dialogy na Macu a při běžné úpravě znovu používá položky stromu
podle id prvku. Regrese ověřuje platnost trvalého indexu přes změnu R1/R2,
obrácení a Zpět. Ve finálním balíčku prošel skutečný průchod: R2 **6 → 8 mm**,
Zpět/Znovu, uložení, otevření téhož souboru z dialogu a kontrola R2 = 8 mm
i objemu **23 880 mm³** v okně. Poté byla testovací kopie vrácena na R2 = 6 mm.
Použitý model i profil byly oddělené od dat autora. Obrácení směru ověřily
automatické GUI testy a self-test, nikoli tento ruční průchod.

Exportovaný STEP otevřel také **FreeCAD 1.1.4 s jiným OCCT 7.8.1**: platný solid,
objem 23 925,604696567 mm³. Pět kolmých řezů v z = 2, 5, 10, 15, 18 mm mělo
poloměry 2,4; 3; 4; 5; 5,6 mm. Největší odchylka 25 měřených bodů od kružnic
byla **9,41 · 10⁻⁹ mm**. Jde o ověření této ukázky, ne přejímku libovolného dílu.

Číselné výsledky úplné sady, místního balíčku a workflow obou systémů se předávají
v navazujícím PR. P6.4 na vlastním autorském dílu ani pokročilé obecné zaoblení,
robustnější skořepiny a vodicí křivky loftu nejsou tímto uzavřené.
