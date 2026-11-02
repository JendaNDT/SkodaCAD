# P7.18 – hromadný posun dílů a podsestav

Datum: **2. 11. 2026**. Navazuje na hromadný výběr P7.17.

## Ovládání

Při výběru více komponent se vpravo objeví **Společný posun [mm]** s poli X/Y/Z.
Jde o přírůstek v osách celé sestavy, nikoli absolutní polohu nebo osy pootočeného
dílu. **Posunout vybrané** nebo Enter provede jeden společný přesun. Podporována
je desetinná čárka i výraz s parametry sestavy. Výraz přírůstku se spočítá jednou;
do původních souřadnic se přidá vypočtená konstanta.

Přesun zahrne všechny vybrané komponenty, včetně ručně skrytých a těch mimo izolaci.
Každá se posune stejným vektorem, bez otočení. Současný výběr rodiče a potomka
zpracuje celou větev jen jednou. Samostatné vnitřní díly podsestav zde upravovat
nejde: vyber jejich celé nadřazené podsestavy, nebo otevři soubor podsestavy.
Pevnost vnitřního dílu vůči vlastní podsestavě nebrání přesunu celého rodiče.

Pevná komponenta nejvyšší úrovně blokuje **celý** příkaz; žádná se tiše nepřeskočí.
Panel uvede proč je tlačítko vypnuté. Přesun také vyžaduje úplně sestavený model
se splněnými vazbami. Absolutní souřadnice, název a otáčení v původním formuláři
zůstávají určeny pro jedinou komponentu.

Vazby mohou zůstat uvnitř i vně výběru, pokud přesně zadaný posun dovolují.
Jestliže by řešič vrátil některý vybraný díl, pootočil ho nebo pohnul nevybraným
sousedem, příkaz se celý odmítne. Uživatel dostane důvod a může upravit vektor,
výběr nebo vazby. Hromadný posun sám vazby ani pevnost nemění.

## Historie a zachované údaje

Celý úspěšný přesun je **jeden krok Zpět/Znovu**. Nulový vektor nepřidá krok ani
nesmaže Znovu. Chyba nemění recept, výsledek ani historii. Kamera, výběr komponent,
ruční viditelnost, izolace a míry průhlednosti zůstávají. Plochy pro vazby se po
překreslení geometrie vyčistí, protože původní výběr již odkazuje na staré polohy.

Vstupy se po úspěchu vynulují; při změně výběru se také začíná nulovým vektorem.
Při chybě nebo pouhé změně pohledu, H/T/I, obnovení rozložení či přepočtu zůstává
rozepsaný vektor zachovaný.

Původní souřadnicové výrazy zůstávají parametrické. Například `-x0` po posunu o
5 mm bude `(-x0) + (5)`; další posun konstantu sloučí a opačný posun původní výraz
obnoví. Osy s nulovým přírůstkem se nepřepisují. Zdrojové soubory dílů a podsestav
se nikdy nezapisují. Změna zdroje během příkazu vede k odmítnutí a žádosti o obnovení.
Formát a závislosti se nemění; uložení a STEP zahrnují úplnou posunutou sestavu.

## Ověření

Jádro používá jednu kopii a jedno sestavení v `_change`. Kontrola po řešiči ověří
polohy všech komponent (absolutní tolerance 1e-6 mm), matice otočení (1e-10)
a otisky všech zdrojů, teprve pak přijme recept a historii.

Regrese ověřují objemy, středy a obálky pootočených kopií, relativní polohy,
parametrické výrazy, pevné i neúplné sestavy, nulový/špatný vstup, nedotčené Znovu,
pohyb souseda podle vazby, pohyb pouze ve volném směru, celé podsestavy, uložení
a úplný STEP. Testy GUI provádějí Enter, kontrolují vysvětlení blokace, zachování
vektoru po chybě a zachování filtrů/výběru po Zpět/Znovu.

Nativní self-test posune dvě parametrické nožičky o **[2,5; −1; −4] mm**, ověří
blokaci pevné krabičky, H/izolaci, kameru, otočení, ostatní díly, fyzický objem
a jeden krok Zpět/Znovu. Vyžaduje se i ze stažených balíčků Windows a macOS.
Protokoly a snímky: `out/p7-batch-move/`; konečné výsledky úplných kontrol patří
do implementačního PR. P7.4 (autorská přejímka celého prostředí) zůstává otevřená.
