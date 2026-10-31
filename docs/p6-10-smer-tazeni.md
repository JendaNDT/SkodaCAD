# P6.10 – omezení směru tažení rukojeti

Rozšíření [P6.8](p6-8-tazeni-rukojeti.md) a [P6.9](p6-9-krok-tazeni.md),
31. 10. 2026. Pod krokem tažení přidává volbu **Směr tažení**:

- **XY (obě osy)** – původní pohyb v rovině XY při pevné výšce.
- **Pouze X** – mění pouze souřadnici X, Y i Z zůstanou stejné.
- **Pouze Y** – mění pouze souřadnici Y, X i Z zůstanou stejné.

Osy jsou souřadnice dílu, nezávisle na natočení kamery. Posun ve zvoleném směru
používá stávající krok od počátku tahu (0 = volně), náhled i uvolnění shodně.
Pohyb, který zvolenou souřadnici nezmění, nevytvoří návrh ani historii.

## Projekce a meze pohledu

Volné XY nadále protíná pohledový paprsek s pevnou výškou. Pro jednu osu se
použije nejbližší bod přímky vedené rukojetí ve směru X nebo Y vůči paprsku.
Proto lze X táhnout i zepředu a Y zprava, přestože je rovina XY vidět z boku.
Kurzor se může pohybovat mimo obraz osy; rukojeť vždy zůstane na své ose.
Rozdíl parametrů proti okamžiku uchopení zabrání počátečnímu poskočení.

Pro jednotkový směr paprsku d, q = počátek paprsku − rukojeť a index osy a je
parametr nejbližšího bodu

s = q[a] − d[a] · Σ(j≠a) q[j]d[j] / Σ(j≠a) d[j]².

Jmenovatel se sčítá z kolmých složek, nikoli odčítáním od jedničky. Při hodnotě
pod 10⁻⁶ osa v pohledu zaniká a tah se odmítne s doporučením natočit pohled.
Nekonečné hodnoty nebo nulový paprsek se nepoužijí. Body zůstávají v mm,
konverze Qt/OCCT pixelů a ochrany z P6.8 se nemění.

## Stav a bezpečnost

Výchozí XY i zvolený směr jsou preference otevřeného okna. Zachovají se při
přepínání prvků/vodítek, Zpět/Znovu i otevření dalšího dílu v témže okně.
Nové okno začíná XY. Změna směru sama nepřepočítá model a nemění dokument,
špinavý stav ani historii. Změna směru během tahu zruší rozpracovaný náhled.

Do receptu se ukládá jen přijatý přírůstek rukojeti přes ModelSession z P6.8.
Neaktivní složka je přesně nulová, takže její původní číslo či parametrický
výraz zůstane nedotčený. Přijetí celého modelu, jeden krok Zpět, zrušení Esc
a odmítnutí neplatného tělesa nebo navazující operace zůstávají stejné.
Formát je stále **34**, bez změny jádra/session a bez nové závislosti.

## Ověření

Testy kombinují XY/X/Y s volným pohybem i několika kroky, porovnávají parametr
osy s nezávislým řešením nejmenších čtverců, zahrnují překlady a měřítko paprsku,
viditelnou i zaniklou osu, různá DPI, shodu náhledu a uvolnění, nulový posun,
zrušení při změně směru a zachování preference v okně a historii.

Nezávislá objemová reference pro první rukojeť A:
V = 77 760 + 249ΔX + 336ΔY mm³. Posun pouze X o 3 mm dává **78 507 mm³**,
pouze Y o −2 mm dává **77 088 mm³**; Zpět vrací **77 760 mm³**.
Testy také ověřují nezměněný výraz druhé souřadnice a pevné Z.
Self-test balíčku provede skutečný Qt/OCCT tah X zepředu a Y zprava s krokem
1 mm, historii a přepnutí zpět na XY. Konkrétní evidence obou OS je v PR.
