# P1.3 — implementace a ověření

Autor 22. 10. 2026 schválil [C1–C8, C.1–C.3 a S01–S20](p1-3-navrh-bezpecnych-referenci.md)
slovy „ok, schvaluji vše“, včetně sloučení návrhového PR #36 (`c46d0e2`).
Implementace má samostatnou větev `codex/p1-3-safe-references` a vlastní PR.
**Sloučení implementace vyžaduje další samostatný pokyn autora.**

23. 10. 2026 autor požádal o převzetí zbývajících zkoušek agentem. [Nový protokol](p1-3-agent-overeni-macos-2026-10-23.md)
odděluje jeho skutečná potvrzení, omezení přímého ovládání a doplňkové automatické
ověření. To odhalilo a opravuje vynechaný přenos `references` při návratu ze
skicáře; původní úspěšné CI nejsou ověřením této nové opravy.

## Výchozí stav a měření

Základ: `c46d0e2581a025d607053570801d83675a3aae4b`, produkční kód shodný s P1.2B.
Před změnou `src/` vzniklo nové měření P0, historií 3/30 přídavků a pozdního odmítnutí
i pěti pevných sémantických dotazů (zahřátí + 3 opakování / dávky po 100 dotazech).
Příloha předání uchovává otisky vstupů, zdrojů, měřičů, prostředí a fyzické podpisy.
Pásma nerozlišitelnosti nejsou meze dovoleného přemístění ani výrobní přesnost.

## Kroky a důkazy

| Krok | Stav |
|---|---|
| C.1 | Jediný výsledek nesmí rozhodnout pořadí, filtry jsou závazné, vstupy se ověřují před geometrií. 74 nových případů / 0,07 s a 147 dosavadních cílených případů / 6,26 s. Ruff OK; celý pytest **1 385 prošlo / 420,71 s**, bez chyb a přeskočení. Všech 1 311 původních případů zachováno; S01–S08/S13. |
| C.2 | Zpětné ověření nového výběru, celý úsek/oblouk a celý fragment plochy, doménové chyby měření/projekce/NDT. 36 nových případů; 61 cílených / 1,34 s. Ruff OK; celý pytest **1 421 prošlo / 419,21 s**, bez chyb a přeskočení. S09–S15; původní testy zachované. |
| C.3 | 27 dalších případů pro přenos, skutečný spawn/Qt, historii, kopie, posunuté/otočené nosiče a meze identity; celkem 137 nových. Ruff OK; celý pytest **1 448 prošlo / 417,98 s**, bez chyb a přeskočení. Všech 68 původních testovacích souborů byte shodných. Měření a nativní kontrola níže; cílové CI a ruční přijetí jsou samostatné zbývající brány. |
| Doplnění C.3, 23. 10. | Oprava vynechaného přenosu existujícího pole `references` při návratu ze skicáře. Tři nové regrese nahrazení/smazání/přidání projekce, všechny selžou se starým přenosem a projdou s opravou. Ruff OK; celý pytest **1 451 prošlo / 429,85 s**, bez chyb a přeskočení; 68 původních souborů zachovaných, celkem 140 nových případů. Šest doplňkových zdrojových Qt scénářů / 7,96 s, 36 stavů. Nové celé CI a meze přímého ovládání balíčku se evidují odděleně. |

`select_edges` ponechává záměrné skupiny; jen `near` vyžaduje jediného nejbližšího
kandidáta. Celý předpis včetně seznamu se ověří a vyčíslí před přístupem ke geometrii.
`find_face` odmítne neznámý druh, nevhodný či neshodný pevný poloměr, neplatný
směr a nerozlišitelný výsledek. Normála se normalizuje pouze pro výpočet.
Opakování téhož tvaru se odstraní přes `is_same`; shodná geometrie různých tvarů ne.
Pojmenovaná rovina používá skutečnou krajní úroveň, ne první položku v pásmu.

Regrese kontrolují obě pořadí skutečných hran/ploch, několik solidů, stejné normály,
meze vzdálenosti i směrového skóre, chybné vstupy skryté za prázdným filtrem,
rozdělenou horní plochu a původní materiál/objem po chybě prvku. Řiditelné testy
mezí doplňují skutečnou geometrii. Původní `<` u poloměru plochy a `<=` u hrany
zůstávají ověřené odděleně; nejde o skryté sjednocení tolerancí.

