# P6.8 – tažení rukojetí řízeného přechodu

Rozšíření [P6.7](p6-7-rizeny-prechod.md), 31. 10. 2026. Formát zůstává **34**,
geometrická konstrukce a omezení profilů se nemění. Žádná nová závislost.

## Použití

1. Vyber řízený přechod ve stromu a vodítko A–D ve formuláři.
2. Větší barevný bod „řízení 1“ nebo „řízení 2“ uchop levým tlačítkem a táhni.
   Rukojeť zůstává ve své výšce H/3 nebo 2H/3 a pohybuje se pouze v XY.
3. Během tahu se kreslí přesná změněná křivka a čárkovaný řídicí polygon.
   Těleso, recept, špinavý stav a historie zůstávají původní. Puštění myši spustí
   ověření celého kandidáta; teprve úspěšný výsledek se přijme jako jeden krok Zpět.
4. Esc, přepnutí z okna nebo změna pohledu tah zruší. Běžný klik bez tahu nedělá změnu.
   Čekající výpočet lze zastavit obvyklým tlačítkem Zastavit; návrh se nezapíše do Znovu.

Neplatný tvar, chyba navazující operace či pomocného procesu ponechá původní
model, výsledek a historii včetně větve Znovu. Chyba vysvětlí důvod česky.
Výrazy se zachovávají přičtením posunu, např. `(4*Bx/3) + (2.0)`;
parametr Bx dál ovlivňuje rukojeť. Ostatní rukojeti se nemění.

Při pohledu téměř podél roviny XY se zobrazí doporučení použít Izometrii nebo
Shora. Překryté rukojeti vyžadují natočení nebo přiblížení. Alt/tah dál patří
sondě NDT, Shift/tah posunu pohledu; rukojeti se uchopují bez modifikátorů.

## Myš, kreslení a číselné meze

Viewer vybírá pouze dvě zobrazené rukojeti aktuálně vybraného vodítka. Roh je
určen znaménky X/Y, rukojeť číslem 0/1; nejde o index topologické hrany OCCT.
Výběrový poloměr je 12 logických bodů obrazovky. Dva body v dosahu s rozdílem
vzdáleností pod 1 bod jsou nejednoznačné a tah se nezahájí. Mrtvá zóna je stávající
hranice 3 logických bodů pro odlišení kliku od tahu.

`V3d_View.Convert` promítá číselné body do pixelů OCCT, `ConvertWithProj` dává
pohledový paprsek. Jeho průsečík s pevným Z určí XY; rozdíl vůči začátku tahu
zachová odchylku kurzoru od středu značky, takže rukojeť při uchopení neposkočí.
Poměr pixelů OCCT k bodům Qt používá stávající měřenou konverzi pro Retinu.
Paprsek s |dz|/|d| < 0,001 nebo nekonečnými hodnotami se nepoužije.
Kolečko se během tahu neuplatňuje; změna kamery, rozměru plochy či dat vodítek
rozpracovaný tah zruší. Viewer pouze kreslí a předá jeden návrh po puštění.

## Přijetí modelu a souběh

`ModelSession.move_guided_handle` ověří aktuální úplný díl, otisk začátku tahu,
roh, rukojeť a konečné XY posuny. Nulový posun do 10⁻⁹ mm je beze změny.
Nejprve běží existující kontrola geometrických vstupů a konvexity z P6.7.
Celý model kandidáta se potom přepočte přes stávající BackgroundRebuilder,
včetně navazujících operací; bez runneru proběhne totéž synchronně.

Do dokončení se recept nezmění. Výsledek musí být úplný, úspěšný, patřit kandidátovi
a vycházet ze stále stejného dokumentu. Přijetí využije `_change` s již ověřeným
BuildResult, založí jediný krok historie, zneplatní odvozené analýzy a nepouští
podruhé totožný přepočet. Nová úprava, otevření nebo Zpět nahradí čekající úlohu
stávajícím mechanismem job id; starý návrh nesmí později přepsat nový model.
Zastavení návrhu nezmění dokument ani historii.

## Ověření

Testy sledují skutečný vliv jedné rukojeti (ve středu křivky váha 3/8), zachování
Z a parametrických výrazů, historii, uložení a otevření v34, konečné těleso,
asynchronní přijetí, zastavení, souběžnou změnu a chybný/cizí výsledek workeru.
Ovladač myši má testované ukotvení, různé DPI, náhled bez změny modelu,
jediné předání při uvolnění, Esc, ztrátu fokusu, změnu podkladu, překrytí,
boční pohled a přednost Alt pro sondu. Offscreen okno ověří propojení signálu
s formulářem a zachování vybraného řádku. Self-test balíčku pošle Qt události
na skutečnou nativní plochu OCCT, provede tah, Zpět/Znovu a Esc.
Konkrétní výsledky a evidence obou systémů jsou v implementačním PR.
