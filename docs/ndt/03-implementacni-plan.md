# Dokumentace modulu NDT — ŠkodaCAD

> Podklad ke konzultaci a plánování. Nejde o schválený NDT postup ani o potvrzení detekovatelnosti vad.

ŠkodaCAD | NDT
Kompletní implementační plán návrhů v0.1 + v0.2

Pracovní verze 1.0 • 16. října 2026 • Podklad k odsouhlasení, bez zásahu do repozitáře



1. Hlavní rozhodnutí
-   NDT bude oddělená analytická vrstva nad existujícím 3D modelem. Simulace nikdy sama
    nepřepisuje geometrii.
-   První metodou je UT, ale společné jádro od počátku počítá s PT, MT a RT.
-   První výstupy určují geometrickou přístupnost a dosah; nikoliv zaručenou detekovatelnost vad
    nebo normovou shodu.
-   Veškeré výpočty poběží místně, bez AI API. AI může jednou vysvětlovat výsledky, ale nesmí být
    autoritou pro numerické závěry.
-   Každá etapa se uzavře testy a krátkou praktickou demonstrací. Další etapa nezačne s rozbitým
    předchozím výsledkem.



2. Výchozí stav aplikace a co znovu nestavět
Podle README a CLAUDE.md (větev main k 16. 10. 2026) ŠkodaCAD používá Python 3.11+, build123d
0.13, Open CASCADE, PySide6; 3D zobrazení AIS/V3d, JSON model, ModelSession, testy a výpočty přes
pomocný proces. Už má raycasting pro tloušťky (measure.py), mapu tloušťky (thickness_map.py), řez
(section.py), sémantické identifikátory ploch (selectors.py), worker.py a historii Zpět/Znovu.
Nezávislé NDT analýzy budou tyto mechanismy znovu využívat, ale nesmí převzít zjednodušení
tloušťkoměru jako platný fyzikální model UT.



3. Mapa závislostí
Základ modelu → studie NDT → geometrické dotazy → polohování zařízení → UT jeden paprsek → UT
interaktivní dráha → mapa pokrytí → svar / cílový objem → audit → automatická trasa → návrhy
změn geometrie. PT/MT/RT navazují po společném jádře a první ověřené UT demonstraci;
nepodmiňují automatickou UT optimalizaci. Pokročilé signály a fyzikální simulace přijdou až po
metodické validaci.



4. Etapy implementace v přesném pořadí
Etapa 00 – Inventura, rozhodnutí a referenční příklady
Závisí na: žádná

Úkoly: Zmapovat rozhraní ModelSession, raycasteru, vieweru, workeru a formátu JSON. Rozhodnout
rozsah v1, přesnost a materiálové vstupy. Připravit minimálně 8 referenčních geometrií: deska, blok
s kapsou, žebro, otvor, trubka, tupý svar, koutový svar, obtížný přístup. Sepsat očekávaný výsledek
ručně.

Výstup: Schválené hranice výpočtů, testovací fixtures a mapa modulů.



                        ŠkodaCAD • Plán implementace NDT • pracovní návrh
Podmínka dokončení: Existující testy projdou a referenční případy mají jednoznačný popis
správného výsledku.

Etapa 01 – Datový model NDT studie a bezpečné uložení
Závisí na: 00

Úkoly: Založit oddělený záznam studie: ID, verze, odkaz na geometrii, metoda, cílová oblast,
zařízení, materiál, nastavení, výsledek a stav ověření. Výsledky přepočítávat, neukládat jako
nezpochybnitelnou pravdu. Migrace starých JSON a Zpět/Znovu; studie se má označit jako zastaralá
po změně geometrie.

Výstup: Studie NDT v souboru a v ModelSession, zatím bez náročných výpočtů.

Podmínka dokončení: Staré modely se načtou; založení/uložení/načtení studie, změna modelu a
rollback fungují.

Etapa 02 – Společné geometrické jádro pro NDT
Závisí na: 01