C.2 ověřuje konečný výběrový předpis i po fallbacku; při potřebě zpřesní stávající
`near` ze 3 na 9 desetinných míst, nebo výběr odmítne. Nová reference musí patřit
k aktuálnímu dílu; bodová reference se znovu vyhodnotí i proti skutečné kliknuté ploše.
Přenos úsečky vyžaduje oba konce na cílovém úseku; kružnice/oblouk shodu středu,
roviny a poloměru a obsažení celého souvislého úhlového intervalu. Testy zahrnují
překročení 0° i opačnou orientaci osy nosné kružnice. Obecná křivka bez nativní
totožnosti se výslovně odmítne.

Závěrečná regrese C.3 navíc odhalila, že téměř rovnoběžná kružnice mohla přes
shodu směrového skóre ležet mimo stávající vzdálenostní mez. Přenos nyní vyžaduje
horní mez odchylky **celé** nosné kružnice (posun středu + rozdíl R + odchylka
otočení) pod původními `1e-5 mm`. Žádné vzorkování ani nová tolerance. Samostatný
případ kontroluje součet odchylky středu a poloměru; dvě odchylky nesmějí každá
spotřebovat celé pásmo. Opačné orientace os a oblouky přes 0° zůstaly platné.

Přenos plochy ověřuje nosič, orientaci a celý fragment pomocí nepoškozujícího
rozdílu OCCT (`SetNonDestructive(True)`, dokončení, neprázdný platný výsledek bez
zbývajících ploch). „Neprázdný“ zde znamená nenulový nativní objekt; prázdný
compound je správný důkaz nulového zbytku. Nepřidává se fuzzy tolerance ani
hluboká kopie celého dílu. Skutečné řezy kvádru/válce/koule/kužele/toru kontrolují
také původní objemy, povrchy, obálky a orientace. Kužel používá záměrně přesnou
shodu velikosti polovičního úhlu; neprokázaný obecný nosič nebo chyba jádra se
odmítne. Shoda jednoho bodu nikdy nenahradí důkaz celého fragmentu.

Rozlišení chybějícího a nejednoznačného předpisu zachovává základní `SelectionError`;
do worker protokolu nevstupují nové typy výjimek. Projekce zachová konkrétní příčinu
a nepoužije uložené staré body. Vadné nové měření/oblast dostanou svou doménovou chybu.
NDT algoritmy se nemění: audit `faces_of` a jeho spotřebitelů potvrzuje odmítnutí
problémů v PT/MT/RT i UT pokrytí/návrhu poloh/plánu. Regrese ověřují, že nový
výběr po změně receptu stále vyžaduje samostatné potvrzení zastaralé studie,
že odmítnuté potvrzení nepřepíše dokument/historii a že zanikne staré odborné ověření.

## Pokrytí matice

| Scénáře | Konkrétní důkaz |
|---|---|
| S01 | Dosavadní `test_picking`, `test_tnp` a fyzické změny parametrů: zachované zaoblení správného rohu. |
| S02–S08, S13 | `test_reference_selectors`: skutečné tvary v obou pořadích, skupiny, normály, číselné meze a struktura vstupů. |
| S09–S11 | `test_reference_mapping`, `test_reference_limits`: zpětné ověření, celý úsek/oblouk/plochový fragment, primitivní nosiče i po otočení a posunu, odmítnutí umělého řezu a neprokázané obecné křivky. Dosavadní testy výběru z řezu a přenosu do historie zachované. |
| S12, S14–S15 | `test_reference_consumers` a `test_reference_interfaces`: bez starých bodů/čísel, všechny čtyři NDT metody, odmítnutí dílčí oblasti a potvrzení vadné vazby, nové ukotvení a ztráta odborného ověření. Dosavadní analytická měření zachovaná. |
| S16–S17 | Skutečný spawn, devítipoložkový BinTools/pickle protokol, CLI, offline souhrn AI bez sítě; chyba/oprava/historie/kopie/nové otevření u čtyř receptů. Qt akce s náhradním viewerem a skutečným workerem. |
| S18 | Nezměněné `test_p12a_compatibility`: všech 26 rekurzivních ukázek, objemy/obálky/počty těles, audit vlastnictví nativních vstupů všech 12 builderů, round-trip a načtení verzí 1–22. Všechny dosavadní testy zachované. |
| S19 | P0 baseline, historie 3/30 těles i pozdní chyba a 10 opakovaných odmítnutí, pět pevných dotazů. Žádný výběr největšího tělesa ani nový časový práh. |
| S20 | `test_reference_limits` výslovně reprodukuje přijetí jiné zbývající díry, geometricky shodné náhrady a zachovaný `top+offset` po odstranění kapsy. Jde o meze, nikoli bezpečné odmítnutí těchto případů. |

## Srovnání výkonu na stejném Macu

