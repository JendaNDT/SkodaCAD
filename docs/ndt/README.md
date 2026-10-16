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

**Závazná rozhodnutí autora (16. 10. 2026)** – mají přednost před staršími návrhy a plánem:

- [Závazné vymezení rozsahu UT](04-zavazne-vymezeni-ut.md) – UT jen **přístupnost sondy** a **geometrické pokrytí**; žádná prozvučitelnost materiálu, detekovatelnost vad ani virtuální signály. Povinné upozornění v okně i ve výstupech (`skodacad.ndt.UT_DISCLAIMER`, hlídá test `tests/test_ndt_scope.py`).
- [Podpora macOS (Apple Silicon)](05-podpora-macos.md) – po dokončení rozpracované etapy NDT první spustitelná verze pro MacBook Air M4; Windows se nesmí rozbít.

(Soubory 04 a 05 mají shodná čísla s návrhy etap – kvůli odkazům se nepřečíslovávají.)

**Stav:** etapy 00 (referenční díly), 01 (NDT studie, formát verze 13, panel NDT), 02 (geometrické jádro, `skodacad paprsek`), 03 (virtuální sonda `ndt/devices.py`, uložená ve studii, Přiložit sondu sem v okně, `skodacad sonda`) a 04 (geometrický model UT paprsku `ndt/ut.py`, formát verze 15, lom podle Snellova zákona se zadanými předpoklady, odrazy, vykreslení dráhy ve 3D a v řezu) jsou hotové a sladěné se závazným vymezením UT (povinné upozornění, skupina *Přístupnost UT sondy*). Další je etapa 05 – ruční pohyb sondy po povrchu se živou odezvou (milník M1). Etapa 16 (virtuální signály) je podle vymezení mimo schválený rozsah.

**Důležité:** geometrická přístupnost a orientační pokrytí nejsou důkazem detekovatelnosti vad, normové způsobilosti ani schválení NDT postupu. Před nasazením pro odborná rozhodnutí je nutná validace.
