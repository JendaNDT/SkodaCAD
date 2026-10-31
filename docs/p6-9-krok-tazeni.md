# P6.9 – nastavitelný krok tažení

Rozšíření [P6.8](p6-8-tazeni-rukojeti.md) z 31. 10. 2026 přidává nad tabulku
vodítek pole **Krok tažení**. Výchozí 0 se zobrazuje jako **Volně (0)**
a zachovává dosavadní plynulé tažení. Lze zadat libovolný krok od 0,001 do
1000 mm se třemi desetinnými místy, například 0,1 / 0,5 / 1 / 5 mm.

## Význam

Krok je přírůstek posunu rukojeti **od začátku každého tahu**, zvlášť v osách
X a Y. Nejde o absolutní mřížku souřadnic dílu ani kótu skutečného vyboulení.
Rukojeť tak při uchopení neposkočí, i když začíná na parametrické souřadnici.
Její výška je stále pevná. Při kroku 1 mm se například volný posun
(2,7; −1,8) mm změní na (3; −2) mm. Přesná polovina kroku se zaokrouhlí
od nuly: při kroku 0,5 mm se ±0,25 mm změní na ±0,5 mm.

Krok se používá na celkový posun od počátku tahu při každé události myši,
nikoli na rozdíly mezi událostmi. Stejný výsledek jde do náhledu i do návrhu
při uvolnění. Desítková aritmetika standardní knihovny zabraňuje zbytkům
jako 0.30000000000000004 v uloženém výrazu. Výsledné dva floaty zkontroluje
stávající ModelSession a celý přepočet z P6.8.

Pohyb menší než půl kroku může skončit nulovým posunem; v takovém případě
nevzniká návrh, přepočet ani položka historie. Změna kroku během rozpracovaného
tahu jej zruší, aby nedošlo k přeskoku. Esc a ostatní ochrany z P6.8 platí dál.

## Stav a kompatibilita

Krok je preference **otevřeného okna**. Zachová se při přepnutí prvku/vodítka,
Zpět/Znovu a otevření dalšího dílu v témže okně. Nové okno začíná volným pohybem.
Volba nemění dokument, špinavý stav, historii ani samotné hodnoty rukojetí.
Do JSON dílu se ukládají pouze přijaté posuny stávajícím způsobem; nastavení
kroku se tam nezapisuje. Formát zůstává **34**, jádro a session se nemění,
nevzniká závislost mimo standardní knihovnu.

## Ověření

Testy pokrývají kladné/záporné posuny, poloviny kroku, desetinné kroky,
volný pohyb, meze, různé DPI, neměnnost počátku tahu, shodný náhled/uvolnění,
nulový krok výsledného posunu a zrušení při změně volby. Test okna ověřuje
volbu bez změny dokumentu, zachování při přepínání, historii a uložení/otevření.

Referenční díl má před tahem 77 760 mm³. Posun první rukojeti A o (3;2) mm
má nezávisle spočítanou změnu objemu 249·3 + 336·2 = 1 419 mm³,
tedy výsledek **79 179 mm³**; Zpět vrátí původní objem. Self-test zabalené
aplikace skutečnými Qt událostmi přes OCCT ověří krok 1 mm, pevné Z,
stejný náhled/výsledek, jeden krok Zpět/Znovu a přepnutí 0,1 mm / Volně.
Konkrétní výsledky místních a systémových běhů jsou v implementačním PR.