Úkoly: Sjednotit dotazy: průnik paprsku s objemem, normála a tečna povrchu, bod uvnitř/vně,
segment v materiálu, viditelnost povrchu a kolize. Výsledky s jednotkami, tolerancemi a kódem
nejistoty. Uložené odkazy na plochy pouze významem, ne indexem. Oddělit přesný OCCT výpočet a
případnou zjednodušenou síť pro rychlý náhled.

Výstup: Testovatelné funkce bez GUI použitelné všemi čtyřmi metodami.

Podmínka dokončení: Analytické bloky, válce a dutiny dávají očekávané průsečíky; žádná tichá
falešná kladná odpověď.

Etapa 03 – Polohování a obálky NDT zařízení
Závisí na: 02

Úkoly: Univerzální souřadný systém zařízení: kontaktní bod, orientace, rozměrová obálka,
požadovaná manipulační rezerva, omezení přiložení a sklonu. Kontrola kolizí při položení a posunu;
průběžné dotazy pracují nad skutečným dílem. Pro začátek virtuální sonda bez katalogových
tvrzení.

Výstup: Zařízení lze umístit na povrch a zobrazit kolizi / volný prostor.

Podmínka dokončení: Sonda odmítnutá při průniku s žebrem, přijatá na volné ploše; test zakřivené
plochy.

Etapa 04 – UT – základní geometrický model paprsku
Závisí na: 02,03

Úkoly: Přímá sonda jako první: osa paprsku, materiál, tloušťka, délka dráhy, vstup/výstup a
případný odraz na hranici geometrie. Přidat úhlovou sondu až poté: refrakce dle Snellova zákona s
definovanými rychlostmi a módem vlny; přechody, kritické úhly a neplatná nastavení správně
ošetřit. Nestavět první verzi na falešných A-scanech.

Výstup: Paprsek a jeho geometrická dráha v řezu a ve 3D.

Podmínka dokončení: Úhly, délky a průsečíky souhlasí s ručními výpočty na jednoduchých tělesech.


                        ŠkodaCAD • Plán implementace NDT • pracovní návrh
Etapa 05 – UT – ruční pohyb sondy v GUI
Závisí na: 04

Úkoly: Režim NDT→UT; výběr sondy, parametrů a kontaktní plochy, tažení myší po povrchu s
přepočtem paprsku, zvýrazněním kolize a lokálního stavu. Řez modelem použít jen pro pohled, ne
měnit těleso. Výpočty oddělit od GUI, u dražších dotazů worker s možností zrušit.

Výstup: Použitelný první prototyp: „jezdím sondou“ a vidím, kam vede geometrická dráha.

Podmínka dokončení: Ovládání plynulé na referenčním dílu, stabilita Windows/Linux, česká
vysvětlení nemožného přiložení.

Etapa 06 – UT – mapa geometrického pokrytí
Závisí na: 05

Úkoly: Definovat přesný cílový objem nebo oblast, prostorově vzorkovat a spočítat, které body
zasáhl uvažovaný paprsek/svazek. Nezaměňovat „zasáhl paprsek“ s „lze detekovat vadu“. Uchovávat
parametry rozlišení, konvergence a dosud neskenované oblasti. Barevná legenda: geometricky
dosaženo, nedosaženo, nejisté, nevyhodnoceno.

Výstup: Mapa s procentem dosaženého cílového objemu a citlivostí na krok výpočtu.

Podmínka dokončení: Pokrytí stoupá s další dráhou, při zpřesnění mřížky se stabilizuje; test hranice
a slepých míst.

Etapa 07 – Svar a cílová oblast jako NDT objekty
Závisí na: 01,02,06

Úkoly: Ruční definice svaru: osa/trasa, typ, rozměry, převýšení, kořen, kontrolovaný objem a
přilehlé oblasti. Není-li CAD sestava svařence, umožnit označit pomocnou NDT oblast bez změny
tělesa. Automatické rozpoznání svarů až později a vždy s potvrzením člověka.

Výstup: UT geometrické pokrytí se vztahuje ke konkrétnímu svaru nebo objemu.

Podmínka dokončení: Tupý a koutový svar mají reprodukovatelný cílový objem; po změně modelu
je vazba ověřena nebo označena jako neplatná.

