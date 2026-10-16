# NDT modul ŠkodaCAD – návrhy a postup vývoje

Dokumentace pro plánované rozšíření ŠkodaCAD o podporu předběžného posouzení kontrolovatelnosti metodami UT, PT, MT a RT.

1. [Návrh v0.1](01-navrh-v0.1.md) – základní koncept, čtyři metody a hranice geometrické simulace.
2. [Rozšířený návrh v0.2](02-navrh-v0.2.md) – svary, virtuální vady, plánování drah, srovnávání konstrukčních variant a ověřování.
3. [Kompletní implementační plán](03-implementacni-plan.md) – integrované pořadí etap, závislosti, výstupy a ověřování.
4. [Návrh etap 00 a 01](04-navrh-etapa-00-01.md) – inventura rozhraní, referenční díly a datový model NDT studie (schváleno 16. 10. 2026).
5. [Referenční díly](05-referencni-dily.md) – osm modelů v `examples/ndt/` s ručně spočítanými očekávanými výsledky (čeká na ověření NDT technikem).
6. [Návrh etapy 02](06-navrh-etapa-02.md) – společné geometrické jádro: paprsek, bod plochy, uvnitř/vně, viditelnost, kolize (schváleno a provedeno 16. 10. 2026).
7. [Návrh etapy 03](07-navrh-etapa-03.md) – virtuální sonda na povrchu dílu: přiložení, mezera, přesah, kolize, vůle, posun (schváleno a provedeno 16. 10. 2026).
8. [Návrh první verze pro macOS](08-navrh-macos.md) – audit knihoven (vše má verzi pro Apple Silicon), Cocoa okno, `SkodaCAD.app` v ZIP, samostatné sestavení na GitHubu, ruční test na MacBooku (hotovo, ověřeno autorem 16. 10. 2026).

**Závazná rozhodnutí autora (16. 10. 2026)** – mají přednost před staršími návrhy a plánem:

- [Závazné vymezení rozsahu UT](04-zavazne-vymezeni-ut.md) – UT jen **přístupnost sondy** a **geometrické pokrytí**; žádná prozvučitelnost materiálu, detekovatelnost vad ani virtuální signály. Povinné upozornění v okně i ve výstupech (`skodacad.ndt.UT_DISCLAIMER`, hlídá test `tests/test_ndt_scope.py`).
- [Podpora macOS (Apple Silicon)](05-podpora-macos.md) – po dokončení rozpracované etapy NDT první spustitelná verze pro MacBook Air M4; Windows se nesmí rozbít.

(Soubory 04 a 05 mají shodná čísla s návrhy etap – kvůli odkazům se nepřečíslovávají.)

**Stav:** etapy 00 (referenční díly), 01 (NDT studie, formát verze 13, panel NDT), 02 (geometrické jádro, `skodacad paprsek`) a 03 (virtuální sonda `ndt/devices.py`, uložená ve studii – formát verze 14, Přiložit sondu sem v okně, `skodacad sonda`) jsou hotové a sladěné se závazným vymezením UT (povinné upozornění, skupina *Přístupnost UT sondy*). První verze pro macOS podle `05-podpora-macos.md` je hotová a ověřená na MacBooku Air M4 (16. 10. 2026). Na řadě je etapa 04 – geometrický model UT svazku: dráha, odraz a lom jen s výslovně zadanými předpoklady (rychlosti), s testy proti ručním výpočtům. Etapa 16 (virtuální signály A/B-scan) je podle vymezení mimo schválený rozsah.

**Důležité:** geometrická přístupnost a orientační pokrytí nejsou důkazem detekovatelnosti vad, normové způsobilosti ani schválení NDT postupu. Před nasazením pro odborná rozhodnutí je nutná validace.
