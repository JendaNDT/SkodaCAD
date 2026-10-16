# Závazné vymezení rozsahu UT modulu ŠkodaCAD

**Rozhodnutí autora: 16. 10. 2026.** Tento dokument má přednost před staršími návrhy v `docs/ndt/` všude tam, kde by starší text požadoval fyzikální simulaci, modelování odezvy vad či vyhodnocování jejich detekovatelnosti. Jde o změnu zadání pro Claude Code, nikoli o schválený NDT postup.

## Co UT modul SMÍ vyhodnocovat

1. **Geometrická přístupnost sondy:** zda se zadaná virtuální sonda/předsádka dá fyzicky přiložit na povrch a pohybovat po požadované trase bez geometrické kolize. Respektovat skutečné rozměry zařízení, orientaci, minimální manipulační prostor a vybranou oblast.
2. **Geometrické pokrytí kontrolovaného objemu:** které body/oblasti cílového objemu protíná zjednodušený geometrický model svazku při zadaném úhlu, rozsahu a trajektorii sondy. Lze znázornit směr, obálku a případně geometricky modelované lomy/odrazy, pouze pokud jsou jejich předpoklady explicitně zadané a algoritmus je skutečně implementuje a testuje.

**Doporučené názvy v GUI a protokolech:** „Přístupnost UT sondy“, „Mapa geometrického pokrytí UT“. Nepoužívat pro tento výsledek zavádějící označení „mapa prozvučitelnosti“.

## Co UT modul NESMÍ tvrdit, že vyhodnocuje

- **Fyzikální prozvučitelnost materiálu:** útlum a rozptyl vln, struktura a anizotropie materiálu, kvalita akustického spojení a reálná použitelnost echa.
- **Detekovatelnost vad:** pravděpodobnost detekce, velikost nebo druh spolehlivě zjistitelné vady, amplitudy indikací, citlivost skutečné sestavy nebo způsobilost kontroly podle normy.

Geometrické pokrytí **není** důkaz, že reálná vada bude detekována. Případné virtuální vady mohou sloužit jen jako výukové geometrické značky; negenerovat z nich „skutečný“ A-scan/B-scan ani tvrzení o detekci. Dříve plánované fyzikální simulace, virtuální signály a modelování detekovatelnosti jsou **mimo schválený rozsah** a nesmí být automaticky implementovány.

## Výsledky a jejich význam

- **Geometricky pokryto**: dané místo zasahuje použitý geometrický model svazku pro některou povolenou polohu sondy.
- **Geometricky nepokryto**: v rámci zadaných poloh, trajektorií a předpokladů nebylo místo zasaženo. Nejde o důkaz, že jiný postup kontroly není možný.
- **Nelze spolehlivě vyhodnotit**: chybné/neúplné vstupy, nepodporovaná geometrie, nejistá numerika či nejednoznačný výpočet. Nevyplňovat tuto oblast fiktivním výsledkem.

Uvádět použitou verzi geometrie, rozměry sondy, polohy/trajektorie, úhel, dosah, případná zjednodušení a omezení výpočtu. Nepřisuzovat procentům geometrického pokrytí význam pravděpodobnosti nalezení vady.

## Povinné upozornění v GUI i v každém exportovaném protokolu

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí kontrolované oblasti na základě zjednodušeného modelu ultrazvukového svazku. Nevyhodnocuje fyzikální prozvučitelnost materiálu ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.

## Požadavky na implementaci

1. Nejprve projít rozpracovaný UT kód a plán a sladit s tímto rozhodnutím, **bez přepisování souběžné práce naslepo**.
2. Výpočty geometrie oddělit od GUI, zajistit reprodukovatelnost, testy kolizí, map pokrytí, hranic úhlů a nevyhodnotitelných stavů.
3. Doporučení k poloze sondy a změně geometrie mají optimalizovat **pouze přístupnost a geometrické pokrytí**, nikoli slibovat detekovatelnost.
4. Toto rozhodnutí se týká především **UT**. Rozsah PT, MT a RT dále podléhá vlastním návrhům a ověřování; ani u nich nelze bez validace vydávat orientační výsledek za kvalifikované schválení kontroly.
5. Starší dokumenty `01-navrh-v0.1.md`, `02-navrh-v0.2.md` a `03-implementacni-plan.md` slouží jako historický kontext. Při rozporu platí **toto upřesnění**.