Etapa 08 – Knihovna zařízení a materiálových profilů
Závisí na: 03,04,07

Úkoly: Oddělit měřené parametry od informačních údajů: rozměr sondy a předsádky, nominální
úhel, rychlosti vln, frekvence, kontaktní požadavky; u RT rozměry zdroje/detektoru, u MT jha/pólů.
Začít generickými profily; komerční údaje jen s konkrétním ověřeným zdrojem. Uvést verzi a původ
dat.

Výstup: Předvolby reálně nastavují geometrii simulace, uživatel může zvolit vlastní hodnoty.

Podmínka dokončení: Kontrola jednotek, rozsahů a původu dat; žádná neověřená „certifikovaná“
předvolba.

Etapa 09 – UT – automatická analýza přístupnosti a doporučené polohy
Závisí na: 06,07,08




                       ŠkodaCAD • Plán implementace NDT • pracovní návrh
Úkoly: Vzorkovat kandidátní kontaktní plochy a orientace, hodnotit kolize, manipulační délku,
dostupný úhel a geometricky pokrytý objem. Vrátit několik řešení s vysvětlením kompromisů.
Nejprve optimalizovat polohu sondy a kontrolní parametry bez změny modelu.

Výstup: Návrh poloh UT sondy a mapa problémových zón.

Podmínka dokončení: Na známé blokované geometrii najde alternativu, nebo poctivě oznámí, že ji
nenašel.

Etapa 10 – UT – automatická skenovací trajektorie
Závisí na: 09

Úkoly: Plán souvislé dráhy po přípustných kontaktních plochách, respektovat rozměry zařízení,
překážky, orientaci a praktický nájezd. Hodnotit pokrytí, délku, počet přestavení a robustnost.
Možnost ručních zakázaných zón a úpravy trasy.

Výstup: Přehratelný plán pohybu sondy v 3D s tabulkou poloh.

Podmínka dokončení: Každý bod navržené trasy je bez kolize, pokrytí souhlasí s nezávislým
přepočtem.

Etapa 11 – PT – přístupnost a praktická použitelnost
Závisí na: 02,03,07

Úkoly: Samostatný PT modul: povrchové oblasti, dostupnost pro aplikaci, čištění, odstranění
přebytku a vyhodnocení. Vyhledat úzké štěrbiny, uzavřené kapsy a zakrytá místa; upozornit na
možné falešné indikace a nemožnost čištění. Nepředstírat predikci skutečného vzlínání či citlivosti
bez experimentálních dat.

Výstup: PT mapa přístupnosti a seznam důvodů omezení.

Podmínka dokončení: Ručně definované otevřené a nepřístupné oblasti správně odlišeny.

Etapa 12 – MT – magnetizační dostupnost a orientace
Závisí na: 02,03,07,08

Úkoly: Nejprve kolize jha/pólů, vzdálenost pólů a možné orientace magnetizace vzhledem k
požadované orientaci vad. Ukázat potřebu různých směrů magnetizace. Fyzikální rozložení
magnetického pole, demagnetizaci a saturaci vést jako samostatnou budoucí simulaci s
materiálovými charakteristikami a validací.

Výstup: MT mapa geometrické proveditelnosti a směrového pokrytí; bez tvrzení o dostatečné
intenzitě pole.

Podmínka dokončení: Uživatel vidí oblasti, kam se jho nevejde, a rozdíl při otočení magnetizace.

Etapa 13 – RT – geometrie projekce a expozice
Závisí na: 02,03,07,08

Úkoly: Zdroj, aktivní ohnisko, směr svazku a detektor/film s kolizemi; průchod paprsků materiálem,
geometrické zvětšení, potenciální překryvy a geometrickou neostrost z rozměru ohniska.
Naplánovat několik projekcí, zkontrolovat, zda se oblast promítne na detektor. Dávku, expoziční
parametry, IQI a skutečnou citlivost nedopočítávat bez validovaných modelů.


                         ŠkodaCAD • Plán implementace NDT • pracovní návrh
Výstup: RT geometrická simulace s náhledem projekce a upozorněními.

Podmínka dokončení: Jednoduchá stěna/otvor správně mění projektovanou tloušťku a obraz při
změně úhlu.

