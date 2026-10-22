# P1.3 — implementace a ověření

Autor 22. 10. 2026 schválil [C1–C8, C.1–C.3 a S01–S20](p1-3-navrh-bezpecnych-referenci.md)
slovy „ok, schvaluji vše“, včetně sloučení návrhového PR #36 (`c46d0e2`).
Implementace má samostatnou větev `codex/p1-3-safe-references` a vlastní PR.
**Sloučení implementace vyžaduje další samostatný pokyn autora.**

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
| C.3 | Čeká: přenos, historie, kompatibilita, výkon a konečné cílové/ruční ověření. |

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

## Zbývající přijetí a meze

P1.3 není dokončené před C.1–C.3, celou maticí S01–S20, oběma kompletními workflow
Windows/macOS včetně testu staženého balíčku, nativní vizuální kontrolou a ručním
přijetím konkrétního sestavení. Starší zelené sestavení nesplňuje tuto bránu.

Formát 22, IPC a závislosti se nemění. Pevné uložené R není živý parametr;
po změně poloměru může odkaz správně vyžádat nový výběr. Zbytkové R04/historická
identita zůstává otevřené: jiná jediná vyhovující díra, shodná náhrada nebo
`top+offset` nedokazují původní identitu. P1.4/R01, R03, R12 a odborná NDT-17
zůstávají samostatné. P1.4/P1.5/P2, nový formát ani NDT-16 se neprovádějí.
