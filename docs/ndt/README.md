# NDT modul ŠkodaCAD – návrhy a postup vývoje

Dokumentace pro plánované rozšíření ŠkodaCAD o podporu předběžného posouzení kontrolovatelnosti metodami UT, PT, MT a RT.

1. [Návrh v0.1](01-navrh-v0.1.md) – základní koncept, čtyři metody a hranice geometrické simulace.
2. [Rozšířený návrh v0.2](02-navrh-v0.2.md) – svary, virtuální vady, plánování drah, srovnávání konstrukčních variant a ověřování.
3. [Kompletní implementační plán](03-implementacni-plan.md) – integrované pořadí etap, závislosti, výstupy a ověřování.
4. [Návrh etap 00 a 01](04-navrh-etapa-00-01.md) – inventura rozhraní, referenční díly a datový model NDT studie (schváleno 16. 10. 2026).
5. [Referenční díly](05-referencni-dily.md) – osm modelů v `examples/ndt/` s ručně spočítanými očekávanými výsledky (čeká na ověření NDT technikem).
6. [Návrh etapy 02](06-navrh-etapa-02.md) – společné geometrické jádro: paprsek, bod plochy, uvnitř/vně, viditelnost, kolize (schváleno a provedeno 16. 10. 2026).
7. [Návrh etapy 03](07-navrh-etapa-03.md) – virtuální sonda na povrchu dílu: přiložení, mezera, přesah, kolize, vůle, posun (schváleno a provedeno 16. 10. 2026).
8. [Návrh první verze pro macOS](08-navrh-macos.md) – audit knihoven (vše má verzi pro Apple Silicon), Cocoa okno, `SkodaCAD.app` v ZIP, samostatné sestavení na GitHubu, ruční test na MacBooku (rozpracováno).
9. [Návrh etapy 04](09-navrh-etapa-04.md) – geometrický model UT paprsku: přímá a úhlová sonda, lom podle Snellova zákona se zadanými předpoklady, odrazy (poloviční a celá rozteč), zobrazení ve 3D a v řezu (schváleno a provedeno 16. 10. 2026).
10. [Návrh etapy 05](10-navrh-etapa-05.md) – ruční pohyb sondy v okně (milník M1): tažení sondy myší po povrchu ve 3D, krokování a posuvník přímé dráhy se živým přepočtem kolize a UT paprsku (schváleno a provedeno 16. 10. 2026).
11. [Návrh etapy 06](11-navrh-etapa-06.md) – mapa geometrického pokrytí UT (začátek milníku M2): pojezd po ploše i přímce, tři stavy, 3D, CSV a kontrola citlivosti na krok (sloučeno v PR #15; 723 testů a zkoušky balíčků Windows/macOS prošly; ruční zkouška vydání po sloučení čeká).
12. [Návrh etapy 07](12-navrh-etapa-07.md) – svar a cílový objem: rovný V a koutový svar, pomocný objem a formát JSON 16; 07A sloučeno v PR #16, 07B sloučeno v PR #17, 07C sloučeno v PR #19 (bez ruční zkoušky).
13. [Návrh etapy 07B](13-navrh-etapa-07b.md) – geometrické pokrytí skutečného cílového objemu: váhy v mm³, tři stavy, zachování objemu, limity, CSV a citlivost na krok; bez nového ovládání (schváleno, sloučeno v PR #17).
14. [Návrh etapy 07C](14-navrh-etapa-07c.md) – cílový objem a jeho pokrytí v okně: editor svaru/objemu s nákresem průřezu, průhledný náhled cíle, objemový výpočet z panelu s citlivostí na krok, barevný povrch cíle a průřez svarem (schváleno 17. 10. 2026, na pokyn autora sloučeno v PR #19 bez ruční zkoušky; ruční zkouška autorem čeká).
15. [Rozbor citlivosti V svaru](15-rozbor-citlivosti-v-svaru.md) – proč objemové pokrytí V svaru „skákalo“ s krokem: správná hodnota 12,2 % nezávisle na mřížce, porovnávací běh hledal s příliš malou tolerancí, buňky 4 mm jsou pro 12mm plech příliš velké; opravy 1–3 schválené a provedené (spravedlivé porovnání kroků, výchozí krok cíle podle průřezu, referenční test).

**Závazná rozhodnutí autora (16. 10. 2026)** – mají přednost před staršími návrhy a plánem:

- [Závazné vymezení rozsahu UT](04-zavazne-vymezeni-ut.md) – UT jen **přístupnost sondy** a **geometrické pokrytí**; žádná prozvučitelnost materiálu, detekovatelnost vad ani virtuální signály. Povinné upozornění v okně i ve výstupech (`skodacad.ndt.UT_DISCLAIMER`, hlídá test `tests/test_ndt_scope.py`).
- [Podpora macOS (Apple Silicon)](05-podpora-macos.md) – po dokončení rozpracované etapy NDT první spustitelná verze pro MacBook Air M4; Windows se nesmí rozbít.

(Soubory 04 a 05 mají shodná čísla s návrhy etap – kvůli odkazům se nepřečíslovávají.)

**Stav:** etapy 00–06 jsou implementované v hlavní větvi; **milník M1 hotový**. Etapa 06:
`ndt/coverage.py`, pojezd po ploše i přímce, tři stavy vzorků, ověření mezilehlých poloh,
citlivost na krok, CSV, výpočet na pozadí a 3D mapa v okně. Etapa 06 ponechala formát 15,
výsledek je pouze pohled a po změně zadání zanikne. Autor potvrdil počáteční místní ruční zkoušku;
po kontrole byly opraveny odrazy od boční stěny a souhrn při posunu sondy posuvníkem.
PR #15 byl po schválení sloučen, balíčky Windows i macOS prošly automatickou zkouškou.
Ruční zkouška vydání po sloučení byla odložena a zatím neproběhla.
Další podle plánu je etapa 07 – svar a cílová oblast jako NDT objekty (pokračování milníku M2);
07A je schváleno a sloučeno do `main` v PR #16, commit `0dea6f8` (formát 16): datový základ
a pomocné objemy, bez nového ovládání. Objemové pokrytí 07B je schválené a sloučené
v PR #17: samostatný výsledek v mm³, CLI/CSV a citlivost na krok. Editor a objemový
náhled v okně (07C, [návrh](14-navrh-etapa-07c.md)) jsou schválené a na pokyn autora
sloučené do `main` v PR #19 bez ruční zkoušky; ruční zkouška autorem čeká.
Etapa 16 (virtuální signály) je podle závazného vymezení mimo schválený rozsah.

**Důležité:** geometrická přístupnost a orientační pokrytí nejsou důkazem detekovatelnosti vad, normové způsobilosti ani schválení NDT postupu. Před nasazením pro odborná rozhodnutí je nutná validace.