Etapa 14 – Společný audit, protokol a vysvětlení
Závisí na: 09,11,12,13

Úkoly: Jedno tlačítko „Předběžný NDT audit“: podle zvolených metod najde omezení, ale nikdy
nevybere normativní postup automaticky. Výsledky podle metody, oblasti, parametrů, stupně jistoty
a omezení; export čitelného PDF/HTML nebo CSV. Exportovat pouze skutečně vypočtené výsledky a
rozlišovat neprovedeno/nedostupné/neznámé.

Výstup: Sdílitelný předběžný protokol a přehled problémových míst.

Podmínka dokončení: Uživatel dohledá důvod každého nálezu i nastavení, kterým vznikl.

Etapa 15 – Konstrukční návrhy bez automatické změny dílu
Závisí na: 09,10,14

Úkoly: Vygenerovat kandidáty úprav vybraných parametrů modelu: posun žebra, zvětšení přístupu,
úprava okolí svaru. Stanovit zamčené rozměry, technologické a pevnostní podmínky, limity změny;
bez těchto vstupů návrh jen informativní. Každou variantu přepočítat a NDT vyhodnotit stejnými
nastaveními. Zobrazit původní/novou geometrii, pokrytí a dopady na objem a hmotnost. Nikdy
neprovádět změny bez schválení.

Výstup: Srovnání konstrukčních variant, ne autonomní překreslování.

Podmínka dokončení: Původní soubor se nemění; návrh lze odmítnout; při zamčené kótě změna
neprojde.

Etapa 16 – Výukové vady a pokročilé signály
Závisí na: 06,07,14

Úkoly: Virtuální trhlina, pór a nespojení jako oddělený scénář bez změny výrobního dílu. Nejprve
geometrická průsečnost; následně A-scan/B-scan jako didaktická syntéza se zřetelným označením.
Fyzikálně věrné echa, rozptyl, útlum, svazek, RT kontrast či MT intenzita až po volbě validovaného
modelu a porovnání s měřením.

Výstup: Volitelný výukový režim oddělený od předběžného auditu.

Podmínka dokončení: Žádný syntetický signál není prezentován jako ověřená detekční schopnost.

Etapa 17 – Validace pro reálné použití a stabilizace
Závisí na: 00–16

Úkoly: Postupně přidávat fyzické referenční vzorky, známé sondy a postupy; srovnat výpočty s ruční
metodikou, měřením a autorizovanými NDT pracovníky. Dokumentovat nejistotu, limity a změny
algoritmů. Testovat rozsáhlé modely, více těles, exporty, instalaci, regresi a dlouhý provoz.
Normovou shodu nebo rozhodnutí o způsobilosti metody umožnit jen na základě příslušného
schváleného postupu.

Výstup: Dokumentované meze použitelnosti a ověřená verze pro konkrétní typy dílů.


                         ŠkodaCAD • Plán implementace NDT • pracovní návrh
Podmínka dokončení: Každá metoda má dohledatelný protokol validace; jinak označení
„orientační“.



5. Praktické milníky a správné pořadí práce
-   M0 – technický základ: 00–03. Bez něj nepřidávat nové metody.
-   M1 – první fungující UT: 04–05. Prohlížení paprsku při pohybu sondy.
-   M2 – hodnotitelný UT: 06–08. Pokrytí definovaného objemu, svary a knihovna zařízení.
-   M3 – asistovaný UT: 09–10. Automatické polohy a trajektorie.
-   M4 – všechny čtyři metody v geometrické úrovni: 11–13. PT, MT, RT mohou postupovat
    paralelně po M2, každá v izolované větvi.
-   M5 – společný audit a konstrukční doporučení: 14–15. Porovnání návrhů.
-   M6 – výukové signály a komplexní validace: 16–17. Vývojově samostatná a potenciálně dlouhá
    oblast.



6. Pravidla každého kroku pro Claude Code
-   Jedna změna = jeden jednoznačný podúkol s demonstrací a testy. Nepřidávat současně GUI,
    algoritmus, nový formát a optimalizaci v jednom commitu.