Mediány 3 zahřátých opakování, časy v ms; dotazy jsou dávky **100 volání**.
Všechny fyzické podpisy a otisky vstupů/měřičů/prostředí souhlasí.
Dva původně nejednoznačné dotazy se záměrně změnily na chybu, ostatní výsledky jsou stejné.

| Scénář | Před | Po |
|---|---:|---:|
| Přepočet příruby | 29,697 | 29,479 |
| Přepočet krabičky | 64,360 | 64,627 |
| Přepočet rámu | 143,221 | 144,543 |
| Přepočet objemového svaru | 42,914 | 42,587 |
| Přenos BinTools/pickle příruby | 0,928 | 0,932 |
| NDT 1 000 paprsků deskou | 72,581 | 71,648 |
| Historie 3 těles | 19,546 | 20,120 |
| Historie 30 těles | 1 495,622 | 1 507,742 |
| Historie 30 těles s pozdním odmítnutím | 1 575,218 | 1 594,345 |
| Dotaz na kružnice příruby ×100 | 28,640 | 29,974 |
| Dotaz na dno krabičky ×100 | 61,263 | 62,211 |
| Dotaz na svislé hrany rámu ×100 | 215,875 | 220,558 |
| Nejednoznačné hrany kvádru ×100 | 34,137 | 33,894 |
| Nejednoznačné plochy dvojice ×100 | 31,187 | 26,805 |

C.3 odstranilo nadbytečný kvadratický průchod `is_same` nad výčtem nativního
`Shape`, který už zamčené build123d deduplikuje. Cizí adaptéry a sjednocení více
výběrů ověření zachovávají. Regrese odlišuje opakování téhož nativního kvádru od
dvou samostatných geometricky shodných kvádrů; druhý případ zůstává nejednoznačný.
Nevznikla cache, nový index ani oslabení výběrových pravidel.

Otisk zdrojů finálního měření P0 a dotazů:
`067fc15cd4abe6d34b9978032a55a7ea0221ce003f2d32cf03a6831fa231fa25`.
Měření vzniklo nad rozpracovaným C.3, proto údaj `commit` ještě označuje rodiče;
zdrojový otisk určuje skutečně měřený kód. Archiv uchovává `*-before.json`,
`*-after-final.json` a `baseline-comparison-final.json`. Tři vzorky nejsou statistický
ani kauzální důkaz zrychlení. Maximum RSS zahrnuje importy/celý proces a nedokazuje
nepřítomnost úniku paměti; nejde o dlouhodobou zátěžovou zkoušku.

## Nativní okno a zbývající cílové testy

23. 10. 2026 prošlo 15 kontrol skutečného Cocoa/OccViewer okna s pomocným procesem:
oprava kliknuté hrany přes Qt akci, Zpět/Znovu a kopie, neplatná oblast/měření u
dvou kvádrů a změněného poloměru, zakázané potvrzení vadné vazby, nové ukotvení
→ zastaralá → výslovně potvrzená studie a vrácení historie, chyba projekce a
odmítnutí umělé plochy řezu bez změny dokumentu. `native-references.json` zachycuje
konkrétní stavy/objemy. Skutečné nativní tvary byly do výběru předány programově;
nejde o autorův fyzický klik myší ani přijetí staženého balíčku.
Šest snímků bylo vizuálně prohlédnuto: správná geometrie, česká chyba, stavy NDT
a řez. Vestavěný nativní self-test skončil `VÝSLEDEK: OK`.

Při uzavření místního kroku C.3 se oba celé Windows/macOS workflow konečné hlavy
PR včetně self-testu staženého balíčku teprve spouštějí. Jejich konkrétní výsledky,
SHA sestavení a odkazy patří do popisu implementačního PR a přílohy předání.
[Ruční přijetí autora](p1-3-rucni-overeni.md) nelze předem prohlásit za hotové.

## Zbývající přijetí a meze

P1.3 není dokončené před C.1–C.3, celou maticí S01–S20, oběma kompletními workflow
Windows/macOS včetně testu staženého balíčku, nativní vizuální kontrolou a ručním
přijetím konkrétního sestavení. Starší zelené sestavení nesplňuje tuto bránu.

Formát 22, IPC a závislosti se nemění. Pevné uložené R není živý parametr;
po změně poloměru může odkaz správně vyžádat nový výběr. Zbytkové R04/historická
identita zůstává otevřené: jiná jediná vyhovující díra, shodná náhrada nebo
`top+offset` nedokazují původní identitu. P1.4/R01, R03, R12 a odborná NDT-17
zůstávají samostatné. P1.4/P1.5/P2, nový formát ani NDT-16 se neprovádějí.