-   Před podstatným rozhodnutím navrhnout rozhraní, dopady na JSON, nové závislosti a zpětnou
    kompatibilitu; vyčkat schválení.
-   Výpočtové moduly bez Qt; GUI pouze volá ModelSession; drahé úlohy běží přes pomocný proces,
    lze je zrušit.
-   Ke každému výpočtu zapsat: definici „pokrytí“, předpoklady, jednotky mm/°, toleranci, verzi
    algoritmu, neznámé vstupy a zdroj materiálových dat.
-   Testovat jednoduchou analytickou geometrii, hraniční případy, výkon i regresi; spustit pytest -q
    a ruff check src tests. U GUI také offscreen a reálný snímek.
-   Ukaž změnu v běžném českém jazyce a připrav jeden konkrétní scénář „klikni, nastav, pozoruj“.
    Nepřeháněj přesnost a nepoužívej „kontrolovatelné“ bez vymezení.
-   Do main slučovat až po schválení jednotlivých větších milníků; žádné zásahy do produkčního
    modelu bez možnosti vrácení.



7. Rozdělení modulů (návrh, nikoli již existující soubory)
-   ndt/study.py – studie, její stav a vazby na model; ndt/geometry.py – společné geometrické
    dotazy; ndt/devices.py – geometrie zařízení a katalog.
-   ndt/ut.py, ndt/coverage.py, ndt/paths.py – UT výpočet, pokrytí, dráhy; ndt/welds.py – definice
    svarů a cílových objemů.
-   ndt/pt.py, ndt/mt.py, ndt/rt.py – metoda-specifická pravidla; ndt/audit.py – společný audit;
    ndt/variants.py – porovnání návrhů.
-   gui/ndt_*.py – panely a interakce; session.py – jediné veřejné rozhraní pro úlohy GUI;
    samostatné tests/test_ndt_*.py.



8. Co zatím výslovně neimplementovat
Falešnou certifikaci podle ČSN/EN/ASME; sliby záchytu minimální vady; automatickou změnu
modelu bez souhlasu; neověřené simulace magnetického pole; výpočet RT dávek a expozičních časů
bez validace; automatické rozpoznávání libovolného svaru bez potvrzení uživatele; AI API jako


                       ŠkodaCAD • Plán implementace NDT • pracovní návrh
zdroj fyzikální pravdy. Vývoj začíná předběžným posouzením geometrické proveditelnosti, ne
náhradou kvalifikovaného NDT postupu.



9. Rozhodnutí potřebná před etapou 01
-   Jaký první referenční díl použít: jednoduchý tupý svar v desce versus blok s žebrem?
    Doporučení: blok s žebrem pro M1, svar pro M2.
-   Jak přesně definovat geometricky pokrytý objem (paprsek, zjednodušený svazek, vzorkovací
    krok) a nejistotu? To musí být napsáno dříve než mapa.
-   Má být NDT studie součástí existujícího JSON, nebo samostatný doprovodný soubor?
    Doporučení: samostatná logická sekce JSON, ale rozhodnout až po kontrole současné
    architektury.
-   Jak se bude spravovat katalog sond a ověřené materiálové údaje? Doporučení: malá verzovaná
    knihovna plus ruční profil.
-   Kdo bude potvrzovat odbornou správnost referenčních případů? Doporučení: NDT technik se
    znalostí metod a případně další kvalifikovaný pracovník.



10. Zadání prvního konkrétního úkolu pro Claude Code
Prostuduj README.md, CLAUDE.md a existující zdrojové moduly ŠkodaCAD. Nic nerefaktoruj
plošně. Navrhni etapu 00 a etapu 01 podle tohoto plánu: sepiš současná rozhraní, připrav sadu
referenčních NDT geometrií a návrh datového modelu NDT studie včetně migrace, zpětné
kompatibility, Zpět/Znovu a invalidace po změně geometrie. Nejprve předlož návrh souborů, změn a
testů ke schválení. Až poté implementuj, vždy po malých krocích. Nepřidávej simulace signálů a
neměň konstrukční geometrii.




                       ŠkodaCAD • Plán implementace NDT • pracovní návrh